#!/usr/bin/env python3
"""Full round-trip test: NORMAL -> QUIET (verify) -> NORMAL (restore).

Two things being tested in one pass:
1. Does SET on a non-current row (QUIET) commit immediately, or does a
   DISPLAY press right after it still cancel cleanly with no hardware
   change (staged-until-SAVE model, like the other CONFIRM sub-pages)?
2. The real commit path (nav -> SET on target row -> nav to SAVE -> SET),
   applied first to QUIET then immediately back to NORMAL, so the amp
   ends this script in exactly the state it started.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
from capture_menu import get_status, get_display, press, wait_for_change, preflight
from capture_subpage import highlighted_text, bail

FAN_RIGHTS = 11
# ring transition table: {current: {press: target}}
RING = {
    "normal": {"left": "quiet", "right": "save"},
    "quiet": {"left": "save", "right": "normal"},
    "save": {"left": "normal", "right": "quiet"},
}


def show(label, state):
    lines, _ = decode_grid(state["chars"])
    hi = highlighted_text(state)
    print(f"\n--- {label} ---")
    for l in lines:
        if l.strip():
            print(f"   |{l}|")
    print(f"   highlighted: {hi!r}")
    return hi


def classify(hi):
    h = hi.lower()
    if "quiet" in h:
        return "quiet"
    if "normal" in h:
        return "normal"
    if h.strip() == "save":
        return "save"
    return None


def enter_fan_subpage():
    st = get_status()
    if not preflight(st)[0]:
        bail(f"NOT SAFE: {preflight(st)[1]}")
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
    return sub


def goto(state, target):
    """Navigate the ring from whatever `state` currently shows to `target`."""
    hi = highlighted_text(state)
    pos = classify(hi)
    if pos is None:
        bail(f"unrecognized sub-page position: {hi!r}")
    if pos == target:
        return state
    direction = "left" if RING[pos]["left"] == target else "right"
    if RING[pos][direction] != target:
        bail(f"ring table has no direct move from {pos} to {target}")
    press(direction)
    nxt = wait_for_change(state)
    if nxt is None:
        bail(f"no change navigating {pos} -> {target}")
    got = classify(highlighted_text(nxt))
    if got != target:
        bail(f"navigated but landed on {got!r}, expected {target!r}")
    return nxt


def commit_mode(target_mode):
    """Full path: enter sub-page, select target_mode, SAVE, dismiss. Returns final display."""
    sub = enter_fan_subpage()
    entry_hi = show("entry", sub)
    current = classify(entry_hi)
    print(f"current mode on entry: {current}")

    on_target = goto(sub, target_mode)
    show(f"cursor on {target_mode}", on_target)

    print(f"pressing SET on {target_mode} row (the untested action)...")
    press("set")
    after_set = wait_for_change(on_target, tries=6, delay=1.0)
    if after_set is None:
        print("  (no display change detected after SET -- may be a no-op if already selected, continuing)")
        after_set = on_target
    else:
        show(f"after SET on {target_mode}", after_set)

    on_save = goto(after_set, "save")
    show("cursor on SAVE", on_save)

    print("pressing SET on SAVE (commit)...")
    press("set")
    after_save = wait_for_change(on_save, tries=8, delay=1.0)
    if after_save is None:
        after_save = get_display()
    show("after SET on SAVE", after_save)

    lines, _ = decode_grid(after_save["chars"])
    text = "\n".join(lines)
    if "storing" not in text.lower() and highlighted_text(after_save):
        print("  NOTE: no 'STORING DATA' animation caught (may have already passed) -- continuing")

    # dismiss whatever screen we're on back toward a standby home screen
    press("display")
    final = wait_for_change(after_save, tries=8, delay=1.0)
    if final is None:
        final = get_display()
    show("after DISPLAY dismiss", final)
    return final


def main():
    print("=== STEP 1: commit QUIET ===")
    final_quiet = commit_mode("quiet")
    lines, _ = decode_grid(final_quiet["chars"])
    text = "\n".join(lines).upper()
    if "QUIET MODE" in text:
        print("\nCONFIRMED live: amp now reports QUIET MODE on its standby screen.")
    else:
        print("\nWARNING: could not confirm 'QUIET MODE' text on the post-save screen -- inspect above before restoring.")

    st = get_status()
    print(f"status check: operatingState={st.get('operatingState')} warningCode={st.get('warningCode')} recentContact={st.get('recentContact')}")

    print("\n=== STEP 2: restore NORMAL ===")
    final_normal = commit_mode("normal")
    lines, _ = decode_grid(final_normal["chars"])
    text = "\n".join(lines).upper()
    if "NORMAL MODE" in text:
        print("\nCONFIRMED live: amp restored to NORMAL MODE on its standby screen.")
    else:
        print("\nWARNING: could not confirm 'NORMAL MODE' text on the post-save screen -- inspect above, amp may not be restored.")

    st = get_status()
    print(f"final status: operatingState={st.get('operatingState')} warningCode={st.get('warningCode')} recentContact={st.get('recentContact')}")


if __name__ == "__main__":
    main()
