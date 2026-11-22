# CEO Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A one-glance CEO dashboard on the existing local page. It shows the #1 pick with a ready-to-send message, a checklist for the rest of the week, a progress ring and last week's score.

**Architecture:** The brief gains a validated, fact-checked `message` per person. `render_pdf.py` also saves a JSON snapshot per brief. A stdlib-only `app/dashboard_data.py` builds the dashboard payload from the newest snapshot plus `.progress.json`. `server.py` serves it at `GET /api/dashboard` and `POST /api/done`. `index.html` gets two tabs: *This week* (design A plus B's ring) and *Make the brief* (today's page).

**Tech Stack:** Python ≥3.11 (stdlib in `app/`; `reportlab`/`openpyxl` unchanged in `scripts/`), plain HTML/CSS/JS, pytest, and Playwright for visual checks.

**Spec:** `docs/design/2026-11-22-ceo-dashboard-design.md`. It builds on `docs/design/2026-11-21-network-focus-design.md`.

## Global Constraints

- **No new dependencies.** `app/*` uses the standard library only. The page is plain HTML/CSS/JS with no build step.
- **The PDF stays one page** and doesn't show messages. Messages appear in the `.md` copy and the dashboard only.
- **Message rules (spec §5.1):**
  - 20–120 words
  - contains the person's first name
  - no `[`, `{`, `<`, `TODO` or `Lorem`
  - any "N days" must match the row
  - required on every `focus` and `dormant` item
- **`focus[0]` is the #1.**
- **Snapshot:** `briefs/<week_of>-network-focus.json`. **Progress:** `<NF_HOME>/.progress.json` as `{"<week_of>": {"<row_id>": true}}`, written atomically (temp file, then rename).
- **The new endpoints use the existing guards:** Host, Origin on POST, token cookie.
- **Everything stays green:** 109+ unit tests, and the test cases re-run (`real-roster` and `missing-columns` at minimum). HANDOFF.md stays one page.

## Review Focus

1. **Re-running the brief in the same week changes the picks.** Done flags for rows no longer in the brief are ignored, and the ring counts only current picks. → Task 3 `test_progress_ignores_rows_not_in_brief`
2. **An older snapshot, or a briefs folder with PDFs but no JSON.** The dashboard returns `{"empty": true}`, or a person with `message: ""`, and never crashes. → Task 3 `test_no_snapshot_is_empty`, `test_missing_message_tolerated`
3. **A half-written or corrupt `.progress.json`** is treated as empty, and the next write repairs it. → Task 3 `test_corrupt_progress_file_ignored`
4. **The browser blocks the clipboard.** The page shows the message pre-selected in a box. → Task 5, Step 3 (Playwright, clipboard permission denied)
5. **Model text containing HTML characters** (in a move, why or name) shows as text, never as markup. → Task 5, Step 3 (Playwright injects `<b>x</b>`). Messages themselves already reject `<` (Task 1).

---

### Task 1: Draft message per person (schema, validator, skill, fact-checker, .md)

**Files:**
- Modify: `plugins/network-focus/schemas/brief.json`, adding a required `message` (string, minLength 1, with a description of the rules) to the `focus` and `dormant` items
- Modify: `plugins/network-focus/scripts/nf_core/brief_checks.py`
- Modify: `plugins/network-focus/scripts/nf_core/render.py`: `render_markdown` adds `- **Message:** …` under each focus and dormant person
- Modify: `plugins/network-focus/skills/brief/SKILL.md` (step 3) and `agents/fact-checker.md`
- Modify: `tests/unit/fixtures/valid_brief.json`, adding a valid `message` to all 7 focus and dormant items
- Test: `tests/unit/test_brief_checks.py`, `tests/unit/test_render.py`

**Interfaces:**
- **Produces:** new problem codes `MESSAGE_LENGTH`, `MESSAGE_NAME` and `MESSAGE_PLACEHOLDER`. `NUMBER_MISMATCH` now also scans `message`.
- **Constants:** `MESSAGE_MIN_WORDS = 20`, `MESSAGE_MAX_WORDS = 120`, `PLACEHOLDERS = ("[", "{", "<", "todo", "lorem")`

- [ ] **Step 1: Add messages to the fixture, then write the failing tests**

```python
def test_message_rules(brief, roster):
    b = copy.deepcopy(brief); b["focus"][0]["message"] = "Hi Diana, quick one."
    assert codes(validate_brief(b, roster)) == ["MESSAGE_LENGTH"]
    b = copy.deepcopy(brief); b["focus"][0]["message"] = b["focus"][0]["message"].replace("Diana", "there")
    assert codes(validate_brief(b, roster)) == ["MESSAGE_NAME"]
    b = copy.deepcopy(brief); b["focus"][0]["message"] += " [Your name]"
    assert codes(validate_brief(b, roster)) == ["MESSAGE_PLACEHOLDER"]
    b = copy.deepcopy(brief); b["dormant"][0]["message"] += " It has been 90 days."
    assert codes(validate_brief(b, roster)) == ["NUMBER_MISMATCH"]
    b = copy.deepcopy(brief); del b["dormant"][1]["message"]
    assert "SCHEMA" in codes(validate_brief(b, roster))

def test_markdown_includes_messages(brief_dict, roster_dict, warnings_dict):
    md = render_markdown(brief_dict, roster_dict, warnings_dict)
    assert brief_dict["focus"][0]["message"] in md and brief_dict["dormant"][0]["message"] in md
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/unit/test_brief_checks.py tests/unit/test_render.py -q`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement**

- **Validator:** in `_check_move_and_numbers`, add the message checks. The name check is case-insensitive against the first token of the row's name. Apply the `_DAYS` regex to `item["message"]` too.
- **SKILL step 3** gets two new paragraphs:
  - "Order `focus` by priority: the first person is the single most important move this week."
  - "Write `message`: 3–5 sentences the CEO can paste and send, in her voice, with the specific ask, no sign-off name. If the move is a call, the message asks for the call. Use only facts in that person's row."
- **fact-checker.md:** add `message` to the fields it checks.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest -q`. Expected: all pass, and the existing validator tests still pass with the updated fixture.

- [ ] **Step 5: Commit**

`feat: draft message per pick (validated, fact-checked)`

### Task 2: Brief snapshot for the dashboard

**Files:**
- Create: `plugins/network-focus/scripts/nf_core/snapshot.py`
- Modify: `plugins/network-focus/scripts/nf_core/render.py`, so `_ctx` uses `questions_for()` instead of building the checks list itself
- Modify: `plugins/network-focus/scripts/render_pdf.py`, which writes `briefs/<stem>.json` after the PDF
- Test: `tests/unit/test_snapshot.py`, `tests/unit/test_render.py`

**Interfaces:**
- **Produces:**
  - `questions_for(brief: dict, roster: dict, warnings: dict) -> list[str]`: warn-level messages that aren't STALE/REUSED, then `extra_checks`, then `"No pick for Goal N (title): note"`
  - `build_snapshot(brief: dict, roster: dict, warnings: dict) -> dict` with these keys:
    - `version` (1), `week_of`, `source` (`file_name`, `as_of`)
    - `goals` (`{str(id): title}`)
    - `people` (`{str(row_id): {name, role, company, days_since_contact}}`, for every focus, dormant and coming_up row and every NEAR_DORMANT row)
    - `brief` (as is)
    - `questions`, `banner` (STALE/REUSED messages)
    - `going_quiet` (`[{row_id, name, days_since_contact}]` for NEAR_DORMANT rows not already picked)

- [ ] **Step 1: Write the failing tests**

```python
def test_build_snapshot(brief_dict, roster_dict, warnings_dict):
    s = build_snapshot(brief_dict, roster_dict, warnings_dict)
    assert s["version"] == 1 and s["week_of"] == "2026-11-23" and s["goals"]["2"] == "Hire a CTO"
    assert s["people"]["3"] == {"name": "Diana Chen", "role": "CTO", "company": "Stripe", "days_since_contact": 28}
    assert [g["name"] for g in s["going_quiet"]] == ["Lin Wang", "Patrick Collison"]
    assert any("a16z" in q for q in s["questions"]) and any("22 days ago" in b for b in s["banner"])
    json.dumps(s)  # serializable

def test_render_pdf_writes_snapshot(tmp_path, brief_dict, roster_dict, warnings_dict):  # in test_render.py, via the CLI
    home = setup_work(tmp_path, brief_dict, roster_dict, warnings_dict)
    code, out = run_cli(home, "--today", "2026-11-23")
    snap = json.loads((home / "briefs" / "2026-11-23-network-focus.json").read_text())
    assert code == 0 and snap["brief"]["focus"][0]["name"] == "Diana Chen"
```

- [ ] **Step 2: Run the tests and confirm they fail.** Then implement. Then run `uv run pytest -q` and confirm everything passes.

- [ ] **Step 3: Commit**

`feat: save a JSON snapshot with each brief`

### Task 3: Dashboard data and progress (`app/dashboard_data.py`, stdlib)

**Files:**
- Create: `plugins/network-focus/app/dashboard_data.py`
- Modify: `plugins/network-focus/app/install_app.py`, adding `"dashboard_data.py"` to `APP_FILES`
- Test: `tests/unit/test_dashboard_data.py`, plus a copy assertion in `tests/unit/test_install_app.py`

**Interfaces:**
- **Consumes:** snapshot files from Task 2, found by the glob `briefs/*-network-focus.json`, newest `week_of` first.
- **Produces:**
  - `week_of(today: date) -> date`: same rule as `nf_core.workspace.week_of`
  - `load_progress(nf_home: Path) -> dict`
  - `set_done(nf_home: Path, week: str, row_id: int, done: bool) -> None`: atomic write
  - `dashboard_payload(nf_home: Path, today: date) -> dict` returns `{"empty": true}`, or:
    - `week_of`, `stale` (bool), `pdf_url` (`/briefs/<stem>.pdf`)
    - `top`, `others`, `dormant`: person dicts of `{row_id, name, role_company, goals: [titles], move, why, message, done, days?}`
    - `questions`, `going_quiet`, `banner`
    - `progress: {done, total, last_week: {done, total} | null}`
  - `pick_ids(snapshot: dict) -> set[int]`: focus plus dormant row ids

- [ ] **Step 1: Write the failing tests**

Snapshots are written into `tmp/briefs` with `nf_core.snapshot.build_snapshot`.

```python
def test_no_snapshot_is_empty(tmp_path): assert dashboard_payload(tmp_path, date(2026,11,23)) == {"empty": True}
def test_payload_top_and_progress(home_with_snapshot):
    set_done(home_with_snapshot, "2026-11-23", 3, True)
    p = dashboard_payload(home_with_snapshot, date(2026,11,23))
    assert p["top"]["name"] == "Diana Chen" and p["top"]["done"] is True and p["top"]["goals"] == ["Hire a CTO"]
    assert p["top"]["role_company"] == "CTO, Stripe" and len(p["others"]) == 4 and len(p["dormant"]) == 2
    assert p["progress"] == {"done": 1, "total": 7, "last_week": None} and p["stale"] is False
def test_last_week_score(home_with_two_weeks): ...      # previous week's snapshot with 3 of 7 done → last_week == {"done": 3, "total": 7}
def test_stale_brief_flagged(home_with_snapshot): ...   # today 2026-12-01 → stale is True
def test_progress_ignores_rows_not_in_brief(home_with_snapshot): ...  # set_done(row 99) → done stays 0
def test_missing_message_tolerated(home_with_snapshot): ...  # strip message from snapshot → top["message"] == ""
def test_corrupt_progress_file_ignored(home_with_snapshot): ...  # write "{" to .progress.json → payload works; set_done then makes valid JSON
```

- [ ] **Step 2: Run the tests and confirm they fail.** Then implement. Then run `uv run pytest -q` and confirm everything passes.

- [ ] **Step 3: Commit**

`feat: dashboard data and weekly progress`

### Task 4: Server endpoints

**Files:**
- Modify: `plugins/network-focus/app/server.py`
- Test: `tests/unit/test_server.py`

**Interfaces:**
- **Consumes:** `dashboard_payload` and `set_done` from Task 3
- **Produces:**
  - `GET /api/dashboard` returns the payload as JSON, with token required
  - `POST /api/done {"row_id": int, "done": bool}` returns `200 {"progress": {...}}`, or `400` if the row isn't a current pick or the body is malformed. Origin and token are required.

- [ ] **Step 1: Write the failing tests**
  - `test_dashboard_empty_then_filled`: empty before any snapshot. After one is written into `briefs/`, `top.name == "Diana Chen"`.
  - `test_done_updates_progress`: POST row 3, then `progress.done == 1`.
  - `test_done_rejects_unknown_row`: row 99 returns 400.
  - `test_done_requires_origin`: a bad Origin returns 403.

- [ ] **Step 2: Run the tests and confirm they fail.** Then implement. Then run `uv run pytest -q` and confirm everything passes.

- [ ] **Step 3: Commit**

`feat: dashboard API`

### Task 5: Dashboard page (design A + ring), with two tabs

**Files:**
- Modify: `plugins/network-focus/app/index.html`
- Test: `tests/unit/test_server.py` (`test_index_has_both_tabs`)

**Interfaces:**
- **Consumes:** `/api/dashboard`, `/api/done`, and the existing `/api/status`, `/api/upload`, `/api/run`, `/api/check`

- [ ] **Step 1: Write the failing test**

`test_index_has_both_tabs`: GET `/?t=` contains `This week`, `Make the brief`, `id="ring"` and `Copy message`. Run it and confirm it fails.

- [ ] **Step 2: Build the page**

Follow mockup A from `scratchpad/mockups/dashboard-variations.html`:
- **Header:** brand, week, an SVG ring showing `done/total`, and the "Last week d/t" text (hidden when null). Tabs are buttons that toggle sections.
- **This week:**
  - the hero shows `top`
  - "Also this week" lists `others` with checkbox and Copy
  - "Worth a note" lists `dormant` with checkbox, Copy and days
  - the side column has "N questions for you" (first 2, plus a `<details>` with the rest) and "Going quiet"
  - an `Open PDF ↗` link
- **Make the brief:** the current controls, unchanged.
- **States:**
  - `empty` opens on *Make the brief* with "No brief yet this week."
  - `stale` shows a banner: "This is the brief from <date>. Make this week's →"
  - after a successful Generate, it reloads the dashboard and switches to *This week*
- **Behaviour:**
  - all text goes through `esc()`
  - Copy uses `navigator.clipboard.writeText`. If that rejects, it opens a `<dialog>` with the message in a pre-selected `<textarea>`.
  - checkboxes and Mark done POST `/api/done` and redraw the ring
- **Theme:** light and dark via the existing CSS tokens.

- [ ] **Step 3: Visual check (Playwright, deviceScaleFactor 1, `--no-proxy-server`)**

Start the server against a temp home holding a snapshot built from the fixture. Check that:
- the light and dark screenshots match the mockup A layout with the ring
- ticking a box changes the ring from 0/7 to 1/7
- with `permissions: []` for clipboard, clicking Copy shows the dialog with the textarea
- a snapshot whose `top.move` contains `<b>x</b>` shows that literally

Run the test from Step 1 and confirm it passes.

- [ ] **Step 4: Commit**

`feat: CEO dashboard page`

### Task 6: Real run, docs, test cases, review, merge

**Files:**
- Modify: `docs/HANDOFF.md` (Monday steps: open the page, Generate, then the dashboard), `docs/VIDEO-OUTLINE.md` (demo segment shows the dashboard, the #1 and Copy message), `README.md`, `docs/PRD.md` (one line on the dashboard)
- Regenerate: `deliverables/*.pdf`

- [ ] **Step 1: Real headless run with the installer's restricted permissions**

Expected:
- success, with 0 permission denials
- each focus and dormant item has a validated `message`
- `factcheck.json` covered the messages
- `briefs/*.json` exists
- the dashboard served from that home shows the real #1

Replace `deliverables/Brief.pdf` with this run's PDF.

- [ ] **Step 2: Run the test cases**

Run `uv run python tests/evals/run_evals.py --case real-roster`, then `--case missing-columns`. Expected: both PASS. Run the full set with `--grade` if time allows, and record the results in `tests/evals/results/`.

- [ ] **Step 3: Update the docs and rebuild the PDFs**

Run `uv run --with markdown python tools/make_pdfs.py`. Expected: PRD ≤2 pages, Handoff 1 page.

- [ ] **Step 4: Whole-branch review, then one fix pass**

A fresh reviewer (opus) reviews `main..dashboard`, then one fix pass follows, test-first.

- [ ] **Step 5: PR and merge**

Open a PR (`dashboard` → `main`) through the REST API. Fast-forward `main`, run `uv run pytest -q` and confirm everything passes, push `main`, and confirm the PR shows as merged.
