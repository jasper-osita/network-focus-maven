# Video script: plain-language version (11–12 minutes, one take)

Record your screen for the whole video (on a Mac: QuickTime → File → New Screen Recording). Say the lines in your own words; the quotes are a guide, not something to read out. **[Slide N]** means: switch to the slide deck for a few seconds. Everything else happens live on screen.

**Words used in this script:**
- **Skill:** the set of instructions Claude follows to make the brief.
- **Helper:** a smaller Claude assistant that does one job, like reviewing one goal.
- **Check:** a small program (not AI) that compares what Claude wrote against the spreadsheet.

---

## Before you press record (about 10 minutes, not filmed)

- [ ] Mac plugged in, notifications off, and the browser zoomed in a little (about 125%).
- [ ] Run the installer again today (version 0.3.6).
- [ ] Put `network_roster_terragrid.xlsx` in **Google Drive › My Drive › Network Focus**, with nothing else in that folder.
- [ ] Do **one practice run** (click Generate once), then delete what's in *Documents › Network Focus › briefs* so the recording starts fresh.
- [ ] Open these browser tabs: the Network Focus page (from the Desktop link), the CEO dashboard link, and the slide deck.
- [ ] Open the project in VS Code with these files ready in tabs:
  - `docs/PRD.md`
  - `skills/brief/SKILL.md`
  - `agents/goal-scout.md`
  - `scripts/nf_core/brief_checks.py`
  - `scripts/nf_core/update.py`
- [ ] Open a Terminal window (you'll paste one line into it later).
- [ ] **Backup plan if the page won't open:** in Terminal, type `cd ~/Documents/Network\ Focus && claude`, then type `/network-focus:brief`. It makes the same brief.

---

## 0:00 – 0:40 · Introduction **[Slide 1]**

"Hi, I'm Jasper. This is Network Focus. Every week, it reads the CEO's list of contacts and her three goals for the quarter (raise money, hire a CTO, and build relationships in AI safety) and tells her, on one page, who to reach out to this week and why. Her chief of staff runs it with one click; nobody has to write code. I'll show you how I planned it, run it live, explain how it's built, and show what happens when the AI makes a mistake."

## 0:40 – 2:00 · From the plan to what I built

- Open `docs/PRD.md` (the plan) and scroll to section 3.
- "One rule shaped everything: **facts are checked by ordinary code, and Claude only makes the judgment calls.** Claude decides who matters this week. Code checks every name, quote and number against the spreadsheet."
- Open `brief_checks.py` and find `_check_person`. "This is the check. If Claude quotes something that isn't in that person's row, it's caught here."
- Open `SKILL.md` (step 2), then `goal-scout.md`. "Second decision: one helper per goal, working at the same time. If one helper looked at everything, fundraising, which has the most contacts, would crowd out the other goals. A separate helper then double-checks the facts."

## 2:00 – 6:00 · Live run on the real spreadsheet

**Show the input:**
- Open the spreadsheet in Google Drive. "This is the real list I was given: 25 contacts."
- Point out two traps: "Marcus's note says he was introduced by 'Patrick at Greylock', but the only Patrick on the list works at Stripe. And the goals mention the investor a16z, but nobody from a16z is on the list."

**Run it:**
- On the Network Focus page, open **Make the brief** and click **Generate this week's brief**.
- **While it works (about 2 minutes), describe each step as it appears.** Don't cut this part; it shows the run is real.
  - "Checking the data: plain code reads the spreadsheet. No AI yet."
  - "Reviewing Goal 1, 2 and 3: three helpers, one per goal, working at the same time."
  - "Fact-checking the picks: a separate helper double-checks the facts."
  - "Making the PDF: the brief is only printed if every check passes."

**Show the output:**
- The page opens **This week**. "One person, one action, one click." Point at Diana Chen.
- Click **Copy message** and paste it into a note. "A ready-to-send message, checked like everything else."
- Click **Mark done**. "The circles at the top show progress on each goal."
- Click **Open PDF**:
  - "Here are this week's picks, and why."
  - "It skipped people who look important but don't help the goals. James Park is a close friend, but he can't help with any of the three goals."
  - "At the bottom, the questions for the CEO: who's the contact at a16z, and who really made that intro."
- Mention these in one sentence each:
  - **Calendar** tab: "Each person gets a suggested day and time, which can be changed and added to her calendar."
  - **Spreadsheet** tab: "Ticks and comments are written back into her own spreadsheet."
  - **CEO dashboard** link: "What the CEO sees on claude.ai, updated from Google Drive."

## 6:00 – 8:30 · How it's built, and why **[Slide 2]**

- **Slide 2, the steps in order:** plain code reads the data, three helpers review the goals, Claude picks the people, code checks the facts, another helper double-checks, and code prints the PDF or refuses to.
  - "Why a separate fact-checking helper: it didn't write the brief, so it has no reason to defend it."
- **`SKILL.md`:** "These are the instructions Claude follows. They list exactly which actions Claude may take without asking, so the chief of staff never gets interrupted by permission pop-ups."
- **`schemas/brief.json`:** "This is the agreed format of the brief. Claude must fill it in exactly this shape, and code rejects anything that doesn't fit."
- **`app/server.py`:** "The page runs only on her own computer, behind a private key. I chose this over a website because a website would mean storing the CEO's private notes on someone else's server, and nobody on her team could fix it."
- **`update.py` → `apply_update`:** "When someone new is added mid-week, Claude only judges whether they matter for fundraising. Code decides where they go, and it never replaces the CEO's #1 or anything she's already done."
- "One more fix: the original spreadsheet said 'days since last contact', which goes out of date. It now stores the actual date and works out the days automatically."

## 8:30 – 11:00 · When the AI makes a mistake **[Slide 3]**

"The most dangerous mistake an AI can make here is inventing something, like a quote the person never said, and that ending up in front of the CEO. Let me make that happen on purpose."

1. In VS Code, open `~/Documents/Network Focus/.work/brief.json`. This is the brief Claude just wrote, before it was turned into the PDF.
2. In Diana's quotes, replace one with something she never said: `"Promised to join as CTO"`. Save.
3. In Terminal, paste:
   ```bash
   cd ~/Documents/Network\ Focus && uv run ~/Library/Application\ Support/Network\ Focus/scripts/validate_brief.py brief .work/brief.json --roster .work/roster.json
   ```
4. It answers `QUOTE_NOT_FOUND`: "'Promised to join as CTO' isn't in Diana Chen's row." Say: "Caught. That's the check catching an invented quote."
5. Open `brief_checks.py` → `_check_person`. "The rule is simple: every quote must appear word for word in that person's row, and every number of days must match the spreadsheet."
6. Open `SKILL.md`, step 4. "If this happens during a real run, Claude gets two tries to correct it. If it still fails, no PDF is made. The CEO never sees a brief with made-up facts."
7. "There's a second safety net: the fact-checking helper. In my first real test, it caught Claude writing '16 days ago' when the spreadsheet didn't support that."
8. **Only if you have time (30 seconds):** rename a column in a copy of the spreadsheet and drop it on the page. It stops straight away and names the missing column. **Afterwards, delete that copy from the Google Drive folder.**

## 11:00 – 12:00 · What's not perfect yet, and what I'd do next **[Slide 4]**

"It's ready for a trial with a real chief of staff, but not yet finished:
- The first time it converts 'days since contact' into real dates, it has to guess from the file's date.
- I tested it with 25 contacts. With hundreds, I'd narrow the list for each goal before the helpers read it.
- Two runs can pick slightly different people, although every check still holds.
- I haven't yet tried it on a real Windows computer with a signed-in account.
- The CEO's dashboard is view-only for now.

For a real launch, I'd bring in data from her calendar, email and CRM, as the plan describes; run a four-week trial with her team; and have someone else review the new parts. Thanks for watching."

---

**If something goes wrong while recording:** say what happened and show the message on screen. The page explains every problem in plain words and saves a record of each run, and that's part of what makes it reliable.
