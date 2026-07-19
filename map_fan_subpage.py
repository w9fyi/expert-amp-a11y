#!/usr/bin/env python3
"""Read-only exploration of the FAN NOISE sub-page's QUIET/NORMAL/SAVE layout.

Never presses SET inside the sub-page — only left/right, each verified by a
display re-read before the next press. Exit is always via DISPLAY (proven
non-committing for CONFIRM-type sub-pages). Goal: find the exact left/right
distance from sub-page entry to QUIET, to NORMAL, and to SAVE so a future
automated button can navigate deterministically.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, save_capture, wait_for_change, CAPDIR
from capture_subpage import highlighted_text, bail

FAN_RIGHTS = 11  # CONFIG -> ... -> FAN NOISE, per MENU_MAP.md


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
    print("entering Set mode...")
    press("set")
    cur = wait_for_change(splash)
    if cur is None:
        bail("no change after SET (menu entry)")

    for i in range(FAN_RIGHTS):
        press("right")
        nxt = wait_for_change(cur)
        if nxt is None:
            bail(f"no change after right press {i+1}")
        cur = nxt

    hi = highlighted_text(cur)
    print(f"top menu, highlighted after {FAN_RIGHTS} rights: {hi!r}")
    if "fan noise" not in hi.lower():
        bail(f"expected FAN NOISE highlighted, got {hi!r}")

    press("set")
    sub = wait_for_change(cur)
    if sub is None:
        bail("no change after SET (sub-page entry)")

    entry_hi = show("entry (0 presses)", sub)
    d = os.path.join(CAPDIR, "fan_map")
    os.makedirs(d, exist_ok=True)
    save_capture(0, "fan_map_entry", sub)

    trail = [("entry", sub, entry_hi)]

    # Probe left up to 3 times
    cur_sub = sub
    for i in range(1, 4):
        press("left")
        nxt = wait_for_change(cur_sub)
        if nxt is None:
            bail(f"no change after left press {i} inside sub-page")
        hi = show(f"after {i} left", nxt)
        save_capture(i, f"fan_map_left{i}", nxt)
        trail.append((f"left{i}", nxt, hi))
        cur_sub = nxt

    # Return to entry point by pressing right the same number of times,
    # then continue right past entry to probe the other direction.
    for i in range(1, 4):
        press("right")
        nxt = wait_for_change(cur_sub)
        if nxt is None:
            bail(f"no change after right (return) press {i}")
        hi = show(f"after left3 then {i} right (return leg)", nxt)
        save_capture(10 + i, f"fan_map_return{i}", nxt)
        trail.append((f"return{i}", nxt, hi))
        cur_sub = nxt

    for i in range(1, 4):
        press("right")
        nxt = wait_for_change(cur_sub)
        if nxt is None:
            bail(f"no change after right (forward) press {i}")
        hi = show(f"after entry then further {i} right (forward leg)", nxt)
        save_capture(20 + i, f"fan_map_right{i}", nxt)
        trail.append((f"right{i}", nxt, hi))
        cur_sub = nxt

    print("\nexiting via DISPLAY (no programming effect expected)...")
    press("display")
    back = wait_for_change(cur_sub)
    if back == splash:
        print("OK: back at standby splash, nothing committed")
    else:
        lines, _ = decode_grid((back or cur_sub)["chars"])
        print("NOTE: post-exit screen is not the original splash — inspect:")
        for l in lines:
            print("   |" + l + "|")
        sys.exit(3)

    print("\n=== SUMMARY (label: highlighted text) ===")
    for label, _, hi in trail:
        print(f"  {label:10s}: {hi!r}")


if __name__ == "__main__":
    main()
