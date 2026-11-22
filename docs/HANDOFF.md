# Network Focus: guide for the chief of staff

Every Monday, Network Focus turns the CEO's network spreadsheet and goals into a one-page brief: who to invest time in this week and why, quiet relationships that still matter, and things to check with her. You never type code.

## One-time setup (about 10 minutes, one click)

**You need** a Mac or a Windows PC and a paid Claude plan (Pro or higher). Double-click **Install Network Focus.zip** to unzip it.

1. **Mac:** double-click *Mac - Install Network Focus* (if macOS says it "can't be opened": **System Settings → Privacy & Security → Open Anyway**). **Windows:** double-click *Windows - Install Network Focus* (if you see "Windows protected your PC": **More info → Run anyway**). A window opens and works through 5 steps on its own.
2. When your browser opens, **sign in to Claude**, then come back to the window. If a Mac asks for your password, type it (nothing shows while you type).
3. When it says **Done**, the dashboard opens and a **Network Focus** link is on your Desktop.

*If the double-click is blocked:* on a Mac, paste into **Terminal** `curl -fsSL https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.sh | bash`; on Windows, paste into **PowerShell** `irm https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.ps1 | iex`

## Every Monday (2 minutes, plus 3 minutes of waiting)

1. Double-click **Network Focus** on the Desktop. On **Make the brief**, drag in this week's spreadsheet and click **Generate this week's brief**. Leave the window open while the steps tick off.
2. It switches to **This week**: the CEO's #1 person with **Copy message** (a ready-to-send draft) and **Mark done**, then a checklist. Tick moves as she makes them. **Open PDF** gives the printable brief.

*No page?* In the Claude app's **Code** tab, with the Network Focus folder open, type **make this week's network brief**.
*Each quarter:* open *Documents › Network Focus › goals.md* in TextEdit (Mac) or Notepad (Windows). Change only the text after each colon, and keep lines like `## Goal 1:` as they are.

## What "good" looks like

**A normal Monday.** *Input:* a 25-contact spreadsheet and 3 goals. *Output:* a one-page PDF with 3–5 entries like *Diana Chen · CTO, Stripe*, each with Why, Move ("Call Diana this week and ask for intros to the 3–4 CTO candidates she mentioned") and At risk, then 2–3 dormant contacts, then checks like *"Goal 1 mentions a16z, but nobody at a16z is in the network list. Who is the contact there?"* Every move should be doable this week, and every reason should match the spreadsheet.

**A changed spreadsheet.** *Input:* the "Days Since Last Contact" header was renamed "Days" and Notes was deleted. *Output:* no brief, and the message *"roster.xlsx is missing these columns: Days Since Last Contact, Notes. Add them back (or fix the header spelling) in the first row, then run again."* Fix the header row, drag the file in again, and click Generate.

## When something goes wrong

| What you see | What to do |
|---|---|
| "There's no spreadsheet…" / "…is missing these columns…" / "I couldn't open…" | Add the file, fix the header row, or re-save it as .xlsx in Excel (double-click a .zip to unzip it first). Run again. |
| **Data warning** at the top (old file date, or the same file as last week) | The brief is still fine to use, but the "days" may be a little off. Export a fresh copy next week. |
| "Who is the contact there?", "Who made the intro?", "Is that the way in?" | These aren't errors. They're questions for the CEO. Fix the spreadsheet or goals.md before next week. |
| "I couldn't make a brief I'm confident in this week" | Click Generate again. If it repeats, click **Check setup** and send a screenshot to whoever set this up. |
| "Claude is signed out" / the page won't open | Double-click **Install Network Focus** again: it signs you back in and repairs the page. |

**Anything else:** click **Check setup** on the page and do the first ❌ fix. **Updates:** double-click **Install Network Focus** again; it updates everything. **To remove it** (keeps your briefs): run the installer from Terminal with `--uninstall` (Mac) or from PowerShell with `-Uninstall` (Windows).
