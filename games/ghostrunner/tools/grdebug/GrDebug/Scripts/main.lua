-- GrDebug: state reporter for the external debugger (C:\coop mods\tools\grdebug\grdebug.py).
--
-- The tool cannot see inside the game, so this mod writes what it needs to a file once a second:
-- the world, the pawn, whether that pawn is the gameplay character, the enemy count, and whether
-- the main-menu button is actually visible. The last part matters: the intro cutscenes run inside
-- the MainMenu world, so world name alone cannot tell a cinematic from the menu itself.

local PAIR = "A"
local NET_DIR = "C:/coop mods/work/grdebug/" .. PAIR .. "/"

local function safe(fn, default)
    local ok, v = pcall(fn)
    if ok then return v end
    return default
end

local function ts(v) return safe(function() return tostring(v) end, "<ts>") end

local function write_state(content)
    local path = NET_DIR .. "state.txt"
    local tmp = path .. ".tmp"
    local f = io.open(tmp, "w")
    if not f then return end
    f:write(content)
    f:close()
    if not os.rename(tmp, path) then
        os.remove(path)
        os.rename(tmp, path)
    end
end

local function player_controller()
    local all = safe(function() return FindAllOf("PlayerControllerOML") end, nil) or {}
    local fallback = nil
    for _, c in pairs(all) do
        if c and safe(function() return c:IsValid() end, false)
            and safe(function() return c.Player:IsValid() end, false) then
            return c
        end
        fallback = fallback or c
    end
    return fallback
end

local function find_widget(root, want, depth)
    if not root or depth > 6 then return nil end
    local full = ts(safe(function() return root:GetFullName() end, ""))
    if full:find(want .. "$") then return root end
    local n = safe(function() return root:GetChildrenCount() end, nil)
    if n then
        for i = 0, n - 1 do
            local r = find_widget(safe(function() return root:GetChildAt(i) end, nil), want, depth + 1)
            if r then return r end
        end
    end
    return nil
end

-- visibility 0 is ESlateVisibility::Visible; 4 is SelfHitTestInvisible etc.
local function menu_state()
    for _, o in pairs(safe(function() return FindAllOf("BP_PanelStartMenu_C") end, nil) or {}) do
        if o and safe(function() return o:IsValid() end, false) then
            local tree = safe(function() return o.WidgetTree end, nil)
            local root = tree and safe(function() return tree.RootWidget end, nil)
            local btn = find_widget(root, "BtnContinue", 0)
            if btn then
                -- IsVisible walks the parent chain, GetVisibility on the button alone does not:
                -- the button reports "visible" even while the whole menu panel is hidden by the
                -- intro cinematic
                -- panel visible = the bottom tab bar is up; the Continue button is only visible
                -- once the "Start game" submenu is expanded
                local panel_visible = safe(function() return o:IsVisible() end, nil)
                -- IsVisible is true even while the submenu is closed: the game fades the
                -- submenu box (VBoxButtonsGR) to opacity 0 and makes it hit-test invisible
                local box = find_widget(root, "VBoxButtonsGR", 0)
                local op = box and safe(function() return box:GetRenderOpacity() end, nil)
                local vis = box and safe(function() return box:GetVisibility() end, nil)
                local open = op ~= nil and op > 0.9 and (vis == 0 or vis == 4)
                if panel_visible == true then
                    if open then return "visible|submenu" end
                    return "visible|nosubmenu"
                end
                if panel_visible == false then return "hidden|hidden" end
                return "unknown|unknown"
            end
            return "no-button"
        end
    end
    return "no-panel"
end

local tick = 0
LoopAsync(1000, function()
    tick = tick + 1
    local pc = player_controller()
    local world = "none"
    local pawn = "none"
    local gameplay = "false"
    if pc then
        local w = safe(function() return pc:GetWorld() end, nil)
        if w then
            world = ts(safe(function() return w:GetFullName() end, "none"))
        end
        local p = safe(function() return pc.Pawn end, nil)
        if p and safe(function() return p:IsValid() end, false) then
            pawn = ts(safe(function() return p:GetFullName() end, "none"))
            gameplay = ts(safe(function() return p:GetFullName() end, "")):find("BP_PlayerCharacter_C") and "true" or "false"
        end
    end
    local enemies = 0
    for _, p in pairs(safe(function() return FindAllOf("Pawn") end, nil) or {}) do
        if p and safe(function() return p:IsValid() end, false) then
            local n = ts(safe(function() return p:GetFullName() end, "")):lower()
            if n:find("enemy") or n:find("boss") then enemies = enemies + 1 end
        end
    end
    write_state(string.format("tick=%d\nworld=%s\npawn=%s\ngameplay=%s\nenemies=%d\nmenu=%s\n",
        tick, world, pawn, gameplay, enemies, menu_state()))
    return false
end)


