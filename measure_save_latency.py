#!/usr/bin/env python3
"""Measure real SET-on-SAVE commit latency inside FAN NOISE, via a same-value
resave (whatever the amp's current mode already is -> SAVE -> SET). No-op
functionally, same class of test as verify_fan_save.py, but with fast rapid
polling to get real sub-second timing instead of the blind 1s poll interval.
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
MAX_WAIT = 6.0


def rapid_wait_for_change(before):
    t0 = time.monotonic()
    while time.monotonic() - t0 < MAX_WAIT:
        now = get_display()
        if now != before:
            return time.monotonic() - t0, now
        time.sleep(POLL_INTERVAL)
    return None, None


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
    elapsed, cur = rapid_wait_for_change(splash)
    if cur is None:
        bail("no change after SET (menu entry)")
    print(f"SET (menu entry): {elapsed*1000:.0f} ms")

    for i in range(FAN_RIGHTS):
        before = cur
        press("right")
        elapsed, nxt = rapid_wait_for_change(before)
        if nxt is None:
            bail(f"no change after right press {i+1}")
        cur = nxt
    print(f"navigated to FAN NOISE ({FAN_RIGHTS} rights)")

    hi = highlighted_text(cur)
    if "fan noise" not in hi.lower():
        bail(f"expected FAN NOISE highlighted, got {hi!r}")

    press("set")
    elapsed, sub = rapid_wait_for_change(cur)
    if sub is None:
        bail("no change after SET (sub-page entry)")
    print(f"SET (sub-page entry): {elapsed*1000:.0f} ms")

    entry_hi = highlighted_text(sub)
    current = classify(entry_hi)
    print(f"current mode: {current}")
    if current not in ("quiet", "normal"):
        bail(f"unexpected entry state: {entry_hi!r}")

    # navigate to SAVE (1 press, direction depends on current position)
    direction = "right" if current == "normal" else "left"
    press(direction)
    elapsed, on_save = rapid_wait_for_change(sub)
    if on_save is None:
        bail("no change navigating to SAVE")
    print(f"nav to SAVE: {elapsed*1000:.0f} ms")
    save_hi = highlighted_text(on_save)
    if save_hi.strip().upper() != "SAVE":
        bail(f"expected SAVE highlighted, got {save_hi!r}")

    print(f"\npressing SET on SAVE (same-value resave: {current} -> {current})...")
    press("set")
    elapsed, after_set = rapid_wait_for_change(on_save)
    if after_set is None:
        print("WARNING: no change detected within 6s -- inspect manually")
        sys.exit(3)
    print(f"SET on SAVE (commit): {elapsed*1000:.0f} ms")
    lines, _ = decode_grid(after_set["chars"])
    print("post-save screen:")
    for l in lines:
        if l.strip():
            print(f"   |{l}|")

    press("display")
    elapsed2, back = rapid_wait_for_change(after_set)
    print(f"\nDISPLAY dismiss: {elapsed2*1000 if elapsed2 else '?'} ms")
    if back:
        lines, _ = decode_grid(back["chars"])
        for l in lines:
            if l.strip():
                print(f"   |{l}|")

    st = get_status()
    print(f"\nfinal status: operatingState={st.get('operatingState')} warningCode={st.get('warningCode')} recentContact={st.get('recentContact')}")
    print(f"\n=== SUMMARY: commit took {elapsed*1000:.0f} ms, dismiss took {elapsed2*1000 if elapsed2 else '?'} ms ===")


if __name__ == "__main__":
    main()
