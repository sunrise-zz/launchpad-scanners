# noxa/ — noxa (Robinhood Chain), source-level via noxa.fi

noxa is a bonding-curve launchpad on Robinhood Chain (chainId 4663, same chain
as pons/flap/vlad). It **died and came back**: the old site `noxa.fun` went
NXDOMAIN 2026-07-18 and its V1 factory (`0xD9eC2db5…`) went dormant the same day;
around **2026-07-22 it relaunched at `noxa.fi` on a new factory**
(`0xdd84fddea1206115b37dbbc0ba5721530e1ba9c5`) — the same domain-move pons made
from `pons.family`. The relaunch rebuilt its index from zero (`coins ==
coins24h`) and immediately ran busier than pons: **~205 launches/hour**,
**$4.7M/24h**, 69K trades/24h measured at restart.

Detect + rank + alert only. It never trades. Stdlib only.

## Why a source-level scanner and not a GMGN trench rider

The other Robinhood pads (bags, bankr, long) ride GMGN's Trenches board because
reverse-engineering each platform isn't worth it. noxa is different on both ends:

- **noxa.fi ships a clean public API** — undocumented but no auth, 240 req/min,
  and every field a scanner needs (holders, volume, trades, price, mcap,
  graduated) in one row, plus a WebSocket firehose. Recovered from the site's JS
  bundle; see `docs/research/noxa-fi-api.md`. That's source-level freshness
  (a launch appears in `/tokens?sort=new` and `ws global:new` on mint) with
  **complete** coverage of the pad, which GMGN's fixed 50-row board can't give.
- **GMGN's `noxa` trench key is the DEAD V1.** A live probe 2026-07-22 of
  `bags --pads noxa` returned only V1 tokens aged 280–510h with `new_creation`
  and `pump` both empty — GMGN files V2 under a *different* key, **`noxafi`**
  (confirmed via `token_info`, which reports `pad: noxafi`). So the `noxa` seat
  in `bags/scan.py`'s PADS is inert on V2 and this scanner does not touch it.

The V2 factory also does **not** emit the `TokenLaunched` topic the V1/pons
contracts share, so `pons/api.py`'s on-chain discovery can't see it either — the
API is genuinely the only complete live source.

### GMGN forensics still get recorded

`pons/outcomes.py` auto-enriches every alert and control row with a GMGN
`token_info` snapshot (smart-money, bot/rat/insider/honeypot rates, dev
reputation), and GMGN *does* carry V2 under `noxafi` — so those forensic fields
land in the tracker for the refit even though this scanner discovers and scores
off noxa.fi. Collected, not gated: `report.py` decides which fields predict
returns before any earns score weight.

## The `graduationPct` trap

noxa.fi has a `graduationPct` field that looks like the bonding-curve `progress`
the trench scanners gate on — it is **not**. Measured 2026-07-22 it sits at a
~6.8% floor and an ~8% median for *active* coins and only jumps to 100% at
graduation: `noxacat` with **709 holders, $161K/24h and 3082 trades** read
14.9%. On this single-sided curve it tracks a net reserve that continuous
two-way trading keeps low, so gating EARLY on it would reject the strongest
coins on the board. The real traction signals here are **holders + volume +
trades**; `progress` is display/score context only. (Same name-collision hazard
as `pons/api.py`'s two `BLOCK_SEC` constants — near-identical name, different
meaning.)

## Feeds and tiers

Two GETs per poll, deduped across both:

| feed | role |
|---|---|
| `GET /tokens?sort=new` | launch discovery, 🐣 EARLY bar, control pool |
| `GET /tokens?sort=trending` | catches 🚀 GRAD and late bar-crossers |
| `GET /tokens/{addr}` | per-alert enrichment (socials, description) |

- **🐣 NOXA EARLY** — a young coin crossing the traction bar.
- **🚀 NOXA GRAD** — `graduated` flipped true (curve completed, trading on DEX).

The first successful poll of each feed **seeds silently** — but only the coins
already over the bar (the strong backlog). Sub-bar coins in the `new` feed are
left un-seeded so a coin launched shortly before a restart can still alert if it
moons afterwards.

## Bar

Traction-only (no honeypot/tax signal in this feed to gate on), and **not** on
`graduationPct` (see above):

| | holders | vol24h |
|---|---|---|
| **noxa** | **60** | **$15K** |

v1 judgment calls against the measured board — provisional like every bar here;
refit from `data/events.jsonl` once outcomes accumulate. `--min-progress` stays
available as an opt-in gate but defaults off.

## Scores are weaker on purpose

This feed carries traction but none of GMGN's forensics, so `score_item` rewards
holders/volume/trades/momentum/socials and there are few red-flag cons (no
honeypot/bot/insider flags to subtract). Honest v1 — the GMGN forensics recorded
alongside each row are what the refit will actually lean on.

## Liveness caveat

A launchpad's web layer can die while its factory keeps minting — noxa already
proved this once (noxa.fun, 2026-07-18). noxa.fi's API **is** the web layer, so
if it goes down this scanner goes deaf, the same way flap does when
`batman.taxed.fun` is down. The on-chain fallback (unused here because it carries
no traction fields to score a bar on) is the factory event:

```
factory 0xdd84fddea1206115b37dbbc0ba5721530e1ba9c5
topic0  0x328c99edaab34570f8f3cc59ed72b4c179f4cb0abd9f57e25a0c563588c36994
        topics[1] = token, topics[2] = deployer
```

Every V2 token address also ends in the chainId suffix **`4663`** (mined via the
API's `/launch/mine-salt`), a cheap secondary label.

## Shadow controls (#9)

One passed-over sub-bar coin (with a measurable nonzero baseline) per open slot
is recorded to `tracker/data/controls.jsonl` under platform `noxa`, giving
`report.py` a baseline to compute EDGE against. State in `data/control_slot.json`.
See `docs/shadow-control-sampling.md` for the policy.

## Usage

```bash
python3 noxa/scan.py --once      # one diagnostic pass: every new-feed coin vs the bar
python3 noxa/scan.py --dry-run   # live loop, print alerts instead of sending
python3 noxa/scan.py             # live -> Telegram (pons/.env creds)
```

No API key needed (noxa.fi is open). Telegram creds from `pons/.env`. Alerts are
labelled `🌀 noxa`, recorded to the tracker under platform `noxa`, and priced by
track method `noxa` (`tracker/track.py` `snap_noxa`).

24/7: `~/Library/LaunchAgents/com.sunrise.noxa-scanner.plist`
(logs -> `noxa/data/noxa_scan.log`).
