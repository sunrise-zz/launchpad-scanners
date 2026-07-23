# long/ — long.xyz (Robinhood Chain, stock-token launches)

`app.long.xyz` is a bonding-curve launchpad on Robinhood Chain (chainId 4663,
same chain as pons/flap/vlad), branded "launch with stock tokens" — most of the
board is equity/tech tickers (MICROSOFT, SANDISK, TSLALONG). Probed 2026-07-22
it was the busiest launchpad on GMGN's robinhood trenches board: **~2.4 new
tokens/min**, graduates reaching $200–400K mcap.

This scanner is `bags/scan.py`'s implementation pointed at one launchpad — same
tiers, scoring, seeding and tracker wiring. See `bags/README.md` for those.

## Why its own instance and not one more entry in `bags` PADS

GMGN returns a fixed number of rows per trenches section, so every launchpad
sharing an instance competes for the same 50 slots. Measured with both pad
lists side by side (2026-07-22):

| `pump` section | bags list | bags list **+ longxyz** |
|---|---|---|
| longxyz | — | **46** |
| bankr | 22 | 2 |
| bags | 19 | 1 |
| virtuals | 9 | 1 |

Adding long.xyz to the shared call would have *removed* coverage of four
launchpads rather than adding one — the `pump` section is what fires 🐣 EARLY,
so bags and bankr would have gone quiet without erroring. A separate instance
gets its own POST, its own 50 slots, and its own `data/` + heartbeat so the
watchdog reports the two feeds independently.

## Why GMGN and not the platform's own API

`api.long.xyz` is Cloudflare-hard-blocked: 403 to curl **and** to plain
`urllib`, unlike flap's `batman.taxed.fun`, which only fingerprints curl's TLS.
The Next.js app's JS chunks were also serving 503, so no endpoint shapes could
be read off a live browser session. GMGN carries the launchpad natively under
`launchpad_platform` key **`longxyz`**, pre-enriched with the same ~118 fields,
and surfaces `new_creation` rows **~6s after mint** — source-level freshness
without reverse-engineering the platform.

If GMGN ever drops the pad, the on-chain fallback is the vanity suffix: every
long.xyz token address sampled ends in **`1e18`** (136/137), the same CREATE2
trick flap uses with `7777`.

## Bar

Tighter than bags because the bar has to scale with how busy the board is, not
just with what looks like traction:

| | holders | vol24h | progress |
|---|---|---|---|
| bags | 25 | $1K | 25% |
| **long** | **40** | **$10K** | **30%** |

On a live board bags' numbers passed 12 of 50 `pump` rows here vs 7 at these —
the extra five were thin rows (16–32 holders on $6–18K) this launchpad emits
continuously. Expect **~2 EARLY/h + ~0.7 GRAD/h**. Provisional like every bar
in this repo; refit from `data/events.jsonl` once outcomes accumulate.

## Shadow controls (#9)

Inherited from the shared implementation: one passed-over `pump` coin per open
slot is recorded to `tracker/data/controls.jsonl` under platform `longxyz`,
giving `report.py` a baseline to compute EDGE against. State in
`data/control_slot_longxyz.json`, separate from bags' quota. See
`bags/README.md` for the sampling design and `docs/shadow-control-sampling.md`
for the policy.

## Usage

```bash
python3 long/scan.py --once      # one diagnostic pass: every coin vs the bar
python3 long/scan.py --dry-run   # live loop, print alerts instead of sending
python3 long/scan.py             # live -> Telegram (pons/.env creds)
```

Needs `GMGN_API_KEY` in `~/.config/gmgn/.env` (read-only key; never
`GMGN_PRIVATE_KEY`). Alerts are labelled `🔭 long` and recorded to the tracker
under platform `longxyz`.

24/7: `~/Library/LaunchAgents/com.sunrise.long-scanner.plist`
(logs -> `long/data/long_scan.log`).
