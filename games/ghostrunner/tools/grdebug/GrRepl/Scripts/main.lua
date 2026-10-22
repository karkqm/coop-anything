-- GrRepl: dev-only Lua console for TEST COPIES. Never ship this in the player kit.
-- The external tool (tools/grdebug/repl.py) atomically drops repl.lua into this copy's
-- private debug folder; this mod runs it once on the game thread and writes repl.out.
-- One persistent environment is kept across calls, so probes can stash state in it.

local PAIR = "A"
local DIR = "C:/coop mods/work/grdebug/" .. PAIR .. "/"
local IN, OUT = DIR .. "repl.lua", DIR .. "repl.out"

local env = setmetatable({}, { __index = _G })
env.R = {}

local function write_out(text)
    local tmp = OUT .. ".tmp"
    local f = io.open(tmp, "w")
    if not f then return end
    f:write(text)
    f:close()
    os.remove(OUT)
    os.rename(tmp, OUT)
end

LoopAsync(200, function()
    local f = io.open(IN, "r")
    if not f then return false end
    local src = f:read("a")
    f:close()
    os.remove(IN)
    ExecuteInGameThread(function()
        local out = {}
        env.print = function(...)
            local t = {}
            for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
            out[#out + 1] = table.concat(t, "\t")
        end
        local fn, err = load(src, "repl", "t", env)
        local ok, res = false, err
        if fn then ok, res = pcall(fn) end
        out[#out + 1] = "--ok=" .. tostring(ok) .. " " .. tostring(res)
        write_out(table.concat(out, "\n") .. "\n")
    end)
    return false
end)

print("[GrRepl] ready for " .. DIR .. "\n")
