# Hermes Agent × launchpad-scanners — integration research

*Researched 2026-07-18. Sources: [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent),
[hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com) + /docs,
[awesome-hermes-agent](https://github.com/0xNyk/awesome-hermes-agent).*

## What Hermes Agent is

Open-source (MIT) personal AI agent by Nous Research. Python core, runs on
anything from a $5 VPS to a Mac. Model-agnostic — Nous Portal (300+ models,
freemium tiers), OpenRouter, OpenAI, or any custom endpoint; switch with
`hermes model`. The pieces that matter for us:

| Piece | What it gives us |
|---|---|
| `hermes chat -q "…"` | **Headless single-shot run** — callable from a shell/daemon. Flags: `--model`, `--provider`, `--toolsets "web,terminal,skills"`, `-s skill-name`. |
| `hermes gateway` | Messaging daemon: **Telegram**, Discord, Slack, WhatsApp, Signal, Email. Wizard: `hermes gateway setup`; service: `hermes gateway install`. Access control via `TELEGRAM_ALLOWED_USERS` / pairing codes; per-user allowed commands. |
| Scheduled tasks (cron) | Jobs in natural language **or cron syntax**, can attach skills and **deliver results to any connected platform** (i.e. proactive Telegram messages). |
| Subagents | `delegate_task` — isolated context, restricted toolsets, 3 concurrent by default. |
| Python RPC | `execute_code` — agent writes Python that calls its own tools programmatically (multi-step work in one turn). |
| Web tools | Search + full browser automation (local Chrome/Chromium via CDP, or Browserbase/Browser-Use cloud). |
| Memory | Persistent `MEMORY.md`/`USER.md`, FTS session search, cross-session recall. |
| Skills | Markdown procedure docs ([agentskills.io](https://agentskills.io) standard), searchable/shareable, **self-improving from experience** — the project's core claim. |
| MCP | Client for any MCP server (e.g. community `hermes-blockchain-oracle` for Solana analytics). |

Community skills already exist for crypto monitoring (cross-exchange arb
scanner, DeFi security scanner, Solana on-chain MCP), so the ecosystem fits
this domain.

## Where it fits our architecture

Our scanners' edge is **deterministic speed**: pons CONFIRMED fires ~44 s
after launch off a 2 s poll loop, from backtested on-chain rules. An LLM can
never live in that hot path — too slow, too expensive, non-reproducible.

What the scanners *can't* do is **qualitative judgment**, and our own outcome
data says that's exactly where the alpha is:

- Social presence is our strongest winner signal (78% of winners have an X
  account vs 10% of dead coins) — but we only check that a link **exists**.
  Real vs botted account, follower quality, account age, engagement — invisible.
- Name/narrative fit ("is this riding today's meta or copying a trending
  coin?") — invisible.
- NEAR-GRAD and MARKETING tiers were turned off as net-negative; a smarter
  discriminator might rescue their rare winners.
- Threshold refits are data-driven but hand-run.

So the shape is: **scanner = fast reflex, Hermes = slow analyst**, joined by
the files we already write (`tracker/data/alerts.jsonl`, `snapshots.jsonl`)
and the Telegram chat we already own.

```
 launches ──► scanners (2s loop, deterministic) ──► 🎯 alert ──► Telegram
                                │                                   ▲
                                └─► alerts.jsonl ──► agent/analyst.py
                                                        │  hermes chat -q (DD prompt)
                                                        │  · open X account / website
                                                        │  · web-search ticker + deployer
                                                        │  · recall similar past alerts
                                                        └─► 🤖 AI-DD reply (verdict+reasons)
                                                             + agent_verdicts.jsonl
 tracker/track.py ──► snapshots.jsonl ──► report.py ──► hermes cron: daily brief,
                                                        weekly refit proposal → Telegram
```

## Integration levels (effort-ordered)

**L0 — Analyst-on-demand (config only).** Run `hermes gateway` against the
same Telegram (restricted to our user id), give it a context file describing
this repo, terminal toolset on. You can then ask in chat: "run
`tracker/report.py` and summarize", "which of today's alerts still look
alive?", "why did X fail?". No code changes.

**L1 — AI second opinion on alerts (the sweet spot).** A small stdlib daemon
`agent/analyst.py` tails `tracker/data/alerts.jsonl`; on each new CONFIRMED
(low volume — a handful/day, so cost is trivial) it shells out to
`hermes chat -q` with the alert JSON and a fixed DD checklist (skill), asking
for a strict output block (`VERDICT: BUY-WATCH|NEUTRAL|AVOID`, `CONF: 0-100`,
3 cited reasons). The daemon posts the verdict as a Telegram follow-up and
appends it to `tracker/data/agent_verdicts.jsonl`.
**Crucially, `report.py` gains a `--by-verdict` slice** so the outcome tracker
measures whether AI verdicts add precision over the heuristic score before we
trust them — same discipline as every other signal in this repo.
Latency of 1–3 min is fine (graduation comes ~90 min after CONFIRMED).

**L2 — Scheduled intelligence (hermes cron).**
- Daily 08:00 brief: run `report.py`, summarize per tier/platform, flag drift
  ("pons precision fell to 12% this week"), deliver to Telegram.
- Weekly refit proposal: read alerts+snapshots, propose threshold changes
  (the kind we already commit by hand — neargrad off, marketing off), post as
  a diff for human approval.
- Narrative radar every few hours: web-search what meta is pumping, one-line
  brief — context for reading alerts.

**L3 — Scanners as tools.** Terminal access already lets Hermes run our
scripts; if that gets clumsy, wrap alerts/outcomes/holder-risk into a tiny MCP
server so skills can query them structurally. Optional polish, not a
prerequisite.

**L4 — Self-improving DD skill.** Encode the DD checklist as a
`memecoin-dd` skill. Weekly cron feeds it its own scorecard from the outcome
tracker ("your AVOID verdicts were right 71%, your BUY-WATCH only 24% — here
are the misses"), and Hermes's learning loop updates the skill. Our tracker
provides the ground truth that makes "self-improving" more than a slogan.

## Cautions

- **Keep the agent out of the hot path.** Detection stays deterministic;
  the agent only enriches after the alert is out.
- **Hallucination guard:** verdict must cite what it actually opened
  (links, numbers); treat as advisory until `--by-verdict` proves lift.
- **X/Twitter browsing** often hits login walls — fall back to web search,
  syndication endpoints, or judge from DexScreener-provided socials + site.
- **Security:** gateway = remote shell on the mac mini. Lock
  `TELEGRAM_ALLOWED_USERS`, keep admin scope to our id only.
- **Cost control:** CONFIRMED-only volume is a few calls/day; pick model via
  `--model` per call (cheap default, strong model for high scores).

## GMGN Agent Skills — live-tested 2026-07-18

[gmgn-skills](https://github.com/GMGNAI/gmgn-skills) are agentskills.io-format
skills (`npx skills add GMGNAI/gmgn-skills`) over GMGN's authed OpenAPI —
i.e. **directly loadable by Hermes with zero glue code**, and equally callable
from plain Python. Read-only with `GMGN_API_KEY` alone; `GMGN_PRIVATE_KEY`
enables swaps (we will never set it — repo is detection-only).

The main docs page says Robinhood chain is unsupported — **that page is
stale**. Tested with the public demo key (`gmgn_solbscbaseethmonadtron`)
against coins from our own alert history:

| Test | Result |
|---|---|
| `token info --chain robinhood` (flap coin) | ✅ full payload: launchpad + progress, per-window buys/sells/vols, socials, dev history, `wallet_tags_stat` (smart 3 / renowned 2 / sniper 3 / bundler 0), `bot_degen_rate` 0.38, `fresh_wallet_rate` 0.24 |
| `token security --chain sol` (pump.fun mint) | ✅ renounced mint/freeze, burn/lock, taxes, `top_10_holder_rate` |
| `token holders --chain robinhood` | ✅ per-wallet: PnL, avg cost, tags (`fresh_wallet`, sniper), **funding source** (`native_transfer.from_address` — coordinated-wallet detection), even holders' Twitter identity |
| `market trending --chain robinhood` | ✅ ~80 fields/row incl. `smart_degen_count`, `rug_ratio`, `entrapment_ratio`, `bundler_rate`, `twitter_create_token_count`, dup-detection (`image_dup`, `twitter_dup`, `website_dup`), honeypot/tax — **and coins from launchpads we don't scan (`bags`, `flap_stocks`)** |

What this adds that we can't currently compute:

- **Cross-platform smart-money prior** — our `smart_wallets.json` is fit on 94
  pons graduations; GMGN tags (`smart_degen`, `renowned`) span all chains/pads.
- **Bot/insider forensics** — `bot_degen_rate`, `rat_trader`/`bundler` rates,
  `entrapment_ratio`, wash-trading flag, funding-source clustering.
- **Dev reputation without our collect pipeline** — created-token count, best
  prior token ATH, twitter rename/delete history. *(Caveat: on flap the
  `creator` is the factory-ish address `0xe9f7…197b` shared across coins — keep
  our own mint-event deployer extraction as truth there.)*
- **Copy detection** — duplicate image/twitter/website counters.
- **Discovery** — robinhood trending surfaces `bags` launchpad coins our six
  scanners never see; Trenches new-token feed filters by launchpad/KOL/rat.

Limits: `track smartmoney/kol` + `market signal` are sol/bsc/base/eth only
(no robinhood); `cooking` sol/bsc/base only; arc chain not covered at all.
Rate limits: weight-based, ~20 req/s for info/security, ~4 req/s for
holders/traders — far above our volume. Demo key is for testing only;
production needs our own key (Ed25519 pubkey upload at gmgn.ai/ai — browser,
Cloudflare-guarded; pricing undocumented). Keep GMGN out of the ~44 s hot
path (indexing lag on seconds-old coins; enrichment stage only).

## Suggested first build

1. Register a GMGN API key (browser: gmgn.ai/ai, upload Ed25519 pubkey);
   `npx skills add GMGNAI/gmgn-skills` into Hermes. **No `GMGN_PRIVATE_KEY`.**
2. `agent/skill/memecoin-dd/SKILL.md` — DD checklist skill: gmgn-token
   info/security/holders first, browser/web-search second.
3. `agent/analyst.py` — jsonl-tailing daemon → `hermes chat -q` → Telegram
   reply + `agent_verdicts.jsonl` (stdlib only, same style as the rest).
4. `tracker/report.py --by-verdict` — measure the lift.
5. **Scanner-side (no LLM):** shared `gmgn.py` helper so alert time records
   GMGN fields (`smart_degen_count`, `bot_degen_rate`, `entrapment_ratio`,
   `rug_ratio`, …) into `alerts.jsonl` — outcome tracker then tells us which
   deserve score weight. Also a candidate `bags` scanner from robinhood
   trending.
6. If verdicts prove out → L2 cron briefs; later L4 skill loop.
