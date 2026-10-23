"""W42 live test: copy A = host, copy B = client, both enter the level, then let the mirror run.

  python w42_live.py [settle_seconds] [--lowmem]

Writes progress to C:\\coop mods\\work\\grdebug\\w42-live.log. Every step has a timeout, so the
script always ends. The relay processes (host+client) must already be running.
"""
from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import enter_continue  # noqa: E402
import grdebug as g  # noqa: E402
from w39_soak import stop_copy, wait_window  # noqa: E402
from w42_diag import LOWMEM, free_gb  # noqa: E402

LOG = Path(r"C:\coop mods\work\grdebug\w42-live.log")


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def alive(pair: str) -> bool:
    """The copy's game process still exists. A copy that runs out of Windows commit memory
    while loading a level just vanishes, which looked like a freeze in earlier runs."""
    try:
        pid = int((g.DEBUG_DIR / f"pid-{pair}.txt").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def bring_up(pair: str, lowmem: bool) -> int:
    stop_copy(pair)
    log(f"{pair}: launch lowmem={lowmem} free(ram,commit)GB={free_gb()}")
    g.launch(pair, LOWMEM if lowmem else [])
    if not wait_window(pair, 90):
        log(f"{pair}: window never appeared")
        return 1
    rc = enter_continue.main(pair)
    log(f"{pair}: enter rc={rc} alive={alive(pair)} state={g.read_state(pair)}")
    return rc


def main(settle: int = 90, lowmem: bool = False) -> int:
    LOG.write_text("", encoding="utf-8")
    for pair in ("A", "B"):
        rc = bring_up(pair, lowmem)
        if rc != 0 and alive(pair):
            rc = bring_up(pair, lowmem)  # one retry, as in the W39 soak
        if rc != 0:
            log(f"FAIL: {pair} did not reach gameplay (alive={alive(pair)} free={free_gb()})")
            return 1
        time.sleep(15)  # level-load commit peak falls back before the next copy loads
    log(f"both in level, letting the mirror run {settle}s")
    time.sleep(settle)
    for pair in ("A", "B"):
        log(f"{pair}: final alive={alive(pair)} state={g.read_state(pair)}")
        g.screenshot(g.window_for_pair(pair), LOG.parent / f"w42-{pair}.png")
    log(f"DONE free(ram,commit)GB={free_gb()}")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(main(int(args[0]) if args else 90, "--lowmem" in sys.argv[1:]))
