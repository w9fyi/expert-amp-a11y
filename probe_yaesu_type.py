#!/usr/bin/env python3
"""Read-only probe: select YAESU in the CAT sub-page, inspect its baud/TYPE
page (which showed 'TYPE: ALL' for KENWOOD/FLEX-RADIO -- want to see what
values TYPE offers for YAESU, since the original scaffold's own comment said
'YAESU (contains Band Data)'). Never presses SET a second time; cancels via
DISPLAY only, same non-destructive style as every other probe so far.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, save_capture, wait_for_change, CAPDIR, preflight
from capture_subpage import highlighted_text, bail

CAT_RIGHTS = 2
TO_YAESU_RIGHTS = 2  # ICOM(entry) -> KENWOOD -> YAESU


def show(label, state):
    lines, _ = decode_grid(state["chars"])
    hi = highlighted_text(state)
    print(f"\n--- {label} ---")
    for l in lines:
        if l.strip():
            print(f"   |{l}|")
    print(f"   highlighted: {hi!r}")
    return lines, hi


def main():
    st = get_status()
    if not preflight(st)[0]:
        print(f"NOT SAFE: {preflight(st)[1]}")
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
    for i in range(TO_YAESU_RIGHTS):
        press("right")
        nxt = wait_for_change(cur_sub)
        if nxt is None:
            bail(f"no change navigating to YAESU, step {i+1}")
        cur_sub = nxt
    _, hi = show("cursor on YAESU", cur_sub)
    if hi.upper() != "YAESU":
        bail(f"expected YAESU highlighted, got {hi!r}")

    print("\npressing SET on YAESU (viewing its page, not committing)...")
    press("set")
    yaesu_page = wait_for_change(cur_sub, tries=8, delay=1.0)
    if yaesu_page is None:
        yaesu_page = get_display()
    lines, hi = show("YAESU page", yaesu_page)

    d = os.path.join(CAPDIR, "cat_yaesu")
    os.makedirs(d, exist_ok=True)
    save_capture(0, "cat_yaesu_page", yaesu_page)

    # Probe whether TYPE is independently reachable via left/right from here
    print("\nprobing further right presses (looking for a TYPE selector)...")
    probe_cur = yaesu_page
    for i in range(1, 5):
        press("right")
        nxt = wait_for_change(probe_cur, tries=6, delay=1.0)
        if nxt is None:
            print(f"  (no change after right press {i} -- stopping probe here)")
            break
        _, hi = show(f"YAESU page after {i} right", nxt)
        save_capture(i, f"cat_yaesu_right{i}", nxt)
        probe_cur = nxt

    print("\ncancelling via DISPLAY (no commit)...")
    press("display")
    back = wait_for_change(probe_cur, tries=8, delay=1.0)
    if back is None:
        back = get_display()
    lines2, _ = decode_grid(back["chars"])
    for l in lines2:
        if l.strip():
            print(f"   |{l}|")
    if back == splash:
        print("\nOK: back at original splash, nothing committed.")
    else:
        print("\nNOTE: not byte-identical to the very first splash read (may just be a different idle screen or transient field) -- verifying CAT brand text above is still FLEX.")


if __name__ == "__main__":
    main()
