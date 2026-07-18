# flap/ — flap.sh scanner (Robinhood Chain)

The busiest launchpad on Robinhood Chain by far: **~170 new tokens per 30 min**
observed (vs a handful/day on pons). Tokens can carry buy/sell trade tax and
graduate off a bonding curve (`progress` → listed).

## How detection works

**On-chain (primary).** Every flap token address ends in `...7777` — vanity
CREATE2 out of the factory diamond `0xe9f7...197b` (methods `newTokenV6`,
`newTokenV6WithVault`, …). The scanner polls Transfer-mint events
(`from = 0x0`) and filters that suffix: new launches show up within seconds,
and no Cloudflare can take this path away. Early traction is measured from the
token's own Transfer events (unique recipients ≈ holders, count ≈ trades),
fetched for the whole young cohort in chunked `eth_getLogs` calls.

**API (enrichment).** `https://batman.taxed.fun` is flap.sh's backend
(discovered via network capture; optional `_refresh` cache-buster):

| endpoint | gives |
|---|---|
| `/v3/board?limit=N` | trending; `sortBy=marketcap\|holders\|liquidity`, `isLowRisk=true` filter |
| `/v3/board/graduatinghot?limit=N` | near-graduation feed (progress, tax, holders, changes) |
| `/v3/coin/{addr}` | full detail: progress %, holdersCount, **inline top-20 holders**, `tax.buyTaxBps/sellTaxBps`, `isLowRisk` (FAC badge), liquidity, volume24h, change5m/1h/4h/24h, curve params |

Cloudflare blocks curl's TLS fingerprint but passes Python `urllib` — still, be
polite: the scanner only calls the API for candidates plus one 60 s
graduatinghot poll, and backs off 10 min after 5 straight failures (on-chain
detection keeps running regardless).

## Alert tiers

- 🐣 **FLAP EARLY** — token younger than 15 min crossing the traction bar
  (default: ≥120 unique recipients & ≥250 transfers; live-measured bars — ≥25
  fired ~470/day, ≥60 still ~290/day since real launches cluster at 60-75
  recipients), then gated on `sellTax ≤ 5%` / `buyTax ≤ 5%` and annotated with
  holders, mc/liq/vol, whale table share, FAC badge. If the API is unreachable
  the alert says `tax: ?` — the tax gate could not run.
- 🔥 **FLAP NEAR-GRAD** — graduatinghot entry ≥70% progress, same tax gates,
  once per token.

## Honest caveat

The EARLY traction bar is a **v1 heuristic, not backtested** — flap history
wasn't collected yet. Every launch, expiry, skip, and alert is appended to
`data/events.jsonl`; once a few days accumulate, fit the thresholds properly
(same playbook as `pons/backtest_multifactor.py`) and update the defaults.

## Run

```bash
python3 flap/scan.py --dry-run     # print alerts, no Telegram
python3 flap/scan.py               # live -> Telegram (reuses pons/.env creds)
python3 flap/scan.py --min-recips 40 --max-sell-tax 300   # stricter
```
