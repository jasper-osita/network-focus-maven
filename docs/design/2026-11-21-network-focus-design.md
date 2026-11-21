# Network Focus — Design

**Status:** Final draft for approval · 2026-11-21
**Context:** MindMaven "AI Builder Partner" trial project. This is our working design. The 1–2 page PRD deliverable gets distilled from it.

---

## 1. Intent

TerraGrid's CEO spends her time on whoever is on her calendar, not on the people who move her three quarterly goals: raise the Series C, hire a CTO, and build AI-safety relationships. Every Monday her chief of staff, who is not technical, runs one command. That command reads the network spreadsheet and produces a one-page brief with:

- 3–5 people to invest in this week: who they are, why they matter to a goal, the specific move to make this week, and what's at risk if she doesn't make it
- 2–3 dormant relationships (60+ days without contact) that are still high-leverage
- A short "Check before the meeting" box listing data problems the skill found

**What MindMaven is really grading:** good judgment in the picks, a PRD Claude Code can build from, a handoff doc a non-technical person can follow, real Claude Code depth, failure handling visible in the code, and a working live demo.

## 2. Goals, non-goals, anti-goals

**Goals**
- The picks are right, and every reason traces back to a spreadsheet row
- Moves are specific ("email Diana today asking for the 3–4 CTO intros she offered"), not generic ("reconnect")
- Install takes two commands. After that, a weekly run is one click on the local page or one sentence in the Claude app, never a terminal.
- When something breaks, the operator gets a plain-English message and a fix
- At least two failure modes are handled in code (we handle seven, listed in §6)

**Non-goals**
- Real Calendar, Gmail or CRM connections. They go in the PRD's Data Sourcing Strategy as a thinking exercise only.
- Windows support. The handoff targets macOS, and Windows is noted as untested.
- Scheduling or automatic Monday runs. Listed as a production next step, since the desktop app has scheduled tasks and a brief could be waiting for her at 7am (not yet tested).

**Anti-goals** (the skill fails if it does these, even when it technically runs)
- Picking by relationship strength or recency alone. That would surface James Park, a strength-5 friend with no link to any goal.
- Inventing facts about a contact, or quietly guessing which "Patrick" a note means
- Producing a confident brief from bad data without saying the data is bad

## 3. What's in the data (and what the skill must catch)

The roster has 25 rows and 10 columns. The test cases are already planted in it:

| Issue | Where | Kind |
|---|---|---|
| Goals name a16z as a warm intro, but no a16z contact exists | Goal 1 vs roster | Missing contact |
| "Warm intro from Patrick at Greylock": no Patrick at Greylock. Patrick Collison is at Stripe, and Reid Hoffman is the Greylock contact. | Marcus Wei notes | Ambiguous reference |
| Goals say "hasn't met anyone at ARC," but Paul Christiano (ARC Evals) was in touch 8 days ago | Goal 3 vs roster | Goals contradict data |
| David Liu / David Park, Jensen Huang / Jensen Carlsson, Diana Chen / Lara Chen, James Park / David Park | Names | Name collisions |
| Anjali Sharma: strength 1, "exchanged cards," unknown company | Row | Thin context |
| "Days since last contact" is relative to an export date the file doesn't record | Whole file | Stale data |
| Lin Wang at 59 days | Row | Just under the 60-day cutoff |
| Maya Patel: "revisit in a month," and that window opens in about 2 weeks | Row | Timing: prepare, don't push |
| Paul Christiano: channel says email, summary says LinkedIn | Row | Inconsistent row |

**Expected picks.** This is our sanity check, not something hard-coded into the skill.
- **This week:** Diana Chen (an open CTO offer that never got a follow-up), Marcus Wei (asked for the full pitch), Reid Hoffman (strongest investor, 81 days quiet), Paul Christiano (warm AI-safety thread), Sarah Guo (serves both investor and AI-safety goals)
- **Dormant:** Priya Mehta (Index, 128 days, strong Series C fit) and Brian Armstrong (67 days, owes her a favor)
- **Should NOT appear:** James Park, Jensen Carlsson, Jensen Huang, Demis Hassabis (the notes say not now), Aaron Goldsmith

## 4. Approaches considered

| | Approach | Trade-off | Verdict |
|---|---|---|---|
| A | One skill, one agent, one data script | Simplest and most reliable, but thin on the Claude Code depth they grade | Rejected |
| **B** | **Plugin: skills, parallel sub-agents, checking scripts** | **More moving parts, but each one has a reason we can defend on camera** | **Chosen** |
| C | Agent SDK app or custom MCP server | Most "production," but adds install burden for a non-technical operator, and the brief asks for a Claude Code skill | Moved to the PRD's "production next steps" |
| D | Web app or Claude artifact | Friendliest screen, but it isn't a Claude Code skill (the brief requires one, and they grade Claude Code depth). It also needs hosting, an API key, billing and login, and puts the CEO's private network data on a server. An artifact can't run sub-agents or local scripts. | Cloud version rejected. A **local** web page is added as a thin final layer on top of the skill (§5.8), so data stays on her Mac and no API key is needed. |

**Guiding rule: code handles facts, the model handles judgment.** Column checks, the 60-day rule, name matching, stale-file detection and quote verification are deterministic Python. They run the same way every Monday and are unit-tested. Choosing people, explaining why, and writing the moves is the model's job.

## 5. Architecture

### 5.1 Packaging

The product is a Claude Code **plugin** in a public GitHub repo, and the repo is also its own marketplace. Install:

```
/plugin marketplace add jasper-osita/network-focus-maven
/plugin install network-focus@network-focus
```

The chief of staff then has two commands:
- `/network-focus:brief`: makes this week's brief
- `/network-focus:check`: diagnoses the setup and prints fixes in plain English

**Where she runs it: the Claude desktop app, not the terminal.** The desktop app's Code tab runs Claude Code on her own Mac in a normal chat window. She installs the plugin with **+ → Add plugins**, opens the `Network Focus` folder, and types `/network-focus:brief` (or picks it from the `/` menu). Per the docs, it works "without using a terminal," and plugins installed there are shared with the terminal version. If the local web page (§5.8) ships, it becomes her main way in and the desktop chat becomes the backup. If not, the handoff doc is written for the desktop app. The video demo uses the terminal, because evaluators want to see file paths and code.

Auto-update is off by default for personal marketplaces. The handoff doc explains how to update (turn on auto-update in `/plugin` → Marketplaces, or run `claude plugin update network-focus@network-focus`).

### 5.2 Operator folder (outside the plugin, so it survives updates)

```
~/Documents/Network Focus/
├── goals.md          ← the CEO's goals; the chief of staff edits this each quarter
├── inbox/            ← drop this week's spreadsheet here (.xlsx or .csv)
├── briefs/           ← finished briefs land here (PDF + Markdown)
└── .history.json     ← file fingerprints from past runs (catches re-used data)
```

On first run, the skill creates this folder and copies in a starter `goals.md`. If the operator passes a path (`/network-focus:brief ~/Downloads/roster.xlsx`), that file is used. Otherwise the skill takes the newest file in `inbox/`.

### 5.3 goals.md format

This is plain Markdown with labeled lines, so a non-technical person can edit it and a script can still parse it:

```markdown
## Goal 1: Raise Series C
Deadline: end of Q3
Target: $40M at $200M valuation
What good looks like: more investor relationships, plus signals that strengthen the pitch (advisor commitments, key hires)
Key organizations: Sequoia, a16z (Andreessen Horowitz), Greylock
No contacts yet at:
```

`Key organizations` and `No contacts yet at` drive the missing-contact and goals-vs-data checks. Aliases go in parentheses, and ARC counts as a match for "ARC Evals." A malformed goals.md stops the run with a message naming the line.

### 5.4 Run flow for `/network-focus:brief`

```
1. load_roster.py   (code)    spreadsheet + goals.md → roster.json + warnings.json
                              BLOCK → stop with a plain message (no brief)
2. goal-scout ×N    (agents)  one per goal in goals.md, run in parallel → candidates JSON
3. main skill       (model)   merge, rank across goals, pick → brief.json
4. validate_brief.py (code)   hard checks; on failure, fix and retry (max 2), then stop
5. fact-checker     (agent)   does each "why" and "risk" claim follow from the cited row?
6. validate_brief.py (code)   re-run on the final version
7. render_pdf.py    (code)    refuses invalid briefs → briefs/YYYY-MM-DD-network-focus.pdf + .md
```

### 5.5 Components

| Piece | Type | Job | Model |
|---|---|---|---|
| `skills/brief/SKILL.md` | Skill | Runs the flow above, applies the selection rules (§5.6), writes brief.json | Inherits the session model |
| `skills/check/SKILL.md` | Skill | Runs `check_setup.py`, reports ✅/❌ with fixes | Inherits (light work) |
| `agents/goal-scout.md` | Sub-agent | Given **one** goal plus the roster, returns ranked candidates with row ID, verbatim evidence quotes, a move, a risk and a confidence level | `sonnet` |
| `agents/fact-checker.md` | Sub-agent | Gets the brief plus only the cited rows, and lists any claim the row doesn't support | `haiku` |
| `scripts/load_roster.py` | Code | Reads xlsx/csv, normalizes, computes flags, runs the failure-mode checks | — |
| `scripts/validate_brief.py` | Code | Schema and grounding checks (§6) | — |
| `scripts/render_pdf.py` | Code | One-page PDF and Markdown; calls validate first and refuses if it fails | — |
| `scripts/check_setup.py` | Code | Checks uv, the folder, goals.md, the spreadsheet, columns and file age | — |
| `schemas/*.json` | JSON Schema | The shapes of the scout output, brief.json and warnings | — |

**Why one generic `goal-scout` and not three goal-specific scouts.** This changes what we discussed earlier. Goals change every quarter. If each goal had its own agent file, next quarter's goals would mean editing agent files, which the chief of staff can't do. With one scout launched once per goal in goals.md, she only ever edits goals.md. It runs in parallel just the same, and it has the same separate-context benefit: Series C, the goal with the most rows, can't crowd out AI safety.

**Why the fact-checker is separate.** It didn't write the brief, so it has no reason to defend it. It sees only the cited rows, so it can't fill gaps from general knowledge. The quote check in code catches made-up quotes, and the fact-checker catches claims the quotes don't actually support.

**Model choices.** Scouts use `sonnet`, which reads each contact carefully and is cheap enough to run several in parallel. The fact-checker uses `haiku`, because it only compares claims against rows and the hard part (quote matching) is already done in code. The main skill uses the session model, because the cross-goal decision is the hardest judgment in the run. We'll tune these after running the test set.

**Permissions.** Each SKILL.md sets `allowed-tools` (Read, Write and `Bash(uv run *)`), so the operator doesn't get a stream of permission prompts.

**Script runtime.** The scripts use Python run through `uv run`, with their dependencies (`openpyxl`, `reportlab`) declared at the top of each script. `uv` downloads Python and the libraries automatically, so the only prerequisite is installing uv once.

### 5.6 Selection rules (written in SKILL.md, checked by the tests)

1. Every pick serves at least one goal. People who serve two goals rank higher.
2. Cover every goal with at least one pick if a credible candidate exists. If none does, say so in the brief.
3. Open loops come first: an offer she hasn't taken up (Diana), an ask waiting on her (Marcus), a note that went unanswered (David Park).
4. Strong but dormant relationships rank high (Reid).
5. Respect timing. If someone asked to wait (Maya), don't push. List them under "Coming up" instead.
6. Exclude contacts with no goal link (James), contacts with strength 1 and no context (Anjali, Jensen Huang) unless marked low-confidence, and contacts where the notes advise against reaching out (Demis).
7. No one appears twice. The dormant section lists 2–3 people at 60+ days who are not already top picks.
8. Each move is one concrete action this week, through a named channel, with the reason it fits.

### 5.7 Brief layout (one page)

```
NETWORK FOCUS · Week of Nov 23, 2026          Data as of: Nov 20 (file date)
─────────────────────────────────────────────────────────────────────────
THIS WEEK (5)
1. Diana Chen · CTO, Stripe · [CTO search]
   Why: Offered 3–4 strong CTO candidates 28 days ago; never followed up.
   Move: Email today — ask for the intros by name, offer a 20-min call.
   At risk: The offer goes cold, and so does the warmest path to candidates.
...
DORMANT BUT HIGH-LEVERAGE (2)
• Priya Mehta · Partner, Index · 128 days · ...
COMING UP
• Maya Patel — "revisit in a month" window opens ~Dec 7. Draft the note now.
CHECK BEFORE THE MEETING
• No a16z contact in the roster, but goals list a warm a16z intro. Who is it?
• Marcus Wei's notes say "Patrick at Greylock". No such contact. Reid Hoffman?
• Goals say no ARC contact, but Paul Christiano (ARC Evals) is in the roster.
```

### 5.8 Local web page (final layer, dropped if late)

A one-page app that runs on her own Mac, so she never has to type anything.

- **What she sees:** this week's spreadsheet, already chosen (the newest file in `inbox/`, or she drags one onto the page). A **Generate this week's brief** button, progress steps as it runs, then **Open PDF**. A **Check setup** button runs `check_setup.py` and shows the same plain-English fixes. Past briefs are listed below.
- **How it works:** `app/server.py` uses only Python's built-in libraries and runs with `uv run`. It serves `app/index.html`, which is plain HTML and JavaScript with no build step. Clicking Generate runs the skill in the background with `claude -p "/network-focus:brief <file>" --output-format stream-json`, with only the tools it needs pre-approved, and streams progress to the page. The skill underneath is the same one the chat uses. The page only starts it and shows the results.
- **Login:** it uses her existing Claude login through the Claude Code command-line tool (to be confirmed, §11). There's no API key, and nothing leaves her Mac beyond what Claude Code normally sends to Claude.
- **Starting it:** she runs `/network-focus:setup-app` once, from the Claude app. It copies the app to `~/Library/Application Support/Network Focus/` and registers it as a login item (a macOS LaunchAgent) so it starts by itself. It also puts a **Network Focus** link on her Desktop. Running it again repairs or updates the app.
- **Security:** a local server that can launch Claude is a target for any other website open in her browser. So it:
  - listens only on 127.0.0.1
  - rejects requests that don't come from the local page itself (checked through the Host and Origin headers)
  - requires a random token created at setup, which is built into her Desktop link
  - allows only one run at a time

  In background runs, Claude can only read and write the Network Focus folder and run the plugin's own scripts.
- **Failures shown in plain English:**
  - server not running: the Desktop link says "restart your Mac or run setup again"
  - Claude signed out: "open the Claude app and sign in"
  - a run already in progress
  - every §6 failure the skill reports

## 6. Failure modes and how the code handles them

| # | Failure | Detected by | What happens |
|---|---|---|---|
| 1 | Spreadsheet missing, unreadable, empty, or required columns renamed or missing | `load_roster.py` | **Stops.** Plain message naming the file and the column, plus the fix. No brief is produced. |
| 2 | Org named in goals has no contact in the roster (a16z, MIRI) | `load_roster.py` (goals.md `Key organizations`) | Warning in the "Check" box |
| 3 | Ambiguous reference: a name in the notes matches the wrong company, or several people (Patrick at Greylock) | `load_roster.py` ("Name at Company" pattern + first-name index); scouts also flag | Warning. The skill never guesses. |
| 4 | Goals contradict data (no ARC contact vs Paul Christiano) | `load_roster.py` (`No contacts yet at`) | Warning: "update goals.md or check the row" |
| 5 | Thin context (strength ≤1 and summary under ~8 words) | `load_roster.py` flag | Excluded unless a scout marks it low-confidence, and then labeled as such |
| 6 | Stale data: file older than 7 days, or the exact same file as a previous run | `load_roster.py` (file date + `.history.json` fingerprint) | Warning at the top of the brief. Days-since values are labeled as "as of" the file date. |
| 7 | Made-up facts: a name not in the roster, a misquote, wrong day counts, a dormant pick under 60 days, duplicates, wrong counts | `validate_brief.py` (row ID and name must match; each evidence quote must appear word-for-word in that row; numbers re-checked against the data; every data warning must appear in the "Check" box) + fact-checker | Fix and retry up to 2 times, then stop and list the problems. `render_pdf.py` refuses to render an invalid brief. |
| — | A scout returns broken output | Skill | Retry once, then continue without that scout and add a warning: "Goal X couldn't be analyzed this week" |
| — | Name collisions (two Davids) | `load_roster.py` | Info only. The brief always shows full name and company. |
| — | Near the cutoff (59 days) | `load_roster.py` | Info: "Lin Wang becomes dormant next week" |

## 7. Data Sourcing Strategy (PRD section, outline)

- **Calendar MCP:** meetings become last-contact dates and the meeting channel. Synced daily.
- **Gmail MCP:** the last email date, a one-line thread summary, and unanswered threads (like David Park's). Read metadata and summaries only, never store full bodies. Synced daily.
- **CRM** (Affinity or HubSpot): company, role, tags and deal/intro history. Synced weekly.
- **Kept manual:** relationship strength, how she knows them, and the notes. That's her judgment, reviewed in a 10-minute Friday pass by the chief of staff.
- **Key fix: store dates, not "days since."** Computing the day count at run time removes the stale-data problem.
- **Trade-offs:** privacy (her inbox) vs completeness, sync cost vs freshness, and LinkedIn, which stays manual because of its terms of service.

## 8. Success criteria

- **All test cases pass** (§9), with every check done in code
- **The real roster's brief** includes Diana Chen and Marcus Wei, excludes the five "should not appear" names, and raises warnings 2, 3, 4 and 6
- **Zero** invented names or quotes across all test runs
- **The grader** scores ≥4/5 on move specificity and grounding
- **A fresh install that follows only HANDOFF.md** works, both for the fresh-eyes agent and for Jasper on his Mac
- **A full run takes a few minutes**, to be measured and reported in the PRD

## 9. Testing (build-time only, not shipped)

- **Unit tests** (`pytest`) for every script, with one test per failure mode
- **Test set** in `tests/evals/`, about six spreadsheets with expected results:
  - the real roster
  - missing columns
  - a stale or re-used file
  - an added duplicate "Diana"
  - a thin-context goal target
  - a CSV version

  Run headless with `claude -p "/network-focus:brief <file>" --plugin-dir plugins/network-focus`.
- **Build-time agents**, in the repo's `.claude/agents/` and not shipped:
  - `eval-grader`: scores briefs against the rubric
  - `handoff-tester`: gets only HANDOFF.md and reports where a non-technical user would get stuck
- **Code review:** the existing `/code-review` skill runs before each push. No custom agent needed.
- **Plugin check:** `claude plugin validate`

## 10. Repo layout

```
network-focus/                          (public GitHub repo, also the marketplace)
├── .claude-plugin/marketplace.json
├── plugins/network-focus/
│   ├── .claude-plugin/plugin.json
│   ├── skills/brief/SKILL.md           → /network-focus:brief
│   ├── skills/check/SKILL.md           → /network-focus:check
│   ├── agents/goal-scout.md
│   ├── agents/fact-checker.md
│   ├── scripts/                        load_roster, validate_brief, render_pdf, check_setup
│   ├── schemas/                        scout-output, brief, warnings
│   ├── templates/goals.md
│   ├── skills/setup-app/SKILL.md       → /network-focus:setup-app (installs the local page)
│   └── app/                            server.py, index.html (local web page, §5.8)
├── sample-data/network_roster_terragrid.xlsx
├── tests/unit/  tests/evals/
├── .claude/agents/                     eval-grader, handoff-tester (build-time)
└── docs/  design/  PRD.md  HANDOFF.md  VIDEO-OUTLINE.md
```

## 11. Risks to rule out first (15-minute test build before the real build)

1. A plugin skill can launch the plugin's own sub-agent (`network-focus:goal-scout`) in parallel. The docs imply this but don't show it. **Fallback:** the skill passes the scout's instructions to a general-purpose sub-agent.
2. `${CLAUDE_PLUGIN_ROOT}` is filled in correctly inside SKILL.md, so the scripts can be found.
3. `uv run` with inline dependencies works on macOS with no other setup.
4. **Desktop app: adding the marketplace.** The plugin browser is a GUI, but adding a *new* marketplace is documented only as the `/plugin marketplace add` command. Test whether that works typed into the desktop chat box. **Fallback:** a one-time terminal command in the handoff doc, after which everything happens in the app.
5. **Desktop app: finding `uv`.** Mac apps opened from the Dock sometimes don't see tools Homebrew installed. **Fallback:** `check_setup.py` and the skill also look in the usual install locations (`/opt/homebrew/bin`, `~/.local/bin`).
6. **Desktop app: permission prompts.** Confirm that `allowed-tools` stops the operator from being asked to approve each script in the default (Manual) mode.
7. **Background runs use her normal Claude login.** Confirm that `claude -p` works with a regular Claude login (no API key) and loads the installed plugin. **Fallback:** the page tells her to use the desktop chat that week.
8. **The login item can find `claude` and `uv`.** Background services on a Mac get a minimal PATH. **Fix:** the setup skill writes full paths into the service file.

## 12. Plan and ownership

| Phase | Work | Who | Time |
|---|---|---|---|
| 0 | GitHub repo, Claude Code + `uv` on the Mac, confirm when the brief arrived | Jasper | 20 min |
| 1 | Test build (§11), then the PRD, reviewed by Jasper | Both | 1 h |
| 2 | Scripts and unit tests first, then skills, agents, packaging | Claude, Jasper directing | 2 h |
| 3 | Run the real roster and the test set, tune against §3 | Both | 45 min |
| 4 | Local web page and the `setup-app` skill. **Cut line:** if it isn't working by the end of day 2, ship without it. | Claude, Jasper directing | 2–3 h |
| 5 | HANDOFF.md, the fresh-eyes check, then a real install on the Mac | Both | 45 min |
| 6 | PDFs, video outline, rehearsal, a 10–12 min recording (QuickTime, uploaded to YouTube unlisted or Drive, since free Loom stops at 5 min), submit | Jasper | 1.5 h |

**What stays with Jasper:** the live demo and the video, recorded on his own machine and typed live, not read from a script. He should be able to explain every decision in §4–6 in his own words.

## 13. Calls made without asking (check these)

- The operator folder is `~/Documents/Network Focus/`, and the newest file in `inbox/` is used by default
- "Dormant" means 60 days or more, and "thin" means strength ≤1 plus a short summary
- A file is stale after 7 days, judged by the file date, plus fingerprint matching against earlier runs
- The handoff covers macOS and the Claude desktop app, with the terminal as a fallback
- Web app or artifact is rejected (§4, row D). This is worth presenting in the video as an architecture decision.
- PDFs are made with `reportlab`, with no system libraries
- The local page uses Python's built-in web server (no extra libraries) and plain HTML. It runs on port 8765, can only be reached from her own Mac, and is protected by a setup token.
- The local page is set up through a skill (`/network-focus:setup-app`), not a terminal script
- The design doc lives in `docs/design/` in the public repo, as visible evidence of the process
