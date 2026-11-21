---
name: brief
description: Make this week's Network Focus brief for the CEO. It picks the 3 to 5 people she should invest in this week, the dormant relationships worth reviving, and the data problems to check. Use when asked for the weekly brief, the network brief, network focus, or who the CEO should reach out to this week.
argument-hint: "[path to spreadsheet, optional]"
allowed-tools: Read, Write, Edit, Bash(uv run *), Bash(/opt/homebrew/bin/uv run *), Bash(~/.local/bin/uv run *), Agent, Task
---

# Network Focus brief

You're making the CEO's weekly Network Focus brief for her chief of staff, who isn't technical. Talk to her in plain English. Never show her JSON, code or the contents of working files. Follow these steps in order.

Every script lives in `${CLAUDE_PLUGIN_ROOT}/scripts`. Run each one with `uv run "<path>"`. If `uv` isn't found, try `/opt/homebrew/bin/uv run` and then `~/.local/bin/uv run`. If none of them work, tell her: "I need a small tool called uv that isn't installed yet. Type /network-focus:check and follow the fix it shows." Then stop.

## 1. Load and check the data

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/load_roster.py" --roster "$ARGUMENTS"`

It prints one line of JSON. Call its `work_dir` WORK.
- If `status` is `setup` or `blocked`, pass on the `message` in friendly words. Keep every file name, column name and folder path exactly as written. Tell her what to do next, then stop.
- If `status` is `ok`, continue. Read `WORK/roster.json` and `WORK/warnings.json`.

## 2. Review each goal in parallel

Launch the `network-focus:goal-scout` agent once for every goal in roster.json `goals`, **all in a single message** so they run at the same time. Set each launch's description to `Goal <id>: <title>`, because it's shown to her as progress. Give each one this prompt:

```
Goal id: <id>
Roster: WORK/roster.json
Warnings: WORK/warnings.json
Schema: ${CLAUDE_PLUGIN_ROOT}/schemas/scout-output.json
Write your output to: WORK/scout-<id>.json
```

When they're done, check each output:
`uv run "${CLAUDE_PLUGIN_ROOT}/scripts/validate_brief.py" scout WORK/scout-<id>.json --roster WORK/roster.json`

If one fails, launch that scout once more with the problems listed. If it fails again, carry on without it and add "Goal <id> (<title>) couldn't be analyzed this week" to `extra_checks`.

## 3. Choose the people

Read every scout output, then decide across all goals using these rules:

1. Every pick serves at least one goal. People who serve two goals rank higher.
2. Cover every goal with at least one pick if a credible candidate exists. If none does, say so in the brief.
3. Open loops come first: an offer she hasn't taken up, an ask waiting on her, a note that went unanswered.
4. Strong but dormant relationships rank high.
5. Respect timing. If someone asked to wait, don't push. List them under "Coming up" instead.
6. Leave out contacts with no goal link, contacts with strength 1 and no context (unless marked low-confidence), and contacts whose notes advise against reaching out.
7. No one appears twice. The dormant section lists 2–3 people at 60+ days who are not already top picks.
8. Each move is one concrete action this week, through a named channel, with the reason it fits.

Tie-breakers:
- If one goal would take more than half of the focus picks while another goal has only one, see whether a strong-but-dormant pick could go in the dormant section instead. That frees a focus slot for the under-covered goal's best open loop.
- Every move contains a specific ask: an intro to whom, a meeting about what, an answer to which question. "Check in" or "keep warm" isn't a move.
- Write so the CEO can act in five minutes. Use one idea per sentence. Use first names instead of "he" or "she" whenever two people could be meant, and call the CEO "the CEO". Don't describe a person or organization in ways their row doesn't support.

Write `WORK/brief.json` so it follows `${CLAUDE_PLUGIN_ROOT}/schemas/brief.json` exactly:
- `week_of`: copy roster.json `source.week_of`.
- `focus`: 3–5 people.
  - `row_id` and `name` exactly as in roster.json, and `goals` as goal ids.
  - `why`, `move` and `risk`: one sentence each, specific to this person. Any "N days" must match the row.
  - `evidence`: 1–2 quotes, at least 3 words each, copied word for word from that contact's `text`.
  - `confidence`: "low" if `flags.thin` is true.
- `dormant`: 2–3 people with `flags.dormant` true who aren't in focus. Copy `days_since_contact` from the row.
- `coming_up`: people to prepare for but not push yet (timing "later"). At most 2.
- `goal_gaps`: any goal with no credible pick, and what's missing.
- `extra_checks`: up to 3 data problems from the scouts' `concerns` that aren't already in warnings.json. Never repeat warnings.json, because the PDF adds those automatically.

## 4. Check the brief

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/validate_brief.py" brief WORK/brief.json --roster WORK/roster.json`

If it lists problems, fix exactly what they say in brief.json and run it again. Allow at most 2 rounds of fixes. If it still fails, tell her "I couldn't make a brief I'm confident in this week," list the problems in plain words, and stop. Never render a brief that fails this check.

## 5. Fact-check

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/validate_brief.py" cited-rows WORK/brief.json --roster WORK/roster.json --out WORK/cited-rows.json`

Then launch `network-focus:fact-checker` with:

```
Brief: WORK/brief.json
Cited rows: WORK/cited-rows.json
Write your output to: WORK/factcheck.json
```

For each claim in factcheck.json that the row doesn't support, rewrite it to say only what the row supports, or remove it. Then run the step 4 check again.

## 6. Make the PDF

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/render_pdf.py" --work WORK`

If it exits with code 4 (too long for one page), shorten `why`, `move` and `risk` to one short sentence each and run it once more.

## 7. Tell her it's ready

Reply in no more than 8 short lines, with no JSON:

```
Brief ready: <pdf path>
This week: <Name>: <move>   (one line each)
Dormant: <names>
<N> things to check with the CEO. They're at the bottom of the brief.
```

N is the number of warn-level warnings, plus `extra_checks`, plus `goal_gaps`.
