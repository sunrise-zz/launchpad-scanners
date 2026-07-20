# Scanner feed watchdog

The watchdog distinguishes a process that is merely running from a scanner
that is successfully ingesting its primary feed. Each scanner writes
`<scanner>/data/heartbeat.json` after a successful parsed feed response. A
valid empty response still counts: quiet launchpads such as Arc must not look
dead just because no new token launched.

Targets are discovered from installed `com.sunrise.*-scanner` and
`com.sunrise.*-collector` LaunchAgents. The script uses the configured program
path to locate the default heartbeat, or honors an explicit `--heartbeat`
argument. This includes scheduled collectors without a second hard-coded target
list.

## Staleness thresholds

| Scanner | Normal primary poll | DOWN after |
|---|---:|---:|
| pons | ~2s, on-chain `TokenLaunched` cursor | 2 min |
| flap | ~3s, Robinhood RPC block/log ingest | 2 min |
| pump | ~20s, active-trades REST feed | 3 min |
| virtuals | ~30s, BASE created-at feed | 4 min |
| arc | ~30s, Railway launches feed | 5 min |
| bags | ~30s, GMGN Trenches feed | 4 min |
| pons-reputation | every 6h, on-chain graduation backfill | 8 h |

Notifications are edge-triggered. A long outage sends one DOWN message, then
nothing until one UP message after ingestion recovers. Failed Telegram sends
remain unacknowledged and retry on the next watchdog pass.

The watchdog writes `watchdog/data/heartbeat.json` every cycle and persists
notification state in `watchdog/data/state.json`. Both files are runtime state
and are gitignored.

## LaunchAgent

Install the committed plist once, then bootstrap it:

```bash
cp watchdog/com.sunrise.scanner-watchdog.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sunrise.scanner-watchdog.plist
launchctl kickstart -k gui/$(id -u)/com.sunrise.scanner-watchdog
```

The job uses the same Telegram credentials as the scanners. Inspect liveness
without sending anything:

```bash
cat watchdog/data/heartbeat.json
launchctl print gui/$(id -u)/com.sunrise.scanner-watchdog
```

Offline tests simulate the feed-dead/process-alive failure mode:

```bash
.venv/bin/python -m pytest tests/test_watchdog.py
```
