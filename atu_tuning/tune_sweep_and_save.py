#!/usr/bin/env python3
"""Full bidirectional sweep per axis (not greedy hill-climb): explore a fixed
range in both + and - directions, record SWR at every point, flag any point
under 2.0 (roughly 1.x:1) as a possible safe point but KEEP GOING through the
whole sweep, then walk directly to whichever point was actually best across
the entire explored range. C first (known target ~10 steps away), then L
(needs a wider range — L moved much more slowly in earlier testing). Then
hold-tune to save, unkey, exit, re-enter (no carrier) to verify persistence.
"""
import json
import os
import socket
import time
import urllib.request

AMP_BASE = "http://localhost:8088/api/v1"
# Hostname, not a literal IP: the radio was swapped once already (FLEX-8400 .117 ->
# FLEX-8600 .157) and the stale literal left the tune-off failsafe below unable to
# reach the radio. flex.lan is a UDR-7 static record pinned by DHCP reservation.
FLEX_HOST = os.environ.get("FLEX_HOST", "flex.lan")
FLEX_PORT = int(os.environ.get("FLEX_PORT", "4992"))

C_SWEEP_STEPS = 15
L_SWEEP_STEPS = 25
SETTLE_DELAY = 0.6
TX_CHECK_GRACE = 90
MAX_NAV_PRESSES = 14
HOLD_TUNE_PRESSES = 6
HOLD_TUNE_INTERVAL = 0.25
POST_HOLD_WATCH_SECS = 5
FLAG_THRESHOLD = 2.0  # "1.x:1" or better

CUSTOM_TEXT = {
    0xAA: "°", 0x8F: "|",
    0x99: "◄", 0x9A: "▲", 0x9B: "▼", 0x9C: "►",
    0x9D: "◄", 0x9E: "►", 0xAE: "✓",
    0x92: "-", 0x93: "-", 0x94: ".", 0x95: "#", 0x98: "#",
}
DECOR = set([0x8D, 0x8E, 0x9F, 0xA0, 0xA1, 0xA2, 0xA3]) | set(range(0xB0, 0xE0))

def decode_cell(code):
    if code in (0x00, 0x60, 0x7F):
        return " "
    if 0x01 <= code <= 0x5F:
        return chr(code + 0x20)
    if code in CUSTOM_TEXT:
        return CUSTOM_TEXT[code]
    if code in DECOR:
        return " "
    return f"[{code:02X}]"

def decode_grid(chars):
    return ["".join(decode_cell(c) for c in row).rstrip() for row in chars]

def highlighted_text(state):
    chars, attrs = state["chars"], state["attrs"]
    out = []
    for r in range(len(attrs)):
        row = "".join(decode_cell(chars[r][c]) for c in range(len(attrs[0])) if attrs[r][c]).strip()
        if row:
            out.append(row)
    return " / ".join(out)

def get_json(path):
    with urllib.request.urlopen(f"{AMP_BASE}/{path}", timeout=8) as r:
        return json.load(r)

def get_status():
    return get_json("status")["data"]

def get_display():
    return get_json("display/state")["data"]["state"]

def press(name):
    req = urllib.request.Request(
        f"{AMP_BASE}/actions/button",
        data=json.dumps({"name": name}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        resp = json.load(r)
    if not resp.get("success"):
        raise RuntimeError(f"button {name} failed: {resp}")

def wait_for_change(before, tries=6, delay=0.8):
    for _ in range(tries):
        time.sleep(delay)
        now = get_display()
        if now != before:
            return now
    return None

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def flex_tune_off():
    try:
        s = socket.create_connection((FLEX_HOST, FLEX_PORT), timeout=5)
        s.settimeout(3)
        buf = b""
        try:
            while b"\n" not in buf or buf.count(b"\n") < 2:
                c = s.recv(4096)
                if not c:
                    break
                buf += c
        except socket.timeout:
            pass
        s.sendall(b"C1|transmit tune off\n")
        reply = b""
        try:
            while True:
                c = s.recv(4096)
                if not c:
                    break
                reply += c
                if b"R1|" in reply:
                    break
        except socket.timeout:
            pass
        s.close()
        log(f"FAILSAFE: sent transmit tune off, reply tail={reply[-80:]!r}")
    except Exception as e:
        log(f"FAILSAFE FAILED: could not reach FLEX to force tune off: {e}")

def check_abort(status):
    alarm = status.get("alarmCode")
    warn = status.get("warningCode")
    if alarm:
        return f"ALARM active: {alarm} / {status.get('alarmsText')}"
    if warn:
        return f"WARNING active: {warn} / {status.get('warningsText')}"
    if not status.get("recentContact", True):
        return "lost serial contact with amp"
    return None

def bail_menu(reason):
    log(f"MENU NAV ABORT: {reason} — pressing display to cancel out")
    press("display")
    time.sleep(1.0)
    flex_tune_off()
    raise SystemExit(1)

def enter_manual_tune():
    st = get_status()
    if st.get("operatingState") != "standby" or not st.get("recentContact"):
        log(f"NOT SAFE TO START: operatingState={st.get('operatingState')} recentContact={st.get('recentContact')}")
        raise SystemExit(2)
    if st.get("tx"):
        log("Carrier already on — forcing off before menu entry.")
        flex_tune_off()
        time.sleep(1.5)
        st = get_status()
        if st.get("tx"):
            log("Carrier still on — aborting.")
            raise SystemExit(2)

    splash = get_display()
    press("set")
    cur = wait_for_change(splash)
    if cur is None:
        bail_menu("no change after SET (menu entry)")
    if "SETUP OPTIONS" not in "\n".join(decode_grid(cur["chars"])).upper():
        bail_menu(f"post-SET screen doesn't look like setup menu: {decode_grid(cur['chars'])}")

    hi = highlighted_text(cur)
    presses = 0
    while "MANUAL TUNE" not in hi.upper() and presses < MAX_NAV_PRESSES:
        press("right")
        nxt = wait_for_change(cur)
        if nxt is None:
            bail_menu(f"no change after right press {presses+1}")
        cur = nxt
        presses += 1
        hi = highlighted_text(cur)
    if "MANUAL TUNE" not in hi.upper():
        bail_menu(f"never reached MANUAL TUNE after {presses} rights, stuck on {hi!r}")

    legend = decode_grid(cur["chars"])[-1] if len(decode_grid(cur["chars"])) >= 8 else ""
    if "CONFIRM" not in legend.upper():
        bail_menu(f"legend does not say CONFIRM: {legend!r}")

    press("set")
    sub = wait_for_change(cur)
    if sub is None:
        bail_menu("no change after SET (sub-page entry)")
    return splash, sub

def exit_to_splash(splash, sub_display):
    press("display")
    back = wait_for_change(sub_display)
    if back is not None and "SETUP OPTIONS" in "\n".join(decode_grid(back["chars"])).upper():
        press("display")
        back2 = wait_for_change(back)
        final = back2 if back2 is not None else back
    else:
        final = back if back is not None else sub_display
    final_lines = decode_grid(final["chars"]) if final else []
    if final == splash or (final_lines and "STANDBY" in "\n".join(final_lines).upper()):
        log("OK: back at standby splash.")
    else:
        log("NOTE: not clearly back at splash:")
        for l in final_lines:
            log(f"  |{l}|")
    return final

def readout(sub_state):
    lines = decode_grid(sub_state["chars"])
    return {
        "l_line": lines[2] if len(lines) > 2 else "",
        "c_line": lines[3] if len(lines) > 3 else "",
    }

def press_n(name, n, all_flags, axis_label):
    """Press `name` n times, recording (cumulative_signed_step, swr) after each.
    Returns (list_of_(step,swr), abort_reason_or_None)."""
    out = []
    for i in range(n):
        press(name)
        time.sleep(SETTLE_DELAY)
        status = get_status()
        reason = check_abort(status)
        if reason:
            return out, reason
        if not status.get("tx"):
            return out, "carrier stopped (tx=false)"
        swr = status.get("swr", 0)
        out.append(swr)
        flagtxt = ""
        if swr < FLAG_THRESHOLD:
            flagtxt = "  *** POSSIBLE SAFE POINT ***"
            all_flags.append((axis_label, name, i + 1, swr))
        log(f"  {name} [{i+1}/{n}]: SWR ATU = {swr:.2f}{flagtxt}")
    return out, None

def sweep_axis(axis, start_swr, steps_each, all_flags):
    """Bidirectional sweep from current position. Leaves the amp AT the best
    position found across the whole explored range (or wherever it got to,
    if aborted). Returns (final_swr, stop_reason_or_None)."""
    plus_name, minus_name = f"{axis}+", f"{axis}-"
    history = {0: start_swr}
    if start_swr < FLAG_THRESHOLD:
        all_flags.append((axis.upper(), "start", 0, start_swr))
        log(f"  *** POSSIBLE SAFE POINT at start: SWR = {start_swr:.2f} ***")

    log(f"Sweeping {axis.upper()}+ x{steps_each}...")
    plus_vals, reason = press_n(plus_name, steps_each, all_flags, axis.upper())
    for idx, v in enumerate(plus_vals, start=1):
        history[idx] = v
    if reason:
        return (plus_vals[-1] if plus_vals else start_swr), reason

    log(f"Returning to start position ({steps_each} x {minus_name})...")
    _, reason = press_n(minus_name, steps_each, [], axis.upper() + " (return)")
    if reason:
        return history[len(plus_vals)], reason

    log(f"Sweeping {axis.upper()}- x{steps_each}...")
    minus_vals, reason = press_n(minus_name, steps_each, all_flags, axis.upper())
    for idx, v in enumerate(minus_vals, start=1):
        history[-idx] = v
    if reason:
        return (minus_vals[-1] if minus_vals else start_swr), reason

    log(f"Returning to start position ({steps_each} x {plus_name})...")
    _, reason = press_n(plus_name, steps_each, [], axis.upper() + " (return)")
    if reason:
        return history[-len(minus_vals)], reason

    best_pos = min(history, key=lambda p: history[p])
    best_val = history[best_pos]
    log(f"{axis.upper()} sweep complete. Best position: {best_pos:+d} steps, SWR = {best_val:.2f}")
    if best_pos == 0:
        return best_val, None

    direction = plus_name if best_pos > 0 else minus_name
    log(f"Moving to best position: {abs(best_pos)} x {direction}...")
    vals, reason = press_n(direction, abs(best_pos), [], axis.upper() + " (to best)")
    if reason:
        return (vals[-1] if vals else best_val), reason
    final_swr = vals[-1] if vals else best_val
    return final_swr, None

def main():
    log("=== Enter MANUAL TUNE, read baseline ===")
    splash, sub = enter_manual_tune()
    baseline = readout(sub)
    log(f"Baseline L: {baseline['l_line']!r}")
    log(f"Baseline C: {baseline['c_line']!r}")

    log("Waiting for carrier (tx=true) — press Tune Carrier On now...")
    waited = 0
    status = get_status()
    while not status.get("tx") and waited < TX_CHECK_GRACE:
        time.sleep(2)
        waited += 2
        status = get_status()
    if not status.get("tx"):
        log("Timed out waiting for carrier. Exiting without changes.")
        exit_to_splash(splash, sub)
        return

    reason = check_abort(status)
    if reason:
        log(f"Abort condition present: {reason}")
        flex_tune_off()
        exit_to_splash(splash, sub)
        return

    start_swr = status.get("swr", 0)
    log(f"Carrier confirmed. Starting SWR (ATU) = {start_swr:.2f}.")

    all_flags = []
    cur_state = sub
    stop_reason = None
    best_swr = start_swr
    try:
        log("=== C axis sweep ===")
        best_swr, stop_reason = sweep_axis("c", best_swr, C_SWEEP_STEPS, all_flags)
        if not stop_reason:
            log("=== L axis sweep ===")
            best_swr, stop_reason = sweep_axis("l", best_swr, L_SWEEP_STEPS, all_flags)

        log(f"Sweeps complete. Best SWR (ATU) = {best_swr:.2f}. Stop reason: {stop_reason or 'completed'}")
        if all_flags:
            log("Flagged possible-safe points seen along the way:")
            for axis_label, name, step, swr in all_flags:
                log(f"  {axis_label} {name} step {step}: SWR = {swr:.2f}")

        unsafe_stop = stop_reason and (
            stop_reason.startswith("ALARM active")
            or stop_reason.startswith("WARNING active")
            or stop_reason in ("carrier stopped (tx=false)", "lost serial contact with amp")
        )
        if not unsafe_stop:
            status = get_status()
            reason = check_abort(status)
            if reason or not status.get("tx"):
                log(f"Cannot save — carrier/abort state changed after sweep: {reason or 'tx=false'}")
            else:
                cur_state = get_display()
                target = readout(cur_state)
                log(f"Position to save — L: {target['l_line']!r}  C: {target['c_line']!r}")
                log(f"Attempting hold-tune save: {HOLD_TUNE_PRESSES} presses of TUNE...")
                save_aborted = None
                for i in range(HOLD_TUNE_PRESSES):
                    press("tune")
                    time.sleep(HOLD_TUNE_INTERVAL)
                    status = get_status()
                    reason = check_abort(status)
                    if reason:
                        save_aborted = reason
                        break
                    if not status.get("tx"):
                        log(f"Carrier dropped during hold-tune (press {i+1}).")
                        break
                    log(f"  tune-hold [{i+1}/{HOLD_TUNE_PRESSES}]: SWR ATU = {status.get('swr', 0):.2f}")
                if save_aborted:
                    log(f"ABORT during save: {save_aborted}")
                else:
                    t0 = time.time()
                    while time.time() - t0 < POST_HOLD_WATCH_SECS:
                        status = get_status()
                        reason = check_abort(status)
                        if reason or not status.get("tx"):
                            break
                        time.sleep(1.0)
                cur_state = get_display()
        else:
            log(f"Sweep aborted ({stop_reason}) — not attempting save, leaving position as-is.")
            cur_state = get_display()
    finally:
        flex_tune_off()

    log("Exiting MANUAL TUNE...")
    exit_to_splash(splash, cur_state)

    log("=== Re-enter MANUAL TUNE fresh, no carrier, verify saved value ===")
    splash2, sub2 = enter_manual_tune()
    final_readout = readout(sub2)
    log(f"Re-entered L: {final_readout['l_line']!r}")
    log(f"Re-entered C: {final_readout['c_line']!r}")
    exit_to_splash(splash2, sub2)

    log("=" * 50)
    log(f"Baseline before this run : L={baseline['l_line'].strip()!r} C={baseline['c_line'].strip()!r} SWR={start_swr:.2f}")
    log(f"Final saved value        : L={final_readout['l_line'].strip()!r} C={final_readout['c_line'].strip()!r}")
    log(f"Best SWR (ATU) found this run: {best_swr:.2f}")

if __name__ == "__main__":
    main()
