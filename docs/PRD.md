# PRD: Network Focus

**Owner:** Jasper Osita · **For:** TerraGrid's CEO and her chief of staff · **Build target:** Claude Code plugin `network-focus`

## 1. Problem and who it's for

The CEO has hundreds of contacts and three goals this quarter: raise a Series C, hire a CTO, and build relationships in AI safety. In practice she spends her time on whoever is on her calendar. **The user** is her chief of staff. She isn't technical, and every Monday she has to produce a brief she can install, run and fix herself. **The reader** is the CEO, who needs a one-page list she can act on in five minutes.

## 2. Inputs and outputs

- **Spreadsheet** (`.xlsx` or `.csv`, one row per contact) with 10 required columns: Name, Role, Company, How She Knows Them, Days Since Last Contact, Last Contact Channel, Last Contact Summary, Relationship Strength (1-5), Tags, Notes. Headers are matched ignoring case and spacing. A header row below a title row is found, and a zipped file is unwrapped.
- **`goals.md`**: Markdown the chief of staff edits each quarter. Each goal is a `## Goal N: Title` block with labeled lines. The code reads two of those lines: `Key organizations:` and `No contacts yet at:`.
- **Output:** a one-page `briefs/YYYY-MM-DD-network-focus.pdf` (plus `.md`), rendered from a validated `brief.json`:

```
focus[3–5]:   { row_id, name, goals[], why, move, risk, evidence[] (verbatim quotes), confidence }
dormant[2–3]: { row_id, name, days_since_contact (≥60), why, move, evidence[] }
coming_up[0–2] · goal_gaps[] · extra_checks[0–3] · week_of
```

The "Check before the meeting" box is filled from `warnings.json`, which the code writes. The model can't leave a data problem off the page.

## 3. Architecture decisions

**Code handles facts, the model handles judgment.** Loading the file, the 60-day rule, name matching, stale-file detection and quote checking are deterministic, unit-tested Python (109 tests). Deciding who matters this week and what to say is left to the model.

```
load_roster.py → goal-scout × N (parallel) → main skill picks → validate_brief.py → fact-checker → validate → render_pdf.py
   (code)          (sub-agents)               (judgment)        (code, ≤2 fixes)   (sub-agent)            (refuses invalid)
```

| Decision | Choice and why |
|---|---|
| Sub-agents vs. one agent | One `goal-scout` per goal, run in parallel, so Series C (the most rows) can't crowd out AI safety. The main skill weighs them against each other, and people serving two goals rank higher. A separate `fact-checker` sees only the cited rows and didn't write the brief, so it has no stake in defending it. |
| One generic scout | It runs once per goal in `goals.md`. When goals change next quarter, she edits one file and never touches an agent. |
| Model choice | Scouts on **Sonnet** (careful reading, run in parallel at modest cost). The fact-checker on **Haiku** (narrow comparison; quote matching is already done in code). The final pick on the session's model (the hardest judgment). |
| Structured output | JSON Schema files in `schemas/` are the single contract. Agents are told to follow them, and the validator enforces them. |
| Grounding | Each evidence quote must appear word-for-word in that contact's row. "N days" in the text must match the data. Moves need a channel and a specific ask. |
| Packaging | A plugin in a GitHub repo that is also its own marketplace: install in two steps, updates from the same repo. |
| Where she runs it | A local one-button web page (Python standard library, local-only, token-protected; background runs may only touch her folder and the plugin's scripts) that runs the same skill with `claude -p`, with the Claude desktop app as backup. **Cloud web app rejected:** it needs hosting, an API key and a login, it puts the CEO's private notes on a server, and she couldn't fix it herself. |

## 4. Data sourcing strategy (production)

| Source | Provides | Sync |
|---|---|---|
| Calendar MCP | Last meeting date and channel | Daily |
| Gmail MCP | Last email date, a one-line thread summary, unanswered threads | Daily, summaries only, no stored bodies |
| CRM (Affinity / HubSpot) | Role, company, tags, intro history | Weekly |
| **Manual** | Strength, how she knows them, notes: the CEO's judgment | A 10-minute Friday review |

**Store dates, not "days since."** The trial sheet's day counts are relative to an export date the file never records, which is why staleness can only be guessed. In production, `last_contact_date` is stored and the gap is computed at run time. **Trade-offs:** inbox access improves completeness at a privacy cost, so it's opt-in and summaries only. Daily sync gives fresher data for more API calls. LinkedIn stays manual because of its terms of service.

## 5. Failure modes handled (in code)

| Failure | Result |
|---|---|
| File missing, unreadable, empty, or a column renamed or missing | **Stops** with a plain message naming the file or column and the fix |
| A goal names an org with no contact (a16z) | Warning: "Who is the contact there?" |
| Ambiguous reference ("Patrick at Greylock", but the only Patrick is at Stripe) | Warning. The skill never guesses. |
| Goals contradict data ("no ARC contact", but Paul Christiano is at ARC Evals) | Warning: update goals.md or check the row |
| Thin context (strength ≤1, summary under 10 words) | Never a dormant pick; a focus pick only if labeled low-confidence (both enforced) |
| Stale or reused file (older than 7 days, or the same fingerprint as an earlier week) | Banner at the top of the brief |
| Invented names, quotes or numbers, dormant picks under 60 days, wrong counts | Fixed (≤2 rounds) or the run stops. The PDF step refuses invalid briefs. |

## 6. Success criteria

- **All 6 end-to-end test cases pass.** Every case runs the real skill on a test spreadsheet: the real roster, missing columns, stale/reused, a duplicate name, a thin goal contact, CSV. The checks are done in code.
- **The real roster's brief** includes Diana Chen and Marcus Wei, excludes the decoys (James Park, Jensen Carlsson, Jensen Huang, Demis Hassabis, Aaron Goldsmith), and flags a16z, "Patrick at Greylock" and ARC.
- **Zero invented names or quotes**, and a **grader score of ≥4/5** on grounding and move specificity.
- **A fresh install from the handoff doc alone works** on a real Mac.
- **Result (Nov 21):** 6/6 cases pass, grader grounding 4 and specificity 4 on every brief, 107–142 s and about $1.10 per weekly run (`tests/evals/results/2026-11-21.md`).
