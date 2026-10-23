-- Extract jarray/jtuples/jlist from CoopFight and test them on a canonical relay inbox line.
local f = io.open("C:/coop mods/kit/experimental/CoopFight-main.lua", "r")
local src = f:read("a"); f:close()
local a = src:find("local function jarray", 1, true)
local b = src:find("local function world_id", 1, true)
local chunk = src:sub(a, b - 1) .. "\nreturn jarray, jtuples, jlist"
local jarray, jtuples, jlist = load(chunk, "readers", "t", _G)()
local raw = '{"connected":true,"state":{"claims":[[9,9,9]],"enemies":[[1,4050,-69550,-379,90],[2,1341,-70267,-38,-45.5]],"kills":[[1.5,-2.0,3.0]],"position":[1.0,2.0,3.0],"roster":[[1,4050,-69550,-379]],"role":"host"}}'
local fails = 0
local function check(name, cond) if not cond then fails = fails + 1; print("FAIL " .. name) end end
local kills = jlist(raw, "kills")
check("kills count", #kills == 1)
check("kills value", kills[1] and kills[1].X == 1.5 and kills[1].Y == -2.0)
local claims = jlist(raw, "claims")
check("claims separate", #claims == 1 and claims[1].X == 9)
local en = jtuples(raw, "enemies", 5)
check("enemies count", #en == 2)
check("enemy yaw", en[2] and en[2][5] == -45.5)
local ro = jtuples(raw, "roster", 4)
check("roster", #ro == 1 and ro[1][1] == 1 and ro[1][4] == -379)
check("missing key", #jtuples(raw, "nope", 3) == 0)
check("empty array", #jtuples('{"kills":[]}', "kills", 3) == 0)
print(fails == 0 and "ALL PASS" or (fails .. " FAILED"))
