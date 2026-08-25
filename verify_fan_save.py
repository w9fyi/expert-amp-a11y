#!/usr/bin/env python3
"""Verify FAN NOISE save-commit behavior with a same-value resave (NORMAL->SAVE->SET).

Since the amp is already in NORMAL, this is a no-op resave: worst case if SET
turns out to apply/stage differently than expected, the value written back is
identical to the value already active. Confirms whether SET on SAVE commits
and returns to splash on its own, or leaves a confirmation screen needing
DISPLAY to dismiss.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, save_capture, wait_for_change, CAPDIR, preflight
from capture_subpage import highlighted_text, bail

FAN_RIGHTS = 11


def show(label, state):
    lines, _ = decode_grid(state["chars"])
    hi = highlighted_text(state)
    print(f"\n--- {label} ---")
    for l in lines:
        if l.strip():
            print(f"   |{l}|")
    print(f"   highlighted: {hi!r}")
    return hi


def main():
    st = get_status()
    if not preflight(st)[0]:
        print(f"NOT SAFE: {preflight(st)[1]}")
        sys.exit(2)
    print(f"pre-check: fan-relevant status ok, operatingState={st.get('operatingState')}")

    splash = get_display()
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
    if "fan noise" not in hi.lower():
        bail(f"expected FAN NOISE highlighted, got {hi!r}")

    press("set")
    sub = wait_for_change(cur)
    if sub is None:
        bail("no change after SET (sub-page entry)")

    entry_hi = show("entry", sub)
    if "normal" not in entry_hi.lower():
        bail(f"expected NORMAL highlighted at entry (current mode), got {entry_hi!r} -- aborting, not the no-op case this script assumes")

    press("right")  # NORMAL -> SAVE
    on_save = wait_for_change(sub)
    if on_save is None:
        bail("no change after right (NORMAL -> SAVE)")
    save_hi = show("on SAVE", on_save)
    if save_hi.strip().upper() != "SAVE":
        bail(f"expected SAVE highlighted, got {save_hi!r}")

    print("\npressing SET on SAVE (same-value resave: NORMAL -> NORMAL)...")
    press("set")
    after_set = wait_for_change(on_save, tries=8, delay=1.0)
    if after_set is None:
        print("NOTE: display did not change within timeout after SET on SAVE")
        after_set = get_display()
    show("after SET on SAVE", after_set)

    if after_set == splash:
        print("\nRESULT: SET on SAVE committed and returned straight to splash (no DISPLAY dismiss needed).")
    else:
        print("\nRESULT: SET on SAVE did NOT return to splash directly -- pressing DISPLAY to dismiss/exit.")
        press("display")
        back2 = wait_for_change(after_set, tries=8, delay=1.0)
        show("after DISPLAY dismiss", back2 or after_set)
        if back2 == splash:
            print("Confirmed: DISPLAY dismiss returned to splash after the save committed.")
        else:
            print("WARNING: still not back at splash -- inspect manually before pressing anything else.")
            sys.exit(3)

    final_status = get_status()
    print(f"\npost-save amp status: operatingState={final_status.get('operatingState')} warningCode={final_status.get('warningCode')}")
    print("Done. Fan mode was resaved as NORMAL (no functional change expected).")


if __name__ == "__main__":
    main()
