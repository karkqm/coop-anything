"""W39: enter a level on a test copy with keyboard only, step by step on game state.

title "press any key" -> main bar (Ghostrunner tab focused) -> Enter opens the submenu with
"Continue" focused -> Enter loads the saved level. Every key is sent only after GrDebug confirms
the expected menu state, and only while the test-copy window is the foreground window.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
import grdebug as g  # noqa: E402


def state(pair):
    return g.read_state(pair)


def wait(pair, pred, timeout, label):
    end = time.time() + timeout
    while time.time() < end:
        s = state(pair)
        if s and pred(s):
            return s
        time.sleep(0.5)
    print(f"timeout: {label}; last state={state(pair)}")
    return None


def main(pair: str = "A") -> int:
    g.PAIR_HINT = pair
    hwnd = g.window_for_pair(pair)
    if not hwnd:
        print("window not found")
        return 1
    if not wait(pair, lambda s: s.get("world", "").find("MainMenu") >= 0, 120, "MainMenu world"):
        return 2
    # 1) title screen: any key until the bottom bar is visible
    for attempt in range(6):
        if state(pair).get("menu", "").startswith("visible"):
            break
        g.press_key(hwnd, "space")
        time.sleep(1.5)
    else:
        print("menu never became visible")
        return 3
    print("menu:", state(pair).get("menu"))
    # 2) open the Ghostrunner submenu (Continue gets focus)
    for attempt in range(3):
        if state(pair).get("menu") == "visible|submenu":
            break
        g.press_key(hwnd, "enter")
        time.sleep(1.5)
    if state(pair).get("menu") != "visible|submenu":
        print("submenu did not open")
        return 4
    print("submenu open, clicking Continue")
    time.sleep(0.8)
    # Enter only moves focus here; the button activates on a mouse click. Ratio of the client
    # area, measured on the menu layout (it scales with the window).
    for attempt in range(3):
        g.click_ratio(hwnd, 0.204, 0.479)
        if wait(pair, lambda s: s.get("menu") != "visible|submenu", 8, "menu leaves"):
            break
    s = wait(pair, lambda s: s.get("gameplay") == "true", 180, "gameplay pawn")
    if not s:
        return 5
    print(f"IN LEVEL world={s.get('world')} enemies={s.get('enemies')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "A"))
