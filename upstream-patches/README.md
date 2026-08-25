# Upstream patches

Local patches applied to [`FtlC-ian/expert-amp-server`](https://github.com/FtlC-ian/expert-amp-server)
on the Node-RED Pi that are **not** in upstream `main`. Kept here so they survive
an SD card failure and so there is a reviewable diff to attach if one is ever
filed upstream.

The Pi's checkout at `~/expert-amp-server` keeps these as commits on a local
branch (`local-readwatchdog`), not as uncommitted working-tree edits. To upgrade:

```sh
git fetch origin
git rebase origin/main
```

Then rebuild from source on the Pi per the usual procedure.

## 0001-serial-read-watchdog.patch

Applies to `internal/runtime/serial_source.go` (+43 lines, no deletions).
Committed on the Pi as `f04c4bb`, based on upstream `30b03db`.

Adds a session-scoped watchdog goroutine inside `readFromPort()` that tracks
`lastReadActivity` (updated after every `port.Read()` return, success or error)
and force-closes the port if no `Read()` has returned at all for
`readWatchdogTimeout` (5 s). Closing the port unblocks the hung `Read()` with an
error, which propagates through the existing `serial read: %w` path into the
reconnect loop already present in `Start()` — no new reconnect logic, just an
intentional trigger for the one that was already there.

**Why:** an observed ~23-minute total stall over the SPE-LAN-UNIT pty bridge, in
which the service reported itself `active`/healthy with zero error log lines and
near-zero CPU, while `/api/v1/status`'s `lastContactAt` stayed frozen at a single
timestamp. Display and status polling froze at the identical instant, confirming
one shared stall rather than two independent bugs. The amp and bridge were
confirmed fine throughout via a fresh raw TCP 7388 connection returning valid
live frames on demand.

**Why not filed upstream:** this is a heuristic workaround (a watchdog timer),
not a root-cause fix. The actual pty-vs-termios timeout mismatch in the
underlying `serial.Port` implementation is still unaddressed, and the stall has
only ever been reproduced on this one LAN-unit bridge setup. Worth filing as an
issue describing the stall — with this diff offered as a starting point — rather
than as a PR presented as the correct fix.

The 5 s threshold is well above the 250 ms configured read timeout plus the
observed ~50–65 ms LAN jitter, so it only fires on a genuine stall.
