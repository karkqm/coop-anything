"""Protocol and two-process integration checks; artifacts stay under local/."""
import argparse
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import relay

KEY = b"test-only-not-a-real-session-key"
OUTPUT = ROOT / "local" / "ghostrunner-transport-tests"


def read_json(path):
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None


def wait_for(predicate, seconds=6):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("condition did not become true within %.1f seconds" % seconds)


class ProtocolTests(unittest.TestCase):
    def test_authentication_and_envelope_validation(self):
        sid = uuid.uuid4().hex
        valid = relay.encode(KEY, "host", sid, 1, {"x": 123})
        self.assertEqual(relay.decode(KEY, valid, "host")["state"], {"x": 123})
        cases = [valid.replace(b"123", b"124"), b"null", b"[]", b"{",
                 b"x" * 1201, b'"NaN"', b'"\\ud800"']
        for wire in cases:
            with self.subTest(wire=wire[:24]), self.assertRaises(ValueError):
                relay.decode(KEY, wire, "host")
        with self.assertRaises(ValueError):
            relay.decode(b"wrong-key", valid, "host")
        with self.assertRaises(ValueError):
            relay.decode(KEY, valid, "client")
        for sequence in [True, -1, 2**53, 1.5]:
            with self.subTest(sequence=sequence), self.assertRaises(ValueError):
                relay.decode(KEY, relay.encode(KEY, "host", sid, sequence, None), "host")
        with self.assertRaises(ValueError):
            relay.encode(KEY, "host", sid, 2, {"x": float("nan")})
        with self.assertRaises(ValueError):
            relay.encode(KEY, "host", sid, 2, {"data": "x" * 1200})

    def test_duplicates_reordering_address_and_retired_session(self):
        peer = relay.Peer()
        old, new = uuid.uuid4().hex, uuid.uuid4().hex
        addr = ("127.0.0.1", 1234)
        self.assertTrue(peer.accept({"session": old, "seq": 8}, addr, 10))
        for seq in [8, 7, 0]:
            self.assertFalse(peer.accept({"session": old, "seq": seq}, addr, 11))
        self.assertEqual(peer.seen, 10)  # Replays must not postpone disconnect.
        self.assertFalse(peer.accept({"session": old, "seq": 9}, ("127.0.0.1", 4321), 11))
        self.assertTrue(peer.accept({"session": new, "seq": 0}, addr, 12))
        self.assertFalse(peer.accept({"session": old, "seq": 999}, addr, 13))
        peer.retire()
        self.assertFalse(peer.accept({"session": new, "seq": 1}, addr, 14))

    def test_seeded_malformed_packet_fuzz(self):
        rng = random.Random(407)
        for _ in range(1000):
            wire = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 1300)))
            try:
                relay.decode(KEY, wire, "client")
            except ValueError:
                pass
            else:
                self.fail("unauthenticated random datagram accepted")


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=OUTPUT))
        self.processes, self.streams = [], []

    def tearDown(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=4)
        for stream in self.streams:
            stream.close()

    def spawn(self, name, command):
        stream = (self.work / (name + ".log")).open("ab")
        self.streams.append(stream)
        env = dict(os.environ, GHOSTRUNNER_COOP_KEY=KEY.decode("ascii"))
        process = subprocess.Popen([sys.executable, "-I"] + list(map(str, command)),
                                   cwd=ROOT, env=env, stdout=stream, stderr=stream)
        self.processes.append(process)
        return process

    def bridge(self, role, connect=None, port=0, tag=None):
        directory = self.work / role
        directory.mkdir(exist_ok=True)
        ready = directory / "ready.json"
        if ready.exists():
            ready.unlink()
        command = [HERE / "relay.py", role, "--directory", directory,
                   "--bind", "127.0.0.1:%d" % port,
                   "--timeout", "0.7", "--state-age", "2", "--hz", "40"]
        if connect:
            command += ["--connect", "127.0.0.1:%d" % connect]
        process = self.spawn(tag or role, command)
        info = wait_for(lambda: read_json(ready))
        self.assertIsNone(process.poll(), "bridge exited during startup")
        return process, info["bind"][1]

    def snapshot(self, role, tick):
        value = {"world": "/Game/Levels/Tutorial/L_Tutorial_Persistant",
                 "position": [tick * (100 if role == "host" else -100), 42, 99],
                 "tick": tick, "role": role}
        wait_for(lambda: relay.atomic_json(self.work / role / "outbox.json", value), seconds=1)
        return value

    def received(self, role, expected):
        value = read_json(self.work / role / "inbox.json")
        return value and value["connected"] and value["state"] == expected

    def inbox(self, role):
        # Windows may briefly deny a read while the bridge replaces this file.
        # Missing data must retry, never count as an observed disconnect.
        return wait_for(lambda: read_json(self.work / role / "inbox.json"))

    def disconnected(self, role):
        value = read_json(self.work / role / "inbox.json")
        return value and value.get("connected") is False

    def converge(self, tick=1):
        host = self.snapshot("host", tick)
        client = self.snapshot("client", tick)
        wait_for(lambda: self.received("host", client) and self.received("client", host))

    def rpc(self, port, method, **params):
        with socket.create_connection(("127.0.0.1", port), timeout=3) as connection:
            connection.sendall(json.dumps({"jsonrpc": "2.0", "id": 1,
                                           "method": method, "params": params}).encode() + b"\n")
            with connection.makefile("rb") as stream:
                result = json.loads(stream.readline())
        if "error" in result:
            self.fail(str(result["error"]))
        return result["result"]

    def test_two_process_bidirectional_and_stale_outbox(self):
        host, port = self.bridge("host")
        client, _ = self.bridge("client", port)
        self.converge()
        stale = self.work / "host" / "outbox.json"
        os.utime(stale, (time.time() - 20, time.time() - 20))
        wait_for(lambda: self.received("client", None))
        self.assertTrue(self.inbox("client")["connected"])
        self.converge(2)
        for invalid in [b"{", b"[]", b'{"x":NaN}', b"x" * 2000,
                        json.dumps({"text": "x" * 1100}).encode()]:
            def write_invalid():
                try:
                    temporary = stale.with_suffix(".producer.tmp")
                    temporary.write_bytes(invalid)
                    os.replace(str(temporary), str(stale))
                    return True
                except OSError:
                    return False
            wait_for(write_invalid, seconds=1)
            wait_for(lambda: self.received("client", None))
            self.assertIsNone(host.poll())
        self.converge(3)
        self.assertIsNone(client.poll())

    def test_loss_delay_reorder_duplicates_and_blackout_recovery(self):
        host, port = self.bridge("host")
        info_path = self.work / "chaos.json"
        chaos = self.spawn("chaos", [ROOT / "tools/chaos/chaos.py", "relay",
                                     "--target", "127.0.0.1:%d" % port,
                                     "--profile", "bad_wifi", "--seed", "407",
                                     "--info-file", info_path,
                                     "--log", self.work / "packets.jsonl"])
        info = wait_for(lambda: read_json(info_path))
        self.rpc(info["rpc"], "set_params", params={"loss": 0.2, "latency_ms": 80,
                 "jitter_ms": 60, "duplicate": 0.25, "reorder": 0.3, "corrupt": 0.05})
        client, _ = self.bridge("client", info["listen"])
        self.converge()
        last = {}
        for tick in range(2, 52):
            self.snapshot("host", tick)
            self.snapshot("client", tick)
            for role in ("host", "client"):
                received = read_json(self.work / role / "inbox.json")
                if received and received["connected"] and received["state"]:
                    sid, seq = received["session"], received["seq"]
                    if role in last and sid == last[role][0]:
                        self.assertGreaterEqual(seq, last[role][1])
                    last[role] = (sid, seq)
            time.sleep(0.04)
        self.converge(999)
        stats = self.rpc(info["rpc"], "stats")
        self.assertGreater(sum(v["dropped"] for v in stats.values()), 0)
        self.assertGreater(sum(v["duplicated"] for v in stats.values()), 0)
        relay.atomic_json(self.work / "chaos-stats.json", stats)
        self.rpc(info["rpc"], "disconnect", duration_ms=1600)
        wait_for(lambda: all((read_json(self.work / role / "inbox.json") or {}).get(
            "connected") is False for role in ("host", "client")))
        for role in ("host", "client"):
            self.assertIsNone(self.inbox(role)["state"])
        time.sleep(1)
        self.converge(1000)
        self.assertTrue(all(p.poll() is None for p in (host, client, chaos)))

    def test_client_and_host_crash_restart(self):
        host, port = self.bridge("host")
        client, _ = self.bridge("client", port)
        self.converge()
        old_session = self.inbox("host")["session"]
        client.kill()
        client.wait(timeout=3)
        wait_for(lambda: self.disconnected("host"))
        client, _ = self.bridge("client", port, tag="client-restart")
        self.converge(2)
        self.assertNotEqual(self.inbox("host")["session"], old_session)
        old_session = self.inbox("client")["session"]
        host.kill()
        host.wait(timeout=3)
        wait_for(lambda: self.disconnected("client"))
        host, new_port = self.bridge("host", port=port, tag="host-restart")
        self.assertEqual(port, new_port)
        self.converge(3)
        self.assertNotEqual(self.inbox("client")["session"], old_session)

    def test_host_ignores_unauthenticated_datagrams(self):
        host, port = self.bridge("host")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            for wire in [b"{}", b"x" * 1300, relay.encode(b"bad-key", "client",
                         uuid.uuid4().hex, 1, {"injected": True})]:
                sender.sendto(wire, ("127.0.0.1", port))
        time.sleep(0.15)
        self.assertFalse(self.inbox("host")["connected"])
        self.assertIsNone(host.poll())
        self.bridge("client", port)
        self.converge()

    def test_lua_staged_outbox_is_adopted_atomically(self):
        self.bridge("host")
        port=read_json(self.work / "host" / "ready.json")["bind"][1]
        self.bridge("client", port)
        self.converge(1)
        expected={"world":"tutorial","position":[456,789,123],"tick":900}
        staged=self.work / "host" / "outbox.next.json"
        wait_for(lambda: relay.atomic_json(staged,expected),seconds=1)
        wait_for(lambda: self.received("client",expected))
        self.assertEqual(read_json(self.work / "host" / "outbox.json"),expected)
        self.assertFalse(staged.exists())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    options = parser.parse_args()
    OUTPUT = options.output.resolve()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(
        sys.modules[__name__]))
    relay.atomic_json(OUTPUT / "summary.json", {"tests": result.testsRun,
                     "failures": len(result.failures), "errors": len(result.errors),
                     "success": result.wasSuccessful()})
    if result.wasSuccessful():
        print("ALL OK")
    sys.exit(0 if result.wasSuccessful() else 1)
