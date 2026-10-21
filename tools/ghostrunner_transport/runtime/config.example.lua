return {
    directory = 'C:/path/to/private/net-A',
    interval_ms = 50,
    timeout = 3,
    qa = false, -- Enable only in isolated test copies for the structured local bot.
    -- Stock humanoid from the player's own game, used as a temporary remote avatar.
    -- No game asset is packaged or downloaded. Must already be loaded in the level.
    mesh = '/Game/Visual/Characters/Enemy_Pistol_01/SK_Enemy_Pistol_01.SK_Enemy_Pistol_01',
    mesh_z = -108, -- Fallback; the runtime adjusts this to the source capsule height.
    mesh_yaw = -90,
}
