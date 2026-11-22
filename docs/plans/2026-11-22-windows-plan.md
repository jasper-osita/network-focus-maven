# Windows Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Network Focus installs and runs on Windows as well as macOS, verified on real Windows and macOS machines through GitHub Actions.
**Architecture:** OS-specific code stays in three places: `install_app.py` (layout, autostart, shortcut), `workspace.documents_dir()` (known folder), and the installers (`install.sh` / `install.ps1`). Everything else is shared.
**Tech Stack:** Python stdlib (ctypes for known folders), PowerShell 5.1, bash, pytest, GitHub Actions.
**Spec:** `docs/design/2026-11-22-windows-design.md`

## Global Constraints
- The Mac behaviour and the verified Mac permission rules stay unchanged. All 140 existing tests stay green.
- No admin rights needed on Windows, and no console window for the background page.
- Plugin id `network-focus@network-focus`; repo `jasper-osita/network-focus-maven`.

## Review Focus
1. **OneDrive-redirected Documents:** the known-folder lookup is used, not `~/Documents`. → `test_documents_dir_uses_known_folder_on_windows`
2. **Re-running the Windows installer:** it updates; there's no duplicate Startup entry or shortcut. → `test_windows_layout_idempotent`
3. **A Windows user name with spaces or non-ASCII characters:** paths are quoted in the `.vbs` and the shortcut. → `test_vbs_quotes_paths`
4. **`-Uninstall`:** keeps the briefs, removes the `.vbs`, the app folder and the shortcut. → `test_ps1_uninstall_keeps_briefs` (Windows CI)
5. **Sign-in fails:** it stops at step 2 with a message. → `test_ps1_login_failure_stops` (Windows CI)

### Task 1: Cross-platform Python (known folders, install_app layouts, setup check, fonts)
**Files:** `scripts/nf_core/workspace.py` (`documents_dir()`), `app/install_app.py` (`install(..., system=sys.platform, nf_home=None)`, `--nf-home`), `scripts/check_setup.py`, `scripts/nf_core/render.py`; tests in `tests/unit/test_workspace.py` and `tests/unit/test_install_app.py`.
- [ ] Write the failing tests: `test_documents_dir_uses_known_folder_on_windows`, `test_windows_layout` (`.vbs` in Startup, `.url` on Desktop, app dir `AppData/Local/Network Focus`, no plist, Windows permission rules), `test_windows_layout_idempotent`, `test_vbs_quotes_paths`. Confirm they fail, implement, run `uv run pytest -q` and confirm everything passes, commit.

### Task 2: Windows installer
**Files:** `install.ps1`, `Install Network Focus.cmd`, `tests/unit/test_install_ps1.py` (Windows only; stand-in `claude.cmd`), the zip with both installers, and a zip test.
- [ ] Write the tests (skipped off Windows), implement, run the local suite and confirm it passes, commit.

### Task 3: GitHub Actions on Ubuntu, macOS and Windows
**Files:** `.github/workflows/tests.yml`
- [ ] Push. Read the runs through the REST API. Fix until all three are green.

### Task 4: Docs, PR, merge
**Files:** HANDOFF (Mac/Windows setup, 1 page), README, PRD (platform line, 2 pages), VIDEO-OUTLINE, PDFs.
- [ ] Rebuild the PDFs and check page counts. Open the PR, merge into `main`.
