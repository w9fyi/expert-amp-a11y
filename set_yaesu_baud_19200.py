#!/usr/bin/env python3
"""LIVE COMMIT: navigate CAT -> YAESU -> FT991 -> baud page and select
19200, confirming to commit. Display-verified at every step; aborts via
DISPLAY (no programming effect per manual) on any mismatch rather than
guessing. Re-enters the baud page afterward (read-only, cancels) to confirm
the new value actually stuck.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, wait_for_change
from capture_subpage import highlighted_text, bail

CAT_RIGHTS = 2
TARGET_MODEL = "FT991"
TARGET_BAUD = "19200"


def show(label, state):
    lines, _unknown = decode_grid(state["chars"])
    hi = highlighted_text(state)
    print(f"\n--- {label} ---")
    for l in lines:
        if l.strip():
            print(f"   |{l}|")
    print(f"   highlighted: {hi!r}")
    return lines, hi


def navigate_to(state, target, max_presses):
    cur = state
    hi = highlighted_text(cur)
    presses = 0
    t = target.upper()
    while t not in hi.upper() and presses < max_presses:
        press("right")
        nxt = wait_for_change(cur, tries=6, delay=1.0)
        if nxt is None:
            bail(f"no change after right press {presses+1} (looking for {target})")
        cur = nxt
        hi = highlighted_text(cur)
        presses += 1
    if t not in hi.upper():
        bail(f"never reached {target} after {presses} rights, last seen {hi!r}")
    print(f"   reached {target!r} after {presses} right press(es)")
    return cur


def enter_baud_page():
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

    on_yaesu = navigate_to(sub, "YAESU", 10)
    press("set")
    grid = wait_for_change(on_yaesu, tries=8, delay=1.0)
    if grid is None:
        bail("no change entering YAESU model grid")

    on_model = navigate_to(grid, TARGET_MODEL, 18)
    hi = highlighted_text(on_model)
    if "band-data" in hi.lower():
        bail(f"navigation landed on BAND-DATA instead of {TARGET_MODEL}, aborting")

    press("set")
    baud_page = wait_for_change(on_model, tries=8, delay=1.0)
    if baud_page is None:
        bail(f"no change entering {TARGET_MODEL} baud page")
    return splash, baud_page


def cancel_to_splash(from_state, splash):
    cur = from_state
    for attempt in range(4):
        press("display")
        nxt = wait_for_change(cur, tries=6, delay=1.0)
        cur = nxt if nxt is not None else get_display()
        lines, _unknown = decode_grid(cur["chars"])
        txt = "\n".join(lines).upper()
        if "CAT" in txt and "BAND" in txt:
            return cur
    return cur


def main():
    print("=== Step 1: verify current baud (read-only) ===")
    splash, baud_page = enter_baud_page()
    _, hi_before = show(f"{TARGET_MODEL} baud page (before)", baud_page)
    print(f"\ncurrent baud: {hi_before!r}")

    if hi_before.upper() == TARGET_BAUD:
        print(f"\nAlready {TARGET_BAUD} -- cancelling with no change.")
        cancel_to_splash(baud_page, splash)
        return

    print(f"\n=== Step 2: navigate to {TARGET_BAUD} ===")
    on_target = navigate_to(baud_page, TARGET_BAUD, 8)
    _, hi_check = show("cursor before commit", on_target)
    if hi_check.upper() != TARGET_BAUD:
        bail(f"expected {TARGET_BAUD} highlighted before commit, got {hi_check!r}")

    print(f"\n=== Step 3: COMMITTING -- pressing SET on {TARGET_BAUD} ===")
    press("set")
    committed = wait_for_change(on_target, tries=8, delay=1.0)
    if committed is None:
        bail("no change / commit did not settle after SET on baud value")
    lines, hi_after = show("after commit", committed)

    print("\nbacking out to splash...")
    back = cancel_to_splash(committed, splash)
    lines2, _unknown = decode_grid(back["chars"])
    for l in lines2:
        if l.strip():
            print(f"   |{l}|")

    print("\n=== Step 4: re-enter baud page read-only to verify it stuck ===")
    splash2, baud_page2 = enter_baud_page()
    _, hi_verify = show(f"{TARGET_MODEL} baud page (verify)", baud_page2)
    cancel_to_splash(baud_page2, splash2)

    if hi_verify.upper() == TARGET_BAUD:
        print(f"\nCONFIRMED: {TARGET_MODEL} baud is now {TARGET_BAUD}.")
    else:
        print(f"\nWARNING: expected {TARGET_BAUD} on verify, got {hi_verify!r} -- check front panel.")


if __name__ == "__main__":
    main()
