-- CoopFight v6: host-authoritative enemy death sync + enemy mirror (W42).
--
-- Enemy mirror (v6)
--   HOST   publishes, per snapshot, a few "roster" entries [id,homeX,homeY,homeZ] (where each
--          enemy stood when it settled) and up to ENEMY_SEND_MAX movement entries
--          [id,x,y,z,yaw], round-robin, enemies that moved first.
--   CLIENT never thinks for enemies: every tick it stops any running BrainComponent and turns
--          off CharacterMovement, maps host ids to its own enemies by nearest home, and moves
--          each mapped enemy toward the host position.
--
-- Authority model
--   HOST   owns enemy liveness. It destroys enemies it sees die and publishes authoritative
--          kill positions. Claims from the client are validated against its own tracked
--          enemies: if the enemy is still alive here, the host destroys it and publishes the
--          kill; if it is already gone, the claim is ignored.
--   CLIENT never publishes authoritative kills. It reports its own observations as claims and
--          applies kills that come from the host.
--
-- Enemy identity is positional: names are stable for level-placed actors but runtime-spawned
-- ones differ between instances, while positions match.
--
-- A destroyed UE4 actor keeps IsValid()==true until GC, so liveness is
-- IsValid() and not HasAnyInternalFlags(EInternalObjectFlags.PendingKill).

local UEHelpers = require("UEHelpers")

local NET_DIR = "C:/coop mods/work/net/"
local PAIR = "A"
local ROLE = "host"                     -- "host" | "client"
local OUT = NET_DIR .. "outbox.next.json"
local INBOX = NET_DIR .. "inbox.json"
local BOOT = NET_DIR .. "fight-boot.log"
local CMD = NET_DIR .. "destroy-cmd.json"

local KILL_REPORT_MAX = 24
local CLAIM_REPORT_MAX = 24
local KILL_MATCH_RADIUS = 150
local MAX_CLAIMS_PER_TICK = 4
local SETTLE_READS = 3
local ORIGIN_GUARD = 50.0
local MASS_LIMIT = 5
local ARM_DELAY_TICKS = 40
local TEST_TRACK_AVATAR = true

-- W42 enemy mirror. The relay caps a state file at 1200 bytes and adds ~150 bytes of envelope.
local ENEMY_SEND_MAX = 8
local ROSTER_PER_TICK = 2
local MIRROR_MATCH_RADIUS = 200
local MIRROR_LERP = 0.35
local PAYLOAD_BUDGET = 1000
local MOVED_EPS = 5.0

local function boot(msg)
    local f = io.open(BOOT, "a")
    if f then f:write(os.date("%H:%M:%S"), " ", msg, "\n"); f:close() end
    print("[FIGHT] " .. msg .. "\n")
end

local function safe(fn, default)
    local ok, v = pcall(fn)
    if ok then return v end
    return default
end

local function ts(v) return safe(function() return tostring(v) end, "<ts>") end

local function cls(o)
    if o == nil then return "nil" end
    if not safe(function() return o:IsValid() end, false) then return "invalid" end
    return ts(safe(function() return o:GetFullName() end, "?"))
end

local function read_all(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local c = f:read("a")
    f:close()
    return c
end

local function write_atomic(path, content)
    local tmp = path .. "." .. PAIR .. ".tmp"
    local f = io.open(tmp, "w")
    if not f then return false end
    local ok = pcall(function() f:write(content) end)
    f:close()
    if not ok then os.remove(tmp) return false end
    if not os.rename(tmp, path) then os.remove(tmp) return false end
    return true
end

local function jbool(s, key)
    local i = s:find('"' .. key .. '"%s*:%s*')
    if not i then return nil end
    local v = s:sub(i):match('^"[^"]-"%s*:%s*(%a+)')
    if v == "true" then return true end
    if v == "false" then return false end
    return nil
end

local function jstr(s, key)
    local i = s:find('"' .. key .. '"%s*:%s*"')
    if not i then return nil end
    return s:sub(i):match('^"[^"]-"%s*:%s*"([^"]*)"')
end

local function jnum(s, key)
    local i = s:find('"' .. key .. '"%s*:%s*')
    if not i then return nil end
    local v = s:sub(i):match('^"[^"]-"%s*:%s*(-?%d+%.?%d*)')
    return v and tonumber(v) or nil
end

local function jtriple(s, key)
    local i = s:find('"' .. key .. '"%s*:%s*%[')
    if not i then return nil end
    local a, b, c = s:sub(i):match('%[%s*(-?%d+%.?%d*)%s*,%s*(-?%d+%.?%d*)%s*,%s*(-?%d+%.?%d*)%s*%]')
    if a and b and c then return { X = tonumber(a), Y = tonumber(b), Z = tonumber(c) } end
    return nil
end

-- The text of the JSON array stored under key, brackets included, or nil. Scans only to the
-- matching close bracket: the old reader matched triples anywhere after the key, so it read
-- later arrays ("claims", "enemies") as part of "kills".
local function jarray(s, key)
    local _, e = s:find('"' .. key .. '"%s*:%s*%[')
    if not e then return nil end
    local depth = 0
    for j = e, #s do
        local ch = s:sub(j, j)
        if ch == "[" then depth = depth + 1
        elseif ch == "]" then
            depth = depth - 1
            if depth == 0 then return s:sub(e, j) end
        end
    end
    return nil
end

-- All inner arrays of exactly n numbers in the array under key.
local function jtuples(s, key, n)
    local arr = jarray(s, key)
    local out = {}
    if not arr then return out end
    for inner in arr:gmatch("%[([^%[%]]*)%]") do
        local t = {}
        for num in inner:gmatch("-?%d+%.?%d*[eE]?[-+]?%d*") do t[#t + 1] = tonumber(num) end
        if #t == n then out[#out + 1] = t end
    end
    return out
end

local function jlist(s, key)
    local out = {}
    for _, t in ipairs(jtuples(s, key, 3)) do out[#out + 1] = { X = t[1], Y = t[2], Z = t[3] } end
    return out
end

local function world_id(pc)
    local w = pc and safe(function() return pc:GetWorld() end, nil)
    if not w then return "unknown" end
    local full = ts(safe(function() return w:GetFullName() end, "unknown"))
    return full:gsub("^World%s+", ""):gsub("%.[^%.%s]+$", "")
end

local function local_controller()
    local all = safe(function() return FindAllOf("PlayerControllerOML") end, nil) or {}
    local fallback = nil
    for _, c in pairs(all) do
        if c and safe(function() return c:IsValid() end, false)
            and safe(function() return c.Player:IsValid() end, false) then
            if safe(function() return c.Player.ControllerId end, nil) == 0 then return c end
            fallback = fallback or c
        end
    end
    return fallback
end

local function is_player_pawn(pawn)
    return pawn and safe(function() return pawn:IsValid() end, false)
        and ts(safe(function() return pawn:GetFullName() end, "")):find("BP_PlayerCharacter_C") ~= nil
end

local function alive_actor(a)
    if a == nil then return false end
    if not safe(function() return a:IsValid() end, false) then return false end
    return safe(function() return a:HasAnyInternalFlags(EInternalObjectFlags.PendingKill) end, nil) ~= true
end

local function looks_enemy(name)
    local lower = name:lower()
    return lower:find("enemy") ~= nil or lower:find("boss") ~= nil
end

local function fkey(x, y, z) return string.format("%.0f,%.0f,%.0f", x, y, z) end

local MESH_PATH = "/Game/Visual/Characters/Enemy_Sniper_01/SK_Enemy_Sniper_01.SK_Enemy_Sniper_01"
local AVATAR_CLASS = "/Script/Engine.Character"
local LIGHT_CLASS = "/Script/Engine.PointLight"

local tick = 0
local avatar, marker_light = nil, nil
local snapped = false
local published, received = 0, 0
local tracked = {}
local built = false
local arm_at = 0
local kill_queue = {}      -- host: authoritative kills to publish
local claim_queue = {}     -- client: observations to send to the host
local applied = {}
local world_seen = nil
local last_cmd_id = 0
local accepted_claims, rejected_claims = 0, 0
local next_id = 0
local by_id = {}            -- host: id -> tracked name
local rr_move, rr_roster = 0, 0
local mirror = {}           -- client: host id -> { name = local tracked name, tx, ty, tz, yaw }
local mirror_claimed = {}   -- client: local name -> host id
local host_roster = {}      -- client: host id -> { X, Y, Z } home on the host
local brains_stopped, mirror_moves = 0, 0

boot("CoopFight v6 loading, pair=" .. PAIR .. " role=" .. ROLE)

local function add(name, actor)
    if tracked[name] == nil then
        next_id = next_id + 1
        tracked[name] = { actor = actor, x = nil, y = nil, z = nil, reads = 0, settled = false, id = next_id }
        by_id[next_id] = name
    end
end

local function seed()
    local pawns = safe(function() return FindAllOf("Pawn") end, nil) or {}
    local found = 0
    local names = {}
    for _, p in pairs(pawns) do
        if p and safe(function() return p:IsValid() end, false) then
            local n = ts(safe(function() return p:GetFullName() end, ""))
            if looks_enemy(n) then names[#names + 1] = { n = n, p = p }; found = found + 1 end
        end
    end
    table.sort(names, function(a, b) return a.n < b.n end)
    for _, it in ipairs(names) do add(it.n, it.p) end
    boot(string.format("seed: %d pawns, %d enemy pawns", #pawns, found))
end

local function spawn_avatar(pc, pawn)
    local world = safe(function() return pc:GetWorld() end, nil)
    local klass = safe(function() return StaticFindObject(AVATAR_CLASS) end, nil)
    local mesh = safe(function() return StaticFindObject(MESH_PATH) end, nil)
    local p = safe(function() return pawn:K2_GetActorLocation() end, nil)
    if not (world and klass and p) then return end
    local ok, actor = pcall(function()
        return world:SpawnActor(klass, { X = p.X + 200, Y = p.Y, Z = p.Z }, { Pitch = 0, Yaw = 0, Roll = 0 })
    end)
    if not (ok and actor and safe(function() return actor:IsValid() end, false)) then
        boot("avatar spawn failed: " .. ts(actor))
        return
    end
    avatar = actor
    pcall(function()
        actor:SetActorEnableCollision(false)
        actor.CharacterMovement:DisableMovement()
        actor.CharacterMovement:SetComponentTickEnabled(false)
        if mesh then actor.Mesh:SetSkeletalMesh(mesh, true) end
    end)
    boot("avatar spawned")
    if TEST_TRACK_AVATAR then add("AVATAR", avatar) end
    -- a bright light is the only reliable "this is your friend" cue: the game ships no
    -- third-person player body, only first-person hands
    local light_cls = safe(function() return StaticFindObject(LIGHT_CLASS) end, nil)
    if light_cls then
        local ok2, light = pcall(function()
            return world:SpawnActor(light_cls, { X = p.X + 200, Y = p.Y, Z = p.Z + 130 }, { Pitch = 0, Yaw = 0, Roll = 0 })
        end)
        if ok2 and light and safe(function() return light:IsValid() end, false) then
            marker_light = light
            pcall(function()
                light.PointLightComponent:SetLightColor({ R = 0.1, G = 1.0, B = 0.35, A = 1.0 })
                light.PointLightComponent:SetBrightness(8000.0)
                light.PointLightComponent:SetAttenuationRadius(260.0)
                light.PointLightComponent:SetCastShadows(false)
                light:SetActorEnableCollision(false)
            end)
            boot("marker light spawned")
        end
    end
end

-- Entries carry the tick they were added. Only recent ones are published (so a lost packet
-- is retransmitted for a while), but old ones are pruned, otherwise a burst of streaming events
-- fills the queue permanently and later real kills never get published.
local QUEUE_TTL_TICKS = 60
local function queue(list, x, y, z)
    if #list >= KILL_REPORT_MAX then table.remove(list, 1) end
    list[#list + 1] = { X = x, Y = y, Z = z, t = tick }
end

local function prune(list)
    local keep = {}
    for _, e in ipairs(list) do
        if e.t and (tick - e.t) <= QUEUE_TTL_TICKS then keep[#keep + 1] = e end
    end
    return keep
end

local function nearest_enemy(x, y, z, radius)
    local best, bestd = nil, radius
    for name, e in pairs(tracked) do
        local ex, ey, ez = e.x, e.y, e.z
        if alive_actor(e.actor) then
            local loc = safe(function() return e.actor:K2_GetActorLocation() end, nil)
            if loc then ex, ey, ez = loc.X, loc.Y, loc.Z end
        end
        if ex ~= nil then
            local dx, dy, dz = ex - x, ey - y, ez - z
            local d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d < bestd then best, bestd = name, d end
        end
    end
    return best, bestd
end

local function destroy_enemy(name)
    local e = tracked[name]
    if not e then return false end
    pcall(function() e.actor:K2_DestroyActor() end)
    tracked[name] = nil
    if e.id then by_id[e.id] = nil end
    return true
end

-- HOST: the enemy part of the snapshot. Movement first for enemies that moved since they were
-- last sent, round-robin so every enemy is refreshed within a few ticks.
local function host_enemy_fields()
    local ids = {}
    for id, name in pairs(by_id) do
        local e = tracked[name]
        if e and e.settled and name ~= "AVATAR" and alive_actor(e.actor) then ids[#ids + 1] = id end
    end
    table.sort(ids)
    local n = #ids
    if n == 0 then return "", "" end
    local moved, still = {}, {}
    for k = 1, n do
        local id = ids[((rr_move + k - 1) % n) + 1]
        local e = tracked[by_id[id]]
        local loc = safe(function() return e.actor:K2_GetActorLocation() end, nil)
        local rot = safe(function() return e.actor:K2_GetActorRotation() end, nil)
        if loc then
            local entry = string.format("[%d,%.0f,%.0f,%.0f,%.0f]", id, loc.X, loc.Y, loc.Z,
                rot and safe(function() return rot.Yaw end, 0) or 0)
            local lx, ly, lz = e.sx or e.hx, e.sy or e.hy, e.sz or e.hz
            local d = math.abs(loc.X - lx) + math.abs(loc.Y - ly) + math.abs(loc.Z - lz)
            if d > MOVED_EPS then moved[#moved + 1] = { entry = entry, e = e, loc = loc }
            else still[#still + 1] = { entry = entry, e = e, loc = loc } end
        end
    end
    rr_move = (rr_move + ENEMY_SEND_MAX) % n
    local out = {}
    for _, list in ipairs({ moved, still }) do
        for _, it in ipairs(list) do
            if #out >= ENEMY_SEND_MAX then break end
            out[#out + 1] = it.entry
            it.e.sx, it.e.sy, it.e.sz = it.loc.X, it.loc.Y, it.loc.Z
        end
    end
    local roster = {}
    for k = 1, math.min(ROSTER_PER_TICK, n) do
        local id = ids[((rr_roster + k - 1) % n) + 1]
        local e = tracked[by_id[id]]
        roster[#roster + 1] = string.format("[%d,%.0f,%.0f,%.0f]", id, e.hx, e.hy, e.hz)
    end
    rr_roster = (rr_roster + ROSTER_PER_TICK) % n
    return table.concat(out, ","), table.concat(roster, ",")
end

-- CLIENT: AI is never allowed to run here. Called every tick; cheap when nothing changed.
local function client_suppress_ai()
    for name, e in pairs(tracked) do
        if name ~= "AVATAR" and alive_actor(e.actor) then
            local ctl = safe(function() return e.actor.Controller end, nil)
            local brain = ctl and safe(function() return ctl.BrainComponent end, nil)
            if brain and safe(function() return brain:IsValid() end, false)
                and safe(function() return brain:IsRunning() end, false) then
                pcall(function() brain:StopLogic("coop mirror") end)
                brains_stopped = brains_stopped + 1
            end
            if not e.movement_off then
                pcall(function() e.actor.CharacterMovement:DisableMovement() end)
                e.movement_off = true
            end
        end
    end
end

-- CLIENT: bind host ids to local enemies by nearest home, then move them toward the host.
local function client_apply_mirror(raw)
    for _, t in ipairs(jtuples(raw, "roster", 4)) do
        host_roster[t[1]] = { X = t[2], Y = t[3], Z = t[4] }
    end
    for id, h in pairs(host_roster) do
        local m = mirror[id]
        if not (m and tracked[m.name]) then
            local best, bestd = nil, MIRROR_MATCH_RADIUS
            for name, e in pairs(tracked) do
                if name ~= "AVATAR" and e.settled and not mirror_claimed[name] and e.hx then
                    local dx, dy, dz = e.hx - h.X, e.hy - h.Y, e.hz - h.Z
                    local d = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if d < bestd then best, bestd = name, d end
                end
            end
            if best then
                mirror[id] = { name = best }
                mirror_claimed[best] = id
                boot(string.format("mirror bind host#%d -> %s d=%.1f", id, best, bestd))
            end
        end
    end
    for _, t in ipairs(jtuples(raw, "enemies", 5)) do
        local m = mirror[t[1]]
        if m then m.tx, m.ty, m.tz, m.yaw = t[2], t[3], t[4], t[5] end
    end
    for id, m in pairs(mirror) do
        local e = tracked[m.name]
        if not e then
            mirror[id] = nil
        elseif m.tx and alive_actor(e.actor) then
            local now = safe(function() return e.actor:K2_GetActorLocation() end, nil)
            if now then
                local dx, dy, dz = m.tx - now.X, m.ty - now.Y, m.tz - now.Z
                if math.abs(dx) + math.abs(dy) + math.abs(dz) > 1.0 then
                    local hit = {}
                    pcall(function()
                        e.actor:K2_SetActorLocation({ X = now.X + dx * MIRROR_LERP, Y = now.Y + dy * MIRROR_LERP,
                            Z = now.Z + dz * MIRROR_LERP }, false, hit, true)
                    end)
                    mirror_moves = mirror_moves + 1
                end
                pcall(function() e.actor:K2_SetActorRotation({ Pitch = 0.0, Yaw = m.yaw, Roll = 0.0 }, false) end)
            end
        end
    end
end

local function refresh(player_loc)
    local gone, gone_settled = 0, {}
    for name, e in pairs(tracked) do
        if alive_actor(e.actor) then
            local loc = safe(function() return e.actor:K2_GetActorLocation() end, nil)
            if loc then
                local away = (loc.X * loc.X + loc.Y * loc.Y + loc.Z * loc.Z) > (ORIGIN_GUARD * ORIGIN_GUARD)
                if away then
                    e.x, e.y, e.z = loc.X, loc.Y, loc.Z
                    e.reads = e.reads + 1
                    if e.reads >= SETTLE_READS and not e.settled then
                        e.settled = true
                        e.hx, e.hy, e.hz = loc.X, loc.Y, loc.Z
                    end
                end
            end
        else
            gone = gone + 1
            if e.settled then gone_settled[#gone_settled + 1] = { name = name, e = e } end
            tracked[name] = nil
            if e.id then by_id[e.id] = nil end
        end
    end

    if gone > MASS_LIMIT then
        boot(string.format("mass disappear: %d gone -> streaming, no kills", gone))
        return
    end

    for _, item in ipairs(gone_settled) do
        local e = item.e
        if item.name == "AVATAR" then
            -- test artifact of the menu harness; claiming it floods the host with junk
        elseif ROLE == "host" then
            queue(kill_queue, e.x, e.y, e.z)
            boot(string.format("local kill (authoritative) at %.0f,%.0f,%.0f", e.x, e.y, e.z))
        else
            queue(claim_queue, e.x, e.y, e.z)
            boot(string.format("local claim at %.0f,%.0f,%.0f", e.x, e.y, e.z))
        end
    end
end

-- One tick of the mod. It touches UObjects, so it must run on the game thread: called from the
-- async loop below through ExecuteInGameThread. Running it straight on the LoopAsync thread
-- raced the game thread during level load and froze whichever copy loaded second (W42).
local function fight_tick()
    tick = tick + 1
    local pc = local_controller()
    local pawn = pc and safe(function() return pc.Pawn end, nil)
    local in_game = is_player_pawn(pawn)
    local wname = world_id(pc)
    local can_build = in_game or (TEST_TRACK_AVATAR and pawn ~= nil)

    if wname ~= world_seen then
        world_seen = wname
        tracked, applied, kill_queue, claim_queue = {}, {}, {}, {}
        by_id, mirror, mirror_claimed, host_roster = {}, {}, {}, {}
        avatar, marker_light = nil, nil
        built = false
        snapped = false
        arm_at = tick + ARM_DELAY_TICKS
        boot("world " .. tostring(wname) .. " arm_at=" .. tostring(arm_at))
    end

    if can_build and tick > arm_at then
        if avatar == nil then spawn_avatar(pc, pawn) end
        if not built then seed(); built = true end
    end

    local player_loc = pawn and safe(function() return pawn:K2_GetActorLocation() end, nil)
    if can_build and built and tick % 8 == 0 then refresh(player_loc) end
    if ROLE == "client" and can_build and built then client_suppress_ai() end

    -- test hook: destroy a tracked enemy; host queues a kill, client queues a claim
    if can_build and built then
        local cmd = read_all(CMD)
        if cmd then
            local id = jnum(cmd, "id") or 0
            local index = jnum(cmd, "index") or 0
            local action = jstr(cmd, "action") or "destroy"
            if id > last_cmd_id and (index > 0 or action == "attack") then
                last_cmd_id = id

                if action == "attack" then
                    local hits = 0
                    for _ = 1, 4 do
                        local okc = pcall(function() pawn["Melee Attack"](pawn) end)
                        if okc then hits = hits + 1 end
                    end
                    boot("TEST melee attack x" .. tostring(hits))
                    return false
                end

                if action == "approach" and player_loc then
                    -- stand close and face the target: a melee swing in the wrong direction
                    -- simply misses, which is what happened on the first attempt
                    local names = {}
                    for name, e in pairs(tracked) do
                        if e.settled and name ~= "AVATAR" then names[#names + 1] = name end
                    end
                    table.sort(names)
                    local name = names[index]
                    if name then
                        local e = tracked[name]
                        local loc = safe(function() return e.actor:K2_GetActorLocation() end, nil)
                        if loc then
                            local px, py, pz = loc.X + 70, loc.Y, loc.Z + 20
                            local hit = {}
                            local okm = pcall(function()
                                pawn:K2_SetActorLocation({ X = px, Y = py, Z = pz }, false, hit, false)
                            end)
                            local yaw = math.deg(math.atan(-(loc.Y - py), loc.X - px))
                            local okr = pcall(function()
                                pawn:K2_SetActorRotation({ Pitch = 0.0, Yaw = yaw, Roll = 0.0 }, false)
                            end)
                            boot(string.format("TEST approach %s move=%s rotate=%s target=%.0f,%.0f,%.0f",
                                name, tostring(okm), tostring(okr), loc.X, loc.Y, loc.Z))
                        end
                    else
                        boot("TEST approach: no target at index " .. tostring(index))
                    end
                    return false
                end

                local names = {}
                for name, e in pairs(tracked) do
                    if e.settled and name ~= "AVATAR" then names[#names + 1] = name end
                end
                table.sort(names)
                if #names == 0 and tracked["AVATAR"] then names[1] = "AVATAR" end
                local name = names[index]
                if name then
                    local e = tracked[name]
                    local x, y, z = e.x, e.y, e.z
                    if x == nil then
                        local loc = safe(function() return e.actor:K2_GetActorLocation() end, nil)
                        if loc then x, y, z = loc.X, loc.Y, loc.Z end
                    end
                    if x ~= nil then
                        if ROLE == "host" then queue(kill_queue, x, y, z) else queue(claim_queue, x, y, z) end
                    end
                    destroy_enemy(name)
                    boot("TEST destroyed " .. name .. " (queued for " .. ROLE .. ")")
                else
                    boot("TEST no target at index " .. tostring(index))
                end
            end
        end
    end

    if pawn and safe(function() return pawn:IsValid() end, false) and player_loc then
        local r = safe(function() return pawn:K2_GetActorRotation() end, nil)
        kill_queue = prune(kill_queue)
        claim_queue = prune(claim_queue)
        local kills, claims = {}, {}
        for _, k in ipairs(kill_queue) do
            kills[#kills + 1] = string.format("[%.1f,%.1f,%.1f]", k.X, k.Y, k.Z)
        end
        local claim_budget = 4
        for i = #claim_queue, 1, -1 do
            local k = claim_queue[i]
            if claim_budget <= 0 then break end
            claims[#claims + 1] = string.format("[%.1f,%.1f,%.1f]", k.X, k.Y, k.Z)
            claim_budget = claim_budget - 1
        end
        local enemies_s, roster_s = "", ""
        if ROLE == "host" and built then enemies_s, roster_s = host_enemy_fields() end
        local function build(en, ro)
            return string.format(
                '{"schema":4,"world":"%s","role":"%s","tick":%d,"gameplay":%s,"position":[%.2f,%.2f,%.2f],"rotation":[0.00,%.2f,0.00],"kills":[%s],"claims":[%s],"enemies":[%s],"roster":[%s]}',
                wname, ROLE, tick, in_game and "true" or "false", player_loc.X, player_loc.Y, player_loc.Z,
                r and safe(function() return r.Yaw end, 0) or 0,
                table.concat(kills, ","), table.concat(claims, ","), en, ro)
        end
        local payload = build(enemies_s, roster_s)
        if #payload > PAYLOAD_BUDGET then payload = build("", roster_s) end
        if #payload > PAYLOAD_BUDGET then payload = build("", "") end
        if write_atomic(OUT, payload) then published = published + 1 end
    end

    local raw = read_all(INBOX)
    if raw and can_build then
        local connected = jbool(raw, "connected")
        local pworld = (jstr(raw, "world") or ""):gsub("%.[^%.%s]+$", "")
        local peer_pos = jtriple(raw, "position")
        local peer_role = jstr(raw, "role") or ""
        if connected and pworld == wname and peer_pos then
            received = received + 1
            if avatar and safe(function() return avatar:IsValid() end, false) then
                local now = safe(function() return avatar:K2_GetActorLocation() end, nil)
                local tx, ty, tz = peer_pos.X, peer_pos.Y, peer_pos.Z
                if now and snapped then
                    tx = now.X + (peer_pos.X - now.X) * 0.4
                    ty = now.Y + (peer_pos.Y - now.Y) * 0.4
                    tz = now.Z + (peer_pos.Z - now.Z) * 0.4
                end
                snapped = true
                local hit = {}
                pcall(function() avatar:K2_SetActorLocation({ X = tx, Y = ty, Z = tz }, false, hit, false) end)
                if marker_light and safe(function() return marker_light:IsValid() end, false) then
                    local mh = {}
                    pcall(function()
                        marker_light:K2_SetActorLocation({ X = tx, Y = ty, Z = tz + 130 }, false, mh, false)
                    end)
                end
            end

            -- CLIENT applies authoritative kills from the host
            if ROLE == "client" then
                client_apply_mirror(raw)
                for _, kp in ipairs(jlist(raw, "kills")) do
                    local pk = fkey(kp.X, kp.Y, kp.Z)
                    if not applied[pk] then
                        applied[pk] = true
                        local best, bestd = nearest_enemy(kp.X, kp.Y, kp.Z, KILL_MATCH_RADIUS)
                        if best then
                            destroy_enemy(best)
                            boot(string.format("host kill applied %s d=%.1f", best, bestd))
                        end
                    end
                end
            end

            -- HOST validates client claims
            if ROLE == "host" and peer_role == "client" then
                for _, cp in ipairs(jlist(raw, "claims")) do
                    local pk = "c" .. fkey(cp.X, cp.Y, cp.Z)
                    if not applied[pk] then
                        applied[pk] = true
                        local best, bestd = nearest_enemy(cp.X, cp.Y, cp.Z, KILL_MATCH_RADIUS)
                        if best then
                            destroy_enemy(best)
                            queue(kill_queue, cp.X, cp.Y, cp.Z)
                            accepted_claims = accepted_claims + 1
                            boot(string.format("claim accepted %s d=%.1f", best, bestd))
                        else
                            rejected_claims = rejected_claims + 1
                            boot(string.format("claim ignored at %.0f,%.0f,%.0f (already dead here)", cp.X, cp.Y, cp.Z))
                        end
                    end
                end
            end
        end
    end

    if tick % 400 == 0 then
        local total, settled = 0, 0
        for _, e in pairs(tracked) do total = total + 1; if e.settled then settled = settled + 1 end end
        local bound = 0
        for _ in pairs(mirror) do bound = bound + 1 end
        boot(string.format("t%d game=%s role=%s tracked=%d settled=%d kills=%d claims=%d acc=%d rej=%d pub=%d rx=%d mirror=%d moves=%d brains_stopped=%d",
            tick, tostring(in_game), ROLE, total, settled, #kill_queue, #claim_queue,
            accepted_claims, rejected_claims, published, received, bound, mirror_moves, brains_stopped))
    end
end

-- pending: while the game thread is busy (a level load) at most one tick waits in its queue
local pending = false
local last_error = nil
LoopAsync(50, function()
    if pending then return false end
    pending = true
    ExecuteInGameThread(function()
        local ok, err = pcall(fight_tick)
        if not ok then
            local msg = tostring(err)
            if msg ~= last_error then last_error = msg; boot("tick error " .. msg) end
        end
        pending = false
    end)
    return false
end)
