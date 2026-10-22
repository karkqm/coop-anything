#!/usr/bin/env python3
"""grdebug - drive a Ghostrunner test copy into a level and inspect it, without a human.

Why this exists: every programmatic way to load a level on this build is blocked (see the
coordination log). The only path that works is the game's own menu, so this tool does what a
player does: it focuses the test-copy window, skips the intro cutscene with a click, presses the
right menu button and then verifies through the GrDebug Lua mod that a level actually loaded.

It only ever touches the window of the process it launched, and it puts the previously focused
window back afterwards. Nothing is sent to any other application.

Usage:
  python grdebug.py launch --pair A            # start the game copy and wait for the menu
  python grdebug.py enter                      # skip cutscene, press New Game, wait for a level
  python grdebug.py state                      # what the game reports right now
  python grdebug.py shot --out shot.png        # capture the game window
  python grdebug.py click --rx 0.25 --ry 0.5   # click at a ratio of the client area
  python grdebug.py loop                       # full flow: launch -> enter -> report
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import time
from pathlib import Path

USER32 = ctypes.WinDLL("user32", use_last_error=True)
GDI32 = ctypes.WinDLL("gdi32", use_last_error=True)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

# explicit signatures: default int return types truncate window handles on x64
USER32.GetForegroundWindow.restype = wt.HWND
USER32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
USER32.GetWindowThreadProcessId.restype = wt.DWORD
USER32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
USER32.AttachThreadInput.restype = wt.BOOL
USER32.SetForegroundWindow.argtypes = [wt.HWND]
USER32.SetForegroundWindow.restype = wt.BOOL
USER32.SetFocus.argtypes = [wt.HWND]
USER32.SetFocus.restype = wt.HWND
USER32.BringWindowToTop.argtypes = [wt.HWND]
USER32.BringWindowToTop.restype = wt.BOOL
USER32.IsWindow.argtypes = [wt.HWND]
USER32.IsWindow.restype = wt.BOOL
USER32.SendInput.argtypes = [wt.UINT, ctypes.c_void_p, ctypes.c_int]
USER32.SendInput.restype = wt.UINT
KERNEL32.GetCurrentThreadId.restype = wt.DWORD
USER32.GetWindowDC.argtypes = [wt.HWND]
USER32.GetWindowDC.restype = wt.HDC
USER32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
USER32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
USER32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
USER32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
USER32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
USER32.IsIconic.argtypes = [wt.HWND]
USER32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
GDI32.CreateCompatibleDC.argtypes = [wt.HDC]
GDI32.CreateCompatibleDC.restype = wt.HDC
GDI32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
GDI32.CreateCompatibleBitmap.restype = wt.HBITMAP
GDI32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
GDI32.SelectObject.restype = wt.HGDIOBJ
GDI32.DeleteObject.argtypes = [wt.HGDIOBJ]
GDI32.DeleteDC.argtypes = [wt.HDC]
GDI32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]

WORK = Path(r"C:\coop mods\work")
DEBUG_DIR = WORK / "grdebug"
PAIR_HINT = "A"


def state_path(pair: str) -> Path:
    """Each game copy writes its own state file; sharing one caused false passes."""
    return DEBUG_DIR / pair / "state.txt"
PAIRS = {
    "A": Path(r"A:\CoopTest\Ghostrunner3"),
    "B": Path(r"A:\CoopTest\Ghostrunner2"),
    "C": Path(r"A:\CoopTest\Ghostrunner"),
}
SW_RESTORE = 9
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_MOUSE = 0


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 24)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _INPUTunion)]


VK_CODES = {
    "space": 0x20, "enter": 0x0D, "escape": 0x1B, "esc": 0x1B,
    "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44, "e": 0x45, "f": 0x46,
    "lshift": 0xA0, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}
INPUT_KEYBOARD = 1


def client_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wt.RECT()
    USER32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wt.POINT(0, 0)
    USER32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top


def focus(hwnd: int) -> int:
    """Bring the window to the foreground and return the window that had focus before.

    SetForegroundWindow is silently refused when the calling process is not the foreground one,
    so the input queues are attached to the current foreground thread first. The caller must
    still verify with is_foreground(): sending input to the wrong window is exactly what must
    never happen here.
    """
    previous = USER32.GetForegroundWindow()
    if USER32.IsIconic(hwnd):
        USER32.ShowWindow(hwnd, SW_RESTORE)
    fg = USER32.GetForegroundWindow()
    tid_fg = USER32.GetWindowThreadProcessId(fg, None) if fg else 0
    tid_me = KERNEL32.GetCurrentThreadId()
    attached = False
    if tid_fg and tid_fg != tid_me:
        attached = bool(USER32.AttachThreadInput(tid_me, tid_fg, True))
    try:
        USER32.BringWindowToTop(hwnd)
        USER32.SetForegroundWindow(hwnd)
        USER32.SetFocus(hwnd)
    finally:
        if attached:
            USER32.AttachThreadInput(tid_me, tid_fg, False)
    time.sleep(0.25)
    return previous


def is_foreground(hwnd: int) -> bool:
    return USER32.GetForegroundWindow() == hwnd


def restore_focus(previous: int) -> None:
    if previous and USER32.IsWindow(previous):
        USER32.SetForegroundWindow(previous)


def click_at(hwnd: int, x: int, y: int) -> None:
    """Left click at client-area coordinates of that window."""
    ox, oy, w, h = client_rect(hwnd)
    ax = int((x + ox) * 65535 / USER32.GetSystemMetrics(0))
    ay = int((y + oy) * 65535 / USER32.GetSystemMetrics(1))
    events = (INPUT * 3)(
        INPUT(type=INPUT_MOUSE, u=_INPUTunion(mi=MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None))),
        INPUT(type=INPUT_MOUSE, u=_INPUTunion(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None))),
        INPUT(type=INPUT_MOUSE, u=_INPUTunion(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None))),
    )
    USER32.SendInput(3, events, ctypes.sizeof(INPUT))


def press_key(hwnd: int, key: str, hold: float = 0.05) -> None:
    """Tap a key in that window (the intro screens ask for "press any key", a click does nothing)."""
    vk = VK_CODES.get(key.lower())
    if vk is None:
        raise SystemExit(f"unknown key '{key}', known: {', '.join(sorted(VK_CODES))}")
    previous = focus(hwnd)
    try:
        if not is_foreground(hwnd):
            print("refusing to send a key: the game window did not take focus "
                  f"(foreground is {USER32.GetForegroundWindow()})")
            return False
        down = INPUT(type=INPUT_KEYBOARD, u=_INPUTunion(ki=KEYBDINPUT(vk, 0, 0, 0, None)))
        up = INPUT(type=INPUT_KEYBOARD, u=_INPUTunion(ki=KEYBDINPUT(vk, 0, 0x0002, 0, None)))
        USER32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        time.sleep(hold)
        USER32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
    finally:
        restore_focus(previous)
    time.sleep(0.4)
    return True


def check_key(hwnd: int) -> bool:
    """The intro screens advance on any key; wait until the menu button is really visible."""
    for key in ("space", "enter", "escape"):
        if not press_key(hwnd, key):
            return False
        if wait_for(lambda s: s.get("menu", "").startswith("visible"), 4, 0.5, f"menu after {key}", quiet=True):
            return True
    return False


def click_ratio(hwnd: int, rx: float, ry: float) -> bool:
    ox, oy, w, h = client_rect(hwnd)
    x, y = int(w * rx), int(h * ry)
    previous = focus(hwnd)
    try:
        if not is_foreground(hwnd):
            print("refusing to click: the game window did not take focus "
                  f"(foreground is {USER32.GetForegroundWindow()})")
            return False
        click_at(hwnd, x, y)
        time.sleep(0.6)
        return True
    finally:
        restore_focus(previous)


def screenshot(hwnd: int, out: Path) -> bool:
    """Capture the window even when it is covered by other windows."""
    user32 = USER32
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return False
    hdc_screen = user32.GetWindowDC(hwnd)
    hdc_mem = GDI32.CreateCompatibleDC(hdc_screen)
    bmp = GDI32.CreateCompatibleBitmap(hdc_screen, w, h)
    GDI32.SelectObject(hdc_mem, bmp)
    PW_RENDERFULLCONTENT = 2
    user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    GDI32.GetDIBits(hdc_mem, bmp, 0, h, buf, ctypes.byref(bi), 0)

    # write a PNG through GDI+ so no third-party imaging library is needed
    from ctypes import wintypes
    gdiplus = ctypes.WinDLL("gdiplus")

    class GdiplusStartupInput(ctypes.Structure):
        _fields_ = [("GdiplusVersion", wt.DWORD), ("DebugEventCallback", ctypes.c_void_p),
                    ("SuppressBackgroundThread", wintypes.BOOL), ("SuppressExternalCodecs", wintypes.BOOL)]

    token = ctypes.c_void_p()
    startup = GdiplusStartupInput(1, None, False, False)
    if gdiplus.GdiplusStartup(ctypes.byref(token), ctypes.byref(startup), None) != 0:
        return False
    try:
        # GdipSaveImageToFile needs a GpImage*, not an HBITMAP: wrap the GDI bitmap first
        gp_image = ctypes.c_void_p()
        if gdiplus.GdipCreateBitmapFromHBITMAP(ctypes.c_void_p(bmp), None, ctypes.byref(gp_image)) != 0:
            return False
        png_clsid = (ctypes.c_ubyte * 16)(0x06, 0xF4, 0x7C, 0x55, 0x04, 0x1A, 0xD3, 0x11,
                                         0x9A, 0x73, 0x00, 0x00, 0xF8, 0x1E, 0xF3, 0x2E)
        status = gdiplus.GdipSaveImageToFile(gp_image, ctypes.c_wchar_p(str(out)),
                                             ctypes.byref(png_clsid), None)
        gdiplus.GdipDisposeImage(gp_image)
        return status == 0
    finally:
        gdiplus.GdiplusShutdown(token)
        GDI32.DeleteObject(bmp)
        GDI32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_screen)


def read_state(pair: str = None) -> dict:
    STATE = state_path(pair or PAIR_HINT)
    if not STATE.exists():
        return {}
    out = {}
    for line in STATE.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def wait_for(predicate, timeout: float, interval: float = 0.5, label: str = "condition", quiet: bool = False) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate(read_state()):
                return True
        except Exception:
            pass
        time.sleep(interval)
    if not quiet:
        print(f"timeout waiting for {label}")
    return False


def game_process(pair: str):
    import psutil  # optional; fall back to tasklist-free approach if unavailable
    return None


def launch(pair: str, args: list[str]) -> int:
    root = PAIRS[pair]
    exe = root / "Ghostrunner" / "Binaries" / "Win64" / "Ghostrunner-Win64-Shipping.exe"
    if not exe.exists():
        print(f"game executable not found: {exe}")
        return 1
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    sp = state_path(pair)
    sp.parent.mkdir(parents=True, exist_ok=True)
    if sp.exists():
        sp.unlink()
    log = DEBUG_DIR / f"launch-{pair}.log"
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen([str(exe), "-windowed", "-ResX=1024", "-ResY=576", "-nosplash"],
                                cwd=str(root), stdout=fh, stderr=fh)
    (DEBUG_DIR / f"pid-{pair}.txt").write_text(str(proc.pid), encoding="utf-8")
    print(f"launched {pair}: pid={proc.pid}")
    time.sleep(2)
    hwnd = find_window_for_pid(proc.pid)
    print(f"window handle: {hwnd}")
    return 0


def find_window_for_pid(pid: int) -> int:
    import ctypes.wintypes
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def enum_proc(hwnd, lparam):
        owner = wt.DWORD()
        USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and USER32.IsWindowVisible(hwnd):
            length = USER32.GetWindowTextLengthW(hwnd)
            if length > 0:
                found.append(hwnd)
        return True

    USER32.EnumWindows(enum_proc, 0)
    return found[0] if found else 0


def window_for_pair(pair: str) -> int:
    pid_file = DEBUG_DIR / f"pid-{pair}.txt"
    if not pid_file.exists():
        return 0
    return find_window_for_pid(int(pid_file.read_text(encoding="utf-8").strip()))


def cmd_state(args) -> int:
    global PAIR_HINT
    PAIR_HINT = args.pair
    state = read_state(args.pair)
    if not state:
        print("no state yet (is the GrDebug mod installed and the game running?)")
        return 1
    for k in ("tick", "world", "pawn", "gameplay", "enemies", "menu"):
        print(f"{k:9s}: {state.get(k, '?')}")
    return 0


def cmd_shot(args) -> int:
    hwnd = window_for_pair(args.pair)
    if not hwnd:
        print("window not found")
        return 1
    out = Path(args.out)
    ok = screenshot(hwnd, out)
    print(f"screenshot {'saved' if ok else 'failed'}: {out}")
    return 0 if ok else 1


def cmd_click(args) -> int:
    hwnd = window_for_pair(args.pair)
    if not hwnd:
        print("window not found")
        return 1
    click_ratio(hwnd, args.rx, args.ry)
    print(f"clicked {args.rx:.3f},{args.ry:.3f} of the client area")
    return 0


def cmd_press(args) -> int:
    hwnd = window_for_pair(args.pair)
    if not hwnd:
        print("window not found")
        return 1
    press_key(hwnd, args.key)
    print(f"pressed {args.key}")
    return 0


def cmd_enter(args) -> int:
    global PAIR_HINT
    PAIR_HINT = args.pair
    hwnd = window_for_pair(args.pair)
    if not hwnd:
        print("window not found")
        return 1
    # 1) intro cinematics advance on any key; the menu button is only visible afterwards
    if not wait_for(lambda s: s.get("menu", "").startswith("visible"), 3, 0.5, "menu already up", quiet=True):
        print("advancing the intro (press any key)")
        if not check_key(hwnd):
            print("could not reach the menu")
            return 3
    state = read_state()
    print(f"menu is up (world={state.get('world')})")

    # 2) the bottom bar tab "Start game" shows the left submenu
    if not wait_for(lambda s: "|submenu" in s.get("menu", ""), 1, 0.2, "submenu", quiet=True):
        print(f"opening the Start-game submenu")
        if not click_ratio(hwnd, args.rx_tab, args.ry_tab):
            return 4
        time.sleep(0.8)
        press_key(hwnd, "enter")
        time.sleep(1.5)

    # 3) New Game is the second entry of that submenu
    print(f"pressing New Game at {args.rx_newgame:.3f},{args.ry_newgame:.3f}")
    if not click_ratio(hwnd, args.rx_newgame, args.ry_newgame):
        return 5
    ok = wait_for(lambda s: s.get("gameplay") == "true", 150, label="a loaded level")
    state = read_state(args.pair)
    print(f"world={state.get('world')} gameplay={state.get('gameplay')} enemies={state.get('enemies')}")
    return 0 if ok else 2


def cmd_loop(args) -> int:
    global PAIR_HINT
    PAIR_HINT = args.pair
    rc = launch(args.pair, [])
    if rc != 0:
        return rc
    time.sleep(4)
    args_enter = argparse.Namespace(pair=args.pair, rx_tab=args.rx_tab, ry_tab=args.ry_tab,
                                     rx_newgame=args.rx_newgame, ry_newgame=args.ry_newgame)
    return cmd_enter(args_enter)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pair", default="A", choices=sorted(PAIRS))
    sub = parser.add_subparsers(dest="command", required=True)

    p_launch = sub.add_parser("launch")
    p_launch.set_defaults(func=lambda a: launch(a.pair, []))

    p_enter = sub.add_parser("enter")
    p_enter.add_argument("--rx-tab", type=float, default=0.22)
    p_enter.add_argument("--ry-tab", type=float, default=0.82)
    p_enter.add_argument("--rx-newgame", type=float, default=0.205)
    p_enter.add_argument("--ry-newgame", type=float, default=0.516)
    p_enter.set_defaults(func=cmd_enter)

    p_state = sub.add_parser("state")
    p_state.set_defaults(func=cmd_state)

    p_shot = sub.add_parser("shot")
    p_shot.add_argument("--out", default=str(DEBUG_DIR / "shot.png"))
    p_shot.set_defaults(func=cmd_shot)

    p_click = sub.add_parser("click")
    p_click.add_argument("--rx", type=float, required=True)
    p_click.add_argument("--ry", type=float, required=True)
    p_click.set_defaults(func=cmd_click)

    p_loop = sub.add_parser("loop")
    p_loop.add_argument("--rx-tab", type=float, default=0.22)
    p_loop.add_argument("--ry-tab", type=float, default=0.82)
    p_loop.add_argument("--rx-newgame", type=float, default=0.205)
    p_loop.add_argument("--ry-newgame", type=float, default=0.516)
    p_loop.set_defaults(func=cmd_loop)

    p_press = sub.add_parser("press")
    p_press.add_argument("--key", default="space")
    p_press.set_defaults(func=cmd_press)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

