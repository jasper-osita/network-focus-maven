# Adaptive Roster: design

**Status:** for approval · 2026-11-22 · builds on `2026-11-22-ceo-dashboard-design.md` and `2026-11-22-installer-design.md`

## 1. Intent

The roster spreadsheet is a living file. The CEO or the chief of staff updates it whenever they like, with no fixed schedule. They add people and change notes. Network Focus should keep up:

- It reads the roster from **a Google Drive folder**, so nobody downloads or drags a file each week.
- It **notices when the roster changes** and says who's new.
- It keeps **this week's focus stable**, with one exception. **Anyone new tied to the main goal (the Series C)** is ranked against the current picks right away, and takes a slot if they beat one.
- The dashboard shows **progress on each of the 3 goals**, so the CEO sees at a glance which goals she's moving this week.

## 2. Goals, non-goals, anti-goals

**Goals**
- The installer creates a **Network Focus folder in her Google Drive**, and the page reads the roster from it.
- Within a few minutes of the roster changing, the dashboard shows a line naming the new and changed people, with an **Update this week's brief** button.
- **Update** looks only at new and changed people.
  - Someone tied to **Goal 1** who beats the weakest open pick takes that pick's slot.
  - Everyone else goes to **Worth considering · since Monday**.
- **One ring per goal**, counting this week's moves done for that goal, next to the existing weekly total.
- It works on Mac and Windows, just as the rest of the app does.

**Non-goals**
- Re-ranking the whole week mid-week. Monday's Generate still does that.
- Native Google Sheets. The roster stays an Excel (.xlsx) or .csv file in Drive. A Google Sheet in the folder gets a plain message explaining how to fix it.
- Refreshing the messages of people already picked when their row changes. They're listed as changed, and Monday's brief picks up the new notes.
- Saving the PDFs to Drive, or showing the dashboard on the CEO's phone. Both are good follow-ups.
- Running Update automatically. It runs only when someone clicks, so the cost and usage-limit hits stay in their hands.

**Anti-goals** (failure even if it works)
- The CEO's list reshuffles under her for anything other than a Series C newcomer.
- A done move, or the #1, changes after an Update.
- A goal loses its only pick because of a swap.
- A new pick states something the roster doesn't say, or a swap the rules forbid gets through because the model said so.
- Her Google password or any key is stored by the app, or the roster leaves her computer and Drive.
- Monday's Generate, the graded skill, breaks.

## 3. Approaches considered

| Choice | Options | Picked and why |
|---|---|---|
| Where the roster lives | Drive for desktop sync folder · Claude's Google Drive connector · Google API login · "Publish to web" link | **Drive for desktop** (Jasper: "just create a folder"). There's no key or password, and the page can check for changes without spending a Claude run. The connector can't watch for changes cheaply and is unverified in background runs. The API login is too much setup for her. Publishing would make the network public. |
| Mid-week behavior | A: keep picks fixed · B: re-rank the open moves | **A, except urgent newcomers** (Jasper). Picks stay fixed unless someone new is urgent; then they're ranked against the current picks for a slot. |
| What counts as urgent | Something due this week · tied to the Series C | **Tied to the main goal** (Jasper: "anyone tied to series C"). The main goal is Goal 1 in goals.md, so this follows her goals if they're reordered. |
| How Update runs | Diff only: code finds the changes, the model judges only those, code applies the rules · Full re-run with picks locked | **Diff only** (Jasper). It's cheaper and faster, and the swap rules live in code, where the model can't bend them. |
| What a goal ring measures | A: this week's moves done · B: share of the network contacted recently · C: real milestones | **A** (Jasper). It's built on data that exists every week, it's tied to Mark done, and it resets on Monday. |

## 4. What she sees

The header gains the goal rings. When the roster changes, a line appears above the #1. The #1 stays visible without scrolling.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Network Focus · Week of Nov 23                  ◔ 3 of 8 done · Last wk 3/5 │
│  ◑ Raise Series C 2/4    ◔ Hire a CTO 1/3    ○ AI safety 0/2               │
│ [ This week ]  [ Make the brief ]                              Open PDF ↗  │
├──────────────────────────────────────────────────────────────────────────┤
│ Roster updated today 10:42 · New: Ana Ruiz, Tom Park · Changed: Marcus Wei │
│                                            [ Update this week's brief ]    │
├──────────────────────────────────────────────────────────────────────────┤
│ THIS WEEK'S #1  Diana Chen (Hire a CTO)                         Done ✓     │
│ …                                                                          │
├─────────────────────────────────────┬────────────────────────────────────┤
│ ALSO THIS WEEK                      │ 7 QUESTIONS FOR YOU                 │
│ ☐ Ana Ruiz · a16z  NEW · SERIES C   │ …                                   │
│ ☐ Marcus Wei · Sequoia     [Copy]   │ GOING QUIET                         │
│ ☐ Paul Christiano · ARC    [Copy]   │ …                                   │
│ ☐ Sarah Guo · Conviction   [Copy]   │                                     │
│ WORTH A NOTE · gone quiet           │                                     │
│ ☐ Reid Hoffman · 81 days   [Copy]   │                                     │
│ WORTH CONSIDERING · since Monday    │                                     │
│   Tom Park · Figma: strong CTO fit; Monday's brief will rank him         │
│   Sophia Lee: moved here to make room for Ana Ruiz                        │
└─────────────────────────────────────┴────────────────────────────────────┘
```

- **Goal ring:** done ÷ this week's moves for that goal. A move serving two goals counts toward both. If a goal has no move this week, its ring is replaced by "No move this week" in the warning color.
- **Roster line:**
  - It appears only when a new or changed person was found (see 5.2).
  - It clears after a successful Update, or when the file goes back to what the brief used.
  - If the newest brief is from an earlier week, it says "New week. Generate this week's brief" instead, as the stale banner does today.
- **After an Update:**
  - A placed person shows the chip **NEW · SERIES C**, with Copy and a message like every other pick.
  - "Worth considering" lists each other new or changed person with one line, plus anyone bumped and why.
  - The PDF header gets "Updated <day> <time>: added <names>".

## 5. How it works

### 5.1 The Drive folder

- **Finding Drive for desktop:**
  - **Mac:** `~/Library/CloudStorage/GoogleDrive-*/My Drive`. If there's more than one account, it takes the first and says which.
  - **Windows:** the first drive letter with a `My Drive` folder (usually `G:\My Drive`), else `%USERPROFILE%\My Drive` (mirror mode).
- **Setting up the folder:** the installer creates `My Drive/Network Focus` and saves its path as `roster_folder` in `<nf_home>/settings.json`. The workspace reads that file, so the interactive skill (`/network-focus:brief` in the Claude app) and the page use the same folder. If the local inbox already holds a roster, the newest one is copied into the Drive folder once.
- **If Drive for desktop isn't installed or signed in:** the installer doesn't fail. It says: "Google Drive isn't set up on this computer. Install Google Drive for desktop, sign in, then run the installer again. Until then, drag spreadsheets onto the page as before." The local inbox keeps working.
- **Which file:** the newest `.xlsx`/`.csv` in the folder, the same rule as the inbox today. `~$` lock files are still ignored.
- **A `.gsheet` file but no spreadsheet:** the run stops with "The roster in Google Drive is a Google Sheet, which I can't read. In Drive, open it and choose File → Download → Microsoft Excel, then put that file in the Network Focus folder. Or keep the roster as an Excel file."
- **Uploads:** dropping a file on the page saves it into the Drive folder, so it syncs.
- **Check setup** gains a "Google Drive folder" line: ok, info (not set up, using the local inbox), or fail (folder missing, or only a Google Sheet found).

### 5.2 Noticing changes (code only, no Claude)

- **Fingerprint every row:**
  - Each brief's snapshot gains `roster_index`, which maps every contact's **identity** to a **row fingerprint**.
  - Identity = normalized name + company.
  - The fingerprint is a hash of role, how she knows them, channel, summary, strength, tags and notes.
  - Days since contact are left out, because every fresh export changes them.
- **Check the file:** a background thread in the page server checks the folder every 2 minutes, looking at the newest file's path, size and modified time.
  - A change counts only once it has held steady for one check, so a file that's still syncing or saving isn't read half-written.
  - Then the server runs `uv run scripts/roster_diff.py --roster <file> --snapshot <latest>`. It prints the new, changed and removed people as JSON.
  - The answer is cached and served by `GET /api/roster-changes`, and the dashboard asks for it every 2 minutes.
- **No change, no line:** when the diff finds no new or changed people, no line is shown. That covers a fresh export where only the day counts moved.

### 5.3 Update (`/network-focus:update`, a new skill)

The dashboard's Update button sends `POST /api/run` with `{"mode": "update"}`. The server then runs `claude -p "/network-focus:update"` headless, just as Generate does, with the same single-run lock, watchdog, progress events and failure messages. The steps:

1. **Load:** `load_roster.py` runs on the newest roster file, unchanged.
2. **Prep:** `update_prep.py --work WORK --snapshot S` (code).
   - It maps this week's picks to their new row numbers by identity, and reads which picks are done.
   - It lists the new and changed people, and lists the **open slots**:
     - empty focus slots first (focus holds 3–5 people),
     - then open focus picks other than the #1, weakest first. Weakest is the lowest in the brief's priority order.
   - It writes `WORK/update-input.json`. If nobody is new or changed, it says so and the run stops with nothing changed.
   - Changed people who are already this week's picks are listed but not judged (see Non-goals).
   - Dormant picks are never open slots; only focus slots are.
3. **Judge (the model):** the skill reads update-input.json and roster.json, then writes `WORK/update.json` following `schemas/update.json`. For each new or changed person:
   - `tied_to_main_goal` (true/false), with `evidence`: a quote copied word for word from that person's row. A true answer must say how they serve Goal 1.
   - `beats`: the row of the open pick they should replace, or `null`. The skill judges this with the brief's existing selection rules.
   - For a placement: `why`, `move`, `risk`, `evidence`, `confidence` and `message`, under the same rules as a focus pick.
   - For everyone else: a one-line `consider` note.
4. **Apply:** `apply_update.py --work WORK --snapshot S` (code). It enforces the rules whatever the model wrote:
   - Only people with `tied_to_main_goal: true` and a validated quote can take a slot.
   - Done picks and the #1 can never be replaced.
   - Empty slots fill before anyone is bumped. Bumps go weakest-first, and each newcomer takes at most one slot.
   - No swap may leave a goal with no pick when it had one. That swap is skipped and the newcomer goes to Worth considering.
   - The bumped pick moves to `considering`, with "moved to make room for <name>".
   - A newcomer takes the bumped pick's place in the priority order; one filling an empty slot goes last.
   - It writes the merged `WORK/brief.json`, with an `updates` entry: when, who was added, who was bumped.
   - It re-keys this week's marks in `.progress.json` to the new row numbers, matching by name and company and writing atomically. A row shift doesn't lose a tick.
5. **Check:** `validate_brief.py brief` runs on the merged brief, and the fact-checker runs on the newly placed picks only. There are at most 2 fix rounds, as in the weekly brief.
6. **Render:** `render_pdf.py` overwrites this week's PDF and snapshot.
   - The snapshot's `source`, `roster_index`, questions, going-quiet list and banner are rebuilt from the new roster.
   - The model-written `coming_up` and `extra_checks` are kept.

**A pick removed from the sheet** stays on the dashboard. A question is added: "<Name> is no longer in the roster. Remove them from this week's list?" Nothing disappears without someone saying so.

### 5.4 Goal rings

- `dashboard_payload` gains `goals: [{id, title, done, total}]`, counted over focus and dormant picks.
- To make that possible, dormant picks gain a `goals` field. It's required in new briefs and optional in old snapshots, which count toward the weekly total only.

## 6. Constraints and risks

- **macOS privacy prompt.** The page runs in the background (launchd). macOS may ask before letting a background process read Google Drive's folder, or refuse silently. This **must be checked on her Mac early** (task 1 of the plan).
  - If it's refused, Check setup and the run show the exact System Settings step to allow it.
  - If that isn't possible, the fallback is that Update copies the file through a step the Claude app is allowed to run.
- **Online-only files.** Drive for desktop may stream files instead of keeping them on disk. Reading one downloads it first, so with no internet the run says "Couldn't open the roster from Google Drive. Check the internet connection."
- **Sharing.** The folder lives in the chief of staff's Drive. The CEO edits the roster by having the folder shared with her. That's a one-time step in the handoff doc.
- **Identity is name + company.** Someone who changes company shows up as new, and as removed under their old company. That's acceptable, and the removed-person question catches it.
- **The PRD and handoff must stay 2 pages and 1 page.** Drive replaces the inbox wording rather than adding to it.

## 7. Testing

- **Unit tests:**
  - the diff: new, changed, removed, identity and fingerprint, ignoring day counts
  - prep: slot order
  - apply: every rule in 5.3 step 4, including the coverage floor and a model that breaks the rules
  - re-keying marks; the goal-ring payload
  - finding the Drive folder, using fake Mac and Windows home folders
  - the `.gsheet` message; the steady-file check; `/api/roster-changes`
- **Server:** a `fake_claude` update mode.
- **Evals:**
  - an a16z partner added with a Series C note must take the weakest open slot
  - a strong CTO candidate added must go to Worth considering
  - a newcomer whose swap would empty a goal must be refused
- **On her Mac:** one signed-in run, which settles the privacy-prompt question.

## 8. Left to the builder

- Exact wording of chips and lines (in the existing plain style), and the ring sizes.
- How `roster_diff.py` shares code with `update_prep.py`.
- Whether the background check uses one thread or the existing request threads.
- Updating the artifact preview to show the goal rings and the roster line, after the build.
