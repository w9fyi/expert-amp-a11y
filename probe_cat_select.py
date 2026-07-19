#!/usr/bin/env python3
"""Probe: what happens right after pressing SET on KENWOOD in the CAT
sub-page? Navigates to KENWOOD (read-only so far, same as map_cat_subpage.py),
presses SET exactly once, captures whatever screen appears, then immediately
cancels via DISPLAY (repeated if needed to get all the way back to splash)
without ever pressing SET again. Verifies the amp's actual CAT brand
(read from the splash status bar) is unchanged afterward.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, save_capture, wait_for_change, CAPDIR
from capture_subpage import highlighted_text, bail

CAT_RIGHTS = 2


def show(label, state):
    lines, _ = decode_grid(state["chars"])
    hi = highlighted_text(state)
    print(f"\n--- {label} ---")
    for l in lines:
        if l.strip():
            print(f"   |{l}|")
    print(f"   highlighted: {hi!r}")
    return lines, hi


def cat_brand_from_splash(splash_state):
    lines, _ = decode_grid(splash_state["chars"])
    for l in lines:
        if "CAT" in l.upper() and "|" not in l.upper().replace("CAT", ""):
            pass
    # status bar is two lines: header row and value row, aligned by column
    header = None
    values = None
    for i, l in enumerate(lines):
        if "CAT" in l.upper() and "BAND" in l.upper():
            header = l
            values = lines[i + 1] if i + 1 < len(lines) else ""
            break
    if header is None:
        return None
    col = header.upper().index("CAT")
    return values[col:col + 6].strip() if values else None


def main():
    st = get_status()
    if st.get("operatingState") != "standby" or not st.get("recentContact"):
        print(f"NOT SAFE: operatingState={st.get('operatingState')} recentContact={st.get('recentContact')}")
        sys.exit(2)

    splash = get_display()
    before_brand = cat_brand_from_splash(splash)
    print(f"CAT brand before test (from splash status bar): {before_brand!r}")

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
    if "cat" not in hi.lower():
        bail(f"expected CAT highlighted, got {hi!r}")

    press("set")
    sub = wait_for_change(cur)
    if sub is None:
        bail("no change after SET (sub-page entry)")

    _, entry_hi = show("CAT sub-page entry", sub)
    if entry_hi.upper() != "ICOM":
        print(f"NOTE: entry highlight is {entry_hi!r}, expected ICOM per earlier mapping -- proceeding cautiously")

    # navigate to KENWOOD (1 right from ICOM per map_cat_subpage.py)
    press("right")
    on_kenwood = wait_for_change(sub)
    if on_kenwood is None:
        bail("no change navigating to KENWOOD")
    _, hi = show("cursor on KENWOOD", on_kenwood)
    if hi.upper() != "KENWOOD":
        bail(f"expected KENWOOD highlighted, got {hi!r}")

    print("\npressing SET on KENWOOD (the untested action)...")
    press("set")
    after_set = wait_for_change(on_kenwood, tries=8, delay=1.0)
    if after_set is None:
        print("NOTE: no display change detected within timeout -- reading display directly")
        after_set = get_display()
    lines, hi = show("after SET on KENWOOD", after_set)

    print("\nimmediately cancelling via DISPLAY (repeat until back at splash, never pressing SET again)...")
    cur_screen = after_set
    for attempt in range(4):
        press("display")
        nxt = wait_for_change(cur_screen, tries=6, delay=1.0)
        if nxt is None:
            print(f"  (no change on cancel attempt {attempt+1} -- reading directly)")
            nxt = get_display()
        lines, hi = show(f"after DISPLAY cancel #{attempt+1}", nxt)
        cur_screen = nxt
        if nxt == splash:
            print("\nBack at the exact original splash screen.")
            break
    else:
        print("\nNOTE: did not detect an exact match to the original splash after 4 DISPLAY presses -- checking status bar directly")

    final_lines, _ = decode_grid(cur_screen["chars"])
    after_brand = cat_brand_from_splash(cur_screen) if "STANDBY" in "\n".join(final_lines).upper() or cur_screen == splash else None
    if after_brand is None:
        # force back to splash-readable state isn't guaranteed; just re-read live display fresh
        fresh = get_display()
        after_brand = cat_brand_from_splash(fresh)
        final_lines, _ = decode_grid(fresh["chars"])

    print(f"\nCAT brand after test (from splash status bar): {after_brand!r}")
    st2 = get_status()
    print(f"status: operatingState={st2.get('operatingState')} recentContact={st2.get('recentContact')} warningCode={st2.get('warningCode')}")

    if before_brand and after_brand and before_brand.upper() == after_brand.upper():
        print("\nCONFIRMED: CAT brand unchanged by this probe.")
    else:
        print(f"\nWARNING: CAT brand looks different ({before_brand!r} -> {after_brand!r}) -- inspect manually before doing anything else.")


if __name__ == "__main__":
    main()
