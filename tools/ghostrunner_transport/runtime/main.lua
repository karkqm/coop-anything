-- UE4SS 3.0.1: one local player, one non-player remote avatar, no console travel.
local J = require('json')
local config = require('config')
local appearance = require('appearance')
local dir = assert(config.directory, 'set config.directory to the private transport folder')
local null = J.null
if _G.GhostrunnerSync then
    _G.GhostrunnerSync.stop=true
    if _G.GhostrunnerSync.visual then _G.GhostrunnerSync.visual:destroy() end
    local previous=_G.GhostrunnerSync.body
    if previous and previous:IsValid() then previous:K2_DestroyActor() end
end
local state = {tick=0, pending=false, world=nil, body=nil, last_error=nil, started=false}
_G.GhostrunnerSync=state
state.config=config
if config.qa then state.qa=require('qa').new(J,dir) end
local function valid(o) return o and o:IsValid() end
local function log(message) print('[GhostrunnerSync] '..message..'\n') end
local function write(name, value)
    local tmp = dir..'/'..name..'.lua.tmp'
    local f = io.open(tmp,'wb')
    if not f then return false end
    f:write(J.encode(value)); f:close()
    if name=='outbox.json' then
        -- Windows Lua's CRT rename cannot replace an existing file. Hand over
        -- a completed staging file; the Python bridge atomically adopts it.
        return os.rename(tmp,dir..'/outbox.next.json') ~= nil
    end
    -- Diagnostics are not consumed as network state. Readers retry partial JSON.
    local out=io.open(dir..'/'..name,'wb')
    if not out then return false end
    out:write(J.encode(value)); out:close(); os.remove(tmp)
    return true
end
local function read(name)
    local f=io.open(dir..'/'..name,'rb')
    if not f then return nil end
    local raw=f:read(8193); f:close()
    local ok,value=pcall(J.decode,raw)
    return ok and value or nil
end
local function xyz(v) return {v.X,v.Y,v.Z} end
local function vector(a) return {X=a[1],Y=a[2],Z=a[3]} end
local function angle(a) return {Pitch=a[1],Yaw=a[2],Roll=a[3]} end
local function finite(n,limit) return type(n)=='number' and n==n and math.abs(n)<limit end
local function triple(a,limit)
    return type(a)=='table' and #a==3 and finite(a[1],limit) and finite(a[2],limit) and finite(a[3],limit)
end
local function world_key(world)
    return world:GetFullName():match('^World (.-)%.')
end
local function hide()
    if valid(state.body) then state.body:SetActorHiddenInGame(true) end
    if state.visual then state.visual:hide(true) end
end
local function destroy()
    if state.visual then state.visual:destroy(); state.visual=nil end
    if valid(state.body) then state.body:K2_DestroyActor() end
    state.body=nil
end
local function spawn(world,pose)
    local cl=StaticFindObject('/Script/Engine.Character')
    local mesh=StaticFindObject(config.mesh)
    assert(valid(cl) and valid(mesh), 'avatar class/mesh is not loaded in this level')
    local body=world:SpawnActor(cl,vector(pose.position),angle(pose.rotation))
    assert(valid(body),'SpawnActor returned no character')
    state.body=body
    body:SetActorEnableCollision(false)
    body.CharacterMovement:DisableMovement()
    body.CharacterMovement:SetComponentTickEnabled(false)
    body.Mesh:SetSkeletalMesh(mesh,true)
    body.Mesh:K2_SetRelativeLocation({X=0,Y=0,Z=config.mesh_z or -88},false,{},true)
    body.Mesh:K2_SetRelativeRotation({Pitch=0,Yaw=config.mesh_yaw or -90,Roll=0},false,{},true)
    body.Mesh:SetOwnerNoSee(false)
    body.Mesh:SetOnlyOwnerSee(false)
    body.Mesh:SetVisibility(true,true)
    body.Mesh:SetHiddenInGame(false,true)
    body.Mesh.VisibilityBasedAnimTickOption=0
    state.visual=appearance.new(body,config)
    log('spawned remote avatar '..body:GetFullName())
    return body
end
local function local_controller()
    local gs=StaticFindObject('/Script/Engine.Default__GameplayStatics')
    -- UEHelpers' first-controlled-pawn search can choose a puppet if it has a
    -- controller; explicitly select the real local player at index zero instead.
    for _,pc in ipairs(FindAllOf('PlayerControllerOML') or {}) do
        if valid(pc) and valid(pc.Player) then
            local first=gs:GetPlayerController(pc,0)
            if valid(first) then return first end
        end
    end
end
local function tick()
    state.tick=state.tick+1
    local pc=local_controller()
    if not valid(pc) then hide(); return end
    local world=pc:GetWorld()
    local key=world_key(world)
    local pawn=pc.Pawn
    state.pc,state.pawn=pc,pawn
    if state.world~=key then
        destroy(); state.world=key; state.last_inbox=nil
        log('world '..tostring(key))
    end
    if not valid(pawn) or not pawn:GetFullName():match('^BP_PlayerCharacter_C ') then
        hide(); write('outbox.json',null)
        write('runtime.json',{schema=1,tick=state.tick,world=key or null,gameplay=false,
                            adapter_generation=config.generation or 'manual'})
        return
    end
    if state.qa then state.qa:update(pc,pawn,config) end
    local position=pawn:K2_GetActorLocation()
    local rotation=pawn:K2_GetActorRotation()
    local velocity=pawn:GetVelocity()
    local pose={schema=1,world=key,tick=state.tick,position=xyz(position),
                rotation={rotation.Pitch,rotation.Yaw,rotation.Roll},velocity=xyz(velocity),
                half_height=pawn.CapsuleComponent:GetScaledCapsuleHalfHeight(),
                motion=appearance.capture(pawn)}
    write('outbox.json',pose)
    local inbox=read('inbox.json')
    local peer=inbox and inbox.state
    local connected=(type(inbox)=='table' and inbox.connected==true
        and finite(inbox.received_at,1e12) and math.abs(os.time()-inbox.received_at)<(config.timeout or 3)
        and type(peer)=='table' and peer~=null and peer.schema==1 and peer.world==key
        and triple(peer.position,1e8) and triple(peer.rotation,1e5) and triple(peer.velocity,1e6)
        and type(inbox.session)=='string' and finite(inbox.seq,2^53))==true
    if not connected then hide()
    else
        local body=valid(state.body) and state.body or spawn(world,peer)
        if not config.mutation_drop_receive then
            assert(body:K2_SetActorLocation(vector(peer.position),false,{},true), 'remote move failed')
            body:K2_SetActorRotation(angle(peer.rotation),true)
        end
        body:SetActorHiddenInGame(false)
        state.visual:update(peer)
    end
    local actual=null
    local actual_rotation=null
    if valid(state.body) then actual=xyz(state.body:K2_GetActorLocation()) end
    if valid(state.body) then
        local r=state.body:K2_GetActorRotation()
        actual_rotation={r.Pitch,r.Yaw,r.Roll}
    end
    local players=0
    for _,p in ipairs(FindAllOf('PlayerControllerOML') or {}) do
        if valid(p.Player) then players=players+1 end
    end
    write('runtime.json',{schema=1,tick=state.tick,world=key,gameplay=true,
          adapter_generation=config.generation or 'manual',peer_motion=connected and peer.motion or null,
          peer_velocity=connected and peer.velocity or null,
          pawn=pawn:GetFullName(),local_position=pose.position,local_rotation=pose.rotation,
          local_velocity=pose.velocity,
          local_players=players,peer_usable=connected,peer_session=inbox and inbox.session or null,
          peer_seq=inbox and inbox.seq or null,peer_expected=connected and peer.position or null,
          body=valid(state.body) and state.body:GetFullName() or null,
          body_position=actual,body_rotation=actual_rotation,body_hidden=not valid(state.body) or state.body.bHidden,
          qa_id=state.qa and state.qa.id or null,qa_active=state.qa and state.qa.hold~=nil or false,
          qa_validation=state.qa and state.qa.validation or null,
          local_motion=pose.motion,appearance=state.visual and state.visual:probe() or null,
          mesh=valid(state.body) and state.body.Mesh.SkeletalMesh:GetFullName() or null})
end
log('loaded; adapter only, no gameplay authority or checkpoint sync')
LoopAsync(config.interval_ms or 50,function()
    if state.stop then return true end
    if state.pending then return false end
    state.pending=true
    ExecuteInGameThread(function()
        if state.stop then state.pending=false; return end
        local ok,err=pcall(tick)
        if not ok then
            local message=tostring(err)
            if message~=state.last_error then log('error '..message); state.last_error=message end
            pcall(hide)
            pcall(destroy)
            pcall(write,'runtime-error.json',{error=message,tick=state.tick})
        end
        state.pending=false
    end)
    return false
end)
