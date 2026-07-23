# noxa.fi API — reverse-engineered surface

**Date:** 2026-07-23
**Platform:** noxa (Robinhood Chain, chainId 4663), relaunched at `noxa.fi`
**Method:** downloaded the homepage Next.js chunks and grepped for the API
client module (the whole client sits in one chunk, exported as `getTokens`,
`getTrades`, …). Every endpoint below was then verified live.

noxa ships **no** developer docs. This is the surface the web app itself uses.
No auth, no API key, CORS-open, fronted by BunnyCDN. Rate limit advertised via
`x-ratelimit-limit: 240` per 60s (per-IP).

## REST — base `https://api.noxa.fi/api`

| Path | Notes |
|---|---|
| `GET /tokens?sort=&q=&page=&limit=` | list. sorts: `trending` `new` `live` `gainers` `mcap` `volume` `holders` `trades` `oldest`. Returns `{items, nextPage, ethUsd}` |
| `GET /tokens/{addr}` | detail — list row **plus** `description`, `socials`, `pool`, `supply`, `positionId`, `poolFee` |
| `GET /tokens/{addr}/trades?limit=&before=` | trade feed; `before` = ts cursor |
| `GET /tokens/{addr}/candles?interval=&from=&to=` | OHLCV, volume `v` in WETH |
| `GET /tokens/{addr}/holders?limit=` | `{holders:[{holder,balance,pct}], total}` |
| `GET /tokens/{addr}/comments?page=` | |
| `GET /stats/overview` | coins, coins24h, volume24h(Weth/Usd), trades24h, holders, creators, lastTradeTs, ethUsd |
| `GET /stats/timeseries?range=` | |
| `GET /stats/top?metric=&limit=` | metric ∈ {volume, …} |
| `GET /profile/{addr}` · `/profile/{addr}/fees?page=` · `/profile/{addr}/claimable` | |
| `GET /launch/quote?ethIn={wei}` | `{tokensOut, priceWethBefore, priceWethAfter, feeWei, capped}` |
| `POST /launch/pin` · `/launch/mine-salt` · `/launch/pin-nonce` | launch flow (mines the `…4663` vanity address) |

### `/tokens` row shape

```json
{
  "token": "0x…4663", "name": "…", "symbol": "…", "logo": "…",
  "deployer": "0x…",
  "priceWeth": 3.2e-7, "marketCapWeth": 321.7, "volume24hWeth": 646.0,
  "priceUsd": 0.00062, "marketCapUsd": 621676.9, "volume24hUsd": 1248399.0,
  "trades24h": "2587", "holderCount": 599, "createdTs": 1784739532,
  "source": "noxa", "changePct5m": 10.4,
  "graduated": true, "graduatedAt": 1784739545, "graduationPct": 100
}
```

Everything a scanner needs in one row — no RPC round-trip. Two gotchas:

- **Numeric fields are inconsistently typed.** `trades24h` comes back a string on
  `/tokens/{addr}` but a number on `/stats/top`; the site coerces every numeric
  field. Coerce on read.
- **`graduationPct` is NOT a bonding-curve progress fraction** despite the name.
  It sits at a ~6.8% floor / ~8% median for active coins and only jumps to 100%
  at graduation (`noxacat`: 709 holders, $161K/24h, 3082 trades → 14.9%). It
  tracks a net curve reserve that two-way trading keeps low. Use holders /
  volume / trades for traction; don't gate on `graduationPct`.
- **`marketCapUsd` is FDV at the current curve price** (`priceUsd × 1e9` supply),
  so it reads small for pre-graduation coins ($6K for that same `noxacat`) and
  jumps at graduation. Fine as a relative-return baseline; misleading as an
  absolute "market cap" next to a large 24h volume.

## WebSocket — `wss://ws.noxa.fi/ws`

Plain JSON, no auth. Subscribe/unsubscribe and receive channel messages:

```
-> {"sub":"global:new"}          <- {"ch":"system","data":{"subscribed":"global:new"}}
-> {"unsub":"global:new"}        <- {"ch":"global:new","data":{…token row…}}
                                 <- {"ch":"global:trades","data":{…trade…}}
```

Channels: `global:new`, `global:trades`, `token:{addr}:trades`, `token:{addr}:price`.
On connect the server sends `{"ch":"system","data":{"status":"connected"}}`.
Reachable from a stdlib-only client (raw `ssl` socket + hand-rolled RFC 6455
frames, ~40 lines) — no dependency, which keeps it inside the scanners' rule.

## On-chain identity (for the liveness fallback)

The web layer died once already (noxa.fun, 2026-07-18), so discovery that must
survive an API outage reads the factory event over RPC instead:

- **V2 factory** `0xdd84fddea1206115b37dbbc0ba5721530e1ba9c5`
- **launch topic0** `0x328c99edaab34570f8f3cc59ed72b4c179f4cb0abd9f57e25a0c563588c36994`
  (`topics[1]` = token, `topics[2]` = deployer), ~143 events/hour
- Does **not** emit the `TokenLaunched` topic V1/pons share, so `pons/api.py`'s
  discovery can't see it.
- Every V2 token address ends in the chainId suffix **`4663`**.
- Trading is single-sided Uniswap V3 from block one; router
  `0xcaf681a66d020601342297493863e78c959e5cb2`.

GMGN carries V2 under `token_info` pad key **`noxafi`** (not `noxa`, which is the
dead V1) — the source of the forensic fields `pons/outcomes.py` records.

See `noxa/scan.py` (source-level scanner) and
`memory:robinhood-chain-two-factories` for the factory history.
