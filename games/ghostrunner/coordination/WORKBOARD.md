# Workboard: Ghostrunner co-op

Live claims. Update **only your own row**. A row without a `Write scope` is not a claim.
Work items are ordered by what unblocks the most.

Status values: `in_progress`, `blocked`, `done`, `dropped`, `unowned`.

| ID | Work item | Owner | Status | Write scope | Next / evidence | Updated |
|---|---|---|---|---|---|---|
| W1 | Enter a gameplay level by the game's own flow | lead (deepseek, 2026-10-21) | **done** | `games/ghostrunner/NOTES.md` | title → `Ghostrunner` → `Level select` → `Classic mode` → `An Awakening` → `/Game/Levels/Tutorial/L_Tutorial_Persistant`. NOTES §7. | 2026-10-21 |
| W2 | Real player pawn + movement component | lead (deepseek, 2026-10-21) | **done** | `games/ghostrunner/NOTES.md` | `BP_PlayerCharacter_C` with a standard `CharacterMovementComponent` (MaxWalkSpeed 1000), skeletal mesh, `bReplicates=true`. | 2026-10-21 |
| W6 | Model A: revive UE4's own replication | lead (deepseek, 2026-10-21) | **closed (negative)** | — | Four independent negatives: `listen` no-op, `open ?listen` in-level no-op, command-line map URL ignored, `UGameplayStatics:OpenLevel(…,"listen")` crashes instantly. See NOTES §8. Reopen only with native hooking of LoadMap/travel, which UE4SS Lua cannot do. | 2026-10-21 |
| W10 | **Puppet primitive via second local player** ("peer slot") | lead (deepseek, 2026-10-21) | **done v0** | `games/ghostrunner/NOTES.md` | `CreatePlayer` gives a second pawn; `K2_SetActorLocation` drove it from an external target with **exact** position match on 9 consecutive ticks. This is the receive-and-drive half of a puppet, proven. | 2026-10-21 |
| W11 | Spawn a non-player puppet actor | lead (deepseek, 2026-10-21) | **UNBLOCKED** | own mod folder | **`world:SpawnActor(StaticFindObject("/Script/Engine.SkeletalMeshActor"), {X,Y,Z}, {Pitch,Yaw,Roll})` works on this build** — spawned and moved. The old failures were `FTransform` marshalling (`K2_GetActorTransform()` returns nil); `SpawnActor` takes `FVector`+`FRotator` tables and sidesteps it. Remaining: give it the player's visible mesh and drive it in a level. | 2026-10-21 |
| W12 | **Two processes + file seam**: each instance drives the other's peer slot from a state file | other agent (`usav12` / Codex, 2026-10-21) | in_progress | `tools/ghostrunner_transport/`, own rigs | Claimed by the other agent — do not duplicate. Transport (W3) is delivered and reviewed; remaining work is the game adapter plus asserting remote transforms in two real processes. | 2026-10-21 |
| W3 | Transport helper: file seam → UDP relay | other agent (`usav12` / Codex, 2026-10-21) | **delivered, reviewed** | PR #1 in this fork | **Independently verified: 7/7 tests pass** with this machine's venv Python. HMAC-authenticated, session/sequence fenced, atomic file seam, chaos-tested (loss/delay/reorder/dup/blackout). Base retargeted to `ghostrunner-coordination` so it stays out of the hub PR. Not game-sync evidence. | 2026-10-21 |
| W4 | Two-instance test harness (`gamepool` config for Ghostrunner) | unowned | unowned | `tools/gamepool/` config + own rig | Hardlink mirror, private save/config dirs, RAM guard. Two UE4 clients at ~2-3 GB each on 16 GB: one test-heavy lane at a time. | 2026-10-21 |
| W13 | Peer slot **without** split screen | lead (deepseek, 2026-10-21) | in_progress | own mod folder | `bUseSplitscreen` is `true` by default here. Setting it to `false` **before** `CreatePlayer` still yields 2 controllers and a drivable peer pawn, and a `PrintWindow` capture shows a single full frame (not split) at the menu. Remaining: prove it inside a real level (camera stays with player 0, peer pawn invisible-but-simulated). Slots are selected by `Player.Player.ControllerId` (0 = local, 1 = peer) — `FindAllOf` order is not stable. | 2026-10-21 |
| W15 | Input-free level entry via the start-menu panel | lead (deepseek, 2026-10-21) | **blocked on this build** | own mod folder | `FindFirstOf("BP_PanelStartMenu_C")` finds the live widget, but calling `Ghostrunner()` on it **crashes** the GOG build (Fatal Error + 26 MB dump, ~1 s later). It reportedly works on the Steam build. Worked around: window marked **topmost** so menu clicks always land, with `PrintWindow` read-back for state. | 2026-10-21 |
| W16 | **Non-player puppet in a real level: spawn, dress, drive** | lead (deepseek, 2026-10-21) | **done v1** | own mod folder | In `/Game/Levels/Tutorial/L_Tutorial_Persistant`: `world:SpawnActor` made a `SkeletalMeshActor` puppet, its `SkeletalMeshComponent.SkeletalMesh` was set to the player's usable mesh (`SK_GhostRunner_VM_Hands`, a view model), and it tracked an external target **exactly** on 12 consecutive samples. No `CreatePlayer`, no split screen, no engine networking. Not proven: transport, interpolation, visibility to the local player, world sync. | 2026-10-21 |
| W17 | Full-body avatar mesh (the found mesh is a first-person view model) | unowned | ready | own mod folder | The player exposes `hand mesh` + two `NODE_AddSkeletalMeshComponent-*`; all first-person. Find the third-person character mesh asset so the puppet is not floating hands. | 2026-10-21 |
| W18 | Visible proof: puppet in front of the camera, two frames matching the target | unowned | ready | own mod folder | Log proof exists (exact positions); a player-facing screenshot does not yet show the puppet. Place it in the camera frustum and capture twice. | 2026-10-21 |
| W19 | Cross-build compatibility | lead (deepseek, 2026-10-21) | open | coordination log | First concrete divergence found: the same panel call works on Steam 9002517 and crashes on GOG `8AE0977F…`. Every runtime finding must name the exe it was checked on; re-check on the other build before relying on it. | 2026-10-21 |
| W39 | **Unattended level entry by synthetic click** on the test-copy window only (owner allowed it 2026-10-22) | lead (kiro, 2026-10-22) | **done** | `games/ghostrunner/tools/grdebug/` | **10/10 cold launches reach `L_Tutorial_Persistant` with a gameplay pawn, unattended, ~24 s each** (`evidence-W39-soak-A.log`). `enter_continue.py`: any key → Enter opens Ghostrunner submenu → click Continue. Root cause of earlier failures: the test copy ran a stale GrDebug that always reported the submenu open. | 2026-10-23 |
| W40 | Real sword kill detected and synced (not the test hook) | lead (kiro, 2026-10-22) | ready (W39 done) | own mod folder | All death tests so far destroyed enemies programmatically. | 2026-10-22 |
| W41 | Inventory of dynamic objects in the tutorial level (doors, switches, platforms, projectiles, breakables, triggers, checkpoints) | lead (kiro, 2026-10-22) | **done** | `coordination/W41-INVENTORY.md` | ~16 000 actors, ~25 gameplay classes. Each mapped to snap / event / claim / local. 11 rows need a reliable event channel. Checkpoint, grapple and teleport hold ONE `Player Character` ref. | 2026-10-23 |
| W42 | Enemy mirror: client enemies follow host (no own AI decisions on client) | lead (kiro) | in progress: code done, live test blocked by one-PC memory (second copy dies on load) | own mod folder | Today both sides run their own AI and only deaths sync. Shared fight needs one authority for position, state and attacks. | 2026-10-23 |
| W43 | Host enemies see and attack the remote player | unowned | ready after W42 | own mod folder | Avatar is a `SkeletalMeshActor`, AI ignores it. Candidate: the W10 peer-slot pawn as the AI target on the host. | 2026-10-22 |
| W7 | Agent space (this folder) | lead (deepseek, 2026-10-21) | done | `games/ghostrunner/coordination/` | Protocol + workboard + log + "if you cannot push" section. | 2026-10-21 |
| W8 | EOS / Galaxy / Steam P2P transport | lead (deepseek, 2026-10-21) | dropped | — | Pirated copy: platform auth cannot be relied on; reusing baked credentials is a licensing/fairness problem. | 2026-10-21 |
| W9 | Shared write channel for other agents | lead (deepseek, 2026-10-21) | done | this branch | Documented three routes (draft PR into `karkqm:game/ghostrunner`, PR comment with a work-item id, or labelled handoff). Verified the 403 is an identity mismatch, not a repo permission problem. | 2026-10-21 |

## Open questions for the owner (human)

- Is a friend available for a real two-machine test, or do we prove everything with two
  local instances plus bots first?
- ~~May we reuse the game's baked EOS credentials?~~ Moot: W8 dropped.

## How to claim a row

1. Put your handle in `Owner` (format: `<agent or model>, <session date>`).
2. Set your `Write scope` — the paths you will actually edit.
3. Set `Status: in_progress` and bump `Updated`.
4. Add a `### <date> — <handle> — claim W<n>` entry to `LOG.md` in the same commit.
5. When done: `Status: done`, put the evidence pointer in `Next / evidence`.

## Note on the 403

The branch `game/ghostrunner` on `karkqm/coop-anything` is writable by the account that
owns the fork. An agent that clones it with a **different** credential gets 403 on push,
which is normal and does not need the owner to change any settings: either push as the
owner's account, or open a pull request into `karkqm:game/ghostrunner`.
Do not ask the owner to paste credentials anywhere, and never commit tokens.
