#!/usr/bin/env python3
"""Shared evidence-logging helpers for capture_menu.py / capture_subpage.py.

Reproduces expert-amp-server's NDJSON capture format (internal/capture/
recorder.go) so our directed-traversal captures hash- and schema-match its
passive display-capture tool. Read-only against the amp except for the
existing display/render.png fetch already used by save_capture().
"""
import hashlib
import json
import os
import struct
import time
import urllib.request

BASE = "http://raspbnodered.local:8088/api/v1"
CAPTURE_FORMAT = "expert-amp-display-capture/v1"  # matches upstream's captureFormat


def get_json(path):
    with urllib.request.urlopen(f"{BASE}/{path}", timeout=8) as r:
        return json.load(r)


def get_snapshot():
    """Single call: chars/attrs + telemetry + lcdFlags + sequence."""
    return get_json("runtime/snapshot")["data"]


def get_version():
    return get_json("version")["data"]


def state_hash(chars, attrs, lcd_flags):
    """Byte-for-byte match of expert-amp-server's capture.StateHash().

    chars/attrs: the 8x40 int grids from snapshot["state"].
    lcd_flags: snapshot["frame"]["lcdFlags"] dict, or None.
    """
    h = hashlib.sha256()
    h.update(CAPTURE_FORMAT.encode())
    for row in chars:
        h.update(bytes(row))
    for row in attrs:
        h.update(bytes(row))
    if lcd_flags is None:
        h.update(b"\x00")
    else:
        h.update(b"\x01")
        h.update(struct.pack("<HH", lcd_flags["rawInverted"], lcd_flags["decoded"]))
        h.update(bytes([
            1 if lcd_flags.get("checksumPresent") else 0,
            1 if lcd_flags.get("checksumValid") else 0,
        ]))
    return "sha256:" + h.hexdigest()


def load_seen_hashes(ndjson_path):
    """Resume support: read stateHash from every existing record."""
    seen = set()
    if not os.path.exists(ndjson_path):
        return seen
    with open(ndjson_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            seen.add(json.loads(line)["stateHash"])
    return seen


def build_record(snapshot, version, transition_label, previous_hash):
    state = snapshot["state"]
    frame = snapshot["frame"]
    h = state_hash(state["chars"], state["attrs"], frame.get("lcdFlags"))
    record = {
        "format": CAPTURE_FORMAT,
        "stateHash": h,
        "previousStateHash": previous_hash or "",
        "transitionLabel": transition_label or "",
        "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshotUpdatedAt": snapshot.get("updatedAt", ""),
        "sequence": snapshot.get("sequence", 0),
        "source": snapshot.get("source", ""),
        "frameKind": snapshot.get("frameKind", ""),
        "chars": state["chars"],
        "attrs": state["attrs"],
        "screenText": frame.get("screenText", ""),
        "lcdFlags": frame.get("lcdFlags"),
        "frame": frame,
        "server": {"baseUrl": BASE.rsplit("/api", 1)[0], **version},
        "amplifier": {
            "modelName": snapshot.get("telemetry", {}).get("modelName", ""),
            "telemetry": snapshot.get("telemetry", {}),
        },
    }
    return record, h


def append_record(ndjson_path, record):
    with open(ndjson_path, "a") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())


def record_evidence(evidence_path, seen, previous_hash, transition_label=""):
    """Fetch the current snapshot, hash it, and append if new.

    Returns (hash, was_new). `seen` is mutated in place (add on new hash) so
    callers can keep passing the same set across a traversal session.
    """
    snapshot = get_snapshot()
    version = get_version()
    record, h = build_record(snapshot, version, transition_label, previous_hash)
    if h in seen:
        return h, False
    seen.add(h)
    append_record(evidence_path, record)
    return h, True
