#!/usr/bin/env python3
"""Enter one Set-mode sub-page, capture it, and DISPLAY-abort out.

Usage: capture_subpage.py <rights> <expect> <label>
  rights : number of `right` presses after menu entry to reach the item
  expect : substring that must appear in the attrs==1 highlighted text
           before SET is pressed (safety gate; case-insensitive)
  label  : capture directory name, e.g. sub_temp

Nothing is pressed inside the sub-page. Exit is via [DISPLAY], which per
manual section 10 (and verified live twice) aborts with no programming effect.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_cell, decode_grid
from capture_menu import get_status, get_display, press, save_capture, wait_for_change, CAPDIR, init_evidence


def highlighted_text(state):
    chars, attrs = state["chars"], state["attrs"]
    out = []
    for r in range(len(attrs)):
        row = "".join(
            decode_cell(chars[r][c]) for c in range(len(attrs[0])) if attrs[r][c]
        ).strip()
        if row:
            out.append(row)
    return " / ".join(out)


def bail(reason):
    print(f"ABORT: {reason} — pressing display to cancel out")
    try:
        press("display")
    finally:
        sys.exit(1)


def main():
    rights, expect, label = int(sys.argv[1]), sys.argv[2], sys.argv[3]

    st = get_status()
    if st.get("operatingState") != "standby" or not st.get("recentContact"):
        print(f"NOT SAFE: operatingState={st.get('operatingState')} recentContact={st.get('recentContact')}")
        sys.exit(2)

    init_evidence()
    splash = get_display()
    press("set")
    cur = wait_for_change(splash)
    if cur is None:
        bail("no change after SET (menu entry)")

    for i in range(rights):
        press("right")
        nxt = wait_for_change(cur)
        if nxt is None:
            bail(f"no change after right press {i+1}")
        cur = nxt

    hi = highlighted_text(cur)
    print(f"highlighted after {rights} rights: {hi!r}")
    if expect.lower() not in hi.lower():
        bail(f"expected {expect!r} highlighted, got {hi!r}")

    press("set")
    sub = wait_for_change(cur)
    if sub is None:
        bail("no change after SET (sub-page entry)")

    d = os.path.join(CAPDIR, label)
    os.makedirs(d, exist_ok=True)
    save_capture(0, label, sub, transition_label=f"SET then RIGHT x{rights} then SET")
    lines, unknown = decode_grid(sub["chars"])
    print("=== sub-page ===")
    for r, l in enumerate(lines):
        print(f"{r}: |{l}|")
    print("highlighted:", repr(highlighted_text(sub)))
    if unknown:
        print("unknown glyphs:", [hex(c) for c in sorted(unknown)])

    print("aborting out via DISPLAY...")
    press("display")
    back = wait_for_change(sub)
    if back == splash:
        print("OK: back at standby splash, nothing committed")
    else:
        lines, _ = decode_grid((back or sub)["chars"])
        print("NOTE: post-exit screen is not the splash — current screen:")
        for l in lines:
            print("   |" + l + "|")
        sys.exit(3)


if __name__ == "__main__":
    main()
