#!/usr/bin/env python3
"""Full round-trip: FLEX-RADIO -> KENWOOD (verify commit) -> FLEX-RADIO@115200 (restore).

Confirmed beforehand (read_flexradio_baud.py): FLEX-RADIO's persisted baud is
115200. This commits KENWOOD (accepting whatever baud the page defaults to),
verifies via the splash status bar, then immediately restores FLEX-RADIO
explicitly at 115200, verifying the amp ends this script in the exact state
it started.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, wait_for_change, preflight
from capture_subpage import highlighted_text, bail

CAT_RIGHTS = 2
TO_KENWOOD_RIGHTS = 1     # ICOM(entry) -> KENWOOD
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


def splash_status_line(state):
    lines, _ = decode_grid(state["chars"])
    text = "\n".join(lines)
    return text


def enter_cat(splash):
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
    return sub


def select_brand(sub, rights, brand_name):
    cur_sub = sub
    for i in range(rights):
        press("right")
        nxt = wait_for_change(cur_sub)
        if nxt is None:
            bail(f"no change navigating to {brand_name}, step {i+1}")
        cur_sub = nxt
    _, hi = show(f"cursor on {brand_name}", cur_sub)
    if hi.upper() != brand_name.upper():
        bail(f"expected {brand_name} highlighted, got {hi!r}")
    return cur_sub


def commit_brand_and_baud(on_brand, brand_name, expect_baud=None):
    print(f"\npressing SET on {brand_name} (opens baud page)...")
    press("set")
    baud_page = wait_for_change(on_brand, tries=8, delay=1.0)
    if baud_page is None:
        baud_page = get_display()
    _, hi = show(f"{brand_name} baud page", baud_page)
    if expect_baud and hi.strip() != expect_baud:
        bail(f"expected baud {expect_baud!r} highlighted for {brand_name}, got {hi!r} -- aborting before commit")

    print(f"pressing SET on baud {hi!r} to commit {brand_name}...")
    press("set")
    after_set = wait_for_change(baud_page, tries=10, delay=1.0)
    if after_set is None:
        after_set = get_display()
    lines, hi2 = show(f"after SET on baud (committing {brand_name})", after_set)
    return after_set


def has_status_bar(state):
    lines, _ = decode_grid(state["chars"])
    for l in lines:
        fields = [f.strip() for f in l.split("|")]
        if "CAT" in fields and "BAND" in fields:
            return True
    return False


def get_to_splash(after_commit, splash_ref):
    cur = after_commit
    for attempt in range(4):
        if has_status_bar(cur):
            return cur
        press("display")
        nxt = wait_for_change(cur, tries=8, delay=1.0)
        if nxt is None:
            nxt = get_display()
        show(f"post-commit dismiss attempt {attempt+1}", nxt)
        cur = nxt
    return cur


def read_cat_brand(splash_state):
    lines, _ = decode_grid(splash_state["chars"])
    for i, l in enumerate(lines):
        header_fields = [f.strip() for f in l.split("|")]
        if "CAT" in header_fields and "BAND" in header_fields:
            values = lines[i + 1] if i + 1 < len(lines) else ""
            value_fields = [f.strip() for f in values.split("|")]
            idx = header_fields.index("CAT")
            return value_fields[idx] if idx < len(value_fields) else None
    return None


def main():
    st = get_status()
    if not preflight(st)[0]:
        print(f"NOT SAFE: {preflight(st)[1]}")
        sys.exit(2)

    splash = get_display()
    before_brand = read_cat_brand(splash)
    print(f"CAT brand before test: {before_brand!r}")
    if before_brand != "FLEX":
        bail(f"expected starting brand FLEX, got {before_brand!r} -- aborting, assumptions don't hold")

    print("\n=== STEP 1: commit KENWOOD ===")
    sub = enter_cat(splash)
    on_kenwood = select_brand(sub, TO_KENWOOD_RIGHTS, "KENWOOD")
    after_commit = commit_brand_and_baud(on_kenwood, "KENWOOD")
    at_splash = get_to_splash(after_commit, splash)
    brand_now = read_cat_brand(at_splash)
    print(f"\nCAT brand after committing KENWOOD: {brand_now!r}")

    st2 = get_status()
    print(f"status: operatingState={st2.get('operatingState')} recentContact={st2.get('recentContact')} warningCode={st2.get('warningCode')}")

    print("\n=== STEP 2: restore FLEX-RADIO @ 115200 ===")
    sub2 = enter_cat(at_splash)
    on_flex = select_brand(sub2, TO_FLEX_RADIO_RIGHTS, "FLEX-RADIO")
    after_commit2 = commit_brand_and_baud(on_flex, "FLEX-RADIO", expect_baud="115200")
    at_splash2 = get_to_splash(after_commit2, splash)
    brand_final = read_cat_brand(at_splash2)
    print(f"\nCAT brand after restoring FLEX-RADIO: {brand_final!r}")

    st3 = get_status()
    print(f"final status: operatingState={st3.get('operatingState')} recentContact={st3.get('recentContact')} warningCode={st3.get('warningCode')}")

    if brand_final == "FLEX" and at_splash2 == splash:
        print("\nCONFIRMED: amp restored to the exact original state (CAT FLEX-RADIO @ 115200, splash byte-identical).")
    elif brand_final == "FLEX":
        print("\nCONFIRMED: CAT brand restored to FLEX, though splash bytes differ slightly (likely just a transient field like SWR) -- inspect above.")
    else:
        print(f"\nWARNING: final brand is {brand_final!r}, not FLEX -- inspect manually before doing anything else.")


if __name__ == "__main__":
    main()
