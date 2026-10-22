"""W39 acceptance: N cold launches of a test copy, each must reach a gameplay pawn unattended.

  python w39_soak.py A 10

Each run: stop the copy this tool launched before, launch it fresh, run enter_continue, record
the result. Results go to C:\\coop mods\\work\\grdebug\\w39-soak-<pair>.log (one line per run).
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import enter_continue  # noqa: E402
import grdebug as g  # noqa: E402

LOG_DIR = Path(r"C:\coop mods\work\grdebug")


def stop_copy(pair: str) -> None:
    """Stop only the process this tool started for that pair (its pid file), never anything else."""
    pid_file = LOG_DIR / f"pid-{pair}.txt"
    if not pid_file.exists():
        return
    pid = pid_file.read_text(encoding="utf-8").strip()
    subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
    time.sleep(5)


def wait_window(pair: str, timeout: float = 60) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if g.window_for_pair(pair):
            return True
        time.sleep(1)
    return False


def main(pair: str = "A", runs: int = 10) -> int:
    log = LOG_DIR / f"w39-soak-{pair}.log"
    log.write_text("", encoding="utf-8")
    passed = 0
    for i in range(1, runs + 1):
        stop_copy(pair)
        t0 = time.time()
        g.launch(pair, [])
        rc = enter_continue.main(pair) if wait_window(pair) else 1
        line = f"run {i}: rc={rc} {time.time() - t0:.0f}s state={g.read_state(pair)}"
        print(line, flush=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        if rc == 0:
            passed += 1
        else:
            g.screenshot(g.window_for_pair(pair), LOG_DIR / f"w39-soak-{pair}-fail{i}.png")
    summary = f"W39 soak {pair}: {passed}/{runs} passed"
    print(summary)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(summary + "\n")
    return 0 if passed == runs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "A",
                  int(sys.argv[2]) if len(sys.argv) > 2 else 10))
