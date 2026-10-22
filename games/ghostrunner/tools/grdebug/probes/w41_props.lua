-- W41: properties declared by one Blueprint class, simple types only (reading struct, delegate
-- and container properties through ForEachProperty crashed the GOG build).
-- The caller prepends:  local CNAME = "<class>"
local SIMPLE = { BoolProperty = 1, FloatProperty = 1, IntProperty = 1, ByteProperty = 1,
  EnumProperty = 1, NameProperty = 1, StrProperty = 1, ObjectProperty = 1 }
local inst = FindFirstOf(CNAME)
if not (inst and inst:IsValid()) then print(CNAME .. ": none") return end
local props = {}
inst:GetClass():ForEachProperty(function(p)
  local n = p:GetFName():ToString()
  local pt = p:GetClass():GetFName():ToString()
  if not SIMPLE[pt] then props[#props + 1] = n .. ":" .. pt:gsub("Property", "") return end
  local s = "?"
  if pt == "ObjectProperty" then
    local ok, v = pcall(function() return inst[n] end)
    if ok and v and v.IsValid and v:IsValid() then
      s = "obj:" .. (tostring(v:GetFullName()):match("([%w_]+)$") or "?")
    else s = "nil" end
  elseif pt == "NameProperty" then
    local ok, v = pcall(function() return inst[n]:ToString() end)
    s = ok and tostring(v) or "?"
  elseif pt == "StrProperty" then
    local ok, v = pcall(function() return inst[n]:ToString() end)
    s = ok and tostring(v) or "?"
  else
    local ok, v = pcall(function() return inst[n] end)
    s = ok and tostring(v) or "?"
  end
  props[#props + 1] = n .. "=" .. s
end)
print(CNAME .. " (" .. #props .. "): " .. table.concat(props, ", "))
