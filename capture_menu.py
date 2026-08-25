#!/usr/bin/env python3
"""Display-verified capture of the 2K-FA Set-mode top-level menu screens.

Safety model (manual section 10, verified 2026-07-18):
- programming only possible in STANDBY (checked before starting)
- changes commit ONLY on [SET]-exit; we never press SET after menu entry
- [DISPLAY] aborts everything with no programming effect (used to exit,
  and as the bail-out on any unexpected screen)
- every button press is verified by re-reading the display and requiring
  it to have changed before the next press

Captures go to captures/NN_<label>/: state.json (raw), decoded.txt, render.png
"""
import json
import os
import sys
import time
import urllib.request

try:
    import websocket as _ws_client  # pip package "websocket-client"
except ImportError:
    _ws_client = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_display import decode_grid
import capture_common as cc

BASE = "http://raspbnodered.local:8088/api/v1"
DISPLAY_WS_URL = "ws://raspbnodered.local:8088/api/v1/display/ws"
CAPDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
EVIDENCE_PATH = os.path.join(CAPDIR, "evidence.ndjson")
MAX_PAGES = 15  # expect 11 menu items; hard stop well above that

_seen_hashes = set()
_previous_hash = ""


def init_evidence():
    """Load existing evidence hashes for dedup+resume. Call once per session."""
    global _seen_hashes
    os.makedirs(CAPDIR, exist_ok=True)
    _seen_hashes = cc.load_seen_hashes(EVIDENCE_PATH)


def get_json(path):
    with urllib.request.urlopen(f"{BASE}/{path}", timeout=8) as r:
        return json.load(r)


def get_status():
    return get_json("status")["data"]


def get_display():
    """Full state object: chars grid + attrs grid (inverse-video/highlight)."""
    return get_json("display/state")["data"]["state"]


def link_live(st=None):
    """True if expert-amp-server currently has a real serial session to the amp.

    Replaces the old `recentContact` pre-flight gate, which was wrong for an
    idle amplifier. `recentContact` derives from change-based timestamps: the
    runtime dedups snapshots that are deep-equal to the previous one and
    deliberately does not touch `UpdatedAt` on that path (internal/runtime/
    runtime.go), and `lastContactAt` is max(snapshot.UpdatedAt, lastProtocolAt).
    So a healthy amp sitting in STANDBY with a static splash screen -- no
    display change, and no protocol-native frames because the PA is idle --
    reports `recentContact: false`, and being a bool with `omitempty` it
    vanishes from the JSON entirely. Diagnosed 2026-08-25; it blocked every
    capture script whenever the connected transceiver was switched off.

    `source` is the signal that actually answers "is the link alive": the
    server serves `fixture:*` placeholder data when it cannot open the serial
    port (e.g. the EBUSY case after a bridge/pty mixup) and `serial` when it
    genuinely has the amp. That is the condition worth gating on.

    Note this is a necessary condition, not a sufficient one -- it says the
    serial session exists, not that this specific press will be seen. The real
    protection is `wait_for_change()`, which verifies every single press and
    bails before the next one.
    """
    if st is None:
        st = get_status()
    return str(st.get("source", "")).startswith("serial")


def preflight(st=None):
    """(ok, reason) for 'safe to start driving the amp's menus'."""
    if st is None:
        st = get_status()
    state = st.get("operatingState")
    if state != "standby":
        return False, f"operatingState={state!r} (must be 'standby')"
    if st.get("tx"):
        return False, "amplifier is transmitting"
    if not link_live(st):
        return False, f"no live serial link (source={st.get('source')!r})"
    return True, f"standby, source={st.get('source')!r}"


def press(name):
    req = urllib.request.Request(
        f"{BASE}/actions/button",
        data=json.dumps({"name": name}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        resp = json.load(r)
    if not resp.get("success"):
        raise RuntimeError(f"button {name} failed: {resp}")
    print(f"  [pressed {name}]")


def save_capture(index, label, state, transition_label=""):
    global _previous_hash
    d = os.path.join(CAPDIR, f"{index:02d}_{label}")
    os.makedirs(d, exist_ok=True)
    json.dump(state, open(os.path.join(d, "state.json"), "w"))
    lines, unknown = decode_grid(state["chars"])
    with open(os.path.join(d, "decoded.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
        if unknown:
            f.write("\n# unknown glyphs: " + ", ".join(f"0x{c:02X}" for c in sorted(unknown)) + "\n")
    with urllib.request.urlopen(f"{BASE}/display/render.png", timeout=8) as r:
        open(os.path.join(d, "render.png"), "wb").write(r.read())

    h, was_new = cc.record_evidence(EVIDENCE_PATH, _seen_hashes, _previous_hash, transition_label)
    _previous_hash = h
    evidence_note = "new evidence" if was_new else "already in evidence (dup screen)"

    print(f"  saved {index:02d}_{label} [{evidence_note}]: " + " / ".join(l.strip() for l in lines if l.strip())[:100])
    return lines


def _before_lines(before):
    lines, _unknown = decode_grid(before["chars"])
    return [l.rstrip() for l in lines if l.strip()]


def wait_for_change(before, tries=25, delay=1.0):
    """Wait for the display to change from `before`, then return a fresh
    get_display() read (or None on timeout).

    Uses expert-amp-server's own native push WebSocket
    (/api/v1/display/ws, internal/server/display_ws.go) rather than
    polling /api/v1/display/state -- found 2026-08-19 that opening a
    second raw TCP connection to the SPE-LAN-UNIT's port-7388 serial
    mirror (to work around HTTP polling staleness) actually corrupts/
    desyncs expert-amp-server's own connection, which is worse. The
    native WS is server-side-pushed the moment its internal Store
    updates -- no polling, no second serial client, no desync risk.
    Every message (including the immediate first one, which reflects
    current state at connect time) is compared against `before`'s
    decoded text, so a change that already happened before the socket
    opens is still caught, not just changes strictly after connecting.
    Falls back to the old polling method if `websocket-client` isn't
    installed or the socket can't connect.
    """
    if _ws_client is None:
        return _wait_for_change_poll(before, tries, delay)

    DEBOUNCE = 1.5  # this hardware's LCD redraws in multiple stages -- a
    # push differing from `before` can be a transient intermediate frame,
    # not the final settled screen (observed live 2026-08-19: a single
    # "first difference" return raced and returned pre-transition content).
    # Wait for the push stream to go quiet for DEBOUNCE seconds before
    # treating the display as settled.

    timeout = max(1.0, tries * delay)
    before_lines = _before_lines(before)
    try:
        conn = _ws_client.create_connection(DISPLAY_WS_URL, timeout=timeout)
    except Exception:
        return _wait_for_change_poll(before, tries, delay)

    try:
        deadline = time.time() + timeout
        differed = False
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return get_display() if differed else None
            per_msg_timeout = DEBOUNCE if differed else remaining
            conn.settimeout(min(per_msg_timeout, remaining))
            try:
                msg = conn.recv()
            except Exception:
                # Timeout or socket error mid-wait: if we'd already seen a
                # difference, this is the debounce window going quiet --
                # that's the normal "settled" exit, not a failure. If we
                # never saw any difference at all, this is a genuine
                # timeout; don't restart via polling and double the wait.
                return get_display() if differed else None
            try:
                event = json.loads(msg)
            except ValueError:
                continue
            screen_text = event.get("frame", {}).get("screenText", "")
            pushed_lines = [l.rstrip() for l in screen_text.split("\n") if l.strip()]
            if pushed_lines != before_lines:
                differed = True
            # else: a push identical to `before` while mid-debounce just
            # resets the quiet window via the recv() above -- fine, since
            # a genuinely settled final frame will stop producing pushes.
    finally:
        conn.close()


def _wait_for_change_poll(before, tries=25, delay=1.0):
    """Fallback: re-read display until it differs from `before` (old polling
    method). Only used if the native WebSocket path is unavailable."""
    for _ in range(tries):
        time.sleep(delay)
        now = get_display()
        if now != before:
            return now
    return None


def bail(reason):
    print(f"ABORT: {reason} — pressing display to cancel out of the menu")
    try:
        press("display")
    finally:
        sys.exit(1)


def main():
    st = get_status()
    if not preflight(st)[0]:
        print(f"NOT SAFE TO START: {preflight(st)[1]}")
        sys.exit(2)

    os.makedirs(CAPDIR, exist_ok=True)
    init_evidence()
    splash = get_display()
    save_capture(0, "standby_splash", splash)

    print("entering Set mode...")
    press("set")
    menu_first = wait_for_change(splash)
    if menu_first is None:
        bail("display did not change after SET press")

    pages = [menu_first]
    save_capture(1, "menu_page", menu_first, transition_label="pressed SET")

    for i in range(2, MAX_PAGES + 2):
        press("right")
        nxt = wait_for_change(pages[-1])
        if nxt is None:
            bail(f"display did not change after right press (page {i})")
        if nxt == menu_first:
            print(f"wrap detected after {len(pages)} pages")
            break
        if nxt == splash:
            bail("unexpectedly back at splash screen mid-traversal")
        pages.append(nxt)
        save_capture(i, "menu_page", nxt, transition_label="pressed RIGHT")
    else:
        bail(f"no wrap after {MAX_PAGES} pages — unexpected menu size")

    print("exiting via DISPLAY (no programming effect)...")
    press("display")
    back = wait_for_change(pages[-1])
    if back == splash:
        print("OK: back at standby splash screen, menu exited cleanly")
    else:
        print("WARNING: post-exit screen is not the original splash — inspect:")
        lines, _ = decode_grid(back or pages[-1])
        for l in lines:
            print("   |" + l + "|")
        sys.exit(3)

    print(f"\nDONE: {len(pages)} top-level menu pages captured in {CAPDIR}")


if __name__ == "__main__":
    main()
