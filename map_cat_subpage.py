#!/usr/bin/env python3
"""Read-only exploration of the CAT sub-page's brand-grid layout.

Never presses SET inside the sub-page -- only left/right, each verified by a
display re-read before the next press. Exit is always via DISPLAY (proven
non-committing for CONFIRM-type sub-pages). Goal: find the traversal order
through the 9-item grid (SPE/ICOM/KENWOOD/YAESU/TEN-TEC/FLEX-RADIO/ELECRAFT/
NONE/EXIT) so a future automated button can navigate deterministically.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, save_capture, wait_for_change, CAPDIR
from capture_subpage import highlighted_text, bail

CAT_RIGHTS = 2  # CONFIG -> ANTENNA -> CAT, per MENU_MAP.md traversal order
MAX_PROBE = 12


def show(label, state):
    lines, unknown = decode_grid(state["chars"])
    hi = highlighted_text(state)
    print(f"\n--- {label} ---")
    for l in lines:
        if l.strip():
            print(f"   |{l}|")
    print(f"   highlighted: {hi!r}")
    return hi


def main():
    st = get_status()
    if st.get("operatingState") != "standby" or not st.get("recentContact"):
        print(f"NOT SAFE: operatingState={st.get('operatingState')} recentContact={st.get('recentContact')}")
        sys.exit(2)

    splash = get_display()
    splash_lines, _ = decode_grid(splash["chars"])
    print("splash status bar (for ground-truth current CAT brand):")
    for l in splash_lines:
        if l.strip():
            print(f"   |{l}|")

    print("\nentering Set mode...")
    press("set")
    cur = wait_for_change(splash)
    if cur is None:
        bail("no change after SET (menu entry)")

    for i in range(CAT_RIGHTS):
        press("right")
        nxt = wait_for_change(cur)
        if nxt is None:
            bail(f"no change after right press {i+1}")
        cur = nxt

    hi = highlighted_text(cur)
    print(f"\ntop menu, highlighted after {CAT_RIGHTS} rights: {hi!r}")
    if "cat" not in hi.lower():
        bail(f"expected CAT highlighted, got {hi!r}")

    lines = decode_grid(cur["chars"])[0]
    legend = lines[-1] if lines else ""
    print(f"legend row: {legend!r}")
    if "confirm" not in legend.lower():
        bail(f"legend does not say CONFIRM: {legend!r}")

    press("set")
    sub = wait_for_change(cur)
    if sub is None:
        bail("no change after SET (sub-page entry)")

    d = os.path.join(CAPDIR, "cat_map")
    os.makedirs(d, exist_ok=True)

    entry_hi = show("entry (0 presses)", sub)
    save_capture(0, "cat_map_entry", sub)

    trail = [("entry", entry_hi)]
    cur_sub = sub
    seen = {entry_hi}
    for i in range(1, MAX_PROBE + 1):
        press("right")
        nxt = wait_for_change(cur_sub)
        if nxt is None:
            bail(f"no change after right press {i} inside CAT sub-page")
        hi = show(f"after {i} right", nxt)
        save_capture(i, f"cat_map_right{i}", nxt)
        trail.append((f"right{i}", hi))
        cur_sub = nxt
        if hi == entry_hi:
            print(f"\nwrap detected after {i} right presses")
            break
    else:
        print(f"\nNOTE: no wrap detected after {MAX_PROBE} presses -- inspect trail below")

    print("\nexiting via DISPLAY (no programming effect expected)...")
    press("display")
    back = wait_for_change(cur_sub)
    if back == splash:
        print("OK: back at standby splash, nothing committed")
    else:
        lines, _ = decode_grid((back or cur_sub)["chars"])
        print("NOTE: post-exit screen is not the original splash -- inspect:")
        for l in lines:
            print("   |" + l + "|")
        sys.exit(3)

    print("\n=== SUMMARY (label: highlighted text) ===")
    for label, hi in trail:
        print(f"  {label:10s}: {hi!r}")


if __name__ == "__main__":
    main()
