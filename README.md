# Network Focus

A Claude Code plugin that turns a CEO's network spreadsheet and quarterly goals into a checked, one-page **weekly Network Focus brief**. The brief covers who to invest time in this week and why, dormant relationships that still matter, and data problems to check. A chief of staff who doesn't write code runs it from a one-button local web page or from the Claude desktop app, and the page opens on a **CEO dashboard**: this week's #1 person with a ready-to-send message, a checklist for the rest, and a progress ring.

Built for the MindMaven *AI Builder Partner* trial project.

## Install

**One click (Mac or Windows):** unzip `deliverables/Install Network Focus.zip` and double-click the installer for your system. Or paste one line:

```bash
# Mac (Terminal)
curl -fsSL https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.sh | bash
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.ps1 | iex
```

It installs `uv` and Claude Code (plus Git for Windows on a PC) if they're missing, checks you're signed in to Claude, installs the plugin, sets up the local page and Desktop link, and opens the dashboard. Re-running updates everything; `--uninstall` (Mac) or `-Uninstall` (Windows) removes it but keeps your briefs. The test suite runs on Ubuntu, macOS and Windows in GitHub Actions.

**Manually:** `/plugin marketplace add jasper-osita/network-focus-maven`, then `/plugin install network-focus@network-focus`, then `/network-focus:setup-app`. Non-technical steps are in [docs/HANDOFF.md](docs/HANDOFF.md).

## How it works

**Code handles facts, the model handles judgment.**

```
load_roster.py → goal-scout × N (parallel) → pick → validate_brief.py → fact-checker → validate → render_pdf.py
```

- `plugins/network-focus/scripts/`: deterministic Python covering loading, data checks (missing orgs, ambiguous references, goals vs data, stale files), grounding validation (word-for-word quotes, matching numbers) and the PDF.
- `plugins/network-focus/agents/`: `goal-scout` (Sonnet, one per goal) and `fact-checker` (Haiku, sees only the cited rows).
- `plugins/network-focus/skills/`: `brief`, `update` (mid-week, new people only), `check`, `setup-app`.
- `plugins/network-focus/app/`: the local page and CEO dashboard (standard-library server, 127.0.0.1 only, token-protected). It reads the roster from *Google Drive › Network Focus* and watches it for new people.
- `schemas/`: the JSON contracts shared by the agents and the validator.

## Docs

[PRD](docs/PRD.md) · [Handoff guide](docs/HANDOFF.md) · [Design](docs/design/2026-11-21-network-focus-design.md) · [Build plan](docs/plans/2026-11-21-network-focus-plan.md) · [Video outline](docs/VIDEO-OUTLINE.md)

## Tests

```bash
uv run pytest                                      # 240+ unit tests, no API calls
uv run python tests/evals/run_evals.py --grade     # 9 real end-to-end runs (6 briefs, 3 mid-week updates) + grader
```
