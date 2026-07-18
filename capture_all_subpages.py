#!/usr/bin/env python3
"""Capture the remaining CONFIRM-type Set-mode sub-pages, one at a time.

Hardened policy (after the TEMP toggle finding):
- only enter items whose top-menu legend shows [SET]:CONFIRM
- press NOTHING inside a sub-page except the exit its own legend indicates
- exit choice: legend containing QUIT near SET -> press set; otherwise press
  display; if that lands on neither splash nor top menu it was a view toggle
  (alarms-log style): capture the alternate view too, then follow ITS legend
- after each item, require the standby splash to match the baseline grid
  exactly before starting the next item; any mismatch aborts the whole run
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_menu import get_status, get_display, press, save_capture, wait_for_change, CAPDIR
from capture_subpage import highlighted_text
from decode_display import decode_grid, decode_cell

# (rights after menu entry, expected highlight substring, capture label)
ITEMS = [
    (0,  "CONFIG",    "sub_config"),
    (1,  "ANTENNA",   "sub_antenna"),
    (2,  "CAT",       "sub_cat"),
    (4,  "DISPLAY",   "sub_display"),
    (9,  "TUN ANT",   "sub_tun_ant"),
    (10, "RX",        "sub_rx_ant"),
    (11, "FAN NOISE", "sub_fan_noise"),
]


def legend_of(state):
    chars = state["chars"]
    return ("".join(decode_cell(c) for c in chars[6]) + " " +
            "".join(decode_cell(c) for c in chars[7])).upper()


def show(state, title):
    lines, unknown = decode_grid(state["chars"])
    print(f"    --- {title} ---")
    for r, l in enumerate(lines):
        if l.strip():
            print(f"    {r}: |{l}|")
    hi = highlighted_text(state)
    if hi:
        print(f"    highlighted: {hi!r}")
    if unknown:
        print("    unknown glyphs:", [hex(c) for c in sorted(unknown)])


def fatal(msg):
    print(f"FATAL: {msg}")
    print("Amp may be mid-menu — current screen:")
    try:
        show(get_display(), "current")
    except Exception:
        pass
    sys.exit(1)


def exit_subpage(state, splash, menu_first, label, view_idx=1):
    """Exit a sub-page following its own legend. Returns final screen."""
    leg = legend_of(state)
    if "QUIT" in leg:
        press("set")
    else:
        press("display")
    nxt = wait_for_change(state)
    if nxt is None:
        fatal(f"{label}: no change on exit press")
    if nxt["chars"] == splash["chars"] or nxt["chars"] == menu_first["chars"]:
        return nxt
    # neither splash nor menu: DISPLAY was a view toggle — capture and recurse
    if view_idx > 3:
        fatal(f"{label}: could not find the exit after {view_idx} views")
    print(f"    (alternate view detected in {label})")
    save_capture(view_idx, f"{label}_view{view_idx}", nxt)
    show(nxt, f"{label} alternate view {view_idx}")
    return exit_subpage(nxt, splash, menu_first, label, view_idx + 1)


def main():
    st = get_status()
    if st.get("operatingState") != "standby" or not st.get("recentContact"):
        fatal(f"not safe to start: {st.get('operatingState')}/{st.get('recentContact')}")

    baseline = get_display()
    print("baseline splash captured")

    for rights, expect, label in ITEMS:
        print(f"\n=== {label} ({expect}, {rights} rights) ===")
        press("set")
        cur = wait_for_change(baseline)
        if cur is None:
            fatal(f"{label}: menu did not open")
        menu_first = cur
        for i in range(rights):
            press("right")
            nxt = wait_for_change(cur)
            if nxt is None:
                fatal(f"{label}: no change on right {i+1}")
            cur = nxt

        hi = highlighted_text(cur)
        leg = legend_of(cur)
        if expect.upper() not in hi.upper():
            press("display")
            fatal(f"{label}: expected {expect!r} highlighted, got {hi!r}")
        if "CONFIRM" not in leg:
            press("display")
            fatal(f"{label}: legend is not CONFIRM ({leg.strip()!r}) — refusing SET")

        press("set")
        sub = wait_for_change(cur)
        if sub is None:
            fatal(f"{label}: no change after SET (sub-page entry)")
        save_capture(0, label, sub)
        show(sub, label)

        final = exit_subpage(sub, baseline, menu_first, label)
        if final["chars"] == menu_first["chars"]:
            press("display")  # leave the top menu too
            final = wait_for_change(final)
            if final is None:
                fatal(f"{label}: could not leave top menu")

        if final["chars"] != baseline["chars"]:
            fatal(f"{label}: post-exit splash differs from baseline — possible settings drift")
        print(f"    OK: exited clean, splash matches baseline")
        time.sleep(1)

    print("\nDONE: all sub-pages captured, splash verified unchanged after every item")


if __name__ == "__main__":
    main()
