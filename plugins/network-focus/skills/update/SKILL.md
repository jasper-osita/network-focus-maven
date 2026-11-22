---
name: update
description: Update this week's Network Focus brief mid-week after the roster spreadsheet changed. It looks only at people who are new or changed since the brief was made, places anyone tied to the main goal (Goal 1) who beats an open pick, and lists everyone else as worth considering. Use when asked to update this week's brief, refresh the brief with new people, or check the new contacts.
allowed-tools: Read, Write, Edit, Bash(uv run *), Bash(/opt/homebrew/bin/uv run *), Bash(~/.local/bin/uv run *), Agent, Task
---

# Network Focus mid-week Update

You're updating this week's Network Focus brief for the CEO's chief of staff, who isn't technical. The roster changed after the brief was made. Talk to her in plain English. Never show her JSON, code or the contents of working files. Follow these steps in order.

This week's picks stay as they are. The only exception is someone new or changed who is **tied to the main goal** (the goal with the lowest id in goals.md, today "Raise Series C") and outranks an open pick. Code decides which slot they take and refuses any swap that breaks a rule. Your job is the judgment only.

Every script lives in `${CLAUDE_PLUGIN_ROOT}/scripts`. Run each one with `uv run "<path>"`, exactly as written below: one command per Bash call, starting with `uv run`. Don't add `cd`, `&&`, pipes or other commands, because only `uv run` commands are pre-approved and anything else will be refused. To look at a file, use the Read tool, never `cat` or `ls`. If a command is refused, run it again exactly as written once before deciding anything is wrong. If `uv` isn't found, try `/opt/homebrew/bin/uv run` and then `~/.local/bin/uv run`. If none of them work, tell her: "I need a small tool called uv that isn't installed yet. Type /network-focus:check and follow the fix it shows." Then stop.

## 1. Load the fresh roster

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/load_roster.py"`

It prints one line of JSON. Call its `work_dir` WORK.
- If `status` is `setup` or `blocked`, pass on the `message` in friendly words. Keep every file name, column name and folder path exactly as written. Then stop.
- If `status` is `ok`, continue.

## 2. Find who's new or changed

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/update_prep.py" --work "WORK"`

- If `status` is `nothing` or `blocked`, tell her the `message` and stop.
- If `status` is `ok`, read `WORK/update-input.json` and `WORK/roster.json`.

update-input.json gives you `main_goal`, this week's `picks` (with `done` and `locked`), the `people` to judge, and the `open_slots` (empty slots first, then open picks, weakest first). Changed people who are already picks are in `listed_only`; leave them alone.

## 3. Judge each new or changed person

Write `WORK/update.json` so it follows `${CLAUDE_PLUGIN_ROOT}/schemas/update.json` exactly. Give every person in `people` one entry, best candidate first:

- `row_id` and `name` exactly as in roster.json.
- `evidence`: 1–2 quotes, at least 3 words each, copied word for word from that person's `text`.
- `tied_to_main_goal`: true only when their row shows a real link to the main goal: an investor or fund, the round itself, or someone offering an intro to an investor. A strong relationship alone isn't a link. When true, `goal_link` says how in one sentence; otherwise leave `goal_link` as "".
- `beats`: only for tied people. The `row_id` of the open pick in `open_slots` they outrank, judged with the weekly brief's selection rules (serves more goals, has an open loop or a reason to act this week, stronger relationship). Leave it out if they don't outrank any open pick.
- `pick`: only for tied people who beat an open pick, or when `open_slots` has an empty slot. Write it like a focus pick in the weekly brief:
  - `goals` as goal ids, including the main goal.
  - `why`, `move` and `risk`: one sentence each, specific to this person. Any "N days" must match the row.
  - `evidence`: 1–2 word-for-word quotes, as above.
  - `confidence`: "low" if `flags.thin` is true.
  - `message`: 3–5 sentences the CEO can paste and send, in her voice, with the specific ask and no sign-off name. Greet the person by first name. Use only facts from that person's row, don't write placeholders like [Name], and never say something is attached.
- `consider`: for everyone without a pick, one plain sentence on why they're worth a look next week.

## 4. Check your answer

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/validate_brief.py" update "WORK/update.json" --roster "WORK/roster.json" --input "WORK/update-input.json"`

If it lists problems, fix exactly what they say in update.json and run it again. Allow at most 2 rounds of fixes. If it still fails, tell her "I couldn't update the brief with confidence," list the problems in plain words, and stop.

## 5. Apply the rules

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/apply_update.py" --work "WORK"`

It writes the merged `WORK/brief.json`. Never edit brief.json yourself. If it exits with problems, fix update.json as they say and run it once more.

## 6. Check the merged brief

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/validate_brief.py" brief "WORK/brief.json" --roster "WORK/roster.json"`

If it lists problems in a new pick, fix that pick in update.json and go back to step 5. Allow at most 2 rounds.

## 7. Fact-check the new picks

Only if step 5 reported anyone in `added`:

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/validate_brief.py" cited-rows "WORK/brief.json" --roster "WORK/roster.json" --out "WORK/cited-rows.json" --only-new`

It also writes `WORK/new-picks.json`: just the people this Update added. Then launch `network-focus:fact-checker` in the foreground with:

```
Brief: WORK/new-picks.json
Cited rows: WORK/cited-rows.json
Write your output to: WORK/factcheck.json
```

For each claim the row doesn't support, rewrite it in update.json to say only what the row supports, then run steps 5 and 6 again. Monday's picks were checked on Monday; leave them alone.

## 8. Make the PDF

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/render_pdf.py" --work "WORK"`

If it exits with code 4 (too long for one page), shorten `why`, `move` and `risk` of the new picks in update.json, then run steps 5 and 8 again.

## 9. Tell her it's done

Reply in no more than 5 short lines, with no JSON:

```
Brief updated: <pdf path>
Added: <name> (in place of <bumped name>)     (one line each, or "No change to the picks")
Worth considering: <names>
```
