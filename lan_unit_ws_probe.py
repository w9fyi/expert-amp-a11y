#!/usr/bin/env python3
"""Read-only probe of the SPE-LAN-UNIT's own web-UI WebSocket (/ws).

Sends ONLY DISPLAY_POLL_CMD (0x55 0x55 0x55 0x01 0x80 0x80) -- the same
display-read request the stock Term_Web UI issues every 250ms. 0x80 is in the
display/status range, NOT the physical-key range, so no button is ever pressed.

Purpose: determine whether the amp's serial side is alive at all, independent
of the wedged TCP-7388 virtual-COM mirror. Run ONLY with spe-lan-bridge.service
stopped, so this is the single client on the amp's serial interface.
"""
import sys
import time

import websocket

URL = "ws://192.168.50.119/ws"
POLL = bytes([85, 85, 85, 1, 128, 128])
DURATION = 15.0


def valid_frame(b):
    if len(b) != 371 or b[0] != 170 or b[1] != 170 or b[2] != 170 or b[7] != 1:
        return False
    e = (b[3] << 8) | b[4]
    t = (b[5] << 8) | b[6]
    return ((e ^ t) & 0xFFFF) == 0xFFFF


def render(b):
    """chars are the first 320 bytes of the 360-byte display payload: 8 rows x 40."""
    payload = b[9:369]
    chars = payload[:320]
    rows = []
    for r in range(8):
        row = chars[r * 40:(r + 1) * 40]
        rows.append("".join(chr(c) if 32 <= c < 127 else "." for c in row))
    return rows


def main():
    print(f"connecting to {URL} ...")
    ws = websocket.create_connection(URL, timeout=5)
    ws.settimeout(1.0)
    frames = acks = other = 0
    last = None
    deadline = time.time() + DURATION
    next_poll = 0.0
    try:
        while time.time() < deadline:
            now = time.time()
            if now >= next_poll:
                ws.send_binary(POLL)
                next_poll = now + 0.25
            try:
                msg = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as exc:
                print(f"recv error: {exc}")
                break
            if not isinstance(msg, (bytes, bytearray)):
                other += 1
                continue
            if valid_frame(msg):
                frames += 1
                last = bytes(msg)
            elif len(msg) == 5 and msg[0] == 170:
                acks += 1
            else:
                other += 1
    finally:
        ws.close()

    print(f"\n=== RESULT over {DURATION:.0f}s ===")
    print(f"valid 371-byte display frames: {frames}")
    print(f"5-byte acks:                   {acks}")
    print(f"other/unrecognized messages:   {other}")
    if last:
        print("\n=== LIVE DISPLAY FROM LAN UNIT ===")
        for row in render(last):
            print(f"  |{row}|")
        print("\nVERDICT: amp serial side is ALIVE -- wedge is in the TCP-7388 mirror.")
        return 0
    print("\nVERDICT: no frames -- amp serial side is NOT responding to the LAN unit.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
