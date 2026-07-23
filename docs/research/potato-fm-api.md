# potato.fm API — reverse-engineered surface

**Date:** 2026-07-23
**Platform:** potato.fm ("Potato Pad"), Robinhood Chain (chainId 4663)
**Method:** opened the site, watched the network panel, then replayed every
endpoint from plain `urllib` server-side to confirm it's reachable without the
browser's cookies/headers.

potato.fm ships **no** developer docs. This is the surface the web app itself
uses. It is a **Next.js app that serves its own API off the same origin**
(`https://potato.fm/api/...`) — there is no separate `api.potato.fm` host. No
auth, no API key. Reachable from stdlib `urllib` (it is **not** Cloudflare-walled
the way long.xyz's own API is).

The site is an **aggregator over several Robinhood-chain pad factories**, not a
single launchpad: every token row carries a `pad` address and a `kind`
(`direct` = launched straight into a locked Uniswap V3 position, `curve` =
bonding-curve). Six distinct `pad` addresses seen at first sight.

It also self-describes as an **unaudited demo MVP**, and behaves like one: the
`/api/tokens` endpoint intermittently returns 502 or times out while its scan
cache is cold (it caches an on-chain scan and serves it; `servedAt −
scanCompletedAt` ≈ 25–35s, so freshness is ~30s, not instant). A client must
tolerate transient failures.

## REST — base `https://potato.fm/api`

| Path | Notes |
|---|---|
| `GET /api/tokens` | the "Growing" board. `{chainId, servedAt, scanCompletedAt, state, creations:[…], unavailable}`. `creations` is the token list. `sort`/`limit` query params are accepted but currently **ignored** (fixed server-side order); at ~60 rows the whole board fits one page anyway. |
| `GET /api/ancient` | the "Ancients" board — tokens matured onto a real WETH pool. `{tokens:[…], unavailable}`. **Richer** per-row than Growing. |
| `GET /api/stats` | pad-wide aggregates (see below). |
| `GET /api/profile?addresses=0x…,0x…` | creator profiles (batch). `{profiles:{addr:{username,bio,avatarUrl,…}}}`. |
| `POST /api/rpc` | a Robinhood-chain JSON-RPC **proxy** (`eth_chainId` → `0x1237` = 4663). The frontend uses it to read each token's V3 pool and compute market cap client-side. |
| `GET /api/tokens/{addr}`, `/api/token/{addr}` | **404** — there is no per-token detail endpoint. |

### `/api/tokens` `creations` row shape

```json
{
  "token": "0x…", "creator": "0x…", "name": "…", "symbol": "…",
  "pool": "0x…",                       // the Uniswap V3 pool
  "imageURI": "ipfs://…",
  "website": "", "twitter": "https://x.com/…", "telegram": "",   // socials INLINE
  "timestamp": 1784500460,             // creation, unix seconds
  "blockNumber": "14202752",           // string
  "pad": "0x…",                        // which pad factory launched it
  "volume24Usd": 126496.83,            // the ONLY per-token traction field here
  "kind": "direct"                     // "direct" | "curve"
}
```

Gotchas:

- **The only traction field is `volume24Usd`.** No holders, no per-token mcap,
  no price, no trade count, no graduation flag. Market cap is computed by the
  frontend from the V3 pool over `/api/rpc`, not served in this row.
- **Socials are inline** (`website`/`twitter`/`telegram`) — no detail fetch
  needed to enrich an alert with them (contrast noxa, whose list feed omits
  socials).
- **Symbols repeat.** Several live tokens share a symbol (multiple `POTATO`,
  `MASH`, `CHIP`, `SPUD`) — they are distinct addresses. **Dedupe by address,
  never symbol.**
- **`blockNumber` is a string**; `timestamp` is unix **seconds**.
- Placeholder **`test`** launches (name/symbol literally "test") show up with
  real volume — filter them out of alerts.

### `/api/ancient` `tokens` row shape (richer)

```json
{
  "address": "0x…", "name": "…", "symbol": "…", "imageUrl": "ipfs://…",
  "tradePool": "0x…", "feeTier": 10000,
  "fdvUsd": 48733874.85,        // the baseline market cap (FDV at pool price)
  "volume24Usd": 5184857.24,
  "liquidityUsd": 4176923.05,
  "hasWethPool": true
}
```

Note the key name differences from Growing: `address` (not `token`), `imageUrl`
(not `imageURI`), `tradePool` (not `pool`). No socials/creator/timestamp/kind on
this feed. This is where fdv/liquidity live — a matured survivor (e.g. CASHCAT:
$48.7M FDV, $4.2M liquidity, $5.2M 24h volume).

### `/api/stats` shape

```json
{
  "tokensLaunched": 60, "activeTokens": 30,
  "volume24Usd": 1939007.88, "marketCapUsd": 1354430.45, "liquidityUsd": 460207.46,
  "traders24": 4118, "trades24": 11053,
  "volumeAllTimeUsd": 2588944.87, "tradesAllTime": 18394,
  "unavailable": false, "updatedAt": 1784781131291
}
```

Aggregates only (pad-wide), not per token. Confirms the pad is small and young.

## On-chain identity (for a liveness fallback)

Unused by the scanner (the pad events carry no traction field to score a bar on),
but recorded for when the API dies (potato.fm's API *is* its web layer):

- Chain: **Robinhood Chain, chainId 4663** (`eth_chainId` via `/api/rpc` → `0x1237`).
- Tokens trade on **Uniswap V3**; each Growing row's `pool` / each Ancient row's
  `tradePool` is the pool address.
- Multiple **pad factory** contracts (the `pad` field). Six seen 2026-07-23,
  e.g. `0x88eB8F4aC925C0a6b5501da0eb7E202a036EA338` (direct),
  `0x94085E08B91dA3cB974c14FE6d51B20a014b6069` (curve).
- GMGN indexes these as ordinary robinhood V3 tokens (by address), which is why
  the tracker prices potato outcomes with the shared `snap_gmgn` rather than a
  potato-specific snap.

See `potato/scan.py` (the source-level scanner) and `potato/README.md`.
