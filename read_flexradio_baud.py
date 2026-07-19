#!/usr/bin/env python3
"""Read-only: navigate into CAT -> FLEX-RADIO's own baud sub-page to see
what baud is currently shown for it, then cancel via DISPLAY without ever
pressing SET a second time. This records the value to restore to before any
real CAT brand change is committed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, wait_for_change
from capture_subpage import highlighted_text, bail

CAT_RIGHTS = 2
TO_FLEX_RADIO_RIGHTS = 4  # ICOM(entry) -> KENWOOD -> YAESU -> TEN-TEC -> FLEX-RADIO


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
    if st.get("operatingState") != "standby" or not st.get("recentContact"):
        print(f"NOT SAFE: operatingState={st.get('operatingState')} recentContact={st.get('recentContact')}")
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
    _, entry_hi = show("CAT sub-page entry", sub)

    cur_sub = sub
    for i in range(TO_FLEX_RADIO_RIGHTS):
        press("right")
        nxt = wait_for_change(cur_sub)
        if nxt is None:
            bail(f"no change navigating to FLEX-RADIO, step {i+1}")
        cur_sub = nxt
    _, hi = show("cursor on FLEX-RADIO", cur_sub)
    if hi.upper() != "FLEX-RADIO":
        bail(f"expected FLEX-RADIO highlighted, got {hi!r}")

    print("\npressing SET on FLEX-RADIO to view its baud page (not committing -- will cancel)...")
    press("set")
    baud_page = wait_for_change(cur_sub, tries=8, delay=1.0)
    if baud_page is None:
        baud_page = get_display()
    lines, hi = show("FLEX-RADIO baud page", baud_page)
    print(f"\n>>> Currently shown baud for FLEX-RADIO: {hi!r} <<<")

    print("\ncancelling via DISPLAY (no commit)...")
    press("display")
    back = wait_for_change(baud_page, tries=6, delay=1.0)
    if back is None:
        back = get_display()
    lines2, _ = decode_grid(back["chars"])
    for l in lines2:
        if l.strip():
            print(f"   |{l}|")
    if back == splash:
        print("\nOK: back at original splash, nothing committed.")
    else:
        print("\nNOTE: not exactly the original splash bytes -- checking status bar text above.")


if __name__ == "__main__":
    main()
