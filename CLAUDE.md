# launchpad-scanners

Memecoin launchpad scanners (pons, flap, pump, virtuals, arc) running as
LaunchAgents on a Mac mini, alerting to Telegram with an outcome-tracking loop.

## Tests

`.venv/bin/python -m pytest` (setup in README). Scanners are stdlib-only — keep
test dependencies out of their runtime path.

`tests/` pins scoring **separation and direction, never exact score values**.
The weights are provisional until the Tier B refit, so a recalibration that
keeps winners above losers should keep the suite green; if it only passes after
you loosen a threshold, the recalibration is the thing to question.

## Agent skills

### Issue tracker

Issues and PRDs live as GitHub issues in `sunrise-zz/launchpad-scanners`,
managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, using their default label strings. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` and `docs/adr/` at the repo root. See
`docs/agents/domain.md`.
