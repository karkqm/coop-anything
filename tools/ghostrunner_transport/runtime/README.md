# Ghostrunner runtime avatar synchronization

In-progress runtime-only UE4SS 3.0.1 adapter for the independent UDP bridge. Tested
with two real Steam build 9002517 processes (UE 4.26), executable SHA-256
`C6CEBA1A667A7859606CF3922B51ACE6F0032A2637718C2502D6B433A8202454`.
Coordination now takes place in [claim issue #108](https://github.com/cranebeaker/coop-anything/issues/108).

The adapter reads the actual local player at index zero, exports its transform,
velocity, capsule height, weapon and melee animation state, and drives a separate
native `Engine.Character` on the other client. It does not call `CreatePlayer`,
split the viewport, or change the owner's original install/profile. All engine
calls execute on the game thread. Snapshot contents never execute as commands.

The remote body currently uses the game's loaded `Enemy_Pistol_01` humanoid as a
temporary avatar. Compatible stock idle/walk/run/air/attack animations play on its
mesh. The player's katana blade and handle are separate runtime actors attached to
the actual `hand_r` bone; their positions follow evaluated animation poses. This is
a proxy of the player's movement/action state, not an exact Jack full-body animation
set. No game assets are distributed.

## Files and manual integration

Copy `main.lua`, `json.lua`, `appearance.lua`, and optionally `qa.lua` into a private
test copy's `Mods/GhostrunnerSync/Scripts/` folder. Copy `config.example.lua` to
`config.lua` there and set `directory` to that instance's private transport folder.
Enable `GhostrunnerSync : 1` in that copy's `Mods/mods.txt`. Keep `qa=false` for normal
play. Start the Python bridge for that folder as described in the parent README,
then enter the same level through the game's own menus on both clients.

The Lua producer publishes a complete `outbox.next.json` by rename. The Python
bridge atomically adopts it as `outbox.json`, solving Windows Lua's inability to
rename over an existing destination. `inbox.json` remains owned by the bridge.
`runtime.json` is diagnostic data: readers retry partial writes and require freshness.

The adapter hides both the remote body and its weapon when the peer is stale,
disconnected, loading, or in a different world. It uses the sender's actual capsule
height to position the visual mesh. It does not synchronize enemy simulation,
damage, pickups, doors, checkpoints, saves or story state.

## Checks actually run

`verify_pair.py` checks two **already running real game PIDs**, in different test
copies and file directories, with opt-in local QA bots. The fixed tutorial fixture
is validated inside each game with a floor trace and a capsule query using that
player's measured radius/half-height. Each source pose and rotation is compared to
the other process's actual body transform. Tests also check actual animation time,
bone observations, weapon attachment and position relative to the animated hand,
wrong-mode/scorer negative controls, a disabled-receive mutation, impaired UDP,
five-second blackout and recovery without restarting the games.

```powershell
python -I tools/ghostrunner_transport/runtime/verify_pair.py --a-dir <net-A> --b-dir <net-B> --pid-a <PID-A> --pid-b <PID-B> --chaos-info <chaos-info.json> --output local/pair-check
python -I tools/ghostrunner_transport/runtime/verify_motion.py --a-dir <net-A> --b-dir <net-B> --pid-a <PID-A> --pid-b <PID-B> --output local/motion-check
```

The passing pair run reached 9 gates, including the floor/capsule fixture checks;
its 10% loss, 80 +/- 40 ms delay/reorder profile recorded actual dropped packets.
The motion check now initializes that same fixture and exercises **each source**
through real `AddMovementInput` and the game's melee callback. The passing run moved
A 1173 cm and B 631 cm, with respectively 9 and 5 distinct received moving snapshots
matching recorded real source poses/velocities. Animation clocks and evaluated feet
advanced, both katana parts stayed on the animated hand, and both sources' melee
actions reached the observer animation. Matching uses the source snapshot actually
received, since the source's newer state can differ during transport delay.

Game-window captures from both clients were inspected: a complete humanoid and its
katana are visible, with posed arms rather than a horizontal bind pose. The temporary
avatar still uses the enemy's stock poses, including its aimed idle; a dedicated Jack
body and sword animations are future work. Integration is manual; no standalone
installer or launcher is provided yet.

The helper suite now has 8 passing tests, including Lua staged-file adoption.
These checks prove the described avatar prototype, not campaign co-op or
Steam/GOG interoperability. The GOG rig and its separate evidence belong to the lead.
