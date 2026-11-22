import json
import os
import shutil
import subprocess
import sys

import pytest

from check_setup import setup_checks
from conftest import HEADERS, ROOT, TEMPLATE_GOALS

CLI = ROOT / "plugins" / "network-focus" / "scripts" / "check_setup.py"
FREE_PORT = 59999  # nothing listens here in tests


@pytest.fixture
def home(tmp_path, sample_xlsx):
    h = tmp_path / "Network Focus"
    (h / "inbox").mkdir(parents=True)
    (h / "briefs").mkdir()
    shutil.copy(TEMPLATE_GOALS, h / "goals.md")
    shutil.copy(sample_xlsx, h / "inbox")
    return h


def status(results):
    return {r.name: r.status for r in results}


def test_healthy_workspace(home):
    r = setup_checks(home, port=FREE_PORT)
    s = status(r)
    assert all(v == "ok" for k, v in s.items() if k not in ("Claude command-line tool", "Network Focus page", "Google Drive folder"))
    assert s["Google Drive folder"] == "info"  # no Drive set up: rosters come from the local inbox
    assert s["Network Focus page"] == "info"
    assert "3 goals" in next(x.detail for x in r if x.name == "goals.md")
    assert "saved today" in next(x.detail for x in r if x.name == "Spreadsheet in inbox")


def test_missing_goals_restored(home):
    (home / "goals.md").unlink()
    g = next(x for x in setup_checks(home, port=FREE_PORT) if x.name == "goals.md")
    assert g.status == "ok" and "starter goals" in g.detail and (home / "goals.md").exists()


def test_empty_existing_folder_has_no_failures(tmp_path):
    h = tmp_path / "Network Focus"
    h.mkdir()
    r = setup_checks(h, port=FREE_PORT)
    assert [x.name for x in r if x.status == "fail"] == []
    assert (h / "inbox").is_dir() and (h / "goals.md").exists()
    assert next(x for x in r if x.name == "Spreadsheet in inbox").status == "info"


def test_bad_spreadsheet_names_column(home, make_roster):
    for f in (home / "inbox").iterdir():
        f.unlink()
    bad = make_roster([["Marcus Wei"] + [""] * 8], headers=[h for h in HEADERS if h != "Notes"])
    shutil.copy(bad, home / "inbox")
    c = next(x for x in setup_checks(home, port=FREE_PORT) if x.name == "Spreadsheet columns")
    assert c.status == "fail" and "Notes" in c.detail


def test_missing_folder(tmp_path):
    r = setup_checks(tmp_path / "nope", port=FREE_PORT)
    assert r[0].name == "Network Focus folder" and r[0].status == "fail" and r[0].fix


def test_cli_output_and_json(home):
    env = {**os.environ, "NF_HOME": str(home)}
    p = subprocess.run([sys.executable, str(CLI), "--port", str(FREE_PORT)], capture_output=True, text=True, encoding="utf-8", env=env)
    lines = [l for l in p.stdout.splitlines() if l and not l.startswith("   ")]
    assert p.returncode == 0 and lines and all(l[0] in "✅❌ℹ" for l in lines)
    j = subprocess.run([sys.executable, str(CLI), "--json", "--port", str(FREE_PORT)], capture_output=True, text=True, encoding="utf-8", env=env)
    data = json.loads(j.stdout)
    assert {"name", "status", "detail", "fix"} <= set(data[0])


# ---- Google Drive folder ----
from nf_core.workspace import save_settings  # noqa: E402


def _line(results, name):
    return next(r for r in results if r.name == name)


def test_check_drive_ok(home, tmp_path, sample_xlsx):
    folder = tmp_path / "Drive" / "Network Focus"
    folder.mkdir(parents=True)
    shutil.copy(sample_xlsx, folder)
    save_settings(home, {"roster_folder": str(folder)})
    r = _line(setup_checks(home, FREE_PORT), "Google Drive folder")
    assert r.status == "ok" and str(folder) in r.detail


def test_check_drive_not_set_up(home):
    assert _line(setup_checks(home, FREE_PORT), "Google Drive folder").status == "info"


def test_check_drive_missing(home, tmp_path):
    save_settings(home, {"roster_folder": str(tmp_path / "gone")})
    r = _line(setup_checks(home, FREE_PORT), "Google Drive folder")
    assert r.status == "fail" and r.fix == "Open Google Drive for desktop and check you're signed in."


def test_check_spreadsheet_google_sheet(home, tmp_path):
    folder = tmp_path / "Drive" / "Network Focus"
    folder.mkdir(parents=True)
    (folder / "Roster.gsheet").write_text("{}", encoding="utf-8")
    save_settings(home, {"roster_folder": str(folder)})
    r = _line(setup_checks(home, FREE_PORT), "Spreadsheet in inbox")
    assert r.status == "fail" and "Microsoft Excel" in r.fix


def test_check_drive_no_access(home, tmp_path, monkeypatch):
    import pathlib
    folder = tmp_path / "Drive" / "Network Focus"
    folder.mkdir(parents=True)
    save_settings(home, {"roster_folder": str(folder)})
    real = pathlib.Path.is_dir
    monkeypatch.setattr(pathlib.Path, "is_dir", lambda self: (_ for _ in ()).throw(PermissionError(1, "denied"))
                        if self == folder else real(self))
    results = setup_checks(home, FREE_PORT)
    r = _line(results, "Google Drive folder")
    assert r.status == "fail" and "Privacy & Security" in r.fix
