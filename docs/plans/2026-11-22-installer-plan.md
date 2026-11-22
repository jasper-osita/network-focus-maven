# One-click Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `install.sh` plus a double-clickable `Install Network Focus.command` that install or update Network Focus end to end, with `--uninstall`.

**Architecture:** A bash script built around the CLI calls already proven in this session (`claude auth`, `claude plugin marketplace/install/update/list --json`, `install_app.py`), tested on Linux through `NF_INSTALL_TEST=1` and stand-in programs on PATH.

**Tech Stack:** bash, the existing `install_app.py`, pytest.

**Spec:** `docs/design/2026-11-22-installer-design.md`

## Global Constraints
- Repo: `jasper-osita/network-focus-maven`. Plugin id: `network-focus@network-focus`. Raw URL: `https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.sh`.
- Log file: `~/Library/Logs/NetworkFocus-install.log`. Never delete `~/Documents/Network Focus`.
- Plain-English output, numbered steps 1/5 to 5/5, and a fix on every failure.

## Review Focus
1. **Already installed and signed in:** a re-run makes no install or login calls and updates instead. → `test_rerun_updates`
2. **Sign-in fails or is cancelled:** it stops at step 2 with a plain message and a non-zero exit. → `test_login_failure_stops`
3. **`uv` or `claude` missing:** the curl installer is called for exactly the missing one. → `test_missing_helper_installed`
4. **Uninstall:** keeps `~/Documents/Network Focus`, removes the app folder, plist and Desktop link. → `test_uninstall_keeps_briefs`
5. **The `.command` without `install.sh` beside it:** falls back to the raw GitHub URL. → `test_command_file`

### Task 1: install.sh, the .command, tests
**Files:** create `install.sh`, `Install Network Focus.command`, `tests/unit/test_install_script.py` (with stand-ins written into tmp: `claude`, `curl`)
- [ ] Write the failing tests: `test_fresh_install` (login, marketplace add, plugin install called; app dir and webloc in tmp HOME; output has "Done"), plus the 5 Review Focus tests. Run them and confirm they fail.
- [ ] Implement the scripts. Run them and confirm they pass. Run `uv run pytest -q` and confirm everything passes. Commit.

### Task 2: Docs and deliverables
**Files:** `docs/HANDOFF.md` (setup becomes 3 lines, 1 page), `docs/PRD.md` (artifact next step, 2 pages), `README.md`, `docs/VIDEO-OUTLINE.md`, `deliverables/Install Network Focus.command`, rebuilt PDFs.
- [ ] Edit, run `uv run --with markdown python tools/make_pdfs.py` and confirm PRD ≤2 pages and Handoff = 1. Commit, open the PR, merge into `main`.
