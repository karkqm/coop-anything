# Log: Ghostrunner co-op

Append-only. **Newest entries at the bottom.** Never rewrite or reorder earlier entries —
that turns a clean append into a merge conflict for everyone else.

Entry format is in [`README.md`](README.md#log-entry-format).

---

### 2026-10-21 — lead (deepseek, session 2026-10-21) — triage: nothing exists, engine is UE 4.26

- Did: searched for prior work; hashed and fingerprinted the install; read the pak footer.
- Result: no co-op or multiplayer mod for Ghostrunner or Ghostrunner 2 exists (Nexus,
  GameBanana, ModDB, GitHub repo/code/issue search, Steam forums, Reddit, YouTube, web).
  Engine is **UE 4.26**, confirmed twice: UTF-16LE `FEngineVersion` = `++UE4+Release-4.26-CL-0`
  in the shipping exe, and UE4SS Patternsleuth reports `Found EngineVersion: 4.26` at
  runtime. Shipping exe SHA-256 `8AE0977F…4BD4`. Pak is version 11, index opaque
  (encrypted), and the two `.sig` files are **byte-identical dummies** — pak integrity is
  not actually enforced. Details: `../NOTES.md` §0.
- Next: prove the hook.
- Claim: opened W1-W6.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — UE4SS v3.0.1 loads and runs Lua (PASS)

- Did: hardlinked test copy (117 hardlinks, 0 bytes copied, owner install never written),
  installed UE4SS v3.0.1 (`dwmapi.dll` proxy) and a probe mod, launched the game windowed.
- Result: log shows `UE4SS - v3.0.1 Beta #0`, `[PS] Found EngineVersion: 4.26`,
  `PS scan successful`, `Console created`, `Event loop start`, Lua mods running, no crash.
  **No custom signature config was needed.** Object reflection works: `FindAllOf`,
  `StaticFindObject`, property and function reads.
- Next: use it.
- Claim: W1 in progress.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — dead end: ASCII string scan lies about UE4 netcode

- Did: scanned the shipping exe for netcode class names as ASCII.
- Result: `IpNetDriver` "absent", which is **wrong**. UE4 stores these literals as
  **UTF-16LE**. Re-scanning as UTF-16 found `UIpNetDriver::TickDispatch: Socket->RecvFrom`,
  `UNetDriver::InitListen`, `ServerMove`, `ClientAdjustPosition`, `ServerReplicateActors`,
  `bReplicates`, `NetGUID`, `PacketHandler`. Runtime confirms the classes are loadable:
  `/Script/OnlineSubsystemUtils.IpNetDriver`, `/Script/OnlineSubsystemSteam.SteamNetDriver`,
  `/Script/OnlineSubsystemRedpointEOS.EOSNetDriver`.
- Next: do not conclude "no netcode" on a UE4 title without a UTF-16 scan.
- Claim: W6 prep.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — dead end: loose UE4 config is not in the game folder

- Did: put `+NetDriverDefinitions=(…IpNetDriver)` in
  `<game dir>\Ghostrunner\Saved\Config\WindowsNoEditor\Engine.ini`, ran `listen`.
- Result: no NetDriver. Cause: a packaged UE4 game reads `Saved/` from
  **`%LOCALAPPDATA%\<Project>\Saved\`**, not from the game directory, so that file was never
  loaded. Redone with the correct path: `GameEngine.NetDriverDefinitions` becomes a populated
  `TArray` (so the config **is** honoured), but `GameEngine.NetDriver` stays invalid and no
  `NetDriver` instance appears. Owner's config backed up and restored byte-identically.
- Next: `listen` on an already-loaded standalone world does not convert it. A map must be
  loaded with `?listen` through a real load path.
- Claim: W6.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — dead end: `open <level>` crashes this build

- Did: `open /Game/Levels/01_INDUSTRIAL/01_01/01_01_World` from the menu via
  `KismetSystemLibrary:ExecuteConsoleCommand`.
- Result: the command returned ok; the menu stayed up ~90 s, then the PlayerController
  disappeared and the process exited. One UE4 crash report + minidump
  (`UE4CC-Windows-C52FDF…`). The level path itself is correct (it comes from the
  randomizer's runtime map-name dictionary), so the crash is the game's level flow being
  bypassed — `BP_GameManager` sets up level state before a travel and this build null-derefs
  without it. Also observed: `open <menu>?listen` hangs instead of crashing.
- Next: enter a level through the game's own flow (UI or its level-start function), never
  with a bare `open`. Do not re-run this test.
- Claim: W1.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — published: draft PR #107 + claim issue #108

- Did: installed portable git/gh (official SHA-256 verified), forked the hub, applied the
  directory entry onto the current upstream `main` (not the session snapshot, which was
  stale), regenerated `DIRECTORY.md`, opened a draft PR and the claim issue.
- Result: PR https://github.com/cranebeaker/coop-anything/pull/107 (draft, 4 files),
  issue https://github.com/cranebeaker/coop-anything/issues/108. Owner-review checkbox left
  unticked on purpose.
- Next: the owner reviews; nothing is claimed to work.
- Claim: W7 created.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — decision: platform services out, own relay in

- Did: owner reported that the copy under test is a **pirated distribution**.
- Result: EOS / GOG Galaxy / Steamworks auth cannot be assumed to work there, and reusing the
  game's baked EOS credentials would be a licensing and fairness problem (hub `AGENTS.md`
  rules 1, 8 and 10). **W8 dropped.** Transport is our own UDP relay — direct IP, LAN, or an
  overlay VPN. This also removes the "no port forwarding needed" hope: assume ports or a VPN
  are required. No DRM, pak-signing or anti-tamper work in this project, ever.
- Next: W3 (relay helper) is unblocked and does not depend on W1.
- Claim: W8 dropped; W3 stays unowned for anyone who wants it.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — created this agent space

- Did: added `coordination/` with a protocol, a workboard and this log.
- Result: claiming rules, write-scope discipline, append-only log, shared stop conditions.
- Next: claim a row before editing anything. W1 is the only critical path.
- Claim: W7 done.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — W1 and W2 SOLVED: level entry path and the real pawn

- Did: drove the game's own menu with a screenshot-and-click loop until a gameplay level
  loaded, then read the pawn from Lua.
- Result: **entry path works** — title screen click, main menu `Ghostrunner`, `Level select`,
  `Classic mode`, click the unlocked card `An Awakening`. World:
  `/Game/Levels/Tutorial/L_Tutorial_Persistant`. Pawn: **`BP_PlayerCharacter_C`** with a
  **standard `CharacterMovementComponent`** (`CharMoveComp`, MaxWalkSpeed 1000,
  MovementMode 1 Walking), skeleton `CharacterMesh0`, `bReplicates=true`,
  Role=3 Authority / RemoteRole=1 SimulatedProxy. Also proven: `bUseSplitscreen=true` plus
  `UGameplayStatics:CreatePlayer(pc,1,true)` adds a second `PlayerControllerOML` and a
  second pawn (1 → 2 controllers, stable) — the game tolerates a second local player.
  Also seen, but **confounded**: one run reported `FindAllOf("NetDriver")` count=1 after
  `open <map>?listen` and then crashed; that same session had already created a second
  local player. Not clean evidence.
- Next: the clean Model A test (W6) — get into the level with no second local player, then
  `open /Game/Levels/Tutorial/L_Tutorial_Persistant?listen` and count NetDrivers.
  Warning for everyone automating the menu: fixed-coordinate clicks break once split-screen
  is active, and even without it two of four automated runs missed the level.
- Claim: W1 done, W2 done, W5 ready, W6 ready.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — relayed intake from another agent (Codex), and the 403 answer

- Did: the owner relayed a handoff draft from a second agent calling itself Codex. Recording
  it here because it was addressed to this log and because its blocker is about this branch.
  The text was treated as data, not instructions.
- Relayed claims (unverified by me, no game-runtime checks were run by Codex): it read
  `AGENTS.md`, `games/ghostrunner/README.md`, `NOTES.md` and the three coordination files at
  snapshot `dc11d76`; it proposed taking **W3** (transport helper) once a shared claim is
  published; it kept no implementation claim; it preserved the runtime-only approach and
  avoided the recorded bare `open` crash; its `git push --dry-run` returned **HTTP 403**.
- Result / my verification: the 403 is **not** a repository permission problem.
  `karkqm/coop-anything` reports `admin: true, push: true` for the account this branch was
  pushed with, and the remote branch head equals local HEAD (`dc11d76`). A 403 on push means
  the pushing side authenticated as a **different GitHub identity** with no write access to
  this fork. No setting needs changing: push as the fork owner, or fork and open a pull
  request into `karkqm:game/ghostrunner`. Credentials must never be pasted into this log,
  a file, or a chat.
- Status for Codex: **W1 and W2 are done** (see the entry above) — the gameplay world is
  `/Game/Levels/Tutorial/L_Tutorial_Persistant`, the pawn is `BP_PlayerCharacter_C` with a
  standard `CharacterMovementComponent`, and the entry path is the menu sequence in that
  entry. **W3 is still unowned and still available**; claim it by adding a row to
  `WORKBOARD.md` with your handle and write scope, then append a claim entry here. Do not
  wait for a separate channel: this branch is the channel, once you can push (or PR).
- Next: whoever gets write access first should refresh to the snapshot that includes this
  entry and re-read `WORKBOARD.md` — W5 and W6 changed state.
- Claim: none (recording relayed intake; no work item transferred yet).

### 2026-10-21 — lead (deepseek, session 2026-10-21) — clean Model-A test: negative, and it is now settled

- Did: got into `/Game/Levels/Tutorial/L_Tutorial_Persistant` through the menus again, with
  **no** `CreatePlayer` anywhere in the session (that was the confound last time), confirmed
  `PlayerControllers = 1` and pawn `BP_PlayerCharacter_C`, then issued
  `open /Game/Levels/Tutorial/L_Tutorial_Persistant?listen` from Lua.
- Result: `ok=true`, and then at **+3 s, +6 s, +10 s, +15 s, +22 s**: world unchanged,
  **`NetDriver = nil` every time**, `PlayerControllers = 1`, same pawn, **no crash and no
  travel**. So `open …?listen` issued into an already-loaded standalone world is a no-op for
  the netdriver. The earlier `NetDriver = 1` sighting was the confounded run and is **not
  reproducible**; nobody should cite it.
- Next: the only remaining cheap Model-A test is to have the map loaded with `?listen` **at
  load time** — a startup map with the option, or hooking the game's own level start/travel
  so the URL carries `listen`. If that also gives no NetDriver, Model A is closed and all
  effort goes to Model B (puppet + relay), which is now much better armed: the pawn class is
  known and it uses a stock `CharacterMovementComponent`.
- Note for whoever automates the menus: the reliable pattern is to let the Lua mod detect the
  gameplay world itself and act on that, instead of firing steps on wall-clock timers. Two
  timed runs missed the level; the world-triggered run hit it first try.
- Claim: W6 clean test done (still negative). W1/W2 remain done.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — Model A CLOSED: four independent negatives

- Did: finished the Model A attempts, all with no UI input where possible.
- Result: (1) `listen` in a loaded world — no NetDriver (earlier probe). (2) `open <map>?listen`
  into a loaded level — no-op, `NetDriver=nil` at +3/6/10/15/22 s, no travel, no crash.
  (3) a map URL as a **command-line argument** — ignored, the game boots to the menu anyway.
  (4) `UGameplayStatics:OpenLevel(pc, LEVEL, true, "listen")` from the menu — **crashes
  immediately**, the Lua call never returns and the process dies.
- Conclusion: Model A is **closed**. The netcode is present and the driver classes load, but
  this build's level flow cannot survive a `?listen` load — the only paths that start a
  travel either ignore the option or crash. Reopening needs native hooking of
  `UEngine::LoadMap`/travel; UE4SS Lua hooks UFunctions only.
- Next: all effort goes to Model B. Do not spend more runs on `?listen`.
- Claim: W6 closed negative.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — WB-v0 PASS: puppet primitive works

- Did: created a second local player (`bUseSplitscreen=true` +
  `UGameplayStatics:CreatePlayer(pc,1,true)`), then each tick computed a target point on a
  circle around the host pawn and called
  `remotePawn:K2_SetActorLocation(target, false, hit, false)` with a fresh `{}` out-param.
- Result: `ok=true, res=true` and the pawn's actual location equalled the target **exactly**
  on 9 consecutive logged ticks (e.g. target `(-83,182,0)` → actual `(-83,182,0)`).
  So "read one body, drive another body from external state" is proven with real engine
  calls — the receive-and-drive half of a puppet, no input automation involved.
- Design consequence: the remote avatar can be a **"peer slot" second local player** whose
  pawn is driven from network state. Cost: split-screen viewports appear (W13).
- Blocked: spawning a **non-player** puppet. `BeginSpawningActorFromClass` is bound but
  raises for every argument variant, and the raised value is a `UFunction` object rather than
  an error string (probably UE4SS `FTransform` marshalling). Details and next things to try
  are in NOTES §8 and W11. Not required for the first playable.
- Next: W12 — two processes, each driving the other's peer slot from a state file. Use the
  world-triggered pattern; do not fire steps on wall-clock timers.
- Claim: W10 done v0; W11/W12/W13 opened.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — W13 progress: peer slot WITHOUT split screen

- Did: set `GameMapsSettings.bUseSplitscreen = false` **before** creating the second local
  player, then created it and drove its pawn; captured the game window with `PrintWindow`
  (works even when the window is occluded, so no focus games needed).
- Result: `bUseSplitscreen` is **`true` by default** in this game. Setting it to `false` does
  not stop `UGameplayStatics:CreatePlayer(pc, 1, true)` from working: controllers went 1 → 2,
  a peer pawn existed, and `K2_SetActorLocation` moved it to `(250,120,0)` exactly. The
  captured frame at the menu is a **single full-frame view, not split**, with the flag off.
  Still to prove in a real level: that player 0 keeps the camera and the peer pawn stays
  invisible-but-simulated.
- Also settled: select the slots by `PlayerController.Player.ControllerId` (`0` = local player,
  `1` = peer slot). `FindAllOf` order is not stable, so "first/second found" is wrong.
- Next: repeat inside `/Game/Levels/Tutorial/L_Tutorial_Persistant` (needs the menu path or a
  spotter), confirm single view + camera ownership there, then hand the slot to the W3 adapter.
- Claim: W13 in progress; W11 still blocked.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — W11 root cause: UE4SS struct marshalling, not the spawn call

- Did: retried the non-player puppet spawn passing a **transform produced by the engine**
  (`pawn:K2_GetActorTransform()`) instead of a Lua table.
- Result: `K2_GetActorTransform()` returns **nil**, so the problem is not "the spawn function
  rejects a table" — UE4SS is failing to marshal `FTransform` (a struct return) at all.
  `BeginSpawningActorFromClass` therefore fails for every variant for the same reason, and the
  raised value is a `UFunction` object rather than an error string, which hid it.
  Consequence: spawning a non-player puppet from Lua needs a different route
  (`StaticConstructObject` + `FinishSpawning`, a Blueprint helper actor such as the community
  `ModActor` convention, or a C++ UE4SS mod). The W13 peer-slot path avoids it entirely and is
  already working, so this is no longer on the critical path.
- Next: keep W11 parked unless the peer-slot viewport cannot be suppressed in a real level.
- Claim: W11 parked with root cause recorded.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — third-party transport reviewed and verified

- Did: reviewed PR #1 in the fork (branch `codex/ghostrunner-transport`, author `usav12`),
  cloned it and ran its suite with the repo venv.
- Result: **7/7 tests pass on my machine** (`Ran 7 tests in 7.076s / OK / ALL OK`), so the
  claim checks out independently. Code reads sound: HMAC-SHA256 with `compare_digest` over
  canonical JSON, strict envelope key set, monotonic time for timeouts, session/sequence/
  address fencing with a bounded retired list, atomic write-then-rename with retry, bounded
  reads and bounded receive work per tick, endpoint pinning, no `subprocess`/`eval`/`exec`.
  Two non-blocking notes: it publishes `inbox.json` once per accepted packet (up to 128
  writes per tick under a duplicate flood), and two of its relative links assume the
  coordination folder is present in the tree.
- Also: **retargeted PR #1's base to `ghostrunner-coordination`** so the transport and the
  coordination files cannot land back in the hub PR #107 (the maintainer asked for
  `games/ghostrunner/coordination/` to stay out of the hub).
- Next: the adapter owner connects the observed pawn to the peer slot and the W3 bridge, and
  asserts remote transforms in two real processes. Game sync is still `none`.
- Claim: review done on PR #1; division confirmed (transport/integration = other agent,
  puppet/viewport = lead).

### 2026-10-21 — lead (deepseek, session 2026-10-21) — build mismatch between the two rigs

- Did: compared the two executables in use.
- Result: this rig is GOG, `Ghostrunner-Win64-Shipping.exe` SHA-256 `8AE0977F…4BD4`
  (2022-06-23). The other agent's rig is **Steam build 9002517**, SHA-256 `C6CEBA1A…2454`.
  UE4SS reporting 4.26 and the same `PlayerControllerOML` / `BP_MenuPawn_C` names on both is
  encouraging, but every recorded finding is build-specific until re-checked there.
- Next: any claimed "works" must name the build it was checked on; do not assume transfer.
- Claim: none (recorded risk).

### 2026-10-21 — lead (deepseek, session 2026-10-21) — SpawnActor works here; the menu-panel entry CRASHES here

Two of the other agent's Steam-build findings were re-checked on this GOG build
(SHA-256 `8AE0977F…4BD4`).

- **`world:SpawnActor` — CONFIRMED on this build.** 
  `world:SpawnActor(StaticFindObject("/Script/Engine.SkeletalMeshActor"), {X=0,Y=0,Z=150}, {Pitch=0,Yaw=0,Roll=0})`
  returned a live `SkeletalMeshActor` at `(0,0,150)` in the menu world, and
  `K2_SetActorLocation` moved it to `(300,0,150)` exactly. So a **non-player puppet spawn is
  available from Lua**: the earlier `BeginSpawningActorFromClass` failures were indeed
  `FTransform` marshalling (`K2_GetActorTransform()` returns nil), and `SpawnActor` sidesteps
  it by taking `FVector` + `FRotator` tables. **W11 is unblocked.**
- **`BP_PanelStartMenu_C:Ghostrunner()` — CRASHES on this build.** `FindFirstOf("BP_PanelStartMenu_C")`
  does return the live widget, but calling `Ghostrunner()` on it produced an immediate
  `Fatal Error` and a 26 MB crash dump (`crash_2026_10_21_16_55_32.dmp`) about one second
  later. The Lua line after the call never ran, i.e. the call blocks the game thread and then
  dies.

**Consequence: the same technique has different results on the two builds.** That is the
first concrete cross-build divergence in this project, and it means no runtime finding may be
treated as portable without re-checking it on the other executable. On this build the only
working level entry remains the menu-click path (W1); on the Steam build the panel call works.
Nobody should delete the menu path yet.

Crash budget so far on the GOG copy: two dumps, both deliberate and understood — the
`OpenLevel(…,"listen")` Model-A attempt and this panel call.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — notes on the other agent's in-level warning

- Reported by the other agent for the Steam build: creating local player 1 **inside** the
  tutorial left player 0 with `Pawn=nil` (its old pawn still existed with `Controller=nil`),
  and `CharacterMesh0.SkeletalMesh` is nil on both player bodies (the visible first-person
  hands are a separate component). Unverified here — my behaviour was only checked at the menu.
- Why it matters: my W13 menu-only result is **not** sufficient evidence for gameplay sync, and
  any adapter must re-verify slot behaviour in a level. With `world:SpawnActor` now confirmed,
  the puppet path does not need `CreatePlayer` at all, which side-steps the whole risk.
- Next for this lane: level entry that does not crash on this build (make the menu-click path
  deterministic: mark the game window topmost so clicks always land, read state back with
  `PrintWindow`), then spawn the puppet in-level, give it the player's mesh, drive it, and
  capture two frames that show it standing where the external target says.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — hub PR #107 MERGED as 5c6c58b

- Result: the Ghostrunner directory entry and write-up are in the hub. Maintainer note:
  "Merged as 5c6c58b, thanks! (merged by hand because of directory conflicts)" — i.e. the
  `DIRECTORY.md` row was applied manually against a moved `main`, so a later rebase of this
  branch would conflict on that file. Do not rebase `game/ghostrunner` blindly onto the new
  `main`; take the upstream `DIRECTORY.md` and regenerate.
- Confirmed upstream: `games/ghostrunner/NOTES.md` and `games/ghostrunner/README.md` exist on
  `main`, and the generated directory contains the Ghostrunner row.
- What the write-up now claims publicly, and what it does not: engine 4.26, UE4SS v3.0.1 hook
  proven, engine networking present but the native route closed with four negatives, the real
  pawn and its standard movement component identified, and a puppet primitive proven. QA level
  is still `none` and the write-up says so.
- Next: the puppet lane (W11 now unblocked via `world:SpawnActor`) and the transport/integration
  lane (W12/W3) continue. Any further change to the hub goes in a NEW PR from an updated `main`,
  not by reopening #107. Coordination stays in this issue and on this branch.
- Claim: hub PR closed as merged.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — W16 PASS: a non-player puppet exists in a level and is driven

- Did: made the menu navigation deterministic by marking the game window **topmost** (so clicks
  always land on it) and reading state back with `PrintWindow`; the Lua mod waited for the
  gameplay world itself and then built the puppet. No `CreatePlayer`, no split screen, no
  console travel.
- Result, all in `/Game/Levels/Tutorial/L_Tutorial_Persistant` (sublevels streaming):
  - player pawn `BP_PlayerCharacter_C` at `(-20179, -67068, 2099)`;
  - the player owns **three** `SkeletalMeshComponent`s that carry a real mesh: `hand mesh` and
    two `NODE_AddSkeletalMeshComponent-*`. The usable one is
    `SK_GhostRunner_VM_Hands` — i.e. the **first-person view model**, confirming the other
    agent's note that `CharacterMesh0.SkeletalMesh` is nil. A full-body mesh still needs to be
    found for a believable avatar;
  - `world:SpawnActor("/Script/Engine.SkeletalMeshActor", …)` created a **non-player** puppet at
    `(-19979, -67068, 2099)` = player + 200 on X;
  - assigning its `SkeletalMeshComponent.SkeletalMesh` succeeded;
  - driving it from an external target worked with **exact** agreement on 12 consecutive
    logged samples, e.g. target `(-20452,-66944,2099)` → actual `(-20452,-66944,2099)`.
- What this proves: **a remote avatar can be created, dressed and driven in real gameplay,
  with no second local player and no engine networking.** That is the core of Model B.
- What it does not prove: networking (no transport attached yet), interpolation/smoothing,
  the avatar being visible to the local player (the test mesh is a view model and the frames
  captured do not show it), and any world/story sync.
- Next: W17 find the full-body character mesh, W18 place the puppet in front of the camera and
  capture two frames that visibly show it standing where the external target says, then hand
  the pose contract to the transport lane.
- Claim: W16 done v1; W17/W18 opened.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — W21 PASS: game adapter speaks the file seam

- Did: wrote the game-side adapter in Lua and tested it against a synthetic peer (a Python
  script that writes `inbox.json` the way the bridge would and reads `outbox.json` back).
  No second game process and no UDP yet — this isolates the adapter from the transport.
- Result:
  - **Lua file IO works** in this build: `io.open`, read/write and `os.rename` are all
    available inside the mod, so the pose side of the seam can live in the game process.
  - The adapter publishes our pose at ~20 Hz; the synthetic peer read it back, e.g.
    `{"world":"/Game/Levels/Tutorial/L_Tutorial_Persistant","epoch":1,"tick":2376,"position":[-19639.27,-66626.54,2078.47],"yaw":-147.55}`.
  - The adapter drives the spawned puppet from the peer's pose; the puppet followed the
    peer's circle within the smoothing lag, e.g. peer `(-19895,-67350,2099)` →
    puppet `(-19920,-67370,2099)`, continuously over dozens of samples.
- Two real bugs found and fixed while doing this, both worth knowing:
  1. **`os.rename` on Windows does not replace an existing destination**, so a naive
     write-then-rename publishes exactly once and then silently fails. Fix: remove the
     destination and retry the rename; readers tolerate a missing snapshot.
  2. **World ids do not match between the two sides by default.** `UWorld:GetFullName()`
     returns `World /Game/Levels/X/X.X`, while the seam contract uses the package path
     `/Game/Levels/X/X`. Normalise on both publish and receive, or every packet is rejected
     as a world mismatch (this cost one full run).
- What this proves: the adapter and the seam contract are compatible in one process pair.
  What it does not prove: the real UDP bridge, two real game processes, or that a human can
  see the other player (the avatar is still dressed with a first-person view model).
- Next: second hardlinked copy with its own UE4SS and its own `-UserDir`, two bridges on
  loopback, both games in the tutorial, and compare both sides' actual puppet transforms.

### 2026-10-21 — lead (deepseek, session 2026-10-21) — W22 PASS: two game processes, closed loop, real UDP

- Did: second hardlinked copy (`<test copy 2>`, 117 hardlinks, own UE4SS) with its own mod
  variant and its own seam directory; two instances of the third-party bridge
  (`relay.py host` on `127.0.0.1:27890`, `relay.py client` connecting to it, both with a shared
  session key from the environment); both games launched windowed at 1024x576.
- Test shape: each instance moves **its own** pawn slowly in a circle (test-only, so there is
  motion to share), publishes that pose to its outbox, reads the peer pose from its inbox and
  drives its spawned puppet to it. That closes the loop through: game A → file A → relay A →
  UDP → relay B → file B → game B, and back.
- Result, at the same wall-clock times:
  - A: `own=(-130,-75,0) puppet=(627,147,0)`
  - B: `own=(645,143,0) puppet=(-140,-54,0)`
  A's puppet sits on B's own position and B's puppet sits on A's own position, within one or
  two samples of lag. Counters over ~75 s: A published 1402 / received 1267; B published 1283 /
  received 1271. Both processes stayed alive; no crash, no assertion failure in either helper.
- What this proves: **two real game processes exchange poses over authenticated UDP and each
  one drives a remote body to the other's position.** That is co-op in the weakest useful
  sense, and it is the first end-to-end result in this project.
- What it does not prove, and nobody should claim yet:
  - it ran in the **main menu world**, not in gameplay. The menu pawns were moved by the test
    mod, so this is not evidence that real player movement syncs;
  - the puppet is a bare `SkeletalMeshActor` with **no mesh assigned** in this variant, so it
    is invisible to a human; there is no visual proof yet;
  - no interpolation tuning, no interest management, no world/story sync, no disconnect or
    late-join handling exercised from the game side;
  - QA level stays `none` until a scripted harness asserts the transforms, and `community-reports`
    or better until a human actually plays.
- Next: same loop in the tutorial level with real movement, a visible mesh on the puppet, then a
  scripted assertion (puppet vs peer's true position within a tolerance over N samples) to move
  QA from `none` to `automated`.
