# Network Focus: guide for the chief of staff

Every Monday, Network Focus turns the CEO's network spreadsheet and goals into a one-page brief: who to invest time in this week and why, quiet relationships that still matter, and things to check with her. You never type code.

## One-time setup (about 15 minutes)

**You need** a Mac with the Claude app, signed in to a paid plan (Pro or higher; you can check this in the Claude app under Settings). To add the two small helper programs it needs, open **Terminal**, the Mac's built-in command window (press ⌘-Space, type *Terminal*, press Return). Paste each of these lines, press Return, and wait about a minute for it to finish: `curl -LsSf https://astral.sh/uv/install.sh | sh` then `curl -fsSL https://claude.ai/install.sh | bash`. If it asks for a password, type your Mac password (nothing shows while you type, which is normal) and press Return.

**Install Network Focus:**

1. In Finder, create *Documents › Network Focus*. In the Claude app, click **Code** at the top, then **Open folder…**, and choose that folder.
2. In the message box at the bottom, type `/plugin marketplace add jasper-osita/network-focus-maven` and press Return. Then click the **+** next to the message box, choose **Add plugins → Network Focus → Install**.
   *If you see an error, or Network Focus isn't in the list, run these in Terminal instead:* `claude plugin marketplace add jasper-osita/network-focus-maven`, then `claude plugin install network-focus@network-focus`
3. In the message box, type `/network-focus:setup-app`. If Claude asks for permission, click **Allow**. A **Network Focus** link appears on your Desktop.
4. Type `/network-focus:check`. You should see ✅ and ℹ️ lines. If a line shows ❌, do what its "Fix" says.

## Every Monday (2 minutes, plus 3 minutes of waiting)

1. Double-click **Network Focus** on the Desktop. It opens in your web browser. Drag this week's spreadsheet (.xlsx or .csv) into the dashed box. Its name appears in the list.
2. Click **Generate this week's brief**. Leave the window open while the steps tick off. Then click **Open PDF** and go through *Check before the meeting* with the CEO.

*No page?* In the Claude app's **Code** tab, with the Network Focus folder open, type **make this week's network brief**.
*Each quarter:* open *Documents › Network Focus › goals.md* with TextEdit (right-click › Open With). Change only the text after each colon, and keep lines like `## Goal 1:` as they are.

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
| "Claude is signed out" / the page won't open | Sign in to the Claude app. If the page still won't open, restart the Mac or type `/network-focus:setup-app`. |

**Anything else:** click **Check setup** on the page (or type `/network-focus:check`) and do the first ❌ fix. **Updates:** turn on auto-update under **+ → Manage plugins → Marketplaces**, and re-run `/network-focus:setup-app` after each update.
