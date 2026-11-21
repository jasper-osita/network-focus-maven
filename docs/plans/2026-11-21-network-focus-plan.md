# Network Focus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Claude Code plugin that turns the CEO's network spreadsheet and goals into a validated one-page weekly Network Focus brief (PDF). A chief of staff who doesn't write code runs it from the Claude desktop app or a local web page.

**Architecture:**
- Deterministic Python (`nf_core`) handles every fact: loading the spreadsheet, the data-quality checks, validating the brief, and rendering the PDF.
- A plugin skill (`/network-focus:brief`) handles the judgment. It sends one `goal-scout` sub-agent per goal in parallel, merges their results into `brief.json`, and gets it checked by the validator and a `fact-checker` sub-agent before `render_pdf.py` will produce the PDF.
- A local web page that uses only Python's standard library runs the same skill in the background (`claude -p`). It is the last layer, and it gets dropped if it's late.

**Tech Stack:**
- Python ≥3.11 run through `uv`, with `openpyxl` and `reportlab` declared inside each script (no other runtime dependencies)
- pytest for tests
- Claude Code plugin: skills, agents, marketplace
- HTML and vanilla JS for the local page
- Playwright (build-time only) to turn the docs into PDFs

**Spec:** `docs/design/2026-11-21-network-focus-design.md`. Read it alongside this plan. Section numbers (§) below refer to it.

## Global Constraints

- **Plugin and marketplace name:** `network-focus`. Skills: `brief`, `check`, `setup-app`. Agents: `goal-scout` (model `sonnet`), `fact-checker` (model `haiku`).
- **Operator folder:** `~/Documents/Network Focus/` (`goals.md`, `inbox/`, `briefs/`, `.history.json`, plus `.work/` for intermediate JSON). Tests override it with the `NF_HOME` env var.
- **Thresholds:**
  - dormant = `days_since_contact >= 60`
  - near-dormant = 53–59 ("becomes dormant within a week")
  - stale file = file date more than 7 days before today
  - thin = strength ≤1 **and** summary under 10 words (this pins the spec's "~8 words": it catches Anjali Sharma, 5 words, and Jensen Huang, 8 words)
- **Brief counts:** focus 3–5. Dormant 2–3, or every eligible dormant contact if fewer than 2 exist. No person appears twice.
- **One page:** the brief PDF is one page. Long text shrinks the font from 10pt down to 8pt in 0.5pt steps. If it still doesn't fit, exit code 4 tells the skill to shorten.
- **Dependencies:** runtime deps are only `openpyxl` and `reportlab`, declared inline (PEP 723) in each CLI script. `app/server.py` uses the standard library only.
- **Local page:** port 8765, bound to `127.0.0.1` only, protected by a token.
- **Operator copy:** every message the operator sees is plain English, names the file, row or column involved, and says what to do next. No stack traces and no JSON in chat. The brief always uses full name + company.
- **Scope:** no real Calendar, Gmail or CRM calls. Operator platform: macOS. Tests must also pass on Linux.
- **Spreadsheet columns:** row 1 = header, so the first contact is `row_id` 2, matching the row number she sees in Excel. The 10 required headers, matched ignoring case, spacing and parentheses: `Name`, `Role`, `Company`, `How She Knows Them`, `Days Since Last Contact`, `Last Contact Channel`, `Last Contact Summary`, `Relationship Strength (1-5)`, `Tags`, `Notes`.

## Review Focus

1. **A zipped spreadsheet.** The Google Drive download of the sample is a `.zip`, and inside it is the `.xlsx`. A file like this, even when it's named `.xlsx`, must be unwrapped if it holds exactly one spreadsheet. Otherwise block with "unzip it first." → Task 2 `test_zip_wrapper_unwrapped`, `test_drive_style_double_wrap`
2. **The spreadsheet is open in Excel.** Excel creates a `~$roster.xlsx` lock file in `inbox/`. Picking the newest file must ignore `~$*` and dotfiles. → Task 5 `test_picks_newest_ignoring_lock_files`
3. **Excel's own data quirks:** numbers stored as text or floats (`"16"`, `16.0`, `" 16 "`), blank trailing rows, and a title row above the header. These must parse cleanly with no warnings. → Task 2 `test_numbers_as_text_and_floats`, `test_blank_rows_skipped_silently`, `test_header_found_below_title_row`
4. **Re-running in the same week.** This must not raise a "same file as last week" warning. Only a match from an earlier week counts. → Task 5 `test_reused_file_warns`
5. **Names outside Latin-1** (for example "李伟") in the PDF. The PDF must stay legible and not crash or draw boxes. The `.md` version keeps the original characters. → Task 7 `test_pdf_safe`

---

### Task 0: Test build (throwaway) and repo init

Goal: settle §11 risks 1–3, the tool names and the headless flags before anything depends on them. Mac-only risks 4–8 go to Task 14.

**Files:**
- Create: `docs/design/spike-notes.md`
- Scratch (deleted afterwards): `$SCRATCH/spike-plugin/`

**Interfaces:**
- Produces, recorded in `spike-notes.md` and used by Tasks 9, 10 and 11:
  - `AGENT_TOOL`: the tool name for launching sub-agents (`Agent` or `Task`)
  - the exact `subagent_type` string for a plugin agent (expected `spike:echo`)
  - whether `${CLAUDE_PLUGIN_ROOT}` gets filled in inside SKILL.md
  - the working `claude -p` flags: `HEADLESS_FLAGS`, covering permission mode, `--allowedTools` and output format
  - the `stream-json` event shapes for a Bash call and an agent call

- [ ] **Step 1: `git init` the repo and make the first commit**

```bash
cd /home/user/network-focus && git init -b main && git add docs && git commit -m "docs: design and plan"
```

- [ ] **Step 2: Build the throwaway plugin `spike`**
  - **Skill `hello`:** runs `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/probe.py"`, then launches agent `echo` twice in parallel
  - **`scripts/probe.py`:** has an inline dependency on `openpyxl` and prints `openpyxl <version>`
  - **Agent `echo`:** `model: haiku`, replies `echo <n>`

- [ ] **Step 3: Run it headless and capture the stream**

```bash
claude -p "/spike:hello" --plugin-dir "$SCRATCH/spike-plugin" --output-format stream-json --verbose --permission-mode dontAsk --allowedTools "Bash(uv run *),Agent,Task,Read" > "$SCRATCH/spike.jsonl"
```

Expected:
- the stream contains `openpyxl 3.`
- two agent tool_use blocks appear in one assistant message, with `subagent_type` `spike:echo`
- exit code 0

If this fails, try `--permission-mode acceptEdits` or `bypassPermissions`, and record which one works.

- [ ] **Step 4: Fill in the fallback if needed**

If plugin-agent dispatch fails, record the fallback in `spike-notes.md`: the skill passes the agent file's body as the prompt to a `general-purpose` sub-agent. Tasks 9 and 10 then follow the fallback.

- [ ] **Step 5: Write up, clean up, commit**

Write `spike-notes.md` with the five findings above and one sample of each event type. Delete the scratch plugin. Commit: `docs: spike findings`.

### Task 1: PRD first draft (Jasper reviews before the build)

**Files:**
- Create: `docs/PRD.md`

- [ ] **Step 1: Draft `docs/PRD.md`, 1–2 pages, condensed from the spec**

Sections, in the order the assignment requires:
- **Problem and who it's for:** §1
- **Inputs and outputs:** the columns, the goals.md format, and the shape of brief.json from Task 6's schema
- **Architecture decisions and reasoning:**
  - single agent vs sub-agents
  - model choice
  - packaging (plugin + desktop app + local page)
  - structured output design
  - why not a cloud web app (§4 row D)
- **Data Sourcing Strategy:** §7
- **Failure modes:** §6, as a table
- **Success criteria:** §8

Write it in Jasper's voice: plain, no filler.

- [ ] **Step 2: Jasper reviews it**

Apply his edits. Commit: `docs: PRD draft`.

### Task 2: Spreadsheet loader (`nf_core/roster.py`, `nf_core/issues.py`)

**Files:**
- Create: `pyproject.toml`
  - test config only: `[tool.uv] package = false`
  - dev group: `pytest`, `openpyxl`, `reportlab`
  - `[tool.pytest.ini_options] pythonpath = ["plugins/network-focus/scripts", "plugins/network-focus/app"]`
- Create: `plugins/network-focus/scripts/nf_core/__init__.py`, `issues.py`, `roster.py`
- Create: `sample-data/network_roster_terragrid.xlsx`, copied from `/tmp/claude-0/-home-user/6e225b03-d3ed-52a2-887f-f0240a68a413/scratchpad/roster/x/network_roster_terragrid.xlsx`. If the scratchpad has been cleared, re-download it from the assignment's Google Drive link and unzip it.
- Test: `tests/unit/conftest.py`, `tests/unit/test_roster.py`

**Interfaces:**
- Produces (`issues.py`):
  - `Issue(code: str, severity: Literal["block","warn","info"], message: str, rows: list[int] = [])` with `to_dict() -> dict`
  - `class BlockingError(Exception)` with attribute `.issue: Issue`
- Produces (`roster.py`):
  - `Contact` dataclass with fields `row_id: int`, `name: str`, `role: str`, `company: str`, `how_known: str`, `days_since_contact: int | None`, `channel: str`, `summary: str`, `strength: int | None`, `tags: list[str]`, `notes: str`
  - `Contact.text() -> str`: role, company, how_known, summary, tags and notes joined with `" | "`. Evidence quotes must come from this text.
  - `Contact.to_dict() -> dict`
  - `REQUIRED_COLUMNS: dict[str, str]`, mapping field name to display header
  - `read_roster(path: Path) -> tuple[list[Contact], list[Issue]]`. Raises `BlockingError` with one of `UNSUPPORTED_FILE`, `FILE_UNREADABLE`, `MISSING_COLUMNS`, `FILE_EMPTY`.
- Produces (`conftest.py`):
  - fixture `sample_xlsx -> Path`
  - fixture `make_roster(tmp_path)`, a factory `(rows: list[dict], fmt="xlsx"|"csv", headers: list[str] | None = None, title_row: bool = False) -> Path`

- [ ] **Step 1: Write the failing tests**

```python
def test_reads_sample_xlsx(sample_xlsx):
    contacts, issues = read_roster(sample_xlsx)
    assert len(contacts) == 25 and issues == []
    m = contacts[0]
    assert (m.row_id, m.name, m.days_since_contact, m.strength) == (2, "Marcus Wei", 16, 3)
    assert m.tags == ["investor", "series-c", "warm"]
    assert "Asked to see the full pitch." in m.text()

def test_reads_csv_with_bom(make_roster): ...      # utf-8-sig CSV; same values as the xlsx for 2 rows
def test_missing_columns_blocks(make_roster):
    # headers without "Notes", and "Days Since Last Contact" renamed to "Days"
    with pytest.raises(BlockingError) as e: read_roster(path)
    assert e.value.issue.code == "MISSING_COLUMNS"
    assert "Notes" in e.value.issue.message and "Days Since Last Contact" in e.value.issue.message
def test_header_found_below_title_row(make_roster): ...   # title_row=True, headers lower-cased with stray spaces → 2 contacts; first row_id == 3
def test_numbers_as_text_and_floats(make_roster): ...     # "16", 16.0, " 16 " → 16; issues == []
def test_bad_cells_warn(make_roster):
    # days "two weeks" → None; strength 7 → None
    assert [i.code for i in issues] == ["BAD_CELL", "BAD_CELL"]
    assert issues[0].severity == "warn" and issues[0].rows == [2]
def test_blank_rows_skipped_silently(make_roster): ...    # 2 contacts + 3 blank rows → 2 contacts, no issues
def test_empty_file_blocks(make_roster): ...              # header only → FILE_EMPTY
def test_unsupported_extension_blocks(tmp_path): ...      # .numbers → UNSUPPORTED_FILE; message contains "Export it as .xlsx or .csv"
def test_zip_wrapper_unwrapped(tmp_path, sample_xlsx): ...   # roster.zip holding one .xlsx → 25 contacts
def test_drive_style_double_wrap(tmp_path, sample_xlsx): ... # a .xlsx file that is a zip holding one .xlsx → 25 contacts
def test_zip_with_two_files_blocks(tmp_path): ...         # FILE_UNREADABLE; message contains "unzip"
def test_corrupt_file_blocks(tmp_path): ...               # random bytes named .xlsx → FILE_UNREADABLE, names the file
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/unit/test_roster.py -q`. Expected: FAIL with ImportError.

- [ ] **Step 3: Implement `issues.py` and `read_roster`**

- **Header detection:** scan the first 5 rows for a row containing a `name` header. Normalize headers to lowercase, drop `(...)`, and collapse whitespace and punctuation.
- **xlsx:** `openpyxl.load_workbook(read_only=True, data_only=True)` on the first sheet.
- **csv:** `encoding="utf-8-sig"`.
- **Zip handling:** detect a wrapper with `zipfile.is_zipfile`, check that `[Content_Types].xml` is missing, and require exactly one `.xlsx` or `.csv` member. Extract it to a temp dir.
- **Tags:** split on commas and strip.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/unit/test_roster.py -q`. Expected: all pass.

- [ ] **Step 5: Commit**

`feat: spreadsheet loader with failure handling`

### Task 3: Goals parser and template (`nf_core/goals.py`, `templates/goals.md`)

**Files:**
- Create: `plugins/network-focus/scripts/nf_core/goals.py`
- Create: `plugins/network-focus/templates/goals.md`
- Test: `tests/unit/test_goals.py`

**Interfaces:**
- Consumes: `Issue`, `BlockingError`
- Produces:
  - `OrgRef(name: str, aliases: list[str])` with `terms() -> list[str]`
  - `Goal(id: int, title: str, text: str, key_orgs: list[OrgRef], no_contacts_yet: list[OrgRef])` with `to_dict()`
  - `parse_goals(text: str) -> list[Goal]`. Raises `BlockingError("GOALS_MALFORMED")`.

- [ ] **Step 1: Write `templates/goals.md` with exactly this content**

```markdown
# The CEO's goals this quarter
# Edit this file when goals change. Keep the "## Goal N: ..." lines and the labels before each colon.

## Goal 1: Raise Series C
Deadline: end of Q3
Target: $40M at a $200M valuation
Where she is: warm intros to Sequoia, a16z and Greylock, but no real process run yet
What good looks like: more investor relationships, plus signals that strengthen the pitch (advisor commitments, key hires)
Key organizations: Sequoia, a16z (Andreessen Horowitz), Greylock
No contacts yet at:

## Goal 2: Hire a CTO
Deadline: this quarter
Where she is: de facto technical leader for 4 years; met two strong candidates, neither the right fit
What good looks like: more candidates who have scaled a 50-person engineering team to 200+, and stronger introductions to them
Key organizations:
No contacts yet at:

## Goal 3: Build relationships in AI safety
Deadline: this quarter
Where she is: attended one EA Global; one casual relationship with a researcher at Anthropic
What good looks like: being part of the AI safety conversation, not just following it — real relationships at MIRI, ARC and academic AI safety groups
Key organizations: Anthropic, MIRI, ARC (Alignment Research Center)
No contacts yet at: MIRI, ARC (Alignment Research Center), academic AI safety groups (academic)
```

- [ ] **Step 2: Write the failing tests**

```python
def test_parses_template(template_text):
    g = parse_goals(template_text)
    assert [x.title for x in g] == ["Raise Series C", "Hire a CTO", "Build relationships in AI safety"]
    assert [o.name for o in g[0].key_orgs] == ["Sequoia", "a16z", "Greylock"]
    assert g[0].key_orgs[1].aliases == ["Andreessen Horowitz"]
    assert [o.name for o in g[2].no_contacts_yet] == ["MIRI", "ARC", "academic AI safety groups"]
    assert g[2].no_contacts_yet[2].aliases == ["academic"]
    assert g[1].key_orgs == [] and "Deadline: this quarter" in g[1].text
def test_no_goals_blocks(): ...          # "hello" → GOALS_MALFORMED; message contains "## Goal 1:"
def test_more_than_five_goals_blocks(): ...  # message contains "5 goals or fewer"
def test_header_without_title_names_line(): ...  # "## Goal 2:" with no title → GOALS_MALFORMED; message contains "line 9"
def test_labels_case_insensitive(): ...  # "key ORGANIZATIONS: X" parses
def test_comment_lines_ignored(): ...    # lines starting with "# " outside goals don't break parsing
```

- [ ] **Step 3: Run the tests and confirm they fail**

- [ ] **Step 4: Implement `parse_goals`**

Split on the regex `^##\s*Goal\s+(\d+)\s*:\s*(.+)$` (multiline). Split org lists on commas that sit outside parentheses. Aliases come from the text inside `(...)`, split on commas.

- [ ] **Step 5: Run the tests and confirm they pass, then commit**

`feat: goals.md parser and TerraGrid template`

### Task 4: Data-quality checks (`nf_core/checks.py`)

**Files:**
- Create: `plugins/network-focus/scripts/nf_core/checks.py`
- Test: `tests/unit/test_checks.py`

**Interfaces:**
- Consumes: `Contact`, `Goal`, `OrgRef`, `Issue`
- Produces:
  - constants: `DORMANT_DAYS = 60`, `NEAR_DORMANT_DAYS = 53`, `THIN_MAX_STRENGTH = 1`, `THIN_MIN_WORDS = 10`
  - `flags_for(c: Contact) -> dict[str, bool]` with keys `dormant`, `near_dormant`, `thin`
  - `org_matches(org: OrgRef, c: Contact) -> bool`. A term matches when all of its normalized word tokens appear in the contact's company tokens plus tag tokens, with tags split on `-` and spaces.
  - `run_checks(contacts: list[Contact], goals: list[Goal]) -> list[Issue]`, using the codes `GOAL_ORG_MISSING` (warn), `GOAL_CONTRADICTION` (warn), `AMBIGUOUS_REFERENCE` (warn), `DUPLICATE_NAME` (warn), `NAME_COLLISION` (info), `THIN_CONTEXT` (info), `NEAR_DORMANT` (info)

- [ ] **Step 1: Write the failing tests (sample roster + template goals)**

```python
def test_flags(sample):            # name → flags
    assert sample["Reid Hoffman"]["dormant"] and not sample["Lin Wang"]["dormant"]
    assert sample["Lin Wang"]["near_dormant"]
    assert sample["Anjali Sharma"]["thin"] and sample["Jensen Huang"]["thin"] and not sample["Marcus Wei"]["thin"]
def test_org_matching(contacts, goals):
    # ARC → Paul Christiano (ARC Evals); Sequoia → Marcus Wei; "academic" → Yifan Zhou (tag); a16z → nobody
def test_missing_key_org_warns(issues):
    miss = [i for i in issues if i.code == "GOAL_ORG_MISSING"]
    assert len(miss) == 1 and "a16z" in miss[0].message      # MIRI is listed under "No contacts yet", so it's expected and not warned
def test_contradiction_warns(issues):
    msgs = " ".join(i.message for i in issues if i.code == "GOAL_CONTRADICTION")
    assert "Paul Christiano" in msgs and "ARC" in msgs and "Yifan Zhou" in msgs
def test_ambiguous_reference(issues):
    a = [i for i in issues if i.code == "AMBIGUOUS_REFERENCE"]
    assert len(a) == 1 and a[0].rows == [2]
    assert all(s in a[0].message for s in ["Patrick at Greylock", "Patrick Collison", "Reid Hoffman"])
def test_no_false_positive_on_capitalized_words(make_contacts): ...  # "Coffee at AI Engineer Summit", "Met at Lattice conference" → no AMBIGUOUS_REFERENCE
def test_name_collisions_info(issues): ...   # one info naming David Liu + David Park; one naming Jensen Huang + Jensen Carlsson
def test_duplicate_full_name_warns(make_contacts): ...  # two "Diana Chen" rows → DUPLICATE_NAME warn, rows [3, 27]
def test_near_dormant_and_thin_info(issues): ...       # NEAR_DORMANT names Lin Wang; THIN_CONTEXT rows include 10 and 11
```

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement**

Ambiguous references: match the regex `\b([A-Z][a-z]+)\s+(?:at|from)\s+([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)*)` over notes and summary. Only consider captures whose first word is a roster first name. Warn when no contact with that first name matches the captured org through `org_matches`. Name the actual same-first-name contacts, and the contacts who do match the org.

Use these message templates (operator copy):
- GOAL_ORG_MISSING: `Goal {id} mentions {org}, but nobody at {org} is in the spreadsheet. Who is the contact there? Add them so the brief can include them.`
- GOAL_CONTRADICTION: `goals.md says there are no contacts yet at {org}, but the spreadsheet has {name} ({company}). Update goals.md or check row {row}.`
- AMBIGUOUS_REFERENCE: `{owner}'s notes mention "{phrase}", but the only {first} in the spreadsheet is {matches}. The {org} contact is {org_contacts}. Check who made the intro.`

- [ ] **Step 4: Run the tests and confirm they pass, then commit**

`feat: data-quality checks for goals vs roster`

### Task 5: Operator folder, history, and `load_roster.py`

**Files:**
- Create: `plugins/network-focus/scripts/nf_core/workspace.py`
- Create: `plugins/network-focus/scripts/load_roster.py`, with a PEP 723 header requiring `openpyxl`
- Test: `tests/unit/test_workspace.py`, `tests/unit/test_load_roster_cli.py`

**Interfaces:**
- Consumes: `read_roster`, `parse_goals`, `run_checks`, `flags_for`
- Produces (`workspace.py`):
  - `nf_home() -> Path`: env `NF_HOME`, else `~/Documents/Network Focus`
  - `Workspace(root)` with properties `goals_path`, `inbox`, `briefs`, `work`, `history_path`
  - `ensure_workspace(ws, template: Path) -> bool`: returns True when it created the folder just now
  - `pick_roster(ws, explicit: Path | None) -> tuple[Path, list[Issue]]`. Raises `NO_SPREADSHEET`.
  - `fingerprint(path) -> str`: sha256 hex
  - `staleness_issues(path, sha, history: list[dict], today: date) -> list[Issue]`, with codes `STALE_FILE` and `REUSED_FILE` (both warn)
  - `load_history(ws) -> list[dict]`
  - `record_run(ws, entry: {"sha256", "file_name", "run_date", "brief"})`
  - `week_of(today: date) -> date`: Mon–Fri gives that week's Monday, Sat/Sun gives the next Monday
- Produces (CLI): `load_roster.py [--roster PATH] [--today YYYY-MM-DD]`
  - writes `work/roster.json`:
    - `source`: `path`, `file_name`, `sha256`, `as_of`, `week_of`
    - `goals`: `[Goal.to_dict()]`
    - `contacts`: `[Contact.to_dict() + {"flags": {...}}]`
  - writes `work/warnings.json` as `{"warnings": [Issue.to_dict()]}`
  - prints one JSON line to stdout: `{"status": "ok"|"blocked"|"setup", "message": str, "work_dir": str, "contacts": int, "warnings": int}`
  - exits 0 when OK, 2 when blocked, 3 on first-run setup

- [ ] **Step 1: Write the failing tests**

```python
def test_week_of():
    assert week_of(date(2026,11,23)) == date(2026,11,23)
    assert week_of(date(2026,11,25)) == date(2026,11,23)
    assert week_of(date(2026,11,21)) == date(2026,11,23)
def test_first_run_creates_folder(tmp_path):       # CLI → exit 3; goals.md, inbox/, briefs/ exist; message contains "inbox"
def test_picks_newest_ignoring_lock_files(tmp_path): ...  # ~$a.xlsx and .DS_Store newer than real.xlsx → real.xlsx chosen
def test_multiple_files_info(tmp_path): ...        # 2 spreadsheets → newest chosen + info naming it
def test_no_spreadsheet_blocks(tmp_path): ...      # exit 2; message contains the inbox path
def test_explicit_path_used(tmp_path, sample_xlsx): ...
def test_stale_file_warns(tmp_path, sample_xlsx): ...     # mtime 10 days ago → STALE_FILE; message contains the as_of date
def test_reused_file_warns(tmp_path, sample_xlsx):
    # history: same sha, run_date one week earlier → REUSED_FILE
    # history: same sha, run_date earlier the same week → no REUSED_FILE
def test_outputs_written(tmp_path, sample_xlsx):
    r = json.loads((work / "roster.json").read_text())
    assert len(r["contacts"]) == 25 and len(r["goals"]) == 3 and len(r["source"]["sha256"]) == 64
    assert r["contacts"][4]["flags"]["dormant"] is True          # Reid Hoffman
    codes = {w["code"] for w in json.loads((work / "warnings.json").read_text())["warnings"]}
    assert {"GOAL_ORG_MISSING", "GOAL_CONTRADICTION", "AMBIGUOUS_REFERENCE"} <= codes
def test_blocking_error_message_plain(tmp_path): ...  # missing column → exit 2; stdout message has no "Traceback"
```

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement `workspace.py` and the CLI**

The CLI catches `BlockingError`, prints `status: blocked` with its message, and exits 2. Any unexpected exception prints `Something unexpected went wrong reading {file}. Run /network-focus:check for details.` and exits 2. The traceback goes to `work/error.log`.

- [ ] **Step 4: Run the tests and confirm they pass, then commit**

`feat: operator folder, stale-data detection, load_roster CLI`

### Task 6: Schemas and brief validator (`nf_core/shape.py`, `nf_core/brief_checks.py`, `validate_brief.py`)

**Files:**
- Create: `plugins/network-focus/schemas/scout-output.json`, `brief.json`, `warnings.json` (JSON Schema subset)
- Create: `plugins/network-focus/scripts/nf_core/shape.py`, `brief_checks.py`
- Create: `plugins/network-focus/scripts/validate_brief.py`
- Test: `tests/unit/test_brief_checks.py`, `tests/unit/fixtures/valid_brief.json`

**Interfaces:**
- Consumes: `roster.json` as written by Task 5
- Produces:
  - `check_shape(value, schema: dict, where: str) -> list[Problem]`. It supports only `type`, `required`, `properties`, `items`, `enum`, `minItems`, `maxItems`, `minLength`. The schema files are the single source of truth, read by both the code and the agents.
  - `Problem(code: str, where: str, message: str)`
  - `validate_brief(brief: dict, roster: dict) -> list[Problem]`
  - `validate_scout(scout: dict, roster: dict) -> list[Problem]`
  - `cited_rows(brief: dict, roster: dict) -> dict`, shaped `{"contacts": [only the cited rows]}`
- Produces (CLI): `validate_brief.py brief|scout <file> --roster <roster.json>`, and `validate_brief.py cited-rows <brief.json> --roster <roster.json> --out <file>`. It prints `{"ok": bool, "problems": [...]}` and exits 0 or 1.
- Schema `brief.json`:
  - `week_of: str`
  - `focus[3..5]` of `{row_id: int, name: str, goals: [int] (min 1), why: str, move: str, risk: str, evidence: [str] (min 1), confidence: "high"|"medium"|"low"}`
  - `dormant[0..3]` of `{row_id, name, days_since_contact: int, why, move, evidence}`
  - `coming_up[0..2]` of `{row_id, name, note}`
  - `goal_gaps[]` of `{goal_id: int, note: str}`
  - `extra_checks[0..3]` of `str`
- Schema `scout-output.json`:
  - `goal_id: int`
  - `candidates[0..6]` of `{row_id, name, fit, move, risk, evidence[], confidence, timing: "now"|"later"}`
  - `concerns[]` of `str`

- [ ] **Step 1: Write `fixtures/valid_brief.json` from the sample roster**
  - **focus:** Diana Chen (row 3, goal 2), Marcus Wei (2, goal 1), Reid Hoffman (6, goal 1), Paul Christiano (4, goal 3), Sarah Guo (5, goals 1 and 3)
  - **dormant:** Priya Mehta (16, 128 days), Brian Armstrong (19, 67 days)
  - **coming_up:** Maya Patel (25)
  - every evidence string is copied word-for-word from the row

- [ ] **Step 2: Write the failing tests**

```python
def test_valid_brief_passes(brief, roster): assert validate_brief(brief, roster) == []
def test_focus_count(brief, roster): ...           # 2 picks → FOCUS_COUNT; 6 picks → FOCUS_COUNT
def test_unknown_row_and_name_mismatch(...): ...   # row_id 99 → UNKNOWN_ROW; row 3 named "Diana Chan" → NAME_MISMATCH
def test_quote_must_be_verbatim(...):
    # "offered to introduce 5 candidates" → QUOTE_NOT_FOUND
    # changed case, curly quotes or doubled spaces → still passes
def test_short_quote_rejected(...): ...            # "investor" → QUOTE_TOO_SHORT (fewer than 3 words)
def test_dormant_rules(...): ...                   # Lin Wang (59) → NOT_DORMANT; Priya with 100 days → DAYS_MISMATCH
def test_duplicate_person(...): ...                # Reid in focus and dormant → DUPLICATE_PERSON
def test_thin_needs_low_confidence(...): ...       # Anjali with confidence "medium" → THIN_NOT_LOW
def test_days_in_text_checked(...): ...            # Reid why "quiet for 90 days" → NUMBER_MISMATCH
def test_vague_move(...): ...                      # move "Reconnect." → VAGUE_MOVE
def test_goal_coverage(...):
    # drop Paul and Sarah → GOAL_NOT_COVERED (goal 3)
    # add a goal_gaps entry for goal 3 → passes
def test_dormant_count_relaxed_when_few_eligible(...): ...  # roster with 1 eligible dormant + 1 dormant entry → passes
def test_scout_validation(...): ...                # missing "candidates" → SCHEMA; a valid scout passes
def test_cited_rows_only_cited(...): ...           # 8 cited rows returned, never the 25
def test_cli_exit_codes(tmp_path, ...): ...        # valid → 0, invalid → 1, both print JSON
```

- [ ] **Step 3: Run the tests and confirm they fail**

- [ ] **Step 4: Implement**

- **Quote matching:** NFKC-normalize, map curly quotes to straight, collapse whitespace, compare case-insensitively against `Contact.text()`.
- **VAGUE_MOVE:** the move has fewer than 8 words, or it doesn't contain any of `email, call, coffee, meeting, intro, introduction, message, note, lunch, dinner, reply, send, ask`.
- **NUMBER_MISMATCH:** every `(\d+)\s+days?` in `focus[].why` and `dormant[].why` must equal that row's days.
- **Goal coverage:** every goal id in the roster appears in some `focus[].goals` or in `goal_gaps`.

- [ ] **Step 5: Run the tests and confirm they pass, then commit**

`feat: brief schema and grounding validator`

### Task 7: Renderer (`nf_core/render.py`, `render_pdf.py`)

**Files:**
- Create: `plugins/network-focus/scripts/nf_core/render.py`
- Create: `plugins/network-focus/scripts/render_pdf.py`, with a PEP 723 header requiring `reportlab` and `openpyxl`
- Test: `tests/unit/test_render.py`

**Interfaces:**
- Consumes: `validate_brief`, `Workspace`, `record_run`, plus `brief.json`, `roster.json` and `warnings.json`
- Produces:
  - `pdf_safe(text: str) -> str`: the output is always cp1252-encodable. Map `→`→`->`, `≥`→`>=`, `✓`→`v`, then NFKD, then `?`.
  - `render_markdown(brief, roster, warnings) -> str`
  - `render_pdf(brief, roster, warnings, out: Path) -> int`: returns the page count after trying font sizes 10, 9.5, 9, 8.5 and 8
- Produces (CLI): `render_pdf.py --work DIR`
  - validates first, and exits 1 with the problems if invalid
  - writes `briefs/{week_of}-network-focus.pdf` and `.md`, then calls `record_run`
  - prints `{"ok": true, "pdf": path, "md": path}`
  - exits 4 if the brief is still more than one page at 8pt
- **Layout, in order** (matches §5.7):
  1. header: `NETWORK FOCUS · Week of {Mon D, YYYY}` and `Data as of: {as_of} (file date) · {file_name}`
  2. a banner with any STALE_FILE or REUSED_FILE messages
  3. `THIS WEEK`, with `Why / Move / At risk` per pick
  4. `DORMANT BUT HIGH-LEVERAGE`
  5. `COMING UP` (if any)
  6. `CHECK BEFORE THE MEETING`: **every warn-level warning, taken from warnings.json by the code**, then `extra_checks`
  7. the `.md` only adds an `Also noted` list of the info-level items

- [ ] **Step 1: Write the failing tests**

```python
def test_markdown_sections(...):
    md = render_markdown(brief, roster, warnings)
    for h in ["THIS WEEK", "DORMANT BUT HIGH-LEVERAGE", "COMING UP", "CHECK BEFORE THE MEETING"]: assert h in md
    for w in warn_level: assert w["message"] in md
def test_stale_banner_on_top(...): ...      # the STALE_FILE message index < index of "THIS WEEK"
def test_pdf_one_page(tmp_path, ...): ...   # render_pdf returns 1; file starts with b"%PDF"
def test_overlong_brief_exit_4(...): ...    # 200-word whys → CLI exit 4; stdout mentions "too long"
def test_refuses_invalid_brief(...): ...    # FOCUS_COUNT problem → exit 1; no PDF in briefs/
def test_pdf_safe(): assert pdf_safe("→ ≥ ✓ 李伟 Bouchard").encode("cp1252")
def test_records_history_and_names(...): ...  # briefs/2026-11-23-network-focus.pdf/.md exist; history has 1 entry with sha256
```

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement**

Use `reportlab.platypus.SimpleDocTemplate` on Letter with 0.6in margins. Count pages with an `onPage` callback. Use the palette from Jasper's design profile: charcoal text, navy headings, a beige banner.

- [ ] **Step 4: Run the tests and confirm they pass, then commit**

`feat: one-page PDF and Markdown renderer`

### Task 8: Setup diagnostics (`check_setup.py`)

**Files:**
- Create: `plugins/network-focus/scripts/check_setup.py`, with a PEP 723 header requiring `openpyxl`
- Test: `tests/unit/test_check_setup.py`

**Interfaces:**
- Consumes: `Workspace`, `read_roster`, `parse_goals`, `pick_roster`
- Produces:
  - `CheckResult(name: str, status: Literal["ok","fail","info"], detail: str, fix: str)`
  - `setup_checks(home: Path, port: int = 8765) -> list[CheckResult]`
  - the CLI prints one line per result: `✅ {name}: {detail}`, `❌ {name}: {detail}\n   Fix: {fix}`, or `ℹ️ {name}: {detail}`. It exits 0, or 1 if anything failed.
- **Checks, in order:**
  1. Network Focus folder
  2. goals.md (how many goals)
  3. Spreadsheet in inbox (name, how many days old)
  4. Spreadsheet columns
  5. Briefs folder writable
  6. Claude command-line tool (info; only needed for the local page)
  7. Local page running (info; GET `http://127.0.0.1:{port}/health` with a 1s timeout)

- [ ] **Step 1: Write the failing tests**
  - healthy workspace: all `ok` apart from the info items
  - missing goals.md: `fail`, with a fix that mentions `/network-focus:brief` recreating it
  - spreadsheet missing the Notes column: `fail`, with a detail that mentions `Notes`
  - local page down: `info`, not `fail`
  - CLI output lines start with ✅ ❌ or ℹ️

- [ ] **Step 2: Run the tests and confirm they fail. Implement. Run them and confirm they pass.**

- [ ] **Step 3: Commit**

`feat: plain-English setup check`

### Task 9: Plugin packaging, agents and skills (`brief`, `check`)

**Files:**
- Create: `.claude-plugin/marketplace.json`:
  ```json
  {"name": "network-focus", "owner": {"name": "Jasper Osita"},
   "plugins": [{"name": "network-focus", "source": "./plugins/network-focus",
                "description": "Weekly Network Focus brief for the CEO"}]}
  ```
- Create: `plugins/network-focus/.claude-plugin/plugin.json`: `{"name": "network-focus", "version": "0.1.0", "description": "...", "author": {"name": "Jasper Osita"}}`
- Create: `plugins/network-focus/agents/goal-scout.md`, `agents/fact-checker.md`
- Create: `plugins/network-focus/skills/brief/SKILL.md`, `skills/check/SKILL.md`

**Interfaces:**
- Consumes:
  - from Task 0: `AGENT_TOOL`, `subagent_type` strings, `HEADLESS_FLAGS`
  - CLIs: `load_roster.py`, `validate_brief.py`, `render_pdf.py`, `check_setup.py`
  - schemas
- Produces:
  - the commands `/network-focus:brief [path]` and `/network-focus:check`
  - artifacts in `.work/`: `scout-{goal_id}.json`, `brief.json`, `cited-rows.json`, `factcheck.json`

- [ ] **Step 1: `agents/goal-scout.md`**

Frontmatter: `name: goal-scout`, `description` (one goal → ranked candidates JSON; used by Network Focus), `tools: Read, Write`, `model: sonnet`.

Body:
- **Inputs:** goal id, and the paths to `roster.json`, `warnings.json`, `schemas/scout-output.json` and the output file.
- **Review every contact** against this one goal, using the goal's "What good looks like."
- **Prefer** open loops, timing windows, strong-but-dormant relationships, and people who are bridges to the goal.
- **Skip** contacts with no link to the goal.
- **Mark** `timing: "later"` when the notes ask her to wait.
- **Evidence** quotes are copied word-for-word from the row (3+ words).
- **Add to `concerns`** any person mentioned who isn't in the roster, and any row that contradicts itself (for example, the channel says email but the summary says LinkedIn).
- **Output:** write JSON that matches the schema, then reply only `done {path}`.

- [ ] **Step 2: `agents/fact-checker.md`**

Frontmatter: `name: fact-checker`, `tools: Read, Write`, `model: haiku`.

Body:
- Read **only** `brief.json` and `cited-rows.json`.
- For every `why`, `risk` and `note`, and the factual premise of every `move`: decide whether the cited row supports it.
- Write `{"unsupported": [{"where": "focus[1].why", "claim": str, "reason": str}]}`, then reply `done {n} unsupported`.

- [ ] **Step 3: `skills/brief/SKILL.md`**

Frontmatter:
- `name: brief`
- `description`: make this week's Network Focus brief; triggers on "weekly brief", "network brief", "who should she reach out to this week"
- `argument-hint: [path to spreadsheet]`
- `allowed-tools: Read, Write, Bash(uv run *), Bash(/opt/homebrew/bin/uv run *), Bash(~/.local/bin/uv run *), {AGENT_TOOL}`

Body, as numbered steps that use `${CLAUDE_PLUGIN_ROOT}` paths:
1. Run `load_roster.py` (`--roster $ARGUMENTS` if given). If the exit code is 2 or 3, give her the `message` in plain words and stop. If `uv` isn't found, try `/opt/homebrew/bin/uv` and then `~/.local/bin/uv`. If it's still missing, tell her to run `/network-focus:check`.
2. Launch one `goal-scout` per goal **in a single message** (parallel). Check each output with `validate_brief.py scout`. Retry a failed scout once. If it fails again, add `"Goal {n} couldn't be analyzed this week"` to `extra_checks`.
3. Merge the scouts' results using the selection rules **copied word-for-word from spec §5.6**. Write `.work/brief.json` per `schemas/brief.json`, with `week_of` taken from `roster.json` `source.week_of`.
4. Run `validate_brief.py brief`. On problems, fix and re-run, at most 2 times. If it still fails, tell her in plain English that the brief couldn't be made safely, list the problems, and stop.
5. Run `validate_brief.py cited-rows`, then launch `fact-checker`. Rewrite or remove each unsupported claim.
6. Validate again.
7. Run `render_pdf.py --work`. On exit 4, shorten the why and move text and retry once.
8. Final chat message, at most 8 lines with no JSON:
   ```
   Brief ready: <pdf path>
   This week: <names, one line each, with the move>
   <N> things to check with the CEO (they're in the brief)
   ```

- [ ] **Step 4: `skills/check/SKILL.md`**

Frontmatter: `name: check`, `allowed-tools: Bash(uv run *)` plus the two full-path variants.

Body: run `check_setup.py` and relay the output as-is. If uv is missing entirely, give the one-line install fix and point to the handoff doc.

- [ ] **Step 5: Validate the packaging**

```bash
claude plugin validate plugins/network-focus && claude plugin validate .
```

Expected: both pass.

- [ ] **Step 6: Smoke test on the real roster (headless)**

```bash
export NF_HOME=$(mktemp -d); mkdir -p "$NF_HOME/inbox"; cp plugins/network-focus/templates/goals.md "$NF_HOME/"; cp sample-data/network_roster_terragrid.xlsx "$NF_HOME/inbox/"
claude -p "/network-focus:brief" --plugin-dir plugins/network-focus {HEADLESS_FLAGS}
```

Expected:
- exit 0
- `$NF_HOME/briefs/*-network-focus.pdf` exists
- `validate_brief.py brief` on `.work/brief.json` gives `ok: true`
- the chat reply contains no JSON

Record the run time.

- [ ] **Step 7: Commit**

`feat: network-focus plugin (skills, agents, marketplace)`

### Task 10: Test set and grader (build-time)

**Files:**
- Create: `tests/evals/make_cases.py`: builds the 6 cases from the sample, deterministically
- Create: `tests/evals/cases/<name>/{roster.xlsx|roster.csv, expected.json, setup.json}`
- Create: `tests/evals/run_evals.py`, `tests/evals/rubric.md`
- Create: `.claude/agents/eval-grader.md`: `tools: Read`, `model: opus`. Scores 1–5 on grounding, move specificity, goal coverage, prioritization and plain language, and returns JSON.
- Output: `tests/evals/results/{date}.md`

**Interfaces:**
- `expected.json`: `{"must_include": [names], "must_exclude": [names], "must_warn": [codes], "must_not_warn": [codes], "must_block": code | null}`
- `setup.json`: `{"mtime_days_ago": int, "history_same_sha_days_ago": int | null}`
- `run_evals.py [--case NAME] [--grade]`. For each case it:
  - creates a temp `NF_HOME`, copies in the template goals and the roster, and applies the setup
  - runs `claude -p "/network-focus:brief" --plugin-dir plugins/network-focus {HEADLESS_FLAGS}`
  - checks the expectations against `.work/*.json` and `briefs/`
  - writes the results table
  - exits 1 if any case fails

| Case | Roster | Expected |
|---|---|---|
| `real-roster` | sample xlsx, fresh mtime | include Diana Chen, Marcus Wei. Exclude James Park, Jensen Carlsson, Jensen Huang, Demis Hassabis, Aaron Goldsmith. Warn GOAL_ORG_MISSING, AMBIGUOUS_REFERENCE, GOAL_CONTRADICTION |
| `missing-columns` | no Notes column, "Days" header | block MISSING_COLUMNS, no PDF |
| `stale-reused` | sample, mtime 21 days ago, history with the same sha 7 days ago | warn STALE_FILE, REUSED_FILE, PDF produced |
| `duplicate-diana` | sample + a second "Diana Chen" (Notion, 45 days) | warn DUPLICATE_NAME, validator passes |
| `thin-target` | sample + "Alex Rivera, Partner, a16z, event, 12, event, Met briefly., 1, investor," | must_not_warn GOAL_ORG_MISSING. If Alex is picked, confidence is low (validator) |
| `csv-version` | the real roster as a utf-8-sig CSV | same as `real-roster` |

Spec correction: §8 expects the real roster to raise warning 6 (stale data). Whether it does depends on the file's date, so staleness gets its own case (`stale-reused`).

- [ ] **Step 1: Write `make_cases.py` and generate the cases**

Write a unit test `tests/unit/test_make_cases.py` asserting that all 6 case dirs exist with valid `expected.json`. Run it and confirm it passes. Commit.

- [ ] **Step 2: Write `run_evals.py` and the grader**

Run `uv run python tests/evals/run_evals.py --case missing-columns`. Expected: PASS (block path, quick).

- [ ] **Step 3: Run the full set and tune**

Run `uv run python tests/evals/run_evals.py --grade`. Expected: all 6 PASS, grader ≥4 on grounding and specificity for every brief.

On failure, adjust the SKILL.md rules or the agent prompts, never the expectations, and re-run. Record the before and after in the results file.

- [ ] **Step 4: Review and commit**

Run `/code-review` on the branch and fix the findings. Commit `test: eval suite and grader` with the results file.

### Task 11: Local web page (cut line: drop it if it isn't working by the end of day 2)

**Files:**
- Create: `plugins/network-focus/app/progress.py`, `app/server.py`, `app/index.html`
- Test: `tests/unit/test_progress.py`, `tests/unit/test_server.py`, `tests/unit/fake_claude.py`

**Interfaces:**
- Consumes:
  - from Task 0: the stream-json event shapes
  - `setup_checks` (copied into the app dir by Task 12)
  - the `briefs/` folder
- Produces (`progress.py`):
  - `progress_from_event(event: dict) -> str | None`, which maps events to these steps:
    - `load_roster` → "Checking the data"
    - a goal-scout dispatch → "Reviewing goal: {description}"
    - `fact-checker` → "Fact-checking the picks"
    - `render_pdf` → "Making the PDF"
    - anything else → None
  - `failure_message(result_text: str, stderr: str) -> str`. Login or authentication text becomes "Claude is signed out. Open the Claude app, sign in, then try again." Anything else becomes the skill's own message.
- Produces (`server.py`):
  - `AppConfig(port: int, token: str, nf_home: Path, claude_path: str, claude_args: list[str], uv_path: str, scripts_dir: Path)`, loaded from `config.json`
  - `make_server(cfg) -> ThreadingHTTPServer`
- **Routes:**
  - `GET /health`: no token required
  - `GET /?t=TOKEN`: sets an `HttpOnly; SameSite=Strict` cookie
  - `GET /api/status`: `{"inbox": [{name, modified}], "briefs": [{name, url}], "running": bool}`
  - `POST /api/upload`: raw body, header `X-Filename`. Only `.xlsx` or `.csv`, up to 10 MB, saved to `inbox/`.
  - `POST /api/run`: `{"file"?}` → `{"run_id"}`, or 409 if a run is already going
  - `GET /api/run/{id}/events`: SSE, sending `{"step"}` lines, then `{"status": "done", "pdf_url"}` or `{"status": "failed", "message"}`
  - `POST /api/check`: `{"results": [...]}`
  - `GET /briefs/{name}`: basename only, and the file must exist in `briefs/`
- **Security:**
  - every route except `/health` requires the Host header to be `127.0.0.1:{port}` or `localhost:{port}`
  - all `/api/*` routes need the token cookie
  - POST requests need an Origin header matching the same host
- **Page:** one file in plain HTML/JS. It shows the newest spreadsheet (with a drop zone), a Generate button, live steps, an Open PDF button, Check setup, and past briefs. It uses the §5.7 palette, and its buttons and messages are written for her.

- [ ] **Step 1: Write the failing tests**

```python
def test_progress_mapping(): ...       # sample events from spike-notes → the expected step strings; unknown → None
def test_failure_message_signed_out(): ...
def test_rejects_wrong_host(server): ...      # Host: evil.com → 403
def test_api_requires_token(server): ...      # no cookie → 401; with cookie → 200
def test_post_requires_origin(server): ...    # Origin: https://evil.com → 403
def test_upload_rules(server): ...            # .exe → 400; 11 MB → 413; ok.xlsx saved to inbox
def test_path_traversal_blocked(server): ...  # /briefs/../goals.md → 404
def test_run_end_to_end_with_fake_claude(server):
    # fake_claude.py prints canned stream-json and writes briefs/2026-11-23-network-focus.pdf
    # events: "Checking the data", ..., status done with pdf_url
def test_single_run_at_a_time(server): ...    # second POST /api/run while one is running → 409
```

- [ ] **Step 2: Run the tests and confirm they fail. Implement. Run them and confirm they pass.**

The server launches `[claude_path, "-p", "/network-focus:brief <file>", *claude_args]` with `cwd=nf_home` and `env NF_HOME` set, and reads stdout line by line.

- [ ] **Step 3: Check the page by eye**

Run the server locally with fake_claude and screenshot the page with Playwright (deviceScaleFactor 1). Expected: the layout matches the sketch in the chat and the text is readable.

- [ ] **Step 4: Commit**

`feat: local web page for the operator`

### Task 12: `setup-app` skill and installer

**Files:**
- Create: `plugins/network-focus/app/install_app.py` (standard library only)
- Create: `plugins/network-focus/skills/setup-app/SKILL.md`
- Test: `tests/unit/test_install_app.py`

**Interfaces:**
- Consumes: `server.py`, `index.html`, `progress.py`, `scripts/` (check_setup + nf_core)
- Produces:
  - `install(plugin_root: Path, home: Path, port: int = 8765, launch: bool = True) -> dict`, returning `{"url", "app_dir", "plist", "webloc"}`
  - `plist_xml(label: str, uv: str, server: Path, path_env: str, log_dir: Path) -> str`
  - `webloc_xml(url: str) -> str`
  - `find_tool(name: str, extra: list[str]) -> str | None`, searching `shutil.which`, `/opt/homebrew/bin`, `/usr/local/bin` and `~/.local/bin`
- **What it does:**
  - copies the app files and `scripts/` to `{home}/Library/Application Support/Network Focus/`
  - writes `config.json`, keeping any existing token
  - writes `{home}/Library/LaunchAgents/com.networkfocus.app.plist` with `RunAtLoad` and `KeepAlive`, absolute uv/claude paths and a PATH that includes their folders
  - if `launch`, runs `launchctl bootout` (errors ignored) and then `launchctl bootstrap gui/{uid}`
  - writes `{home}/Desktop/Network Focus.webloc`
- **SKILL.md:** `allowed-tools: Bash(uv run *)` plus the full-path variants. It runs the installer, then tells her: "Double-click *Network Focus* on your Desktop."

- [ ] **Step 1: Write the failing tests (`home=tmp_path`, `launch=False`)**
  - files are copied
  - `config.json` holds a 32+ character token, and the same token survives a second install
  - the plist parses with `plistlib` and holds absolute paths
  - the webloc URL contains `127.0.0.1:8765/?t=`
  - a missing `claude` → install still works, and the result says the page needs Claude Code installed

- [ ] **Step 2: Run the tests and confirm they fail. Implement. Run them and confirm they pass.**

- [ ] **Step 3: Commit**

`feat: one-step local page setup`

### Task 13: Deliverable docs and PDFs

**Files:**
- Modify: `docs/PRD.md` (final pass)
- Create: `docs/HANDOFF.md`, `docs/VIDEO-OUTLINE.md`, `tools/make_pdfs.py` (build-time: `markdown` + Playwright print to PDF)
- Create: `.claude/agents/handoff-tester.md`: `tools: Read`. It gets only HANDOFF.md, follows it as a non-technical chief of staff, and lists every step where she'd get stuck.
- Output: `deliverables/PRD.pdf`, `deliverables/Handoff.pdf`, and `deliverables/Brief.pdf`, which is a **copy of the real skill output from Task 9/10, not re-rendered**

- [ ] **Step 1: Finish the PRD**

Fill in the measured run time, the test-set results and the final model choices. Make sure it has the 6 required sections.

- [ ] **Step 2: Write `HANDOFF.md` (1 page, plain language)**

- **Prerequisites:** Mac, Claude app and plan, uv
- **Install:** the plugin through the desktop app, plus `/network-focus:setup-app` if the local page shipped
- **Weekly use**
- **Two use cases with sample input and expected output:**
  - a normal Monday run
  - a spreadsheet with a renamed column, showing the message and the fix
- **When it breaks:** one line each for the 7 failure modes in §6, plus server not running and signed out
- **How to update the plugin**

- [ ] **Step 3: Run the fresh-eyes check**

Run `handoff-tester` against HANDOFF.md and fix every gap it finds.

- [ ] **Step 4: Write `VIDEO-OUTLINE.md`**

Five timed segments, matching the assignment:
1. **PRD → build (1–2 min):** open PRD.md, then show the sub-agent decision and the "code handles facts" decision in the code
2. **Live demo (3–4 min):** the real roster through the local page or the desktop app, then open the PDF
3. **Architecture with code (2–3 min):** SKILL.md, goal-scout.md, validate_brief.py
4. **Failure mode (2–3 min):** live-edit a copy of the roster to rename a column, run, show the block message and the code that produced it. Then show the "Patrick at Greylock" check in `checks.py`.
5. **Limitations (1–2 min):** stale dates from file times, a small data set, no live integrations, macOS only

Write talking points, not a script.

- [ ] **Step 5: Make the PDFs and check page counts**

Run `uv run --with markdown python tools/make_pdfs.py`. Expected: PRD ≤2 pages, Handoff 1 page, and the PDFs exist in `deliverables/`.

- [ ] **Step 6: Commit and push**

Commit `docs: PRD, handoff, video outline, PDFs` and push to the GitHub remote.

### Task 14: Jasper's Mac run-through (manual)

Each step gets an expected result. Record anything that doesn't match in `docs/design/spike-notes.md`, then fix it before recording.

- [ ] In the Claude desktop app: **+ → Add plugins**, add the marketplace (`/plugin marketplace add <user>/network-focus`), then install. Expected: `/network-focus:brief` appears in the `/` menu. (§11 risk 4)
- [ ] Open the `~/Documents/Network Focus` folder and type "make this week's network brief". Expected: the first-run setup message appears. Drop the sample into `inbox/` and run again: the PDF opens. (risks 5 and 6: no `uv not found`, no permission prompts for the scripts)
- [ ] Run `/network-focus:setup-app`, then double-click the Desktop link. Expected: the page loads and Generate produces the PDF using the normal Claude login. (risks 7 and 8)
- [ ] Rehearse once from VIDEO-OUTLINE.md. Record with QuickTime and upload to YouTube (unlisted) or Drive. Submit the 3 PDFs and the link.
