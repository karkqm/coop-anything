"""Two-player file/UDP snapshot bridge. Python 3.8+, standard library only."""
import argparse
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import select
import socket
import sys
import time
import uuid

VERSION = 1
MAX_PACKET = 1200
MAX_FILE = 1200
MAX_SEQUENCE = 2**53 - 1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def encode(key, role, session, sequence, state):
    body = {"v": VERSION, "role": role, "session": session,
            "seq": sequence, "state": state}
    body["mac"] = hmac.new(key, canonical(body), hashlib.sha256).hexdigest()
    wire = canonical(body)
    if len(wire) > MAX_PACKET:
        raise ValueError("snapshot exceeds 1200-byte wire budget")
    return wire


def decode(key, wire, expected_role):
    if len(wire) > MAX_PACKET:
        raise ValueError("oversize packet")
    try:
        packet = json.loads(wire)
        if not isinstance(packet, dict) or set(packet) != {
                "v", "role", "session", "seq", "state", "mac"}:
            raise ValueError("invalid envelope")
        mac = packet.pop("mac")
        expected_mac = hmac.new(key, canonical(packet), hashlib.sha256).hexdigest()
        if not isinstance(mac, str) or not hmac.compare_digest(mac, expected_mac):
            raise ValueError("authentication failed")
        if type(packet["v"]) is not int or packet["v"] != VERSION:
            raise ValueError("unsupported version")
        if packet["role"] != expected_role:
            raise ValueError("unexpected role")
        sid = packet["session"]
        if not isinstance(sid, str) or len(sid) != 32 or uuid.UUID(hex=sid).hex != sid:
            raise ValueError("invalid session")
        seq = packet["seq"]
        if type(seq) is not int or not 0 <= seq <= MAX_SEQUENCE:
            raise ValueError("invalid sequence")
        if packet["state"] is not None and not isinstance(packet["state"], dict):
            raise ValueError("state must be an object or null")
        return packet
    except (TypeError, UnicodeError, OverflowError, RecursionError, AttributeError) as exc:
        raise ValueError("invalid packet") from exc


def atomic_json(path, value):
    """Readers either see the previous complete file or the new complete file."""
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(canonical(value))
        os.replace(str(temporary), str(path))
        return True
    except OSError:
        # A Windows reader can briefly hold the destination without delete sharing.
        # Retry on the next tick, without blocking either the game or the socket.
        return False


def read_state(path, max_age):
    try:
        with path.open("rb") as stream:
            stat = os.fstat(stream.fileno())
            if time.time() - stat.st_mtime > max_age:
                return None
            raw = stream.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            return None
        value = json.loads(raw)
        if not isinstance(value, dict):
            return None
        canonical(value)  # Reject NaN/Infinity before constructing the wire envelope.
        return value
    except (OSError, ValueError, TypeError, RecursionError, UnicodeError):
        return None


class Peer:
    """Sequence fencing and timeout use receiver monotonic time, not peer clocks."""
    def __init__(self):
        self.session = None
        self.sequence = -1
        self.address = None
        self.seen = None
        self.retired = []

    def retire(self):
        if self.session is not None:
            self.retired.append(self.session)
            self.retired = self.retired[-128:]
        self.session = None
        self.sequence = -1
        self.address = None
        self.seen = None

    def accept(self, packet, address, now):
        sid = packet["session"]
        if sid in self.retired:
            return False
        if sid == self.session:
            if address != self.address or packet["seq"] <= self.sequence:
                return False
        else:
            self.retire()
            self.session = sid
            self.address = address
        self.sequence = packet["seq"]
        self.seen = now
        return True


class Bridge:
    def __init__(self, role, directory, key, bind, remote=None, hz=20,
                 timeout=3, state_age=2):
        self.role, self.directory, self.key = role, Path(directory), key
        self.remote, self.interval = remote, 1 / hz
        self.timeout, self.state_age = timeout, state_age
        self.session, self.sequence = uuid.uuid4().hex, 0
        self.peer = Peer()
        self.stats = {"sent": 0, "received": 0, "rejected": 0,
                      "outbox_rejected": 0, "timeouts": 0, "file_errors": 0}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(bind)
        self.socket.setblocking(False)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.publish(False, None)

    def publish(self, connected, state):
        self.pending = {"v": VERSION, "connected": connected,
                 "session": self.peer.session if connected else None,
                 "seq": self.peer.sequence if connected else None,
                 "received_at": time.time(), "state": state}
        self.flush()

    def flush(self):
        if self.pending is not None:
            if atomic_json(self.directory / "inbox.json", self.pending):
                self.pending = None
            else:
                self.stats["file_errors"] += 1

    def expire(self, now):
        if self.peer.seen is not None and now - self.peer.seen >= self.timeout:
            self.peer.retire()
            self.stats["timeouts"] += 1
            self.publish(False, None)
            # Rotate our sending session too, so the other side can reconnect after
            # it has retired our previous session during the same outage.
            self.session, self.sequence = uuid.uuid4().hex, 0

    def receive(self, now):
        # Bound work per tick even if a stranger floods the bound UDP socket.
        for _ in range(128):
            try:
                # Windows raises WSAEMSGSIZE instead of returning a truncated
                # datagram. Receive the full UDP maximum, then reject by length.
                wire, address = self.socket.recvfrom(65535)
            except (BlockingIOError, ConnectionResetError):
                break
            if self.remote is not None and address != self.remote:
                self.stats["rejected"] += 1
                continue
            try:
                packet = decode(self.key, wire, "client" if self.role == "host" else "host")
                if not self.peer.accept(packet, address, now):
                    raise ValueError("stale session, sequence, or address")
            except ValueError:
                self.stats["rejected"] += 1
                continue
            self.stats["received"] += 1
            self.publish(True, packet["state"])

    def send(self):
        target = self.remote or self.peer.address
        if target is None:
            return
        state = read_state(self.directory / "outbox.json", self.state_age)
        try:
            wire = encode(self.key, self.role, self.session, self.sequence, state)
        except (ValueError, RecursionError):
            self.stats["outbox_rejected"] += 1
            wire = encode(self.key, self.role, self.session, self.sequence, None)
        self.sequence += 1
        try:
            self.socket.sendto(wire, target)
            self.stats["sent"] += 1
        except (BlockingIOError, ConnectionResetError, OSError):
            # UDP errors do not terminate the bridge. Liveness will time out.
            pass

    def run(self, seconds=0):
        started = time.monotonic()
        tick = started
        try:
            while not seconds or time.monotonic() - started < seconds:
                now = time.monotonic()
                self.expire(now)
                if now >= tick:
                    self.flush()
                    self.send()
                    tick = now + self.interval
                readable, _, _ = select.select([self.socket], [], [],
                                                min(self.interval, max(0, tick - now)))
                if readable:
                    self.receive(time.monotonic())
        finally:
            self.socket.close()
            self.publish(False, None)
            atomic_json(self.directory / "stats.json", self.stats)


def endpoint(value):
    try:
        host, port = value.rsplit(":", 1)
        port = int(port)
        if not 0 <= port <= 65535:
            raise ValueError()
        return socket.gethostbyname(host), port
    except (OSError, ValueError) as exc:
        raise argparse.ArgumentTypeError("expected IPv4 host:port") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("host", "client"))
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--bind", type=endpoint, default=("127.0.0.1", 0))
    parser.add_argument("--connect", type=endpoint)
    parser.add_argument("--hz", type=float, default=20)
    parser.add_argument("--timeout", type=float, default=3)
    parser.add_argument("--state-age", type=float, default=2)
    parser.add_argument("--seconds", type=float, default=0)
    parser.add_argument("--key-env", default="GHOSTRUNNER_COOP_KEY")
    args = parser.parse_args()
    key = os.environ.get(args.key_env, "").encode("utf-8")
    if len(key) < 16:
        parser.error("set the shared secret environment variable (at least 16 bytes)")
    if (args.role == "client") != (args.connect is not None):
        parser.error("client requires --connect; host must not use --connect")
    if args.connect and args.connect[1] == 0:
        parser.error("--connect needs a nonzero port")
    if not math.isfinite(args.hz) or not 1 <= args.hz <= 120:
        parser.error("--hz must be between 1 and 120")
    if not all(math.isfinite(x) and x > 0 for x in (args.timeout, args.state_age)):
        parser.error("--timeout and --state-age must be positive finite seconds")
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error("--seconds must be nonnegative finite seconds")
    try:
        bridge = Bridge(args.role, args.directory, key, args.bind, args.connect,
                        args.hz, args.timeout, args.state_age)
        ready = {"role": args.role, "bind": list(bridge.socket.getsockname()), "v": VERSION}
        if not atomic_json(args.directory / "ready.json", ready):
            raise OSError("cannot write ready.json")
        print(json.dumps(ready), flush=True)
        bridge.run(args.seconds)
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print("bridge error: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
