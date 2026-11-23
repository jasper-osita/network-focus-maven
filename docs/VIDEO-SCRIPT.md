# Video script: live demo (target 11 minutes, one take)

Screen-record the whole thing (QuickTime → File → New Screen Recording, or Loom). Talk in your own words; the lines in quotes are a guide. **[Slide N]** means switch to the deck for a few seconds; everything else is live.

## Set up before you hit record (10 minutes, not recorded)

- [ ] Mac plugged in, notifications off (Focus), browser zoom ~125%.
- [ ] Installer re-run today (version 0.3.4). `network_roster_terragrid.xlsx` is in **Google Drive › My Drive › Network Focus**, and nothing else is in that folder.
- [ ] Do **one rehearsal Generate**, then **Reset**: delete `briefs/*` in *Documents › Network Focus* so the recording starts clean. (The rehearsal also adds the *Last Contact Date* column, which you'll show.)
- [ ] A copy of the roster on the Desktop named `broken.xlsx`, open in Excel (for the failure demo).
- [ ] Tabs open: the Network Focus page (Desktop link), the CEO dashboard artifact, the GitHub repo. VS Code open on the repo with: `docs/PRD.md`, `plugins/network-focus/skills/brief/SKILL.md`, `agents/goal-scout.md`, `scripts/nf_core/brief_checks.py`, `scripts/nf_core/update.py`, `scripts/nf_core/roster.py`.
- [ ] The deck open in a browser tab.
- [ ] Fallback if the page won't open: a Terminal in `~/Documents/Network Focus` with `claude` running; type `/network-focus:brief` instead of clicking Generate. Everything else is the same.

---

## 0:00 – 0:40 · Intro **[Slide 1]**

"I'm Jasper. This is Network Focus, a Claude Code skill that turns a CEO's network spreadsheet and her three goals into a one-page weekly brief: who to invest time in this week, and why. The person running it is her chief of staff, who isn't technical, so everything is one click. I'll show it running for real, then the architecture, then how it fails safely."

## 0:40 – 2:00 · From PRD to build

- Open `docs/PRD.md`, scroll to §3. "One rule drove every decision: **code handles facts, the model handles judgment.**"
- Open `brief_checks.py`, find `_check_person`. "Every quote in the brief must appear word for word in that person's row, and every 'N days' must match. If not, the PDF step refuses to render."
- Open `SKILL.md` step 2, then `agents/goal-scout.md` (`model: sonnet`). "One scout per goal, in parallel, so the Series C, which has the most rows, can't crowd out AI safety. A separate Haiku fact-checker sees only the rows the brief cites."

## 2:00 – 4:30 · Live run

- Switch to Google Drive › Network Focus and open the spreadsheet briefly. "This lives in Google Drive. Two traps: Marcus's note says 'intro from Patrick at Greylock', but the only Patrick works at Stripe; and the goals mention a16z, but nobody at a16z is in the list." Point at the **Last Contact Date** column: "The sheet now stores real dates; day counts are formulas."
- Switch to the Network Focus page → **Make the brief** → **Generate this week's brief**.
- **While it runs (about 2 minutes), narrate each step as it ticks:**
  - "Checking the data: pure Python. No model has run yet."
  - "Reviewing Goal 1, 2, 3: three sub-agents in parallel."
  - "Fact-checking the picks: an independent agent."
  - "Making the PDF: it won't render a brief that fails a check."
- Don't cut the wait. It shows the run is real.

## 4:30 – 6:30 · What the CEO and chief of staff get

- The page switches to **This week**. "One person, one move, one click." Point at **Diana Chen**, then click **Copy message** and paste into a note. "The draft is checked like every other claim."
- Click **Mark done**: the ring and the **Hire a CTO** goal ring move.
- Click the **Spreadsheet** tab: Diana's row now has today's date in **Done**. Type a comment, press Tab. "Ticks and comments are written back to the CEO's own spreadsheet."
- **Now start the mid-week change** (it shows up 2 minutes later): in Excel or Google Drive, add a row: *Ana Ruiz · Partner · Andreessen Horowitz · investor · 5 · email · "Asked for a Series C call before Friday." · 3 · investor, series-c*. Save.
- Back on **This week**, click **Open PDF**: walk the picks, then the decoys it skipped ("James Park: strength 5, best friend, no goal link"), then **Check before the meeting**: a16z, Patrick, ARC.
- Switch to the **CEO dashboard artifact**. "This is what the CEO opens on claude.ai. It reads the dashboard the page just saved into Google Drive, through her own Google Drive connection." Point at **Live from Google Drive** and the updated time.

## 6:30 – 7:30 · Mid-week Update

- Back on the page. The line **Roster updated · New: Ana Ruiz** has appeared (if not yet, carry on and come back). "The page checks the folder every 2 minutes, in code, without spending a Claude run."
- Click **Update this week's brief** and narrate: "Claude only judges the new person. Code applies the rules: done picks and the #1 never move, she takes the weakest open slot, and no goal is left without a pick."
- When it finishes: Ana has the **New · Raise Series C** chip, and the person she replaced is under **Worth considering**, with the reason.

## 7:30 – 9:00 · Architecture, with code **[Slide 2]**

- Repo tree: "The repo is its own plugin marketplace. The one-click installers for Mac and Windows are tested on both by GitHub Actions."
- `SKILL.md`: `allowed-tools` pre-approves only `uv run` and the agents, so she never sees a permission prompt.
- `schemas/brief.json`: "one contract the agents follow and the validator enforces."
- `update.py` → `apply_update`: "the model says who's tied to the Series C; code decides the slot."
- `app/server.py`: "local only, token-protected. Her data stays on her computer and her Drive."

## 9:00 – 10:15 · A failure mode, live **[Slide 3]**

- In `broken.xlsx` (Excel), rename **Days Since Last Contact** to **Days** and delete **Notes**. Save.
- Drag it onto the page's **Make the brief** box, then click **Generate**. It stops at once with: "broken.xlsx is missing these columns: Days Since Last Contact, Notes…"
- Open `roster.py` → `MISSING_COLUMNS`: "It stops before any model runs. No PDF is ever made from bad data."
- **Delete `broken.xlsx` from the Drive folder now**, or it stays the newest file.
- One line on the second failure mode: "`checks.py` found the 'Patrick at Greylock' ambiguity; the brief asks the CEO instead of guessing."

## 10:15 – 11:15 · Limitations and what's next **[Slide 4]**

"It's pilot-ready, not production-ready:
- The first date conversion relies on the file's date.
- I tested on 25 contacts; at hundreds, I'd filter rows per goal before the scouts.
- Model picks vary slightly between runs, although every rule holds.
- Windows has never had a signed-in background run.
- The CEO's live view is read-only: ticks happen on the chief of staff's page or in the sheet.

Next: four weeks of piloting with real usage, then an independent review of the write-back. Thanks for watching."

---

**If something breaks on camera:** say what happened and show the message. The page explains every failure in plain words and keeps a log, and that is itself part of the demo.
