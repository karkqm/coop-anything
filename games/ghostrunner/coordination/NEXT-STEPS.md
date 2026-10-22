# Ghostrunner co-op — what is done, and what to do next

Written 2026-10-21 at the end of the working session. Read this first if you pick the project up.

## State: a working two-process prototype, packaged

- **Sync works.** Two real Ghostrunner processes, one level, real movement: the remote avatar
  tracks the partner's pose (measured error p95 0.0 against the received pose; the visible lag is
  delivery time).
- **Tested under impairment.** `bad_wifi` (2% loss, 35±25 ms) and `hell` (8% loss with bursts,
  200±150 ms, reorder 10%, dup 5%, 512 kbit/s) both PASS, and a 4 s total outage hides both
  avatars and recovers without restarting either game.
- **Packaged.** `ghostrunner-coop-kit-v0.1.zip` (33 421 bytes, SHA-256
  `CA2B9E030858D564C9D482A75FF4AC4AAD47738F11529755CD7056E57B2327C4`): installers with `.cmd`
  wrappers, preflight check, network check, sync verifier, outage test, Russian README.
- **Avatar** is a temporary enemy humanoid with borrowed animation clips and the player's katana;
  not Jack's body. Story, enemies, checkpoints and cutscenes are **not** synchronized — each player
  plays their own copy of the level.
- **Not verified:** two physical PCs. Deferred by the owner on 2026-10-21 with "we will do the
  hardware check later, obviously it will work". Everything below the second machine is already
  exercised: real interface (not loopback), through the chaos proxy, plus install/preflight.

### The deferred two-machine checklist (do this first when hardware exists)

1. `python netcheck.py host --port 27890` on one PC, `client --peer <ip>` on the other → `PATH OK`.
2. `install.cmd -GameDir <game> -Pair A|B -NetDir <dir>` on both.
3. `run.cmd -Role host` / `run.cmd -Role client -Peer <ip> -Key <key>`.
4. Both enter the same level, then `python verify_sync.py --a-dir <dir> --b-dir <dir>`.
5. Expected: same PASS as single-machine, with bigger transport numbers (latency).

## What to do next — options in priority order

### 1. Ship it as a real project (highest value, ~half a session)

Hub rule 7 says a game's code belongs in its own repo, linked from the hub. Right now the runtime
lives in a fork branch and the fork PR #1, which is not a stable home.

- Create a public repo for the mod (kit + runtime + bridge, with attribution to the runtime author
  `usav12`), MIT or ask the owner which license.
- Tag `v0.1`, attach the kit zip as a release artifact with its SHA-256.
- Then open hub PR #2: change the Ghostrunner directory entry from a bare gap to a project entry
  (`status: prototype`, `qa: automated` for pose sync, `networking: direct-ip | vpn-needed`), link
  the repo, and update `games/ghostrunner/README.md` with the verified results and the honest
  "not a campaign co-op" scope.
- Playbook contribution: two techniques cost real time here and are not in the playbook —
  (a) UE4 config lives under `%LOCALAPPDATA%`, not the game dir; (b) Windows Lua `os.rename`
  cannot replace an existing file, which breaks naive write-then-rename seam publication.
  Also worth adding: "verify a UE4 title's netcode with a UTF-16 scan".

### 2. Close the gameplay gap (the actual product question)

Today this is "you can see each other", not "you play together". Decide the target, then build:

- **Enemies/damage**: host authority. The runtime already publishes a pose; it would need to
  publish enemy state, and the host would arbitrate hits. Hard: Ghostrunner is one-hit-kill, so
  arbitration must be fast and authoritative or it feels broken.
- **Checkpoints and level flow**: the game's own level manager is single-player; this is the same
  wall the native-replication route hit. Probably host-driven with a barrier on transitions.
- **Story/objectives**: out of scope until the two above work.
- Cheapest useful next increment: **shared enemy health/death for one enemy class** as a spike, to
  learn the cost before promising anything.

### 3. Make the avatar honest (small, high perceived quality)

The remote body is an enemy humanoid. Find the player's third-person mesh and its animation set,
or add a marker/nameplate so a player can tell "that is my friend" at a glance. Cheap version:
attach a small light or a nameplate widget above the avatar.

### 4. Usability for real players (small)

Host/join from in-game instead of two terminals: read a small `coop.cfg` written by the launcher,
show connection status on screen, and print the session key somewhere visible. Today the key is
copied from a console window, which is a poor experience for a non-technical friend.

### 5. Robustness (medium, testable without a second PC)

Late join (start B after A is already in a level), rejoin after a bridge restart, and world
mismatch (one in a level, one in the menu → avatar must stay hidden). All three are cheap to test
with the existing rig and would remove surprises in the first real two-machine session.

## Open questions for the owner

1. Which license for the mod repo, and can the other agent's runtime be published there with
   attribution? (It is their code; I did not write it.)
2. Is the target "see each other and race" or "fight the same enemies"? That decides whether
   option 2 is next or never.
3. Should the mod repo be public from the start, or private until it is less raw?

## Lessons worth keeping (also in LOG.md)

- Test the layer below before blaming a layer above: I concluded "firewall" when the real cause was
  the bridge's client binding `127.0.0.1`.
- A verifier that lies is worse than no verifier: stale QA command ids and a single movement
  direction both produced false FAILs before the sync was touched.
- Never drive the UI by wall-clock timers: act on game state. Never send keystrokes to a window you
  cannot prove is focused.

## Auto-entry: exhausted, a decision is needed (2026-10-22)

Every non-input path to load a level on the GOG build has now been tried and failed:

| Approach | Outcome |
|---|---|
| positional map argument | ignored, boots to MainMenu |
| `-map=/Game/...` | ignored |
| `-ExecCmds="open /Game/..."` | ignored |
| `APlayerController:ConsoleCommand` | not callable from Lua |
| `KismetSystemLibrary:ExecuteConsoleCommand("open ...")` | runs, world unchanged |
| `KismetSystemLibrary:ExecuteConsoleCommand("travel ...")` | runs, world unchanged |
| `UWorld:ServerTravel` | errors |
| `APlayerController:ClientTravel` | errors |
| `UGameplayStatics:OpenLevel` | crashes the game |
| menu panel functions | only `RefreshSubMenuPosition` exists on this build |
| function lookup by 24 candidate names | no hits |
| `ButtonOML:TryNavigate` | works only as UI navigation (needs an argument, returns the target); does not load a level |

The level entry is routed exclusively through the game's own UI flow. Two realistic options remain:

1. **UI click emulation** - the widget tree is readable and `ButtonOML` has `TryNavigate`; a chain
   of button activations could reach "Continue". Uncertain and slow, and it still has to make the
   game's Blueprint flow call the level loading.
2. **OS-level click on the dedicated test-copy window only** - reliable, but needs the owner's
   explicit permission (it takes focus briefly). The owner has previously asked not to inject input
   into the game; this was asked again and no answer has arrived yet.
3. **Owner presses Continue once per test session** - zero risk, costs the owner ~5 seconds.

Recommendation: option 3 for now (it unblocks everything immediately), option 2 if the owner agrees
and long unattended runs become necessary.

## Owner decisions 2026-10-22 — the plan from here

Target: **fight the same enemies, with every dynamic object in sync.** The host is the single
authority for the world; the client shows the host's world and sends its own actions as claims.
Synthetic clicks on the test-copy window are allowed, so tests can run without a human.
Discussion lives in this fork (issues enabled); nothing goes upstream for now.

| Order | Item | Why it is in this place |
|---|---|---|
| 1 | W39 unattended level entry (click) | every test below needs a level |
| 2 | W40 real sword kill | closes the death path already built |
| 3 | W41 dynamic-object inventory | decides what "full sync" means in numbers |
| 4 | W42 enemy mirror on the client | one authority for enemy position, state, attacks |
| 5 | W43 host enemies target the remote player | without it only one player is in danger |
| 6 | projectiles, doors, switches, platforms, checkpoints (from W41) | one class at a time, each with a test |
| 7 | remote katana animation (PR #1 lane) and Jack's body (W17) | looks, after the world is shared |
| 8 | two-PC test | real latency |
