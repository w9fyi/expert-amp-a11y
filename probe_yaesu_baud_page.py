#!/usr/bin/env python3
"""Read-only: navigate into CAT -> YAESU -> FT991's baud sub-page (current
CAT brand as of 2026-08-02, confirmed at 1200 baud) to see its exact layout
and control legend, then cancel via DISPLAY without ever pressing SET a
second time. Goal: learn how the baud value is selected/cycled before
attempting to actually change it to 19200.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, wait_for_change
from capture_subpage import highlighted_text, bail

CAT_RIGHTS = 2
TO_YAESU_RIGHTS_MAX = 10


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
    while "yaesu" not in hi.lower() and presses < TO_YAESU_RIGHTS_MAX:
        press("right")
        nxt = wait_for_change(cur_sub)
        if nxt is None:
            bail(f"no change navigating to YAESU, step {presses+1}")
        cur_sub = nxt
        hi = highlighted_text(cur_sub)
        presses += 1
    print(f"reached YAESU after {presses} right press(es)")

    print("\npressing SET on YAESU (entering model grid)...")
    press("set")
    grid = wait_for_change(cur_sub, tries=8, delay=1.0)
    if grid is None:
        grid = get_display()
    _, hi0 = show("model grid entry", grid)

    cur_grid = grid
    hi = highlighted_text(cur_grid)
    presses2 = 0
    while "ft991" not in hi.lower() and presses2 < 18:
        press("right")
        nxt = wait_for_change(cur_grid, tries=6, delay=1.0)
        if nxt is None:
            bail(f"no change navigating to FT991, step {presses2+1}")
        cur_grid = nxt
        hi = highlighted_text(cur_grid)
        presses2 += 1
    print(f"reached FT991 after {presses2} right press(es)")
    if "ft991" not in hi.lower() or "band-data" in hi.lower():
        bail(f"expected FT991 highlighted, got {hi!r}")

    print("\npressing SET on FT991 to view its baud page (not committing -- will cancel)...")
    press("set")
    baud_page = wait_for_change(cur_grid, tries=8, delay=1.0)
    if baud_page is None:
        baud_page = get_display()
    lines, hi = show("FT991 baud page", baud_page)
    print(f"\n>>> Currently shown/highlighted on baud page: {hi!r} <<<")

    print("\ncancelling via DISPLAY (no commit)...")
    press("display")
    back = wait_for_change(baud_page, tries=6, delay=1.0)
    if back is None:
        back = get_display()
    lines2, _unknown = decode_grid(back["chars"])
    for l in lines2:
        if l.strip():
            print(f"   |{l}|")
    if back == splash:
        print("\nOK: back at original splash, nothing committed.")
    else:
        print("\nNOTE: not exactly the original splash bytes -- checking status bar text above.")


if __name__ == "__main__":
    main()
