local function find(root, want, d)
  if not root or d > 7 then return nil end
  if root:GetFullName():find("%." .. want .. "$") then return root end
  local okn, n = pcall(function() return root:GetChildrenCount() end)
  if okn and n then for i = 0, n - 1 do local r = find(root:GetChildAt(i), want, d + 1) if r then return r end end end
  return nil
end
R.find = find
for i, p in pairs(FindAllOf("BP_PanelStartMenu_C") or {}) do
  print("panel", i, p:GetFullName(), "IsVisible", pcall(function() return p:IsVisible() end), "InViewport", pcall(function() return p:IsInViewport() end))
  local root = p.WidgetTree.RootWidget
  for _, n in ipairs({"VBoxButtonsGR","SiBoxContinue","BtnContinue","HorBoxMainButtons","BtnGhostrunner"}) do
    local x = find(root, n, 0)
    if x then
      local _, vis = pcall(function() return x:GetVisibility() end)
      local _, op = pcall(function() return x:GetRenderOpacity() end)
      local _, iv = pcall(function() return x:IsVisible() end)
      local _, hov = pcall(function() return x:IsHovered() end)
      print("  ", n, "vis", vis, "op", op, "isvis", iv, "hov", hov)
    end
  end
end
