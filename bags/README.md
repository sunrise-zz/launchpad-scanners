# bags/ — GMGN Trenches scanner (uncovered Robinhood-chain launchpads)

Watches the launchpads on Robinhood Chain that the six source-level scanners
**don't** cover — `bags`, `bankr`, `noxa`, `dyorswap` and virtuals-on-robinhood
(`virtuals/scan.py` only sees the BASE/SOLANA app API) — via GMGN's Trenches
board (`pons/gmgn.py trenches()`, one authed POST per poll, no RPC).

Found 2026-07-18 while probing the GMGN Agent API: robinhood trending surfaced
`bags` coins (RobinHub, $157K mcap, 414 holders) that never appear in any feed
we scan. pons/flap/flap_stocks are deliberately excluded here — the dedicated
scanners catch those minutes earlier at the source.

`longxyz` is excluded for a different reason: it runs the same implementation as
its own instance (`long/scan.py`). GMGN returns a fixed number of rows per
section, so pads on one instance compete for the same 50 slots — long.xyz is
busy enough to take 46 of 50 `pump` rows and push bags 19 → 1. Adding a
launchpad that big here would silently blind the ones already listed; give it
its own instance instead. See `long/README.md`.

## Tiers

| Tier | Source section | Fires when |
|---|---|---|
| 🐣 TRENCH EARLY | `pump` (= near_completion) | age ≤ 24h · holders ≥ 25 · vol24h ≥ $1K · progress ≥ 25% · sell tax ≤ 5% · not honeypot |
| 🚀 TRENCH GRAD | `completed` | coin newly bonds (post-seed) |

Trenches items arrive pre-enriched (~118 fields), so alerts carry GMGN
forensics for free: smart_degen/renowned counts, bot/rat/insider rates,
X follower count, taxes. The v1 score (base 42/50 ± modifiers) and the bar
are judgment calls — every launch/alert is logged to `data/events.jsonl` and
every alert to the outcome tracker (track method `gmgn`), so both get refit
from real returns like every other scanner in this repo.

## Shadow controls (#9)

Each poll, one coin that was **evaluated and passed over** — on the `pump`
board but under the bar — is sampled per launchpad and recorded to
`tracker/data/controls.jsonl`, never to the alert stream. Without it
`report.py` can print "TRENCH EARLY returned +X%" but not "…against what",
and can't tell whether the bar is too tight, because the coins just under it
were never measured.

Drawn from `pump` rather than `new_creation` because that is the only section
this scanner makes a decision on, and it keeps controls at a comparable point
in a coin's life — sampling at mint would baseline every control at age 0
against alerts that fire hours in.

**One quota per launchpad, not per process.** `pons/controls.py` assumes a
scanner covers one launchpad; this one covers five, and `report.py`'s EDGE
subtracts the control median of the *same* platform. A shared quota would
spend the hour on whichever pad was busiest and leave the rest with no
baseline — no error, just an EDGE that can't be computed. State lives in
`data/control_slot_<pad>.json`, one file each. Kill switch: `--controls-k 0`.

Startup seeds each section silently (no backlog spam) and takes no controls
during seeding — the backlog was marked done rather than evaluated, so nothing
in it was genuinely passed over. Needs `GMGN_API_KEY`
in `~/.config/gmgn/.env` (read-only key; never `GMGN_PRIVATE_KEY`).

## Usage

```bash
python3 bags/scan.py --once      # one diagnostic pass: every coin vs the bar
python3 bags/scan.py --dry-run   # live loop, print alerts instead of sending
python3 bags/scan.py             # live -> Telegram (pons/.env creds)
```

24/7: `~/Library/LaunchAgents/com.sunrise.bags-scanner.plist`
(logs -> `bags/data/bags_scan.log`).
