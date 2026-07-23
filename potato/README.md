# potato/ — potato.fm ("Potato Pad"), source-level via potato.fm

potato.fm is a launchpad on **Robinhood Chain** (chainId 4663, the same chain as
pons/flap/noxa/long). "Potato Pad — PEOPLE'S LAUNCHPAD" plants a coin straight
into a **locked Uniswap V3 position, live and tradable from the first block** —
so `direct`-kind launches have no bonding curve to graduate. It is an
**aggregator over several pad factory contracts** (six seen at first sight),
each row tagged with its `pad` address and a `kind` (`direct` = straight-to-V3,
`curve` = bonding-curve).

Detect + rank + alert only. It never trades. Stdlib only.

## Why a source-level scanner and not a GMGN trench rider

The other Robinhood pads without their own scanner (bags, bankr, long) ride
GMGN's Trenches board because reverse-engineering each isn't worth it. potato is
worth it on both ends:

- **potato.fm ships a clean public API** off its own Next.js origin — no auth,
  and **urllib-reachable** (it is *not* Cloudflare-walled the way long.xyz's own
  API is, which is what forced long onto GMGN). See
  `docs/research/potato-fm-api.md`.
- **The whole pad is tiny** — `/api/stats` showed ~60 tokens all-time at first
  sight, ~30 active. One page of `/api/tokens` *is* the complete board, so this
  gets **100% coverage**, which GMGN's fixed 50-row board can't give — and does
  so before GMGN would even index a brand-new pad.

## The two feeds are asymmetric on purpose

potato.fm exposes exactly what the site itself shows, and the two boards carry
different fields:

| feed | role | traction fields |
|---|---|---|
| `GET /api/tokens` ("Growing") | discovery, 🥔 EARLY bar, control pool | **`volume24Usd` only** + socials (inline) + age + `kind`/`pad` |
| `GET /api/ancient` ("Ancients") | 🚀 GRAD tier | **`fdvUsd` + `liquidityUsd` + `volume24Usd`** |

A Growing row has **no per-token mcap/holders/price/trades** — the site computes
market cap client-side from the V3 pool over RPC, which this scanner does not do.
So the EARLY bar is **volume + age only**, and (unlike noxa) there is no
`graduationPct` name-collision trap to sidestep — the field simply isn't there.

Socials (`website`/`twitter`/`telegram`) are **inline on the Growing feed**, so
an EARLY alert needs no per-token detail fetch (noxa needs one; potato doesn't).
There is also no per-token detail endpoint — `/api/tokens/{addr}` 404s.

## Tiers

- **🥔 POTATO EARLY** — a young coin on the Growing board crossing the volume bar.
- **🚀 POTATO GRAD** — a coin surfacing in the Ancients (matured onto a real
  Uniswap V3 WETH pool), carrying real fdv/liquidity. Its *appearance* is the
  event.

The first successful poll of each feed **seeds silently** — for Growing, only
the coins already over the bar (the strong backlog we must not re-alert on
restart); sub-bar Growing coins are left un-seeded so a coin launched shortly
before a restart can still alert if it crosses the bar afterwards.

## Bar

Volume + age only (the Growing feed carries no honeypot/tax/holders signal to
gate on):

| | vol24h | max age |
|---|---|---|
| **potato** | **$5K** | **24h** |

v1 judgment call against the measured board (2026-07-23): the young end (coins
<24h) sat almost entirely under $1K with a clean gap up to the one real mover
(~$13–16K). $5K sits in that gap. Provisional like every bar here; refit from
`data/events.jsonl` once outcomes accumulate.

Deal flow is genuinely thin right now (~10 launches/24h, most fizzle
immediately), so this fires rarely by design — a tight, high-signal bar on a
nascent pad, not a firehose.

## Scores are weaker on purpose

This feed carries volume + socials (+ fdv/liquidity for grads) and **none** of
GMGN's forensics (smart money, bot/insider/honeypot rates), so `score_item`
rewards volume/socials/size and there are few red-flag cons. Honest v1 — the
GMGN forensics recorded alongside each row (via `pons/outcomes.py`) are what the
refit will actually lean on.

## Pricing the outcome (track method: gmgn)

Every potato alert prices by track method **`gmgn`** (chainSlug `robinhood`) —
potato coins are ordinary Uniswap V3 tokens on Robinhood that GMGN indexes,
unlike noxa V2 (invisible to GMGN, needs its own `snap_noxa`). So
`tracker/track.py` needs **no** potato-specific method.

- **GRAD** alerts carry `fdvUsd` as a real return baseline (`mcap0`).
- **EARLY** alerts have no t0 mcap in the feed, so they record `mcap0=None` and
  lean on the tracker's earliest-snapshot baseline (`report.py`'s documented
  "baseline = price0 if present, else earliest snapshot"). Slightly conservative
  — a first-5-minute pump lands in the baseline — but correct and self-healing.

## Shadow controls (#9)

One passed-over sub-bar Growing coin per open slot is recorded to
`tracker/data/controls.jsonl` under platform `potato`. The measurable-baseline
gate here is **`volume24Usd > 0`** (a coin that has traded has a GMGN price to
snapshot) — the potato analog of noxa's `mcap > 0` gate, since potato has no
per-token mcap. State in `data/control_slot.json`. See
`docs/shadow-control-sampling.md`.

## Liveness caveat

potato.fm's API **is** its web layer, so if it goes down this scanner goes deaf
(same failure mode as noxa/flap). It is also an unaudited demo MVP: `/api/tokens`
occasionally 502s or times out under a cold scan cache — `get()` folds every
such failure to None, so a bad poll is skipped, never fatal. The on-chain
fallback (unused here — the pad factory events carry no traction field to score a
bar on) is the pad `Creation`/launch event; the pad addresses ride on each row
under `pad`.

## Usage

```bash
python3 potato/scan.py --once      # one diagnostic pass: Growing vs the bar + Ancients
python3 potato/scan.py --dry-run   # live loop, print alerts instead of sending
python3 potato/scan.py             # live -> Telegram (pons/.env creds)
```

No API key needed (potato.fm is open). Telegram creds from `pons/.env`. Alerts
are labelled `🥔 potato`, recorded to the tracker under platform `potato`, and
priced by track method `gmgn`.

24/7: `~/Library/LaunchAgents/com.sunrise.potato-scanner.plist`
(logs -> `potato/data/potato_scan.log`). The watchdog auto-discovers it from the
heartbeat at `potato/data/heartbeat.json`.
