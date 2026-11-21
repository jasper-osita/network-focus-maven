# Network Focus

A Claude Code plugin that turns a CEO's network spreadsheet and quarterly goals into a checked, one-page **weekly Network Focus brief**. The brief covers who to invest time in this week and why, dormant relationships that still matter, and data problems to check. A chief of staff who doesn't write code runs it from a one-button local web page or from the Claude desktop app.

Built for the MindMaven *AI Builder Partner* trial project.

## Install

```
/plugin marketplace add jasper-osita/network-focus-maven
/plugin install network-focus@network-focus
```

Then `/network-focus:brief` makes the brief, `/network-focus:check` diagnoses the setup, and `/network-focus:setup-app` installs the local page. Requires `uv`. Full non-technical steps are in [docs/HANDOFF.md](docs/HANDOFF.md).

## How it works

**Code handles facts, the model handles judgment.**

```
load_roster.py → goal-scout × N (parallel) → pick → validate_brief.py → fact-checker → validate → render_pdf.py
```

- `plugins/network-focus/scripts/`: deterministic Python covering loading, data checks (missing orgs, ambiguous references, goals vs data, stale files), grounding validation (word-for-word quotes, matching numbers) and the PDF.
- `plugins/network-focus/agents/`: `goal-scout` (Sonnet, one per goal) and `fact-checker` (Haiku, sees only the cited rows).
- `plugins/network-focus/skills/`: `brief`, `check`, `setup-app`.
- `plugins/network-focus/app/`: the local page (standard-library server, 127.0.0.1 only, token-protected).
- `schemas/`: the JSON contracts shared by the agents and the validator.

## Docs

[PRD](docs/PRD.md) · [Handoff guide](docs/HANDOFF.md) · [Design](docs/design/2026-11-21-network-focus-design.md) · [Build plan](docs/plans/2026-11-21-network-focus-plan.md) · [Video outline](docs/VIDEO-OUTLINE.md)

## Tests

```bash
uv run pytest                                      # 92 unit tests, no API calls
uv run python tests/evals/run_evals.py --grade     # 6 real end-to-end runs + grader (~$8)
```
