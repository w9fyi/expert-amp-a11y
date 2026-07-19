#!/usr/bin/env python3
"""Read-only probe: from the YAESU model grid, select BAND-DATA and see what
follows (a baud page like KENWOOD/FLEX-RADIO, straight commit, or something
else). Never presses SET a second time; cancels via DISPLAY only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, save_capture, wait_for_change, CAPDIR
from capture_subpage import highlighted_text, bail

CAT_RIGHTS = 2
TO_YAESU_RIGHTS = 2       # ICOM(entry) -> KENWOOD -> YAESU
TO_BAND_DATA_RIGHTS = 1   # FT991(entry) -> BAND-DATA, per probe_yaesu_type.py


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

    press("set")
    yaesu_page = wait_for_change(cur_sub, tries=8, delay=1.0)
    if yaesu_page is None:
        yaesu_page = get_display()
    _, hi = show("YAESU model grid entry", yaesu_page)

    cur_model = yaesu_page
    for i in range(TO_BAND_DATA_RIGHTS):
        press("right")
        nxt = wait_for_change(cur_model, tries=6, delay=1.0)
        if nxt is None:
            bail(f"no change navigating to BAND-DATA, step {i+1}")
        cur_model = nxt
    _, hi = show("cursor on BAND-DATA", cur_model)
    if hi.upper() != "BAND-DATA":
        bail(f"expected BAND-DATA highlighted, got {hi!r}")

    print("\npressing SET on BAND-DATA (viewing next page, not committing)...")
    press("set")
    next_page = wait_for_change(cur_model, tries=8, delay=1.0)
    if next_page is None:
        next_page = get_display()
    lines, hi = show("page after SET on BAND-DATA", next_page)

    d = os.path.join(CAPDIR, "cat_band_data")
    os.makedirs(d, exist_ok=True)
    save_capture(0, "cat_band_data_page", next_page)

    print("\ncancelling via DISPLAY (no commit)...")
    press("display")
    back = wait_for_change(next_page, tries=8, delay=1.0)
    if back is None:
        back = get_display()
    lines2, _ = decode_grid(back["chars"])
    for l in lines2:
        if l.strip():
            print(f"   |{l}|")

    # keep cancelling until back to a status-bar-bearing screen, to check CAT brand
    attempts = 0
    while attempts < 3:
        fields_found = any(
            "CAT" in [f.strip() for f in l.split("|")] and "BAND" in [f.strip() for f in l.split("|")]
            for l in lines2
        )
        if fields_found:
            break
        press("display")
        back = wait_for_change(back, tries=6, delay=1.0) or get_display()
        lines2, _ = decode_grid(back["chars"])
        for l in lines2:
            if l.strip():
                print(f"   |{l}|")
        attempts += 1

    if back == splash:
        print("\nOK: back at original splash, nothing committed.")
    else:
        print("\nCheck CAT brand text above -- should still read FLEX.")


if __name__ == "__main__":
    main()
