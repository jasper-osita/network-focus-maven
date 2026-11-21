# Video outline (10–12 min, one take, lightly cut at most)

These are talking points, not a script. Say them in your own words, and type live: MindMaven explicitly checks for that.

## Before you hit record

- [ ] On your Mac, the plugin is installed from GitHub (handoff steps), and `/network-focus:check` shows all ✅.
- [ ] A fresh copy of `network_roster_terragrid.xlsx` is on the Desktop. A second copy, `broken.xlsx`, is open in Numbers, ready for the failure demo.
- [ ] VS Code is open on the repo with these tabs: `docs/PRD.md`, `skills/brief/SKILL.md`, `agents/goal-scout.md`, `scripts/nf_core/brief_checks.py`, `scripts/nf_core/checks.py`, `scripts/nf_core/roster.py`, `tests/evals/results/` (latest).
- [ ] Notifications are off (Focus mode), the font size is bumped, and the browser shows only the Network Focus page.

## 1. PRD to build (1–2 min)

- Open `PRD.md` §3. The one-line thesis: **"code handles facts, the model handles judgment."**
- **Decision 1, grounding in code.** Jump to `brief_checks.py` → `_check_person`: every evidence quote has to appear word-for-word in that person's row, and "N days" has to match. The model can't sneak in an invented fact.
- **Decision 2, one scout per goal in parallel.** Show SKILL.md step 2, then `agents/goal-scout.md` (`model: sonnet`). Why: if one agent sees everything, Series C (the most rows) drowns out AI safety. When goals change next quarter, she edits one Markdown file.

## 2. Live demo on the real spreadsheet (3–4 min)

- Briefly show the spreadsheet. Point at two traps: Marcus Wei's note "intro from Patrick at Greylock", and the goals' "warm intro to a16z".
- Double-click **Network Focus** on the Desktop. Drag the spreadsheet in and click **Generate**.
- **While it runs (about 2–3 min), narrate the steps as they tick:** "Checking the data" is pure Python. "Reviewing Goal 1/2/3" is three sub-agents running in parallel. "Fact-checking" is a separate Haiku agent that only sees the cited rows. Then "Making the PDF". Don't cut the wait; it shows the run is real.
- Open the PDF and walk through it: the picks and why, then the decoys it skipped (James Park: strength 5, best friend, no goal link; Jensen Huang: famous, no relationship). Finish on **Check before the meeting** (a16z, Patrick, ARC and the academic contradiction) and the extra issues the scouts spotted (Paul's email vs LinkedIn, David Liu's "ex-colleague").

## 3. Architecture with code visible (2–3 min)

- Show the repo tree. The root `marketplace.json` makes the repo installable. Under `plugins/network-focus/` are `skills/` (brief, check, setup-app), `agents/`, `scripts/` and `schemas/`.
- SKILL.md: `allowed-tools` is limited to `uv run` plus the agents, so there are no permission prompts for her. `${CLAUDE_PLUGIN_ROOT}` locates the scripts.
- `schemas/brief.json`: one contract that the agents follow and the validator enforces.
- `app/server.py`: why a **local** page instead of a cloud app. Her data stays on her Mac, it uses her Claude login, and there's no server to break. Show the guards: 127.0.0.1 only, Host/Origin checks, a token, one run at a time.
- The test set: open the latest `tests/evals/results/*.md`. Six real end-to-end cases plus an independent grader, alongside 92 unit tests.

## 4. A failure mode, live, with the code (2–3 min)

- In `broken.xlsx`, rename "Days Since Last Contact" to "Days" and delete the Notes column. Save it and drag it onto the page. You get no brief, and the message names both columns and the fix.
- Open `roster.py` → `MISSING_COLUMNS`: it stops before any model runs, and no PDF is ever made.
- Second one, briefly: `checks.py` → the "<First> at <Org>" check that produced the Patrick warning. Code finds the ambiguity, and the brief asks the CEO instead of guessing.
- One sentence on the safety net that caught a real problem: in the first real run, the fact-checker flagged "he asked 16 days ago" as unsupported, and it was rewritten before the PDF.

## 5. Honest limitations and production next steps (1–2 min)

- **Staleness is a guess.** The sheet stores "days since" with no export date, so I use the file date and a fingerprint. In production I'd store dates (Calendar and Gmail MCP).
- **Tested on 25 contacts.** At hundreds, I'd pre-filter rows per goal in code before the scouts read them.
- **Model picks can vary a little between runs.** The must-include and must-exclude checks hold, but the order and wording shift. The fact-checker can miss soft embellishments (the grader caught "ARC is a key AI safety organization").
- **macOS only.** The local page needs the Claude Code command-line tool, and a scheduled Monday 7am run isn't built yet.
- **About 2–3 minutes and about $1.20 per run.** The scouts could drop to Haiku if cost matters more than nuance.
