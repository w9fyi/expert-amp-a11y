#!/usr/bin/env python3
"""Measure how long the amp's /api/v1/display/state actually takes to reflect
a button press, so fanModeRunner0001's waitForChange delay can be tuned with
real data instead of borrowing the SWR-settling SETTLE_DELAY (a different
subsystem) from the ATU tuner.

Safe: only uses left/right navigation inside the top-level Set-mode menu
(already proven non-destructive across many prior sessions), never enters a
sub-page, never presses SET/TUNE. Exits via DISPLAY at the end.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_menu import get_status, get_display, press, CAPDIR, preflight
from capture_subpage import bail

POLL_INTERVAL = 0.08  # 80ms
MAX_WAIT = 3.0
N_SAMPLES = 10


def rapid_wait_for_change(before):
    t0 = time.monotonic()
    while time.monotonic() - t0 < MAX_WAIT:
        now = get_display()
        if now != before:
            return time.monotonic() - t0, now
        time.sleep(POLL_INTERVAL)
    return None, None


def main():
    st = get_status()
    if not preflight(st)[0]:
        print(f"NOT SAFE: {preflight(st)[1]}")
        sys.exit(2)

    splash = get_display()
    press("set")
    cur, _ = None, splash
    elapsed, cur = rapid_wait_for_change(splash)
    if cur is None:
        bail("no change after SET (menu entry)")
    print(f"SET (menu entry): {elapsed*1000:.0f} ms")

    samples = []
    for i in range(N_SAMPLES):
        before = cur
        press("right")
        elapsed, nxt = rapid_wait_for_change(before)
        if nxt is None:
            bail(f"no change after right press {i+1}")
        samples.append(elapsed)
        print(f"right press {i+1}: {elapsed*1000:.0f} ms")
        cur = nxt

    print("\nexiting via DISPLAY...")
    press("display")
    elapsed, back = rapid_wait_for_change(cur)
    print(f"DISPLAY exit: {elapsed*1000 if elapsed else '?'} ms")

    samples_ms = [s * 1000 for s in samples]
    samples_ms.sort()
    print(f"\n=== {len(samples_ms)} right-press samples (ms) ===")
    print(f"  min={samples_ms[0]:.0f} max={samples_ms[-1]:.0f} "
          f"median={samples_ms[len(samples_ms)//2]:.0f} "
          f"mean={sum(samples_ms)/len(samples_ms):.0f}")
    print(f"  all: {[f'{s:.0f}' for s in samples_ms]}")


if __name__ == "__main__":
    main()
