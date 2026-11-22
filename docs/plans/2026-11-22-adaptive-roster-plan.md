# Adaptive Roster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Network Focus reads the roster from a Google Drive folder, notices when it changes, lets someone run a mid-week **Update** that places urgent Series C newcomers under rules enforced in code, and shows one progress ring per goal.

**Architecture:**
- **Code (stdlib + openpyxl through `uv run`)** handles everything factual: finding Drive, the diff, slot rules, re-keying marks.
- **The model** judges only the new or changed people, in a new `/network-focus:update` skill.
- **The page server** (still stdlib only) watches the folder, serves the changes, and runs Update the way it runs Generate.

**Tech Stack:** Python 3.11, pytest, reportlab/openpyxl via `uv run`, vanilla JS in `index.html`, bash/PowerShell installers, GitHub Actions (ubuntu, macos, windows).

**Spec:** `docs/design/2026-11-22-adaptive-roster-design.md`

All paths below are relative to `plugins/network-focus/` unless they start with `tests/`, `docs/`, `install` or `.claude-plugin`.

## Global Constraints

- **Existing behaviour:**
  - Monday Generate (`/network-focus:brief`) keeps working. Its only change is that dormant picks now carry `goals`.
  - Every existing test stays green on all three CI systems.
- **Dependencies:**
  - `app/server.py` and `app/install_app.py` stay standard-library only.
  - `nf_core/drive.py` and `nf_core/workspace.py` must stay stdlib-only, because the installer imports them.
- **Roster files:** only `.xlsx`/`.csv`, ignoring names starting with `~$` or `.`. A folder holding only a `.gsheet` stops with the spec's Google Sheet message.
- **Watching:** check every **120 s**. A file counts only once it's steady (same path, size and mtime as the last check, or last modified ≥ 120 s ago).
- **Identity and fingerprint:**
  - Identity = whitespace-collapsed, casefolded `name` + `"|"` + `company`.
  - Fingerprint = sha256 over role, how_known, channel, summary, strength, sorted tags and notes. **Never days since contact.**
- **Update rules:**
  - The main goal is the goal with the lowest id.
  - Locked: done picks, `focus[0]`, every dormant pick.
  - Empty focus slots (focus max 5) fill before bumps. Bumps go weakest-first.
  - A swap may never leave a previously covered goal with no focus pick.
  - Update runs only on click, under the existing one-run lock.
- **Copy:** use the spec's exact strings where it gives them. Everything else is plain English, with no jargon on screen.
- **Platform:**
  - Explicit `encoding="utf-8"` on all file I/O.
  - No `%-d` in date formats (Windows).
- **Version:** bump the plugin to `0.3.0` so `claude plugin update` delivers it.

## Review Focus

1. **Excel saving, or Drive syncing a half-written file.** The page waits for a steady file and never reads `~$` lock files. → `test_watch_waits_for_steady_file`, `test_watch_ignores_lock_files` (Task 4)
2. **The first week after upgrading,** when the newest snapshot is v1 with no `roster_index`. There must be no false "25 new people"; the line stays hidden until the next Generate. → `test_roster_diff_cli_no_index`, `test_update_prep_cli_blocked_without_index` (Tasks 4, 5)
3. **Drive signed out or unmounted after setup.** Runs stop with the plain message, the watcher reports nothing, and the page doesn't crash. → `test_pick_roster_drive_folder_missing`, `test_watch_survives_missing_folder` (Tasks 1, 4)
4. **Update clicked when nothing changed, or when the newest brief is last week's.** The response is a 409 with a sentence she can act on, and no Claude run. → `test_update_refused_when_nothing_changed`, `test_update_refused_when_brief_is_stale` (Task 7)
5. **The model tries to slip past the rules.** It names a locked `beats` target, or marks a present row `missing`. Code ignores the target and refuses the flag. → `test_apply_uses_weakest_open_slot_not_model_target`, `test_missing_flag_rejected_on_present_row` (Task 6)

---

### Task 1: Find Google Drive and the roster folder setting

**Files:**
- Create: `scripts/nf_core/drive.py`
- Modify: `scripts/nf_core/workspace.py` (settings, `Workspace.roster_folder`, `Workspace.inbox`, `ensure_workspace`, `pick_roster`)
- Test: `tests/unit/test_drive.py` (new), `tests/unit/test_workspace.py`

**Interfaces:**
- Produces:
  - `drive.FOLDER_NAME = "Network Focus"`
  - `drive.find_my_drive(home: Path, system: str, win_roots: list[Path] | None = None) -> list[Path]`: existing "My Drive" folders, best first.
    - Mac: sorted `home/Library/CloudStorage/GoogleDrive-*/My Drive`.
    - Windows: `root/"My Drive"` for each root (default `D:\` … `Z:\`), then `home/"My Drive"`.
  - `workspace.SETTINGS_FILE = "settings.json"`
  - `workspace.load_settings(root: Path) -> dict` returns `{}` if the file is missing or unreadable.
  - `workspace.save_settings(root: Path, data: dict) -> None` writes atomically (temp file plus `os.replace`).
  - `Workspace.roster_folder -> Path | None`, taken from `settings["roster_folder"]`.
  - `Workspace.inbox -> Path`: the roster folder if set, else `root/"inbox"`.
  - `ensure_workspace` creates `root/"inbox"`, `briefs` and `.work`. **Never the roster folder.**
  - `pick_roster` gains two blocks:
    - `DRIVE_FOLDER_MISSING`: "I can't find the Network Focus folder in Google Drive ({path}). Open Google Drive for desktop and check you're signed in, then try again."
    - `GOOGLE_SHEET`, the spec's copy: "The roster in Google Drive is a Google Sheet, which I can't read. In Drive, open it and choose File → Download → Microsoft Excel, then put that file in the Network Focus folder. Or keep the roster as an Excel file."

- [ ] **Step 1: Write the failing tests**
  - `test_find_my_drive_mac`: two `GoogleDrive-*/My Drive` folders → both, sorted; none → `[]`.
  - `test_find_my_drive_windows`: `win_roots=[tmp/"E", tmp/"G"]`, only `G/"My Drive"` exists, plus `home/"My Drive"` → `[G/"My Drive", home/"My Drive"]`.
  - `test_inbox_follows_roster_folder`:
    - setting saved → `inbox == folder`
    - no setting → `root/"inbox"`
    - `settings.json` containing `{not json` → `root/"inbox"`
  - `test_ensure_workspace_never_creates_drive_folder`: setting points to a missing path → it still doesn't exist after `ensure_workspace`.
  - `test_pick_roster_drive_folder_missing`: code `DRIVE_FOLDER_MISSING`, and the path is in the message.
  - `test_pick_roster_google_sheet`: the folder holds only `Roster.gsheet` → code `GOOGLE_SHEET`, and "File → Download → Microsoft Excel" is in the message.
  - `test_pick_roster_reads_from_drive_folder`: an `.xlsx` in the configured folder gets picked.
- [ ] **Step 2: Run them and confirm they fail.** `uv run pytest -q tests/unit/test_drive.py tests/unit/test_workspace.py` → FAIL (no `nf_core.drive`, no `load_settings`).
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run all tests and confirm they pass.** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit.** `git commit -m "Read the roster from a configured Google Drive folder"`

### Task 2: Installer, Check setup and the page use the Drive folder

**Files:**
- Modify: `app/install_app.py`, `scripts/check_setup.py`, `app/dashboard_data.py`, `app/server.py` (status, upload, run path), `install.sh`, `install.ps1`, `tests/unit/fake_claude.py` (record argv)
- Test: `tests/unit/test_install_app.py`, `tests/unit/test_check_setup.py`, `tests/unit/test_server.py`

**Interfaces:**
- Consumes (Task 1): `find_my_drive`, `FOLDER_NAME`, `load_settings`, `save_settings`.
- Produces:
  - `install(plugin_root, home, port=8765, launch=True, system=None, nf_home=None, drive_roots: list[Path] | None = None) -> dict`. The result gains `"roster_folder": str | None`.
    - **Drive found:** create `drives[0]/FOLDER_NAME`, merge `{"roster_folder": ...}` into `settings.json`, and use `shutil.copy2` to copy the newest local-inbox roster into it if the folder has no `.xlsx`/`.csv`.
    - **More than one Drive:** add the warning "Google Drive has more than one account on this computer. Using {drives[0].parent.name}."
    - **None found:** add the spec warning "Google Drive isn't set up on this computer. Install Google Drive for desktop, sign in, then run the installer again. Until then, drag spreadsheets onto the page as before." Leave any existing setting untouched.
  - `dashboard_data.roster_dir(nf_home: Path) -> Path`: same rule as `Workspace.inbox`, duplicated on purpose because the server can't import `nf_core`. It carries a one-line comment saying so.
  - `check_setup` gets a new line, `CheckResult("Google Drive folder", ...)`, placed after "Network Focus folder":
    - ok: "Reading the roster from {folder}."
    - info: "Not set up, so rosters come from the inbox folder. To use Google Drive, install Google Drive for desktop, sign in, then run the installer again."
    - fail: detail "I can't find {folder}.", fix "Open Google Drive for desktop and check you're signed in."
    - The Google-Sheet-only case is reported by the existing "Spreadsheet in inbox" line through the `GOOGLE_SHEET` block, with fix "In Drive, open it and choose File → Download → Microsoft Excel, then put that file in the folder."
  - The server's `/api/status` list, `/api/upload` destination and `/api/run` file check all use `roster_dir(cfg.nf_home)`. `Run` builds its prompt path from it too.
  - `fake_claude.py` writes `json.dumps(sys.argv[1:])` to `NF_HOME/.fake-argv.json`.
  - The installers print `[OK] Roster folder: Google Drive > My Drive > Network Focus` when `roster_folder` is set. Warnings are already printed.

- [ ] **Step 1: Write the failing tests**
  - `test_install_creates_drive_folder`: Mac home with `Library/CloudStorage/GoogleDrive-x/My Drive` → `roster_folder` ends with `My Drive/Network Focus`, the folder exists, and `settings.json` holds it.
  - `test_install_copies_local_roster_once`: `inbox/roster.xlsx` gets copied with its mtime. Re-running after a different file is added to Drive copies nothing.
  - `test_install_without_drive_warns`: `roster_folder is None`, a warning contains "Google Drive isn't set up on this computer", and `inbox/` exists.
  - `test_install_windows_drive_root`: `system="win32"`, `drive_roots=[tmp/"G"]` → `G/My Drive/Network Focus`.
  - Check setup:
    - `test_check_drive_ok`: status ok, and the folder path is in the detail.
    - `test_check_drive_not_set_up`: status info.
    - `test_check_drive_missing`: status fail, with the fix above.
    - `test_check_spreadsheet_google_sheet`: the "Spreadsheet in inbox" line fails, and the fix mentions Microsoft Excel.
  - Server:
    - `test_status_lists_drive_folder`
    - `test_upload_saves_into_drive_folder`
    - `test_run_passes_drive_file`: `.fake-argv.json`'s prompt contains the Drive folder path.
- [ ] **Step 2: Run them and confirm they fail.** `uv run pytest -q tests/unit/test_install_app.py tests/unit/test_check_setup.py tests/unit/test_server.py` → the new tests FAIL.
- [ ] **Step 3: Implement.** Update the installer tests (`test_install_script.py`, `test_install_ps1.py`) only if they assert "no warnings": test mode now prints the "Google Drive isn't set up" warning.
- [ ] **Step 4: Run all tests and confirm they pass.** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit.** `git commit -m "Installer creates the Drive folder; check and page use it"`

### Task 3: Snapshot v2 (roster index, dormant goals) and goal rings

**Files:**
- Create: `scripts/nf_core/changes.py`
- Modify:
  - `scripts/nf_core/snapshot.py`
  - `schemas/brief.json`
  - `scripts/nf_core/brief_checks.py` (dormant goal ids)
  - `skills/brief/SKILL.md` (dormant `goals` line)
  - `tests/unit/fixtures/valid_brief.json` (dormant `goals`)
  - `app/dashboard_data.py`, `app/index.html`
- Test: `tests/unit/test_changes.py` (new), `test_snapshot.py`, `test_brief_checks.py`, `test_dashboard_data.py`, `test_server.py`

**Interfaces:**
- Produces:
  - `changes.identity(name: str, company: str) -> str`
  - `changes.row_fingerprint(contact: dict) -> str` (fields per Global Constraints)
  - `changes.roster_index(contacts: list[dict]) -> dict[str, dict]`: `{identity: {"name": str, "fp": str}}`, first occurrence wins.
  - `snapshot.SNAPSHOT_VERSION = 2`. `build_snapshot` adds `"roster_index"` and `source["sha256"]`. `questions_for` appends `brief.get("update_questions", [])`.
  - `brief.json`:
    - Dormant items **require** `goals` (array of integer, minItems 1).
    - Documented optional fields:
      - top level: `considering` (`[{row_id, name, note}]`), `updates` (`[{at, added: [str], bumped: [str]}]`), `update_questions` (`[str]`)
      - focus items: `new` (bool), `missing` (bool), `who` (str)
  - `validate_brief`: `UNKNOWN_GOAL` also checked on dormant items.
  - `dashboard_payload` adds:
    - `"goals": [{"id": int, "title": str, "done": int, "total": int}]`, ordered by id and counted over focus and dormant items whose `goals` include the id.
    - `"considering"`
    - `"updated_at": str | None`, the last `updates[].at`.
  - `_person` adds `"new": bool`, and `role_company` falls back to `item.get("who", "")`.
  - `index.html`:
    - `#goalRings` under the brand: one mini ring plus "Title d/t" per goal. `total == 0` shows "No move this week" in a new `--warn` token, in both themes.
    - Chip "New · {Goal 1 title}" on new picks.
    - `#considerTitle` "Worth considering · since Monday" and `#considering` rows "**Name**: note", hidden when empty.

- [ ] **Step 1: Write the failing tests**
  - `test_identity_distinguishes_company`: `identity("Diana  Chen","Stripe") == identity("diana chen","stripe ")`, and `!= identity("Diana Chen","Google")`.
  - `test_fingerprint_ignores_days`: days 10 vs 40 give the same fp; changed notes give a different fp.
  - `test_roster_index_duplicate_keeps_first`
  - `test_snapshot_has_roster_index`: `snap["version"] == 2`, and `len(snap["roster_index"])` equals the number of distinct identities in the sample.
  - `test_dormant_needs_goals`: no `goals` → SCHEMA. Goal 9 → `UNKNOWN_GOAL`.
  - `test_goal_rings`: fixture snapshot with row 3 marked done → goal 2 `done == 1`. Each `total` equals the picks serving that goal. A goal with no picks has `total == 0`.
  - `test_old_snapshot_dormant_without_goals_still_loads`: a v1 snapshot loads, and rings count focus only.
  - `test_person_role_falls_back_to_who`
  - `test_index_has_goal_rings`: the page contains `id="goalRings"` and `id="considering"`.
- [ ] **Step 2: Run them and confirm they fail.** `uv run pytest -q tests/unit/test_changes.py tests/unit/test_snapshot.py tests/unit/test_brief_checks.py tests/unit/test_dashboard_data.py tests/unit/test_server.py` → the new tests FAIL.
- [ ] **Step 3: Implement**, including the brief skill line: "`goals` on every dormant person too: the goal ids they serve."
- [ ] **Step 4: Run all tests and confirm they pass.** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit.** `git commit -m "Snapshot v2 with roster index; goal rings on the dashboard"`

### Task 4: Noticing roster changes

**Files:**
- Create: `scripts/roster_diff.py`, `app/roster_watch.py`
- Modify: `scripts/nf_core/changes.py`, `app/dashboard_data.py`, `app/server.py`, `app/index.html`
- Test: `tests/unit/test_changes.py`, `tests/unit/test_roster_watch.py` (new), `tests/unit/test_server.py`

**Interfaces:**
- Consumes: `roster_index`, `identity`, `row_fingerprint` (Task 3), `roster_dir` (Task 2).
- Produces:
  - `changes.diff_roster(index: dict[str, dict], contacts: list[dict]) -> dict`: `{"new": [{"row_id", "name", "company"}], "changed": [same], "removed": [{"name"}]}`.
  - `roster_diff.py --roster PATH --snapshot PATH` (PEP 723, openpyxl) prints one JSON line and always exits 0:
    - `{"ok": true, "file": str, "new", "changed", "removed"}`
    - `{"ok": false, "reason": "no_index"}`
    - `{"ok": false, "reason": "blocked", "message": str}`
  - `dashboard_data.latest_snapshot_path(nf_home: Path) -> Path | None`
  - `roster_watch.RosterWatch(nf_home: Path, run_diff: Callable[[Path, Path], dict], interval: int = 120)`, with:
    - `check_once(now: float) -> None`, which never raises
    - `state() -> dict`: `{"changes": None | {"file", "modified": float, "new", "changed", "removed"}}`
    - `start() -> None`: a daemon thread.
  - It diffs only when the file is steady and `(file key, snapshot path, snapshot mtime_ns)` differs from the last diff. `changes` is `None` unless `ok` and (`new` or `changed`).
  - `AppConfig.watch_interval: int = 120`. With `0`, no thread starts; tests call `srv.watch.check_once`.
  - `make_server` sets `srv.watch`, whose `run_diff` calls `uv run roster_diff.py` through a subprocess with a 120 s timeout.
  - `GET /api/roster-changes` (token required) returns `srv.watch.state()`.
  - `index.html`:
    - `#rosterLine` banner: "Roster updated {today 10:42 | Nov 24, 10:42} · New: A, B · Changed: C", with a `#updateBtn` "Update this week's brief" button that Task 7 wires up.
    - Hidden when `changes` is null or `dash.stale`.
    - Fetched on load and every 120 000 ms.

- [ ] **Step 1: Write the failing tests**
  - `test_diff_new_changed_removed`: from the sample, add "Ana Ruiz | Andreessen Horowitz", change Marcus Wei's notes, remove Lin Wang, and add 3 to every `days_since_contact` → `new == [Ana Ruiz]`, `changed == [Marcus Wei]`, `removed == [Lin Wang]`.
  - `test_roster_diff_cli_no_index`: a v1 snapshot → `{"ok": false, "reason": "no_index"}`.
  - `test_roster_diff_cli_reports_new`: uses `make_roster` and a v2 snapshot.
  - `test_watch_waits_for_steady_file`: mtime = now → no diff on the first check, one diff on the second.
  - `test_watch_ignores_lock_files`: only `~$roster.xlsx` → no diff, and `changes is None`.
  - `test_watch_no_repeat_diff`: a third check with the same key leaves the diff count at 1.
  - `test_watch_rediffs_after_new_snapshot`: touching the snapshot → a second diff.
  - `test_watch_survives_missing_folder`: setting points to a missing folder → `changes is None`, and nothing is raised.
  - `test_watch_reports_none_when_nothing_new`: `run_diff` returns ok with empty lists → `None`.
  - `test_roster_changes_endpoint`: 401 without the cookie. With a stub diff, it returns the new names.
- [ ] **Step 2: Run them and confirm they fail.** `uv run pytest -q tests/unit/test_changes.py tests/unit/test_roster_watch.py tests/unit/test_server.py` → the new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests and confirm they pass.** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit.** `git commit -m "Watch the roster folder and show who's new"`

### Task 5: Update, part 1: prepare and validate (code)

**Files:**
- Create: `scripts/nf_core/update.py`, `schemas/update.json`, `scripts/update_prep.py`
- Modify: `scripts/validate_brief.py` (mode `update`, `--input`)
- Test: `tests/unit/test_update.py` (new)

**Interfaces:**
- Consumes:
  - `identity`, `diff_roster` (Tasks 3–4)
  - `brief_checks._check_person` and `_check_move_and_numbers`, reused as they are.
- Produces:
  - `update.main_goal(roster: dict) -> dict`: `{"id", "title"}` of the lowest-id goal.
  - `update.load_marks(root: Path, week: str) -> dict[str, str]`: reads `.progress.json`, `{}` on error.
  - `update.latest_snapshot(briefs: Path) -> Path | None`: same rule as `dashboard_data.latest_snapshot_path`.
  - `update.prep_update(snapshot: dict, roster: dict, marks: dict[str, str]) -> dict`, which returns:
    ```
    {"week_of", "main_goal": {"id", "title"},
     "picks": [{"section": "focus"|"dormant", "rank": int, "old_row_id": int, "row_id": int|None,
                "name", "goals": [int], "done": bool, "locked": bool}],
     "people": [{"row_id", "name", "kind": "new"|"changed"}],   # changed people who are picks are excluded
     "listed_only": [str],                                      # names of changed people who are already picks
     "open_slots": [{"kind": "empty"}, ..., {"kind": "replace", "row_id", "name", "rank"}]}
    ```
    - `locked` = dormant, or `rank == 0`, or done.
    - `row_id` is `None` when the identity is gone.
    - `open_slots` lists the `5 - len(focus)` empty slots first, then unlocked focus picks that have a `row_id`, highest rank first.
  - `schemas/update.json`: `{"people": [{"row_id": int, "name": str, "tied_to_main_goal": bool, "evidence": [str, minItems 1], "goal_link": str, "beats": int?, "pick": {goals, why, move, risk, evidence, confidence: enum low|medium|high, message}?, "consider": str?}]}`
  - `update.validate_update(update: dict, roster: dict, update_input: dict) -> list[Problem]`, with these codes:
    - `MISSING_PERSON`, `UNEXPECTED_PERSON`: every input person appears exactly once.
    - Quote codes from `_check_person`.
    - `NO_GOAL_LINK`: `tied_to_main_goal` is true but `goal_link` is empty.
    - `PICK_NOT_ALLOWED`: a `pick` without (tied and (`beats` names an open replace slot, or an empty slot exists)).
    - `BEATS_NOT_OPEN`
    - `PICK_GOAL`: the pick's `goals` lack the main goal id.
    - `UNKNOWN_GOAL`, `THIN_NOT_LOW`, plus the `_check_move_and_numbers` codes.
    - `NO_CONSIDER_NOTE`: no `pick` and an empty `consider`.
  - `update_prep.py --work WORK [--snapshot PATH]` writes `WORK/update-input.json` and prints one of:
    - `{"status": "ok", "people": n}`, exit 0
    - `{"status": "nothing", "message": "Nobody new or changed since this week's brief."}`, exit 0
    - `{"status": "blocked", "message": ...}`, exit 2, with either:
      - "This week's brief hasn't been made yet. Click Generate instead." (no snapshot, or its week ≠ `roster.source.week_of`)
      - "This week's brief was made before the page could track changes. Click Generate once, then Update will work." (no `roster_index`)
  - `validate_brief.py update WORK/update.json --roster WORK/roster.json --input WORK/update-input.json`

- [ ] **Step 1: Write the failing tests**
  - `test_main_goal_is_lowest_id`
  - `test_prep_maps_rows_by_identity`: a row inserted at the top → every pick's `row_id == old_row_id + 1`.
  - `test_prep_locks_done_top_and_dormant`: marks `{"2": "Marcus Wei"}` lock Marcus, `focus[0]` and the dormant picks.
  - `test_prep_open_slots_order`: 4 focus picks → `[empty, replace rank 3, replace rank 2, replace rank 1]`, with done ones excluded.
  - `test_prep_lists_changed_picks_only`
  - `test_prep_missing_pick_row_none`
  - Validation:
    - `test_validate_update_quote_must_exist`
    - `test_validate_update_every_person_once`
    - `test_validate_update_pick_needs_main_goal`
    - `test_validate_update_pick_message_rules`: the first name missing from the message → `MESSAGE_NAME`.
    - `test_validate_update_not_placed_needs_note`
  - CLI:
    - `test_update_prep_cli_nothing`
    - `test_update_prep_cli_blocked_when_stale`
    - `test_update_prep_cli_blocked_without_index`
- [ ] **Step 2: Run them and confirm they fail.** `uv run pytest -q tests/unit/test_update.py` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests and confirm they pass.** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit.** `git commit -m "Update prep and validation in code"`

### Task 6: Update, part 2: apply the rules and show "Updated" on the PDF

**Files:**
- Create: `scripts/apply_update.py`
- Modify:
  - `scripts/nf_core/update.py`
  - `scripts/nf_core/brief_checks.py` (`missing` items)
  - `scripts/validate_brief.py` (`cited-rows --only-new`)
  - `scripts/nf_core/render.py` (PDF and markdown line)
- Test: `tests/unit/test_update.py`, `test_brief_checks.py`, `test_render.py`

**Interfaces:**
- Consumes: the `prep_update` output and `validate_update` (Task 5).
- Produces:
  - `update.apply_update(snapshot: dict, roster: dict, update_input: dict, update: dict, now: str) -> tuple[dict, dict[str, str], dict]`, which returns:
    - the merged brief,
    - the marks to **add** to this week's `.progress.json` (`{str(new_row_id): name}` for done picks),
    - a summary: `{"added": [str], "bumped": [str], "refused": [str]}`.
  - `apply_update.py --work WORK [--snapshot PATH] [--now ISO]` behaves like this:
    - It runs `validate_update` first and exits 1 with `{"ok": false, "problems": [...]}` if anything fails.
    - It writes `WORK/brief.json`.
    - It merges the new mark keys into `<root>/.progress.json` atomically, **keeping the old keys**. Old keys stay correct for the old snapshot, and the name check makes them harmless afterwards.
    - It prints `{"ok": true, "added", "bumped", "refused"}`.
  - `validate_brief` handles `missing: true` items:
    - It skips their row checks only when the `row_id` isn't in the roster.
    - `MISSING_BUT_PRESENT`: the item is marked missing but its row is in the roster.
    - `MISSING_NOT_ALLOWED`: the item is marked missing but the brief has no non-empty `updates`.
  - `cited-rows --only-new`: only focus items with `new: true`.
  - `render_pdf` and `render_markdown`: when `updates` exists, print a line under the title. The date is built with `f"{d:%a} {d:%b} {d.day}, {d:%H:%M}"`:
    - "Updated Wed Nov 25, 10:50: added Ana Ruiz", or
    - "Updated Wed Nov 25, 10:50: no change to the picks".

- [ ] **Step 1: Write the failing tests**
  - `test_apply_fills_empty_slot_first`: 4 picks → the newcomer is appended, and `bumped == []`.
  - `test_apply_bumps_weakest_open_pick`:
    - 5 picks, and the newcomer `beats` rank 2 → rank 4 is bumped.
    - The newcomer sits at index 4 with `new: true`.
    - `considering` gets "Moved here to make room for Ana Ruiz."
  - `test_apply_never_bumps_done_or_top`: all non-top picks done → `refused == ["Ana Ruiz"]`.
  - `test_apply_uses_weakest_open_slot_not_model_target`: `beats` names a done row → the weakest open pick is bumped instead.
  - `test_apply_keeps_goal_coverage`:
    - The weakest open pick is the only goal-3 pick → the next weakest is bumped.
    - If none keeps coverage → refused, with "no open slot could be freed this week".
  - `test_apply_untied_goes_to_considering`: considered people carry their `consider` note.
  - `test_apply_remaps_rows_and_marks`: rows shift by 1 → the merged brief and the returned marks use the new ids.
  - `test_apply_missing_pick_kept_with_question`:
    - The pick keeps `missing: true`, its old `row_id` and `who`.
    - `update_questions` contains "is no longer in the roster".
  - `test_apply_considering_accumulates_and_dedupes`
  - `test_missing_flag_rejected_on_present_row`, `test_missing_flag_needs_updates`
  - `test_render_shows_updated_line`: markdown contains "Updated Wed Nov 25, 10:50: added Ana Ruiz".
  - `test_apply_update_cli_refuses_invalid`: exit 1, and `brief.json` is untouched.
- [ ] **Step 2: Run them and confirm they fail.** `uv run pytest -q tests/unit/test_update.py tests/unit/test_brief_checks.py tests/unit/test_render.py` → the new tests FAIL.
- [ ] **Step 3: Implement `apply_update`** with this algorithm (the signature doesn't determine it):
  ```
  brief = deepcopy(snapshot["brief"])
  remap focus/dormant/coming_up row_ids via update_input.picks (by old_row_id); row_id None ->
      keep old id, missing=True, who="<role>, <company>" from snapshot.people; update_questions +=
      "<Name> is no longer in the roster. Remove them from this week's list?"
  before = goals covered by focus; empties = count of empty slots; taken = set()
  for p in update.people (model order) with tied_to_main_goal and pick:
      if empties: append new item; empties -= 1; added += p; continue
      floor = rank of p.beats among replace slots (0 if absent or not an open slot)
      for s in replace slots weakest-first, s not taken, s.rank >= floor:
          if goals(focus with s replaced by p) ⊇ before: replace in place; taken += s;
              considering += {s, note "Moved here to make room for <p>."}; added += p; bumped += s; break
      else: refused += p; considering += {p, note "Tied to <main goal title>, but no open slot could be freed this week."}
  for p without pick: considering += {p, note p.consider}
  considering = earlier considering minus anyone placed now, then the new entries; dedupe by row (last wins)
  brief.updates += {at: now, added, bumped}
  marks = {str(new_row_id): name for done picks}
  ```
- [ ] **Step 4: Run all tests and confirm they pass.** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit.** `git commit -m "Apply Update under code-enforced swap rules"`

### Task 7: The update skill, the Update button and the server's update mode

**Files:**
- Create: `skills/update/SKILL.md`
- Modify:
  - `app/server.py` (`Run` mode, `/api/run`)
  - `app/progress.py`
  - `app/index.html` (Update flow)
  - `tests/unit/fake_claude.py` (`update` mode)
  - `.claude-plugin/plugin.json` (`0.3.0`)
- Test: `tests/unit/test_server.py`, `tests/unit/test_progress.py`

**Interfaces:**
- Consumes: `update_prep.py`, `validate_brief.py update`, `apply_update.py`, `cited-rows --only-new`, `render_pdf.py` (Tasks 5–6); `srv.watch` (Task 4).
- Produces:
  - `Run(cfg, file, mode: str = "brief", on_done: Callable[[], None] | None = None)`. Update mode uses the prompt `"/network-focus:update"`. `on_done` runs after a successful run; the server passes `lambda: srv.watch.check_once(time.time())` so the line clears straight away.
  - `POST /api/run` with `{"mode": "update"}` responds:
    - 400 for any mode other than `brief`/`update`.
    - 409 "This week's brief hasn't been made yet. Click Generate instead." when the dashboard payload is empty or stale.
    - 409 "Nobody new or changed since this week's brief." when `srv.watch.state()["changes"] is None`.
    - Otherwise it starts the run under the same lock.
  - `progress_from_event`:
    - `update_prep.py` → "Looking at who's new"
    - `apply_update.py` → "Placing new people"
    - the existing steps unchanged
  - `skills/update/SKILL.md` keeps the brief skill's header, `allowed-tools`, the one-`uv run`-per-call rule and the plain-English rules. Its steps:
    1. `load_roster.py`, handled exactly as in the brief skill.
    2. `update_prep.py --work WORK`. On `nothing`, reply with its message and stop. On `blocked`, pass the message on and stop.
    3. Read `update-input.json` and `roster.json`, then write `WORK/update.json` following `schemas/update.json`:
       - `tied_to_main_goal` only when the row shows a link to the main goal (an investor, the round, an intro to an investor), with `goal_link` saying how.
       - `beats` = the open pick this person outranks under the brief's selection rules.
       - `pick` only for tied people, written under the brief's message rules.
       - A one-sentence `consider` for everyone else.
    4. `validate_brief.py update …`, with at most 2 fix rounds.
    5. `apply_update.py --work WORK`. On exit 1, fix `update.json` and run it once more.
    6. `validate_brief.py brief`.
    7. If anyone was added: `cited-rows --only-new`, then the fact-checker in the foreground. Fix claims in `update.json`, then re-run step 5 and step 6.
    8. `render_pdf.py --work WORK`.
    9. Reply in at most 5 lines: "Brief updated: <pdf>", "Added: <name> (in place of <bumped>)", "Worth considering: <names>".
  - `index.html`: `#updateBtn` POSTs `{"mode": "update"}` and follows the SSE stream, showing the current step in `#rosterLine`:
    - done → `loadDashboard()` and re-fetch `/api/roster-changes`
    - failed → the message plus the log path
    - 409 → its message

- [ ] **Step 1: Write the failing tests.** Snapshots in these tests use `week_of(date.today())`, so they're never stale by accident.
  - `test_update_refused_when_nothing_changed`
  - `test_update_refused_when_brief_is_stale`: a snapshot one week earlier → 409, and "Click Generate" is in the message.
  - `test_unknown_run_mode_400`
  - `test_update_run_uses_update_skill`:
    - The stub watch has changes, and `FAKE_CLAUDE_MODE=update`.
    - The POST returns 200, and the final SSE event is `done`.
    - `.fake-argv.json` contains "/network-focus:update".
    - The steps include "Looking at who's new".
  - `test_update_step_names` (test_progress)
  - `test_update_skill_names_every_script`: the `SKILL.md` text contains `update_prep.py`, `apply_update.py`, `--only-new` and `render_pdf.py`.
- [ ] **Step 2: Run them and confirm they fail.** `uv run pytest -q tests/unit/test_server.py tests/unit/test_progress.py` → the new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests and confirm they pass.** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit.** `git commit -m "Update skill, Update button and server update mode"`

### Task 8: End-to-end evals for Update

**Files:**
- Modify: `tests/evals/make_cases.py`, `tests/evals/run_evals.py`, `tests/unit/test_make_cases.py`
- Create: `tests/evals/cases/update-*/`, `tests/evals/results/<date>.md`

**Interfaces:**
- An update case has:
  - `setup.json` `{"kind": "update", "marks": {...}}`
  - `base_brief.json`, built from `tests/unit/fixtures/valid_brief.json`
  - `roster.xlsx`: the sample plus the case's rows
  - `expected.json`: `{"must_place": [str], "must_consider": [str], "must_keep": [str], "must_refuse": [str]}`
- `run_evals.py` behaves like this for `kind == "update"`:
  - **Prepare:**
    - Set the base brief's `week_of` to this week.
    - Write the v2 snapshot with `build_snapshot`, using the **sample** roster so `roster_index` reflects Monday.
    - Copy the case roster to `inbox/` and write the marks.
    - Run `claude -p "/network-focus:update"`.
  - **Check:**
    - `must_place` people are in focus with `new: true`.
    - `must_consider` and `must_refuse` people are in `considering` and not in focus.
    - `must_keep` people are still in focus.
    - `validate_brief` passes on the merged brief.
- The cases:
  - `update-series-c-newcomer`:
    - Adds "Ana Ruiz, Partner, Andreessen Horowitz", summary "Asked for a Series C call before Friday.", tags "investor, series-c", strength 3.
    - Expects `must_place: ["Ana Ruiz"]`, `must_keep: ["Diana Chen"]`.
  - `update-cto-newcomer`:
    - Adds "Tom Park, Engineering Director, Figma", summary "Scaled engineering from 40 to 220 people.", tags "cto-candidate".
    - Expects `must_consider: ["Tom Park"]`.
  - `update-coverage-floor`:
    - Marks every open pick done except the only goal-3 pick, and adds Ana Ruiz as above.
    - Expects `must_refuse: ["Ana Ruiz"]`.

- [ ] **Step 1: Write the failing test.** `test_update_cases_built`: `make_cases` writes the 3 case folders, each with `setup.json` kind `update`.
- [ ] **Step 2: Run it and confirm it fails.** `uv run pytest -q tests/unit/test_make_cases.py` → FAIL.
- [ ] **Step 3: Implement.** Run `uv run python tests/evals/make_cases.py`.
- [ ] **Step 4: Run the unit test and confirm it passes**, then the three evals: `uv run python tests/evals/run_evals.py --case update-series-c-newcomer` (and the other two). These use real Claude. Expected: 3/3 pass. Record cost and time in the results file.
- [ ] **Step 5: Commit.** `git commit -m "Evals for mid-week Update"`

### Task 9: Docs, deliverables and the Mac check

**Files:**
- Modify: `docs/PRD.md`, `docs/HANDOFF.md`, `README.md`, `docs/VIDEO-OUTLINE.md`
- Regenerate: `deliverables/PRD.pdf`, `deliverables/Handoff.pdf` via `uv run python tools/make_pdfs.py`

**What changes:**
- **PRD:**
  - §4 Data sourcing: the roster comes from the Drive folder. "Store dates, not days since" stays.
  - §5 Failure modes: Google Sheet in the folder, Drive missing, and the mid-week Update rules.
  - It stays at **2 pages**.
- **Handoff:** stays at **1 page**.
  - Install Google Drive for desktop.
  - Share `My Drive > Network Focus` with the CEO.
  - Put the roster there.
  - When the roster line appears, click Update.
- **The installer zip doesn't change.** Its launchers download `install.sh`/`install.ps1` from GitHub.

- [ ] **Step 1: Update the docs and regenerate the PDFs.**
- [ ] **Step 2: Check page counts.** `pdfinfo deliverables/PRD.pdf | grep Pages` → 2. `pdfinfo deliverables/Handoff.pdf | grep Pages` → 1.
- [ ] **Step 3: Run all tests and confirm they pass.** `uv run pytest -q` → all pass.
- [ ] **Step 4: Commit and push.** Wait for GitHub Actions to go green on ubuntu, macOS and Windows: `gh run watch`.
- [ ] **Step 5: The Mac check (Jasper, on the CEO-side Mac), after merging to main:**
  1. Re-run the installer and click **Check setup**. The "Google Drive folder" line should be ok. This is the privacy-prompt test: the check runs inside the background page.
  2. Put the roster in Drive's Network Focus folder, then click Generate.
  3. Add a Series C row in Drive and wait about 4 minutes. The roster line should appear.
  4. Click Update. Report the result, or the failure message and log path.
