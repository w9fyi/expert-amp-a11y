#!/usr/bin/env python3
"""Prototype decoder: expert-amp-server /api/v1/display/state -> text.

Validated 2026-07-18 against /api/v1/display/render.png ground truth on a real
EXPERT 2K-FA (standby splash screen: "EXPERT 2K-FA / Solid State / Fully
Automatic / Standby" + status bar "IN 2 | BAND 80 m | ANT 2 | CAT FLEX |
OUT MID | SWR --.-- | TEMP 81°F"). Every text cell decoded correctly.

Glyph-code mapping (codes are indices into the amp's 256-glyph 8x8 font ROM,
see expert-amp-server internal/font/spe1300_rom.go):

  0x01-0x5F : shifted ASCII -> chr(code + 0x20), covering ASCII 0x21-0x7F
              (includes lowercase: 'a' 0x61 -> code 0x41)
  0x00,0x60,0x7F : blank / space
  0x80-0xDF : custom SPE LCD symbols. Identified so far:
      0xAA  degree sign
      0x8F  vertical column separator (status bar)
      0x8D, 0x8E  horizontal divider segments
      0x9F, 0xA0  top/bottom border segments
      0xA1  right border vertical
      0xA2, 0xA3  corners
      0xB0-0xDF  SPE logo artwork (standby splash screen)
      (bar-graph/meter glyphs expected on the operate screen - TBD)

Usage: decode_display.py [--json]   (default: human-readable grid dump)
"""
import json
import sys
import urllib.request
from collections import Counter

URL = "http://raspbnodered.local:8088/api/v1/display/state"

# Custom glyphs with a sensible text rendering
CUSTOM_TEXT = {
    0xAA: "°",   # degree sign
    0x8F: "|",        # column separator
    0x99: "◄", 0x9A: "▲",  # left/up arrow-key symbols (menu legends)
    0x9B: "▼", 0x9C: "►",  # down/right arrow-key symbols
    0x9D: "◄", 0x9E: "►",  # plain arrowheads (slider end buttons)
    0xAE: "✓",              # check mark: current value in radio/checkbox lists
    0x92: "─", 0x93: "─",   # slider track segments
    0x94: "▫",              # small slider marker/tick
    0x95: "█", 0x98: "█",   # slider thumb (current level position)
}

# Custom glyphs that are pure decoration: borders, dividers, logo art.
# Decoded as space for text extraction.
DECOR = set([0x8D, 0x8E, 0x9F, 0xA0, 0xA1, 0xA2, 0xA3]) | set(range(0xB0, 0xE0))


def decode_cell(code, unknown=None):
    if code in (0x00, 0x60, 0x7F):
        return " "
    if 0x01 <= code <= 0x5F:
        return chr(code + 0x20)
    if code in CUSTOM_TEXT:
        return CUSTOM_TEXT[code]
    if code in DECOR:
        return " "
    if unknown is not None:
        unknown[code] += 1
    return f"[{code:02X}]"


def decode_grid(chars):
    unknown = Counter()
    lines = [
        "".join(decode_cell(code, unknown) for code in row).rstrip()
        for row in chars
    ]
    return lines, unknown


def main():
    raw = json.load(urllib.request.urlopen(URL))
    chars = raw["data"]["state"]["chars"]
    lines, unknown = decode_grid(chars)
    if "--json" in sys.argv:
        print(json.dumps({"lines": lines, "unknown_glyphs": sorted(unknown)}))
        return
    print(f"grid: {len(chars)} rows x {len(chars[0])} cols")
    for r, line in enumerate(lines):
        print(f"{r}: |{line}|")
    if unknown:
        print("\nunidentified glyphs (code: count):")
        for code, cnt in sorted(unknown.items()):
            print(f"  0x{code:02X}: {cnt}")


if __name__ == "__main__":
    main()
