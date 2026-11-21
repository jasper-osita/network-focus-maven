# PRD: Network Focus

**Owner:** Jasper Osita · **For:** TerraGrid CEO and her chief of staff · **Build target:** Claude Code plugin `network-focus`

## 1. Problem and who it's for

The CEO has hundreds of contacts and three goals for the quarter: raise a Series C, hire a CTO, and build relationships in AI safety. In practice she spends her time on whoever is on her calendar. She wants to choose deliberately who she invests in each week, but nobody has time to audit her network by hand every week.

**User:** her chief of staff. She isn't technical, and she runs it every Monday before the CEO's planning session. She needs to install it, run it and fix it without writing code.
**Reader:** the CEO. She gets a one-page brief she can act on in five minutes.

## 2. Inputs and outputs

**Inputs**
- **Network spreadsheet** (`.xlsx` or `.csv`, one row per contact). Required columns: Name, Role, Company, How She Knows Them, Days Since Last Contact, Last Contact Channel, Last Contact Summary, Relationship Strength (1-5), Tags, Notes. Headers are matched ignoring case, spacing and parentheses. A header row can sit below a title row. A zipped spreadsheet is unwrapped.
- **`goals.md`**: plain Markdown the chief of staff edits each quarter. One `## Goal N: Title` block per goal, with labeled lines, including two the code reads: `Key organizations:` and `No contacts yet at:`.

**Output:** `briefs/YYYY-MM-DD-network-focus.pdf` (one page) plus a `.md` copy. It's built from a validated `brief.json`:

```
week_of: "2026-11-23"
focus[3–5]:   { row_id, name, goals[], why, move, risk, evidence[] (verbatim quotes), confidence }
dormant[2–3]: { row_id, name, days_since_contact (≥60), why, move, evidence[] }
coming_up[0–2]: { row_id, name, note }      goal_gaps[]: { goal_id, note }      extra_checks[0–3]
```

The "Check before the meeting" box on the page comes from `warnings.json`, which is written by code and not by the model, so a data problem can't be left off the brief.

## 3. Architecture decisions

**Code handles facts, the model handles judgment.** Loading the file, checking columns, the 60-day dormant rule, name matching, stale-file detection and quote verification are deterministic Python. They're unit-tested and behave the same way every Monday. Deciding who matters this week and what to say is the model's job.

```
load_roster.py ─▶ goal-scout ×N (parallel) ─▶ main skill picks ─▶ validate_brief.py
     (code)          (sub-agents)               (judgment)          (code, max 2 fixes)
                                                                          │
           render_pdf.py ◀─ validate again ◀─ fact-checker (sub-agent) ◀──┘
      (refuses invalid briefs)
```

| Decision | Choice | Why |
|---|---|---|
| Single agent vs sub-agents | One `goal-scout` per goal in parallel, plus a separate `fact-checker` | If one agent sees all three goals, Series C (the most rows) crowds out AI safety. Separate scouts each argue for their goal, then the main skill decides between them, so people who serve two goals rank higher. The fact-checker didn't write the brief and only sees the cited rows, so it can't defend its own work or fill gaps from memory. |
| One generic scout, not three | A scout runs once per goal listed in `goals.md` | Goals change every quarter. The chief of staff edits one Markdown file and never touches agent code. |
| Model choice | Scouts: Sonnet. Fact-checker: Haiku. Main pick: the session model | Scouts read every contact carefully and run in parallel, so Sonnet balances quality and cost. The fact-checker only compares claims against rows, and the hard part (quote matching) is already done in code. The cross-goal decision is the hardest judgment, so it uses the strongest model. |
| Structured output | JSON Schema files shared by the code and the agents | `schemas/*.json` is the single contract. The validator reads the same files the agents are told to follow. |
| Grounding | Each evidence quote must appear word-for-word in that contact's row. Day counts in the text must match the data. | This catches made-up facts mechanically, without trusting the model's own judgment. |
| Packaging | A Claude Code plugin in a GitHub repo that is also its own marketplace | Install is two steps, and updates come from the same repo. |
| Where she runs it | A local web page (one button) on top of the Claude desktop app | No terminal ever. Data stays on her Mac and uses her existing Claude login. **A cloud web app was rejected:** it needs hosting, an API key and a login, it puts the CEO's private notes on a server, and the chief of staff couldn't fix it herself. |
| MCP | Not built for this trial | The data is a local file. Calendar and Gmail MCP are the production data path (§4). |

## 4. Data sourcing strategy (production)

| Source | What it provides | Sync |
|---|---|---|
| Google Calendar MCP | Meetings become last-contact dates and the meeting channel | Daily |
| Gmail MCP | The last email date, a one-line thread summary, and unanswered threads (like David Park's) | Daily. Metadata and summaries only, never stored bodies. |
| CRM (Affinity or HubSpot) | Role, company, tags, intro and deal history | Weekly |
| **Manual** | Relationship strength, how she knows them, notes | A 10-minute Friday pass by the chief of staff. This is the CEO's judgment, and automation shouldn't overwrite it. |

**Key change: store dates, not "days since."** The trial sheet's day counts are relative to an export date the file never records, which is the root cause of the stale-data problem. Production stores `last_contact_date` and computes the gap at run time.
**Trade-offs:** reading her inbox gives completeness but costs privacy, so it uses summaries and an explicit opt-in. Daily sync means fresh data but more API calls. LinkedIn stays manual because of its terms of service.

## 5. Failure modes handled

| Failure | Caught by | Result |
|---|---|---|
| File missing, unreadable, empty, or a column renamed or missing | `load_roster.py` | **Stops** with a plain message naming the file or column and the fix |
| A goal names an org with no contact (a16z) | code, from `Key organizations` | A warning in the Check box |
| Ambiguous reference ("Patrick at Greylock", but the only Patrick is at Stripe) | code (name + org match) | A warning. The skill never guesses. |
| Goals contradict data ("no ARC contact", but Paul Christiano is at ARC Evals) | code, from `No contacts yet at` | A warning: update goals.md or check the row |
| Thin context (strength ≤1 and a summary under 10 words) | code flag + validator | Left out, or included and labeled low-confidence |
| Stale or reused data (file older than 7 days, or the same file as a previous week) | code (file date + fingerprint) | A banner at the top of the brief |
| Made-up names, quotes or numbers, dormant picks under 60 days, wrong counts | `validate_brief.py` + fact-checker | Fixed and re-checked up to 2 times, then it stops. The PDF step refuses an invalid brief. |

## 6. Success criteria

- **All 6 test cases pass:** the real roster, missing columns, stale/reused, a duplicate name, a thin goal contact, CSV. Every check is done in code.
- **The real roster's brief** includes Diana Chen and Marcus Wei, excludes James Park, Jensen Carlsson, Jensen Huang, Demis Hassabis and Aaron Goldsmith, and flags a16z, "Patrick at Greylock" and the ARC contradiction.
- **Zero invented names or quotes** across all test runs.
- **The grader scores ≥4/5** on grounding and move specificity.
- **A fresh install that follows only the handoff doc works**, on a real Mac.
- **Run time:** _measured after the build_.
