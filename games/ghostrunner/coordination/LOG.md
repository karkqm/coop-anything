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

### 2026-10-21 — Codex — claim W3: file seam and independent UDP bridge

- Did: refreshed to `bc4dbee`; read the W1/W2 completion and clean negative W6 result, networking playbooks, and PoppyCoop Phase 5/6. Retested direct push: HTTP 403 for the connected identity. Created a writable contributor fork instead; this change is delivered as a PR against `karkqm:game/ghostrunner`.
- Observed: W3 is unowned at this snapshot. W1/W2 are reported done by lead; Codex has performed no game-runtime checks. No existing game files, test rigs, NOTES.md, or game README will be edited for W3.
- Scope: `tools/ghostrunner_transport/`, this W3 row, and appended LOG entries. Implement a documented atomic file seam and a two-player UDP bridge with bounded packets, authenticated messages, session/sequence fencing, keep-alive/timeout, and game-free subprocess checks through the existing chaos tool. Python stdlib is sufficient; no platform SDK or ctypes is needed for plain UDP.
- Next for lead: the adapter will write `outbox.json` and read `inbox.json` in a private per-instance directory. Contract and commands will be in `tools/ghostrunner_transport/README.md`. Continue W5/W6 independently; no game launches or resource-heavy tests are planned on this lane.
- Claim: W3 in_progress. No other row is transferred or edited.

### 2026-10-21 — Codex — W3 helper delivered; ready for W5 adapter integration

- Did: implemented `tools/ghostrunner_transport/relay.py` (Python 3.8+ stdlib), documented its file/wire contract in that folder's README, and ran `python -I tools/ghostrunner_transport/run_tests.py` on Windows. Delivery: draft PR https://github.com/karkqm/coop-anything/pull/1 against this game's branch. No game process was launched, no game files/config/saves changed, and no NOTES.md/game README edits were made.
- Observed: **7 tests passed, ALL OK**, including separate helper subprocesses exchanging distinct poses through separate file directories; client crash/restart; host crash/restart; stale, malformed, oversized and nonfinite outboxes; unauthenticated/tampered datagrams; sequence/address/retired-session fencing; and 1000 seeded malformed packets. Chaos used seed 407, 20% base loss, 80 +/- 60 ms one-way delay, 30% reorder, 25% duplication, 5% corruption, and a 1.6-second blackout. Pre-blackout counters in the passing run: c2s 89 seen/21 dropped/15 duplicated; s2c 86 seen/23 dropped/18 duplicated. Both inboxes cleared on timeout and converged after healing. Local artifacts are ignored under `local/ghostrunner-transport-tests/`.
- Fixes found by testing: Windows `recvfrom` with a small buffer raises WSAEMSGSIZE on oversized UDP; receive the full UDP maximum and then reject by the 1200-byte protocol limit. Windows readers can temporarily prevent atomic replacement; retry pending inbox updates on subsequent ticks, including disconnect notifications.
- Handoff to W5 owner: per instance, atomically publish a UTF-8 object in `outbox.json`; consume `inbox.json` only if `connected`, non-null `state`, locally fresh `received_at`, and a compatible application world/epoch. The helper sends newest full snapshots, not reliable one-off events. Default 20 Hz, peer timeout 3 s, outbox freshness 2 s. Each pair uses its own environment-provided secret, separate directories, and independent UDP; no platform SDK/credentials. Full commands and constraints are in the tool README.
- Unknown: UE4SS adapter integration, second-body behavior, interpolation, authority validation, checkpoints, story sync, and two-real-game-client QA. The transport tests establish helper behavior only; Ghostrunner QA remains `none`.
- Next: review/merge PR #1 into the game branch, connect the W5 adapter to the documented seam, and run a two-real-client pose check before making any gameplay claim. NOTES.md/README.md consolidation stays with lead.
- Claim: W3 done for the helper scope; W5 and W6 remain with their existing owners/statuses.
