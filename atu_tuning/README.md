# SPE 2K-FA manual ATU tuning — automated sweep + save

Built and proven live 2026-07-18: took the 80m/Antenna-1/Input-2 manual-tune
entry (originally 3.806 MHz) from a native ~7.4:1 mismatch to a saved,
persisted 1.19:1. Full backstory, protocol details, and everything that was
tried (including dead ends) is in Claude's memory —
`spe_atu_manual_tune_protocol.md` — this README is just the practical
how-to for running it again on a new frequency.

## Why this exists

The SPE 2K-FA's manual tuner (`SET > MANUAL TUNE`) stores one C/L match per
~20kHz sub-band, not one per band. An antenna with a bad native SWR on part
of a band needs this run once per sub-band segment you want to use
(e.g. 80m in 20kHz steps: 3.800, 3.820, 3.840, 3.860, 3.880 MHz, ideally
starting closer to 3.5 MHz too).

## Prerequisites before running either script

1. Amp in STANDBY (not Operate), ATU engaged for the target band/antenna
   (not bypassed — `atuStatusCode` should read `"a"` from
   `GET http://localhost:8088/api/v1/status` on the Pi).
2. **Set the FlexRadio's VFO to the target frequency first.** The amp's
   sub-band selection is derived from the live CAT frequency it's tracking
   — the script does not set frequency for you.
3. Carrier must be OFF when you start the script — `SET` is blocked by the
   amp while transmitting, so menu navigation has to happen first with a
   clean, unkeyed radio.
4. Scripts must run **from the Pi** (`raspbnodered.local`) — they talk to
   `expert-amp-server` on `localhost:8088` and open their own direct
   connection to the FlexRadio's SmartSDR API at `flex.lan:4992` for
   the safety failsafe. Override with the `FLEX_HOST` / `FLEX_PORT` env vars if
   the radio moves. (Was hardcoded to `192.168.50.117` — the FLEX-8400 — which
   went dead when the FLEX-8600 replaced it on 2026-08-22, leaving the failsafe
   unable to reach the radio. Use the hostname, not a literal.) Copy them over
   and run via SSH, e.g.:
   ```
   scp tune_sweep_and_save.py ai5os@raspbnodered.local:/tmp/
   ssh ai5os@raspbnodered.local "python3 /tmp/tune_sweep_and_save.py"
   ```

## Workflow for a new frequency

1. Tune the FLEX to the target frequency, confirm amp is in Standby with
   the ATU engaged for the antenna in use.
2. Run `tune_sweep_and_save.py`. It will:
   - Navigate `SET > MANUAL TUNE` (display-verified every step).
   - Wait up to 90s for `tx=true` — **key up via the dashboard's "Tune
     Carrier On" button once you see the script has entered the sub-page**,
     not before.
   - Run a full bidirectional sweep on C (±15 steps) then L (±25 steps),
     recording SWR at every point, flagging anything under 2.0 as a
     possible safe point but continuing the full sweep regardless.
   - Walk to whichever point was actually best across the whole sweep.
   - Save it by holding TUNE (~6 rapid presses simulate a hold — the
     protocol has no real "hold" concept).
   - Force the FLEX carrier off (hard failsafe, independent of Node-RED,
     runs on every exit path including aborts).
   - Exit the menu, then re-enter fresh with no carrier to confirm the
     saved L/C readout actually persisted.
3. **If the log says the best point is at the very edge of the sweep
   window** (still improving when the range ran out), follow up with
   `tune_extend_until_climb.py` from the same saved point — it presses
   `l+` until it sees 3 consecutive rises in SWR (a confirmed real
   turnaround) or hits a 30-step safety cap, then returns to whichever
   point was actually best and re-saves. Run it again if it's still at
   the edge; stop once it either confirms a climb or the improvement per
   round becomes negligible (diminishing returns — this is what happened
   on 80m: 2.25 → 1.54 → 1.24 → 1.19, each round smaller than the last).

## Safety notes

- Every abort path (alarm, warning, lost serial contact, carrier drops
  unexpectedly) stops immediately without saving and force-unkeys the FLEX.
- Tune power defaults to 10% (`transmit set tunepower=10`), set by the
  existing "Tune Carrier On" dashboard button in the Node-RED flow — these
  scripts don't key the radio themselves, only the dashboard button does.
- If a script ever exits uncleanly (crashed, killed, network drop), check
  `GET http://localhost:8088/api/v1/status` for `tx:true` and, if so, press
  "Tune Carrier Off" on the dashboard manually.
