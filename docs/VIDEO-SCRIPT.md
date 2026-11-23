# Video script: live demo (target 11–12 minutes, one take)

Screen-record the whole thing (QuickTime → File → New Screen Recording, or Loom). Talk in your own words; the lines in quotes are a guide. **[Slide N]** means switch to the deck for a few seconds; everything else is live.

## Set up before you hit record (10 minutes, not recorded)

- [ ] Mac plugged in, notifications off (Focus), browser zoom ~125%.
- [ ] Installer re-run today (version 0.3.6). `network_roster_terragrid.xlsx` is in **Google Drive › My Drive › Network Focus**, and nothing else is in that folder.
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

## 2:00 – 6:00 · Live run on the provided spreadsheet (real input → real output)

- Open Google Drive › Network Focus › `network_roster_terragrid.xlsx`. "This is the real input." Point at two traps: Marcus's note "intro from Patrick at Greylock" (the only Patrick works at Stripe), and the goals naming a16z although nobody at a16z is in the list.
- On the Network Focus page: **Make the brief** → **Generate this week's brief**. Narrate each step as it ticks, and **don't cut the wait**:
  - "Checking the data: pure Python. No model has run yet."
  - "Reviewing Goal 1, 2, 3: three sub-agents in parallel."
  - "Fact-checking the picks: an independent agent."
  - "Making the PDF: it won't render a brief that fails a check."
- **Real output:**
  - **This week** shows Diana Chen as #1. Click **Copy message** and paste it into a note, then click **Mark done**: the rings move.
  - Click **Open PDF** and walk through it: the picks and why, the decoys it skipped ("James Park: strength 5, best friend, no goal link"), and **Check before the meeting**: a16z, Patrick, ARC.
- One line each, and keep it moving:
  - **Calendar** tab: "every move gets a time she can change, and Add to calendar."
  - **Spreadsheet** tab: "ticks and comments are written back to her sheet."
  - The CEO dashboard artifact: "the CEO's live view, read from Google Drive."

## 6:00 – 8:30 · Architecture, with code **[Slide 2]**

- **The pipeline (slide):** code, then three Sonnet scouts, then the pick, then code validation, then a Haiku fact-check, then code that renders or refuses. "Why scouts per goal: if one agent sees everything, the Series C, which has the most rows, crowds out AI safety. Why a separate fact-checker: it never wrote the brief, so it has no stake in defending it."
- **`SKILL.md`:**
  - `allowed-tools` pre-approves only `uv run` and the agents, so she never sees a permission prompt.
  - "One `uv run` per call" is there because chained commands get refused in background runs.
- **`schemas/brief.json`:** "one contract that the agents follow and the validator enforces."
- **`app/server.py`:** "local only, with a token, so her data stays on her computer and in her Drive. A cloud app would need hosting and keys, and put her private notes on a server."
- **`nf_core/update.py` → `apply_update`:** "for a mid-week change, the model only says who's tied to the Series C. Code decides the slot: done picks and the #1 never move, and no goal loses its only pick."
- **`nf_core/sheet.py` → `convert_dates`:** "the trial sheet stored 'days since', which goes stale. It now stores a Last Contact Date, and the days are an Excel formula."

## 8:30 – 11:00 · AI failure mode, live, with code **[Slide 3]**

**The failure: the model invents a fact.** It's the most dangerous one, because a made-up quote would land in the CEO's brief.

1. In VS Code, open `~/Documents/Network Focus/.work/brief.json` (left from the run you just did). In Diana's `evidence`, replace a quote with something she never said: `"Promised to join as CTO"`. Save.
2. In Terminal, run:
   ```bash
   cd ~/Documents/Network\ Focus && uv run ~/Library/Application\ Support/Network\ Focus/scripts/validate_brief.py brief .work/brief.json --roster .work/roster.json
   ```
   It prints `QUOTE_NOT_FOUND`: "'Promised to join as CTO' isn't in Diana Chen's row. Quote the spreadsheet word for word."
3. Open `scripts/nf_core/brief_checks.py` → `_check_person`. "Every quote must appear word for word in that person's row, and every 'N days' must match the data."
4. Open `skills/brief/SKILL.md` step 4. "The skill gets at most two rounds to fix it. Then `render_pdf.py` checks again and refuses to make a PDF from an invalid brief."
5. "A second layer: the Haiku fact-checker. On my first real run it flagged 'he asked 16 days ago' as unsupported, and it was rewritten."
6. **If time allows (30 s), the data failure:** rename a column in `broken.xlsx` and drop it on the page. Generate stops at once and names the missing column (`roster.py` → `MISSING_COLUMNS`). **Then delete `broken.xlsx` from the Drive folder.**

## 11:00 – 12:00 · Limitations and what I'd do in production **[Slide 4]**

"It's pilot-ready, not production-ready:
- The first date conversion relies on the file's date.
- I tested on 25 contacts; at hundreds, I'd filter rows per goal before the scouts.
- Picks vary slightly between runs, although every rule holds.
- Windows has never had a signed-in background run.
- The CEO's live view is read-only.

In production: data from Calendar, Gmail and the CRM, as the PRD's data-sourcing section lays out; a four-week pilot with real usage; and an independent review of the write-back. Thanks for watching."

---

**If something breaks on camera:** say what happened and show the message. The page explains every failure in plain words and keeps a log, and that is itself part of the demo.
