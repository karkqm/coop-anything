# Ghostrunner W3: file seam and UDP bridge

A small, two-player snapshot transport for the runtime-only Ghostrunner prototype.
Python 3.8+ and the standard library are sufficient. The helper neither loads the game
nor uses Steam, EOS, GOG, or game credentials. It does not install anything.

```text
game A -> A/outbox.json -> helper A == UDP == helper B -> B/inbox.json -> game B
game A <- A/inbox.json  <- helper A == UDP == helper B <- B/outbox.json <- game B
```

The W3 helper is implemented and checked without game clients. A separate
[runtime adapter prototype](runtime/README.md) now has two-real-client avatar checks
on the Steam build. Campaign authority, checkpoint/respawn behavior, and story
synchronization remain separate work; playable campaign co-op is not claimed.

## Run two helpers

Use a distinct private directory for each game instance and exactly one helper per
directory. Keep these directories outside tracked source (the hub ignores `local/`).
Run the commands from the repository root. `python` below means a Python 3.8+ executable.

In the host terminal, generate a fresh session secret and start the host:

```powershell
$env:GHOSTRUNNER_COOP_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python -I tools/ghostrunner_transport/relay.py host --directory local/net-A --bind 127.0.0.1:27890
```

In a second terminal, set the **same** secret and start the client:

```powershell
$env:GHOSTRUNNER_COOP_KEY = '<same session secret as the host>'
python -I tools/ghostrunner_transport/relay.py client --directory local/net-B --connect 127.0.0.1:27890
```

The secret is read from the environment, never printed or put in a command-line
argument by the helper. `--key-env NAME` selects a different environment variable.
Readiness is printed once to stdout and written to `<directory>/ready.json`:

```json
{"role":"host","bind":["127.0.0.1",27890],"v":1}
```

For another PC on a LAN or an existing VPN, bind the host to `0.0.0.0:27890` and point
the client at the host's LAN/VPN IPv4 address, adding `--bind 0.0.0.0:0` to the client
command as well. Its default loopback bind cannot reach a non-loopback peer. This is direct UDP, not a hosted relay
or NAT traversal service. No firewall, router, VPN, game install, or save configuration
is changed automatically. Packets are authenticated, not encrypted; use a trusted
private link or an encrypted VPN. Only two players are supported. A holder of the same
secret can replace the active client, so do not reuse a secret across separate pairs.

`--bind 127.0.0.1:0` chooses a free local port (the default). `--hz` defaults to 20
(allowed range 1–120), `--timeout` to 3 seconds, and `--state-age` to 2 seconds.
`--seconds N` stops after N seconds; otherwise use Ctrl+C. `stats.json` is written
on graceful exit; process termination cannot guarantee that final file.

## Contract for the game-adapter owner

The adapter owns **outbox.json**. Publish a complete UTF-8 JSON object regularly
(suggested: 20 Hz); write a temporary file, close it, then atomically rename it over
the outbox. Retry a rename on the next game tick if Windows reports a sharing error.
Do not rewrite the visible outbox in place. Use a temporary name other than the
helper's reserved `<filename>.tmp` names.

Windows Lua producers can instead rename the complete file to `outbox.next.json`.
Only publish when that staging name is absent. The helper atomically replaces
`outbox.json` from the staging file before reading; no shell process or non-atomic
delete/replace is needed inside the game. The ordinary outbox contract still works.

Example payload, **not an implemented game schema**:

```json
{"world":"/Game/Levels/Tutorial/L_Tutorial_Persistant","epoch":1,"tick":123,"position":[100,42,99],"yaw":90}
```

The bridge treats the object as opaque data. It accepts at most 1200 bytes from the
outbox; the encoded **whole UDP packet**, including its envelope and signature, must
also fit 1200 bytes. Keeping payloads below 800 ASCII bytes leaves room for the envelope.
Measure the actual encoded size if near the limit; Unicode is escaped on the wire.
Missing, stale, malformed, non-object, nonfinite, or oversize snapshots are sent as
`null`. A fresh unchanged snapshot is still sent periodically, so a lost final movement
update is eventually repaired. If the game stops publishing, its last pose is not
resent indefinitely: the file-age limit clears it while the helpers stay connected.

The helper owns **inbox.json**, using temporary-file replacement:

```json
{"v":1,"connected":true,"session":"0123456789abcdef0123456789abcdef","seq":12,"received_at":1792540000.0,"state":{"tick":123,"position":[100,42,99]}}
```

- `connected` means a valid, authenticated peer packet arrived within the timeout.
  It does not mean a gameplay pawn exists. Valid packets with `state: null` maintain
  the connection while the other game is loading or its outbox is invalid/stale.
- `session` is the remote helper's random session identifier; `seq` increases within
  that session. A new process/session starts a new sequence. Do not compare sequences
  across session IDs. Received duplicates, older sequences, and packets from superseded
  sessions are ignored and do not refresh the timeout.
- `received_at` is the receiving machine's Unix wall time, not the sender's clock.
  The adapter must also stop using the inbox when its age exceeds the timeout (allow
  a small scheduling margin). This watchdog covers the local helper being killed,
  which leaves the previous inbox file behind.
- On startup, peer timeout, or graceful exit, the helper writes `connected: false`
  and clears `state`, `session`, and `seq`. Transient Windows rename errors are retried
  on subsequent ticks, including a pending disconnect notification.
- Treat missing, unreadable, invalid, stale, disconnected, or null-state inboxes as
  “no usable peer pose”; hide/stop the puppet rather than retaining a stale pose.
  Only apply compatible `world`/`epoch` snapshots once the adapter defines those fields.

Transport session IDs are not world epochs or actor identities. The game adapter must
define authority and an application schema: the host controls world/story/checkpoint
decisions; a client snapshot is a report of that client's own pose. Never apply an
arbitrary remote field as a console command or a function call.

## Wire and failure handling

Wire version 1 is a JSON object with `v`, `role` (`host`/`client`), `session` (32 lowercase
UUID hex digits), `seq` (integer 0 through 2^53−1), `state` (object/null), and `mac`.
The MAC is HMAC-SHA256 over the ASCII encoding produced by Python `json.dumps` on the
other six fields with `sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=True`,
and `allow_nan=False`. Both ends use this helper; Lua does not handle wire signing.

Snapshots are deliberately unreliable: each tick sends the newest full state.
No ordered event delivery, fragmentation, save transfer, or exactly-once semantics is
provided. A future event channel must be designed separately; do not send a one-off
checkpoint/damage/pickup event and assume this channel guarantees its delivery.

The client accepts packets only from its resolved `--connect` IPv4 endpoint. The host
learns a client endpoint from an authenticated packet. An active session is pinned to
its endpoint; a new authenticated session can replace it after a restart or port
change. Each process remembers the last 128 retired remote sessions; that replay
history is bounded and does not persist across helper restarts. On a peer timeout,
the helper clears the remote pose and rotates its own sending session so a healed
link can rejoin without a process restart. No clocks are compared across machines.

## Verification

```powershell
python -I tools/ghostrunner_transport/run_tests.py
```

The script uses only the standard library and the existing `tools/chaos/` tool. It
launches real, separate Python helper processes, writes distinct host/client poses,
and asserts exact bidirectional delivery through each instance's own files. It also
checks crash/restart of each side, stale/malformed/oversize outboxes, unauthenticated
traffic, packet tampering, sequence/address/session fencing, and 1000 seeded malformed
datagrams. A chaos proxy adds 20% base loss, 80 ± 60 ms one-way delay, 30% reordering,
25% duplicates, 5% corruption, then a 1.6-second total blackout. Checks assert actual
packet drops/duplicates, no sequence regression, cleared poses, and reconvergence.

Artifacts and a machine-readable `summary.json` stay in ignored
`local/ghostrunner-transport-tests/`; `--output PATH` selects another directory.
Child processes started by the suite are stopped during cleanup. No game process is
started or stopped. A passing run ends with `ALL OK`. This suite establishes transport
behavior; the separate [runtime checks](runtime/README.md) describe the avatar tests
actually run with real game clients and their limits.

Design references: [PoppyCoop file seam](../../games/poppy-playtime/NOTES.md),
[networking playbook](../../playbook/networking.md), and
[Ghostrunner claim issue](https://github.com/cranebeaker/coop-anything/issues/108).
