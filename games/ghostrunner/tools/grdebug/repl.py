"""Send Lua to a running test copy through the GrRepl mod and print the result.

  python repl.py A probe.lua          # run a file
  python repl.py A -e "print(1+1)"    # run a snippet
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

DEBUG = Path(r"C:\coop mods\work\grdebug")


def run(pair: str, src: str, timeout: float = 20.0) -> str:
    d = DEBUG / pair
    d.mkdir(parents=True, exist_ok=True)
    out = d / "repl.out"
    if out.exists():
        out.unlink()
    tmp = d / "repl.lua.tmp"
    tmp.write_text(src, encoding="utf-8")
    os.replace(tmp, d / "repl.lua")
    end = time.time() + timeout
    while time.time() < end:
        if out.exists():
            try:
                text = out.read_text(encoding="utf-8", errors="replace")
            except OSError:
                time.sleep(0.1)
                continue
            if "--ok=" in text:
                return text
        time.sleep(0.15)
    return "--timeout (game not running, not in a state that ticks, or GrRepl not enabled)\n"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    pair = argv[0]
    if argv[1] == "-e":
        src = " ".join(argv[2:])
    else:
        src = Path(argv[1]).read_text(encoding="utf-8-sig")
    text = run(pair, src)
    sys.stdout.write(text)
    return 0 if "--ok=true" in text else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
