-- W39: list every widget in the start-menu tree whose name mentions VBoxButtons / Continue,
-- with visibility, opacity and absolute position, to see what GrDebug's matcher really hits.
local function walk(w, d, out)
  if not w or d > 9 then return end
  local okf, full = pcall(function() return w:GetFullName() end)
  full = okf and tostring(full) or "?"
  local name = full:match("%.([%w_]+)$") or full
  if name:find("VBoxButtons") or name:find("Continue") or name:find("SiBox") then
    local _, vis = pcall(function() return w:GetVisibility() end)
    local _, op = pcall(function() return w:GetRenderOpacity() end)
    local _, iv = pcall(function() return w:IsVisible() end)
    local pos = "?"
    pcall(function()
      local g = w:GetCachedGeometry()
      local a = g.AbsolutePosition or g.Position
      local s = g.AbsoluteSize or g.Size
      if a then pos = string.format("%.0f,%.0f", a.X, a.Y) end
      if s then pos = pos .. string.format(" size %.0fx%.0f", s.X, s.Y) end
    end)
    out[#out + 1] = string.format("%s%s vis=%s op=%s isvis=%s pos=%s", string.rep(" ", d), name,
      tostring(vis), tostring(op), tostring(iv), pos)
  end
  local okn, n = pcall(function() return w:GetChildrenCount() end)
  if okn and n then for i = 0, n - 1 do walk(w:GetChildAt(i), d + 1, out) end end
end
for i, p in pairs(FindAllOf("BP_PanelStartMenu_C") or {}) do
  local _, valid = pcall(function() return p:IsValid() end)
  print("panel", i, p:GetFullName(), "valid", tostring(valid))
  local out = {}
  walk(p.WidgetTree.RootWidget, 0, out)
  for _, l in ipairs(out) do print(l) end
end
