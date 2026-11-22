# CEO Dashboard: design

**Status:** for approval · 2026-11-22 · builds on `2026-11-21-network-focus-design.md`

## 1. Intent

The CEO should see, in one glance, the **one person to focus on this week** and act on it in one click. She isn't technical and doesn't want to read a report. She wants a dashboard that says what to do, gives her a ready-made message, and shows whether she's following through.

## 2. Goals, non-goals, anti-goals

**Goals**
- The #1 pick, the move and a ready-to-send message are visible without scrolling or reading anything else.
- Every pick has one-click **Copy message**, and every move has **Mark done**.
- Progress is visible: this week's progress ring, plus last week's score.
- It runs only on the Mac where Network Focus is installed (same local page, same security).

**Non-goals**
- Sending email or creating calendar events. The spreadsheet has no email addresses, so "Copy" puts the draft on the clipboard.
- Syncing between devices.
- Editing picks by hand.
- Live CRM data.

**Anti-goals** (failure even if it works)
- She has to read more than one sentence to know what to do.
- A message invents a fact the spreadsheet doesn't support.
- The dashboard breaks the graded skill or the existing one-button flow.

## 3. Approaches considered

| Choice | Options | Picked and why |
|---|---|---|
| Concept | 1 "One Thing" card · 2 goal scoreboard · 3 action list · 4 relationship map | **1 + 3**: one-glance focus plus follow-through. 2's numbers can mislead on thin data. 4 is decoration. |
| Visual design | A Calm Focus · B Command Center · C Morning Headline · D Week Board | **A + B's progress ring** (Jasper's choice): A's clarity, with B's sense of progress. |

## 4. What she sees

```
┌───────────────────────────────────────────────────────────────────┐
│ Network Focus · Week of Nov 23        ◔ 2 of 5 done · Last week 3/5 │
│ [ This week ]  [ Make the brief ]                       Open PDF ↗  │
├───────────────────────────────────────────────────────────────────┤
│ THIS WEEK'S #1                                                      │
│ Diana Chen  (Hire a CTO)                CTO, Stripe                 │
│ Call Diana and ask her to name her 3–4 CTO candidates…             │
│ She offered to help 28 days ago and the offer was never taken up.  │
│ [ Copy message ]  [ Mark done ]                                     │
├───────────────────────────────────┬───────────────────────────────┤
│ ALSO THIS WEEK                    │ 2 QUESTIONS FOR YOU            │
│ ☐ Marcus Wei · Sequoia   [Copy]   │ Who's your warm intro at a16z? │
│ ☐ Sarah Guo · Conviction [Copy]   │ Who made Marcus's intro…?      │
│ ☐ Paul Christiano · ARC  [Copy]   │ + 5 more ▾                     │
│ ☐ Sophia Lee · Pinterest [Copy]   │ GOING QUIET                    │
│                                   │ Lin Wang · 59 days             │
│ WORTH A NOTE (dormant)            │ Patrick Collison · 53 days     │
│ ☐ Reid Hoffman · 81 days [Copy]   │                                │
│ ☐ Priya Mehta · 128 days [Copy]   │                                │
└───────────────────────────────────┴───────────────────────────────┘
```

The layout follows mockup A (`scratchpad/mockups/dashboard-variations.html`), with B's ring in the header.
- **The ring** shows this week's done out of total, counting the #1, the others and the dormant picks.
- **"Last week 3/5"** comes from last week's saved progress, and is hidden when there's none.
- **Light and dark** follow the Mac's setting.

**Two tabs on the same local page:**
- **This week** is the dashboard, and the default once a brief exists for this week.
- **Make the brief** is today's page: drop the spreadsheet, Generate, Check setup, past briefs.

**Empty states:**
- With no brief yet, it opens on *Make the brief* and says "No brief yet this week."
- If the newest brief is from an earlier week, it shows that brief with a banner: "This is the brief from Nov 16. Make this week's →".

## 5. How it works

### 5.1 The brief gains a draft message per person (skill change, kept small)

- **Schema:** `schemas/brief.json` gets a required `message` (string) on every `focus` and `dormant` item.
- **The message itself:** 3–5 sentences in the CEO's voice, with the specific ask, and no sign-off name.
  - If the move is a call, the message is a short note asking for the call.
  - It may only use facts in that person's row.
- **SKILL.md:** a new step-3 instruction to write it. Focus is ordered by priority, and **`focus[0]` is the #1**, the single most important move this week, picked with the existing rules (open loops first, then goals served, then strength gone quiet).
- **Validator (`brief_checks.py`)** adds `MESSAGE_*` checks. The message must:
  - be 20–120 words
  - contain the person's first name
  - contain no placeholders (`[`, `{`, `<`, "TODO", "Lorem")
  - mention no "N days" figure that doesn't match the row
- **Fact-checker:** also checks each message's facts.
- **PDF:** unchanged and still one page. Messages appear only in the `.md` copy and the dashboard.

### 5.2 A saved snapshot per brief

`render_pdf.py` also writes `briefs/<week>-network-focus.json`. It holds the brief, the goal titles, the warnings, and for each picked or going-quiet person: name, role, company and days. The dashboard reads the newest snapshot. It never reads `.work/`, because each run clears it.

### 5.3 Progress

`.progress.json` in her folder stores `{ "<week_of>": { "<row_id>": true } }`. Only rows in that week's brief are accepted.

### 5.4 Server (`app/server.py`)

- `GET /api/dashboard` returns:
  - `week_of`, `stale` (true if the brief is from an earlier week), `pdf_url`
  - `top`, `others`, `dormant`, each with name, role/company, goal titles, move, why, message and done
  - `questions` (warnings in Check-box order, then extra checks, then goal gaps), `going_quiet`
  - `progress {done, total, last_week: {done, total} | null}`
- `POST /api/done {row_id, done}` updates `.progress.json`.
- The existing guards apply to both: Host, Origin, token, local-only.

### 5.5 Page (`app/index.html`)

Plain HTML, CSS and JS, no build step, same palette as the brief.
- **Copy** uses the clipboard (allowed on `127.0.0.1`). If that fails, it shows the message selected in a box.
- **Mark done** and the checkboxes save straight away, and the ring updates.

## 6. Constraints

- Every existing check stays green: 109 unit tests, 6/6 test cases. After the skill change, re-run at least `real-roster` and `missing-columns`, and the full set if time allows (about $6).
- The PDF stays one page, and the graded behaviour is unchanged apart from the added message.
- HANDOFF.md (the Monday steps) and VIDEO-OUTLINE.md (demo the dashboard) are updated, and HANDOFF stays one page.
- No new dependencies.

## 7. Calls made (check these)

- The dashboard lives on the **same Mac** as Network Focus. The CEO sees it there (in the Monday meeting) or on her own Mac if it's installed there too. There's no sync.
- **#1 is simply the first focus pick,** ordered by the existing rules. There's no separate "why #1" field.
- **Dormant picks get messages and checkboxes too,** and count in the ring.
- **"Questions for you"** shows the first 2 checks, with the rest behind "+ N more".
- **Messages don't appear in the PDF,** to keep it one page.
- **Timing:** this is about 3–4 hours of building, during day 2 of the 3-day window. If it's going into the submission, consider asking MindMaven for the 5-day extension today.
