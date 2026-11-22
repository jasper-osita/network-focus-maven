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
    assert all(v == "ok" for k, v in s.items() if k not in ("Claude command-line tool", "Network Focus page"))
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
