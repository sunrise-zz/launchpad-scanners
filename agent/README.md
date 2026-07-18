# agent/ — Hermes AI second-opinion layer

The scanners stay deterministic and fast; this layer adds the qualitative
judgment they can't do, using [Hermes Agent](https://github.com/NousResearch/hermes-agent)
(installed at `~/.local/bin/hermes`). Research/decision doc:
`docs/hermes-agent-integration.md`.

## Pieces

- `skill/memecoin-dd/SKILL.md` — the DD method: GMGN forensics first
  (`pons/gmgn.py` via terminal), then X-account quality + narrative via web
  tools, ending in a strict `VERDICT/CONF/WHY1-3` block. Symlinked into
  `~/.hermes/skills/memecoin-dd` (repo copy is the source of truth).
- `analyst.py` — daemon that tails `tracker/data/alerts.jsonl`; for each new
  alert in `--tiers` (default `CONFIRMED,TRENCH EARLY,TRENCH GRAD,FLAP
  EARLY:55` — a `TIER:55` entry means only score ≥ 55) it runs
  `hermes chat -q … -s memecoin-dd --toolsets web,terminal,skills`, parses
  the verdict and **edits it into the original alert message** (the alert
  bubble grows a 🤖 AI-DD section a few minutes later — no separate
  follow-up message drifting between other alerts; falls back to a threaded
  reply, then a standalone message). Also appends to
  `tracker/data/agent_verdicts.jsonl`.
- `tracker/report.py --by-verdict` section — measures whether AI verdicts
  separate outcomes better than the heuristic score. **Verdicts are advisory
  until this shows lift** (same collected-then-refit rule as every signal).

## Setup

```bash
# 1. model provider (one of):
hermes auth add nous          # Nous Portal OAuth (free tier available)
# or put OPENROUTER_API_KEY= / ANTHROPIC_API_KEY= etc. in ~/.hermes/.env

# 2. run
python3 agent/analyst.py --dry-run --backfill 1   # test on the last alert
# 24/7: ~/Library/LaunchAgents/com.sunrise.analyst.plist
```

`HERMES_ANALYST_MODEL` (or `--model`) overrides the model per run; otherwise
Hermes's configured default is used. The daemon is safe to run un-authed —
failed DDs are logged to agent_verdicts.jsonl with `ok:false` and no
Telegram message is sent.
