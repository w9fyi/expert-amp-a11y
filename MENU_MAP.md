# EXPERT 2K-FA Set-mode menu map

Captured 2026-07-18 from live hardware via expert-amp-server, using
display-verified traversal (`capture_menu.py`). Raw captures with `chars` +
`attrs` grids under `captures/`. Firmware is newer than the May 2011 manual:
the menu is a single 2D grid screen, not sequential pages, and has two items
the manual lacks (CONFIG, EXIT).

## The menu screen (entered from STANDBY with [SET])

```text
0:        SETUP OPTIONS vs. INPUT 2
1:  CONFIG        DISPLAY        ALARMS LOG
2:  ANTENNA       BEEP    On     TUN ANT
3:  CAT           START   Oprt   RX  ANT
4:  MANUAL TUNE   TEMP.   °F     FAN NOISE
5:                               EXIT
6:  <context help for selected item>
7:  [◄▲][▼►]:SELECT          [SET]:CONFIRM
```

- Title row shows the active input ("vs. INPUT 2") — settings are per-input.
- Items with a live value show it inline (BEEP On, START Oprt, TEMP. °F).
- Row 6 is a context-help line that changes with the selection.
- Row 7 is the key legend (glyphs 0x99/0x9A = ◄▲, 0x9B/0x9C = ▼►).

## Traversal order ([▼►] = `right` button), column-major, wraps after EXIT

| # | Item | Context help (row 6) | Inline value |
| --- | ---- | -------------------- | ------------ |
| 1 | CONFIG | OTHER SETTINGS | — |
| 2 | ANTENNA | SET ANTENNAS vs. BANDS | — |
| 3 | CAT | SET CAT INTERFACE FEATURES | — |
| 4 | MANUAL TUNE | MANUAL TUNE OPERATIONS | — |
| 5 | DISPLAY | BACKLIGHT/CONTRAST SETTINGS | — |
| 6 | BEEP | KEYBOARD BEEP On/Off | On |
| 7 | START | SET STARTUP DEFAULT MODE | Oprt |
| 8 | TEMP. | TEMPERATURE °C/°F | °F |
| 9 | ALARMS LOG | BROWSE/CLEAR ALARMS LOG | — |
| 10 | TUN ANT | TUNABLE ANTENNAS SETTINGS | — |
| 11 | RX ANT | RX-ONLY ANTENNA SETTING | — |
| 12 | FAN NOISE | POWER-SUPPLY FAN MANAGEMENT | — |
| 13 | EXIT | LEAVE THIS MENU PAGE | — |

## Reading the selection programmatically

`/api/v1/display/state` returns `state.chars` (glyph codes) and `state.attrs`.
`attrs == 1` marks inverse-video cells — exactly the highlighted item.
Decoding the attr-1 cells yields the item name plus inline value
(e.g. " TEMP.   °F "), ready to speak. Row 6 gives a natural longer
description. This is the complete read layer for an accessible menu:

1. selected-item announcement = decode(attr==1 cells)
2. description = decode(row 6)

## Item types — machine-readable from the legend row (verified live)

The row-7 legend changes with the selected item and tells you what [SET] does
BEFORE you press it:

- **`[SET]:CHANGE`** — inline toggle: BEEP, START, TEMP. Pressing [SET]
  cycles the value **with immediate effect**.
- **`[SET]:CONFIRM`** — opens a sub-page (CONFIG, ANTENNA, CAT, MANUAL TUNE,
  DISPLAY, ALARMS LOG, TUN ANT, RX ANT, FAN NOISE) or executes (EXIT).

**CRITICAL: [DISPLAY] does NOT revert toggle items.** Verified live: [SET] on
TEMP. flipped °F→°C instantly; [DISPLAY]-exit left the amp in °C (status bar
read 27°C). Reverting required navigating back and toggling again. The 2011
manual's "DISPLAY exits with no programming effect" does not hold for CHANGE
items on this firmware. Traversal engines must treat every [SET] press on a
CHANGE item as a live write.

Navigation presses (left/right) remain provably safe — two full 13-position
traversals plus targeted navigations changed nothing.

## ALARMS LOG sub-page (CONFIRM item; entered/verified live)

Local key semantics differ from the top menu — the on-screen legend is
authoritative per page:

```text
0:                ALARMS LOG
1: 10)IN2: SWR EXCEEDING LIMITS
2:  9)IN2: SWR EXCEEDING LIMITS
   ...4 entries visible...
6:  [◄▲] [▼►] | [TUNE] & [OP]  |   [SET]
7:   SCROLL   | CLEAR HISTORY  |   QUIT
```

- Arrows scroll the 10-entry history; **[SET] quits** (straight back to the
  splash, not the setup menu); **[DISPLAY] toggles a second view** showing
  timestamps in cumulative operate-hours:
  `OP Time: 1944:18:52` / `10)P2B01  1941:17:47  AFTER 0:03:03` …
- [TUNE]+[OPERATE] clears the history — never send these here.

## Safety rules for traversal (updated after live findings)

- Menu only opens in STANDBY.
- Read the legend row BEFORE any [SET] press; refuse [SET] on a CHANGE item
  unless the intent is a write.
- Sub-pages carry their own legends — parse them per page, don't assume the
  top-menu key semantics.
- Every press display-verified (wait for `sequence`/grid change).

## Sub-pages (all captured 2026-07-18, entered/exited clean, zero drift)

Raw captures in `captures/00_sub_*`. Key structural finding: **sub-pages have
explicit SAVE items** (CONFIG, ANTENNA, TUN ANT, RX ANT, FAN NOISE) — inside
a sub-page, edits are staged until SAVE. [DISPLAY] exits a sub-page cleanly
(verified: splash matched baseline byte-for-byte after every entry/exit).
The DISPLAY page uses `[SET]:QUIT` instead; CAT has an EXIT list item.

- **CONFIG** ("OTHER SETTINGS"): checkboxes `[ ] REMOTE ANT SWITCH`,
  `[ ] SO2R MATRIX`, `[ ] COMBINER` (all unchecked on Justin's amp) + SAVE.
- **ANTENNA**: the entire per-band × 3-slot antenna matrix on one screen
  (IN2: 160m "1 N N", 80m "1 2 N", 60m "1 N N", 40m "1 2 5", 30m "1 N N",
  20m/17m/15m/12m "3 1 5", 10m "3 1 5", 6m "3 6 4") + SAVE. [TUNE] toggles
  ATU yes/no per slot. Context line narrates the cursor cell
  ("SET 2nd ANTENNA ON 80m BAND").
- **CAT**: brand list (SPE/ICOM/KENWOOD/YAESU/TEN-TEC/FLEX-RADIO/ELECRAFT/
  NONE) + EXIT. NOTE: cursor sat on ICOM while the splash bar says CAT FLEX
  for IN2 — cursor position is NOT the current value here; how the current
  brand is marked is still an open question.
- **DISPLAY**: BACKLIGHT and CONTRAST slider bars with `[◄L]`/`[L►]`,
  `[◄C]`/`[C►]` step buttons; thumb glyph position = current level.
  **`[INPUT]:FACTORY DEFAULTS` — never send `input` on this page.**
  `[SET]:QUIT` exits.
- **TUN ANT**: ANT1–6 each Yes/No (all No) + PORT + SAVE.
- **RX ANT**: ANT2–6 each Yes/No (all No; ANT1 not offered) + SAVE.
- **FAN NOISE**: radio group `[ ] QUIET MODE (SSB ONLY)` /
  `[✓] NORMAL MODE (ALL MODES)` + SAVE; ✓ (glyph 0xAE) marks the current
  value. **This makes legacy Fan Mode's blind backlight-byte macro obsolete:
  fan switching = enter sub-page, select, SAVE — all display-verified.**

## Glyph catalog additions (identified from ROM bitmaps)

- 0x99/0x9A/0x9B/0x9C: ◄▲▼► arrow-key symbols (legends)
- 0x9D/0x9E: plain ◄/► arrowheads (slider end buttons)
- 0xAE: ✓ check mark — current value in radio/checkbox lists
- 0x92/0x93: slider track; 0x95/0x98: slider thumb; 0x94: small tick

## Still unmapped

- MANUAL TUNE (live RF procedure — needs Justin present and a dummy load).
- ALARMS LOG scrolling (entries 6..1) — only 10..7 captured.
- How CAT marks its current brand.
- Operate-screen meter/bar glyphs — capture while transmitting.
