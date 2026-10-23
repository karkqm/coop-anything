"""W42 diag: bring ONE copy into the level alone and log free RAM while it loads.

  python w42_diag.py <pair> <label>

Tells a memory shortage apart from a mod bug when copy B hangs on level load.
Appends to C:\\coop mods\\work\\grdebug\\w42-diag.log. Every step has a timeout.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import enter_continue  # noqa: E402
import grdebug as g  # noqa: E402
from w39_soak import stop_copy, wait_window  # noqa: E402

LOG = Path(r"C:\coop mods\work\grdebug\w42-diag.log")


class MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_gb() -> tuple[float, float]:
    m = MemStatus()
    m.dwLength = ctypes.sizeof(MemStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return round(m.ullAvailPhys / 2**30, 2), round(m.ullAvailPageFile / 2**30, 2)


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


LOWMEM = ["-ExecCmds=sg.TextureQuality 0,sg.ShadowQuality 0,sg.EffectsQuality 0,"
          "sg.PostProcessQuality 0,r.Streaming.PoolSize 200"]


def commit_mb(pid: int) -> int:
    """Private commit of one process, MB (PROCESS_MEMORY_COUNTERS_EX.PrivateUsage)."""
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize",
                                          "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                          "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                          "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return -1
    c = PMC()
    c.cb = ctypes.sizeof(PMC)
    ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb)
    ctypes.windll.kernel32.CloseHandle(h)
    return c.PrivateUsage // 2**20


def main(pair: str, label: str, lowmem: bool = False) -> int:
    log(f"=== {label}: pair={pair} free(ram,commit)GB={free_gb()}")
    low = [free_gb()]
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            f = free_gb()
            if f[0] < low[0][0]:
                low[0] = f
            time.sleep(1)

    threading.Thread(target=sample, daemon=True).start()
    stop_copy(pair)
    g.launch(pair, LOWMEM if lowmem else [])
    if not wait_window(pair, 90):
        log(f"{pair}: window never appeared")
        stop.set()
        return 1
    rc = enter_continue.main(pair)
    s = g.read_state(pair)
    log(f"{pair}: enter rc={rc} state={s}")
    time.sleep(20)
    s2 = g.read_state(pair)
    ticking = bool(s and s2 and s.get("tick") != s2.get("tick"))
    stop.set()
    pid = int((g.DEBUG_DIR / f"pid-{pair}.txt").read_text(encoding="utf-8"))
    log(f"{pair}: 20s later state={s2} ticking={ticking} lowest_free(ram,commit)GB={low[0]} "
        f"game_commit_MB={commit_mb(pid)}")
    verdict = "PASS" if rc == 0 and ticking else "FAIL"
    log(f"{label}: {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], "--lowmem" in sys.argv[3:]))
