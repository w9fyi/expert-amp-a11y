#!/usr/bin/env python3
"""Read-only probe: find where the YAESU model grid's cursor actually sits
today (expected BAND-DATA, per the live catModeRunner0001 failure on
2026-08-02), then test whether a single RIGHT press wraps around the list
back to FT100 or gets stuck (no change). Never presses SET a second time
inside the model grid -- only views and cancels via DISPLAY, same
non-destructive style as every other probe in this directory.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, save_capture, wait_for_change, CAPDIR
from capture_subpage import highlighted_text, bail

CAT_RIGHTS = 2


def show(label, state):
    lines, _unknown = decode_grid(state["chars"])
    hi = highlighted_text(state)
    print(f"\n--- {label} ---")
    for l in lines:
        if l.strip():
            print(f"   |{l}|")
    print(f"   highlighted: {hi!r}")
    return lines, hi


def main():
    st = get_status()
    if st.get("operatingState") != "standby":
        print(f"NOT SAFE: operatingState={st.get('operatingState')}")
        sys.exit(2)

    splash = get_display()
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
    if "cat" not in highlighted_text(cur).lower():
        bail(f"expected CAT highlighted, got {highlighted_text(cur)!r}")

    press("set")
    sub = wait_for_change(cur)
    if sub is None:
        bail("no change after SET (sub-page entry)")

    cur_sub = sub
    hi = highlighted_text(cur_sub)
    presses = 0
    while "yaesu" not in hi.lower() and presses < 10:
        press("right")
        nxt = wait_for_change(cur_sub)
        if nxt is None:
            bail(f"no change navigating to YAESU, step {presses+1}")
        cur_sub = nxt
        hi = highlighted_text(cur_sub)
        presses += 1
    print(f"reached YAESU after {presses} right press(es)")
    if "yaesu" not in hi.lower():
        bail(f"never reached YAESU, got {hi!r}")

    print("\npressing SET on YAESU (entering model grid)...")
    press("set")
    grid = wait_for_change(cur_sub, tries=8, delay=1.0)
    if grid is None:
        grid = get_display()
    _, hi0 = show("model grid entry (today's actual default)", grid)

    print("\npressing RIGHT once from here...")
    press("right")
    after_right = wait_for_change(grid, tries=6, delay=1.0)
    if after_right is None:
        print("   NO CHANGE -- right press did nothing (stuck at end, no wrap)")
        after_right = grid
    else:
        _, hi1 = show("after 1 right press", after_right)

    print("\npressing LEFT once to return...")
    press("left")
    back_left = wait_for_change(after_right, tries=6, delay=1.0)
    if back_left is None:
        print("   NO CHANGE after left press")
        back_left = after_right
    else:
        _, hi2 = show("after 1 left press (should match original)", back_left)

    print("\ncancelling via DISPLAY repeatedly back to splash (no commit)...")
    cur_back = back_left
    for attempt in range(4):
        press("display")
        nxt = wait_for_change(cur_back, tries=6, delay=1.0)
        cur_back = nxt if nxt is not None else get_display()
        lines, _unknown = decode_grid(cur_back["chars"])
        for l in lines:
            if l.strip():
                print(f"   |{l}|")
        if cur_back == splash:
            print("\nOK: back at original splash, nothing committed.")
            break
    else:
        print("\nNOTE: did not confirm byte-identical splash after 4 DISPLAY presses -- check CAT brand text above.")


if __name__ == "__main__":
    main()
