#!/usr/bin/env python3
"""Same-value resave, but keep polling fast past the first change to see the
full 'STORING DATA!' animation through to its real settled end, so the
production code knows how long to keep waiting rather than accepting the
first (possibly mid-animation) frame as done.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press
from capture_subpage import highlighted_text, bail

FAN_RIGHTS = 11
POLL_INTERVAL = 0.08
MAX_WAIT = 8.0


def classify(hi):
    h = hi.lower()
    if "quiet" in h:
        return "quiet"
    if "normal" in h:
        return "normal"
    if h.strip() == "save":
        return "save"
    return None


def main():
    st = get_status()
    if st.get("operatingState") != "standby" or not st.get("recentContact"):
        print(f"NOT SAFE: operatingState={st.get('operatingState')} recentContact={st.get('recentContact')}")
        sys.exit(2)

    splash = get_display()
    press("set")
    t0 = time.monotonic()
    cur = splash
    while time.monotonic() - t0 < 3.0:
        now = get_display()
        if now != cur:
            cur = now
            break
        time.sleep(POLL_INTERVAL)

    for i in range(FAN_RIGHTS):
        before = cur
        press("right")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 3.0:
            now = get_display()
            if now != before:
                cur = now
                break
            time.sleep(POLL_INTERVAL)

    hi = highlighted_text(cur)
    if "fan noise" not in hi.lower():
        bail(f"expected FAN NOISE highlighted, got {hi!r}")

    press("set")
    t0 = time.monotonic()
    sub = None
    while time.monotonic() - t0 < 3.0:
        now = get_display()
        if now != cur:
            sub = now
            break
        time.sleep(POLL_INTERVAL)
    if sub is None:
        bail("no change after SET (sub-page entry)")

    entry_hi = highlighted_text(sub)
    current = classify(entry_hi)
    print(f"current mode: {current}")

    direction = "right" if current == "normal" else "left"
    press(direction)
    t0 = time.monotonic()
    on_save = None
    while time.monotonic() - t0 < 3.0:
        now = get_display()
        if now != sub:
            on_save = now
            break
        time.sleep(POLL_INTERVAL)
    if on_save is None:
        bail("no change navigating to SAVE")

    print(f"\npressing SET on SAVE (same-value resave: {current} -> {current})...")
    press("set")

    t_start = time.monotonic()
    prev = on_save
    frame = 0
    settled = None
    while time.monotonic() - t_start < MAX_WAIT:
        now = get_display()
        if now != prev:
            elapsed = time.monotonic() - t_start
            lines, _ = decode_grid(now["chars"])
            text = "\n".join(lines).upper()
            is_storing = "STORING DATA" in text
            frame += 1
            print(f"  frame {frame} at {elapsed*1000:.0f} ms -- storing_data={is_storing}")
            for l in lines:
                if l.strip():
                    print(f"     |{l}|")
            prev = now
            if not is_storing:
                settled = now
                settle_elapsed = elapsed
                break
        time.sleep(POLL_INTERVAL)

    if settled is None:
        print("TIMED OUT waiting for settle -- inspect manually")
        sys.exit(3)

    print(f"\n=== settled (non-STORING-DATA) after {settle_elapsed*1000:.0f} ms total, {frame} frame(s) ===")

    st = get_status()
    print(f"status: operatingState={st.get('operatingState')} recentContact={st.get('recentContact')}")


if __name__ == "__main__":
    main()
