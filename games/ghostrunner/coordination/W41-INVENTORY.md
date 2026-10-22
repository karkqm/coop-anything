# W41 — dynamic objects in L_Tutorial and how each one syncs

Measured 2026-10-23 on copy A (GOG build) in `L_Tutorial_Persistant`, entered with W39.
Raw data: `work/grdebug/w41-actors.txt` (all actor classes, counts), `w41-props*.txt`
(Blueprint-declared state per class). Probes: `work/grdebug/probes/w41_*.lua`.

Rule (owner decision): the host owns the world. The client shows it and sends claims.

Channels:
- **snap** — continuous state in the existing UDP snapshot (host → client, lossy is fine).
- **event** — one-shot, must arrive: reliable channel with acks (not built yet, see plan step 3).
- **claim** — client → host request; host decides and answers with an event.
- **local** — runs on each machine by itself, no sync.

| Class (count) | State it carries | Channel | Notes |
|---|---|---|---|
| BP_EnemyShooterPistol_C (13) + Controller | transform, anim, alive, AI target | snap + event(death) | W42: client copy has no AI, follows host. Death sync done (W33/W34). |
| BP_GunPistol_C (13) | fire | event(shot) | Projectiles spawn at runtime; host spawns, client gets spawn event with origin+dir. |
| BP_ShieldBeaconEnergyShieldBeacon_C (2) / …Enemy_C (5) | shield up, `Refresh` | event | Beacon destroyed → shield off on linked enemies. |
| BP_TriggerSwitchEnemiesLogicOn_C (10) | `EnemiesList` | claim → event | Turns enemy AI on. Host only; client trigger becomes a claim. |
| BP_Group_Killed_C (3), GroupKilledEventDemo1-7 | `TriggerCheckpoint`, `Unlock Holodoors`, `Activate Access Point`, `Slowmo` | host only → events | Fires from enemy deaths, so only the host runs it; results go out as events. |
| BP_Holo_Doors_01_C (6) | `Door Opened`, `Door Locked` | event | Send state, not the timeline. |
| BP_Door_Sliding_01_C (3) | timeline, `OnDoorOpened/Closed/Stopped` | event | Hook the delegates on host, replay open/close on client. |
| AccessPoint_C (1), AccessPointNew2_C (2) | `Player In`, `Button Clicked`, `IsWorking`, `usable` | claim → event | Client presses → claim; host clicks → event. |
| BP_Level_Elevator_C (2) | teleport triggers, own checkpoint, exit holo door | event | Start/arrive events; both players must be inside — host decides. |
| Checkpoint_C (33) | `Player Character` (single ref), `RestartFromCheckpoint`, `Respawn Enemy` | event | Host owns "last checkpoint". Respawn of enemies is host only. Holds ONE player ref — single-player assumption. |
| LevelSequenceActor (5), MatineeActor (1), BP_DialogTrigger_C (21) | play state | event | Cutscene / dialog start on host → client plays it. |
| LevelStreamingVolume (7), L_Tutorial_Sub/Stream levels | loaded sublevels | event | Client must load what the host loaded, before host-side objects there are mirrored. |
| BP_CollectibleStoryItemTrigger_C (2), BP_Collectible_Icon_example_C (2) | `Collectible` id | claim → event | Taken once for both. |
| TriggerBox (44), BP_TriggerBoxOML_C (17), BP_ObjectiveTrigger_C (2), BP_Light_Trigger_C (8), BP_OnFocusTrigger_C, BP_Look_at_event_C | overlap | claim → event | Each one needs checking: gameplay trigger (claim) or cosmetic (local). |
| Teleport_to_taget_point_with_offset_C (14) | `PlayerRef`, `IsWorking` | local | Moves whoever enters; position then flows in the player snapshot. |
| Grapling_Point_C (16) | per-player range/selection; `ShouldGraplingPointMove=false` | local | All static here. If one moves, add snap. |
| KillVolumeInvisible_C (48), kill_volume_C (14) | overlap | local → claim(death) | Each player dies locally, reports death to host. |
| BP_electric_arches_01_C (28), BP_Electric_Panel_C (14) | `inc_01` counter | local | Constant beam, no on/off phase seen. Recheck if a hazard toggles. |
| BP_InGameTutorial_C (13), BP_InGameTutorialCrouch_C (2), TutorialPathPreview_C (3) | prompts | local | |
| BP_Objective_Marker_Updater_C (5), ObjectiveMarker_C | objective | event | Follows host progress. |
| Lights, decals, emitters, sounds, fog, rain, fans, BP_Simple_rotate_C, BP_Drill_Machine_01_C, holograms | visuals | local | ~16 000 actors, none matter for gameplay. |

## Findings that change the plan

1. Checkpoint_C, Grapling_Point_C and Teleport hold exactly one `Player Character` reference.
   Anything that resolves "the player" in Blueprint will ignore the second player. On the host the
   remote player is a puppet, so W43 must hand enemies a real target (the W10 peer pawn).
2. Enemy activation is trigger-driven (`BP_TriggerSwitchEnemiesLogicOn_C` → `EnemiesList`).
   The client must never run these: on the client they become claims.
3. Mass level logic hangs off kills (`BP_Group_Killed_C`). Because only the host kills, only the
   host runs it; that keeps doors and checkpoints consistent for free once events replay.
4. The reliable event channel is needed by 11 of the rows above — it is the next blocker after W42.
5. Reading struct/delegate properties via UE4SS `ForEachProperty` crashes this build. Probe only
   simple types (see `w41_props.lua`).
