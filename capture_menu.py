#!/usr/bin/env python3
"""Display-verified capture of the 2K-FA Set-mode top-level menu screens.

Safety model (manual section 10, verified 2026-07-18):
- programming only possible in STANDBY (checked before starting)
- changes commit ONLY on [SET]-exit; we never press SET after menu entry
- [DISPLAY] aborts everything with no programming effect (used to exit,
  and as the bail-out on any unexpected screen)
- every button press is verified by re-reading the display and requiring
  it to have changed before the next press

Captures go to captures/NN_<label>/: state.json (raw), decoded.txt, render.png
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid

BASE = "http://raspbnodered.local:8088/api/v1"
CAPDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
MAX_PAGES = 15  # expect 11 menu items; hard stop well above that


def get_json(path):
    with urllib.request.urlopen(f"{BASE}/{path}", timeout=8) as r:
        return json.load(r)


def get_status():
    return get_json("status")["data"]


def get_display():
    """Full state object: chars grid + attrs grid (inverse-video/highlight)."""
    return get_json("display/state")["data"]["state"]


def press(name):
    req = urllib.request.Request(
        f"{BASE}/actions/button",
        data=json.dumps({"name": name}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        resp = json.load(r)
    if not resp.get("success"):
        raise RuntimeError(f"button {name} failed: {resp}")
    print(f"  [pressed {name}]")


def save_capture(index, label, state):
    d = os.path.join(CAPDIR, f"{index:02d}_{label}")
    os.makedirs(d, exist_ok=True)
    json.dump(state, open(os.path.join(d, "state.json"), "w"))
    lines, unknown = decode_grid(state["chars"])
    with open(os.path.join(d, "decoded.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
        if unknown:
            f.write("\n# unknown glyphs: " + ", ".join(f"0x{c:02X}" for c in sorted(unknown)) + "\n")
    with urllib.request.urlopen(f"{BASE}/display/render.png", timeout=8) as r:
        open(os.path.join(d, "render.png"), "wb").write(r.read())
    print(f"  saved {index:02d}_{label}: " + " / ".join(l.strip() for l in lines if l.strip())[:100])
    return lines


def wait_for_change(before, tries=6, delay=1.0):
    """Re-read display until it differs from `before`. Returns new grid or None."""
    for _ in range(tries):
        time.sleep(delay)
        now = get_display()
        if now != before:
            return now
    return None


def bail(reason):
    print(f"ABORT: {reason} — pressing display to cancel out of the menu")
    try:
        press("display")
    finally:
        sys.exit(1)


def main():
    st = get_status()
    if st.get("operatingState") != "standby" or not st.get("recentContact"):
        print(f"NOT SAFE TO START: operatingState={st.get('operatingState')} recentContact={st.get('recentContact')}")
        sys.exit(2)

    os.makedirs(CAPDIR, exist_ok=True)
    splash = get_display()
    save_capture(0, "standby_splash", splash)

    print("entering Set mode...")
    press("set")
    menu_first = wait_for_change(splash)
    if menu_first is None:
        bail("display did not change after SET press")

    pages = [menu_first]
    save_capture(1, "menu_page", menu_first)

    for i in range(2, MAX_PAGES + 2):
        press("right")
        nxt = wait_for_change(pages[-1])
        if nxt is None:
            bail(f"display did not change after right press (page {i})")
        if nxt == menu_first:
            print(f"wrap detected after {len(pages)} pages")
            break
        if nxt == splash:
            bail("unexpectedly back at splash screen mid-traversal")
        pages.append(nxt)
        save_capture(i, "menu_page", nxt)
    else:
        bail(f"no wrap after {MAX_PAGES} pages — unexpected menu size")

    print("exiting via DISPLAY (no programming effect)...")
    press("display")
    back = wait_for_change(pages[-1])
    if back == splash:
        print("OK: back at standby splash screen, menu exited cleanly")
    else:
        print("WARNING: post-exit screen is not the original splash — inspect:")
        lines, _ = decode_grid(back or pages[-1])
        for l in lines:
            print("   |" + l + "|")
        sys.exit(3)

    print(f"\nDONE: {len(pages)} top-level menu pages captured in {CAPDIR}")


if __name__ == "__main__":
    main()
