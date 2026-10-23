"""Deploy kit CoopFight to the test copies: A = host (Ghostrunner3), B = client (Ghostrunner2).

  python deploy_coopfight.py

Copy B gets its own NET_DIR / PAIR / ROLE lines. Also sets CoopFight : 1 in both mods.txt.
"""
from __future__ import annotations

import re
from pathlib import Path

KIT = Path(r"C:\coop mods\kit\experimental\CoopFight-main.lua")
COPIES = {
    "A": (Path(r"A:\CoopTest\Ghostrunner3"), "C:/coop mods/work/net/", "host"),
    "B": (Path(r"A:\CoopTest\Ghostrunner2"), "C:/coop mods/work/net-B/", "client"),
}


def render(src: str, pair: str, net_dir: str, role: str) -> str:
    out, n1 = re.subn(r'^local NET_DIR = ".*"$', f'local NET_DIR = "{net_dir}"', src, count=1, flags=re.M)
    out, n2 = re.subn(r'^local PAIR = ".*"$', f'local PAIR = "{pair}"', out, count=1, flags=re.M)
    out, n3 = re.subn(r'^local ROLE = "[a-z]+"', f'local ROLE = "{role}"', out, count=1, flags=re.M)
    if (n1, n2, n3) != (1, 1, 1):
        raise SystemExit(f"config lines not found for {pair}: {(n1, n2, n3)}")
    return out


def main() -> int:
    src = KIT.read_text(encoding="utf-8")
    for pair, (root, net_dir, role) in COPIES.items():
        mods = root / "Ghostrunner" / "Binaries" / "Win64" / "Mods"
        (mods / "CoopFight" / "Scripts" / "main.lua").write_text(render(src, pair, net_dir, role), encoding="utf-8")
        txt = mods / "mods.txt"
        t = txt.read_text(encoding="utf-8")
        t2 = re.sub(r"^CoopFight : \d", "CoopFight : 1", t, flags=re.M)
        if t2 != t:
            txt.write_text(t2, encoding="utf-8")
        print(f"{pair}: deployed role={role} net={net_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
