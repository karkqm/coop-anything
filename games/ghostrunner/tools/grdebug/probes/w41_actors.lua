-- W41: inventory of actors in the loaded level, grouped by class, with mobility and tick state.
-- Output: one line per class: count, movable count, ticking count, sample name.
local counts = {}
local function cls_of(a)
  local ok, c = pcall(function() return a:GetClass():GetFName():ToString() end)
  return ok and c or "?"
end
for _, a in pairs(FindAllOf("Actor") or {}) do
  local okv, valid = pcall(function() return a:IsValid() end)
  if okv and valid then
    local full = tostring(a:GetFullName())
    if full:find("PersistentLevel") or full:find("L_Tutorial") then
      local c = cls_of(a)
      local e = counts[c]
      if not e then e = { n = 0, mov = 0, tick = 0, sample = full:match("([%w_]+)$") }; counts[c] = e end
      e.n = e.n + 1
      pcall(function()
        local root = a.RootComponent
        if root and root:IsValid() and root.Mobility == 2 then e.mov = e.mov + 1 end
      end)
      pcall(function() if a:IsActorTickEnabled() then e.tick = e.tick + 1 end end)
    end
  end
end
local list = {}
for c, e in pairs(counts) do list[#list + 1] = { c = c, e = e } end
table.sort(list, function(x, y) return x.e.n > y.e.n end)
for _, it in ipairs(list) do
  print(string.format("%s\t%d\tmov=%d\ttick=%d\t%s", it.c, it.e.n, it.e.mov, it.e.tick, it.e.sample or ""))
end
