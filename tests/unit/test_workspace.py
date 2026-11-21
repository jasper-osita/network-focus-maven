import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest

from conftest import HEADERS, ROOT, TEMPLATE_GOALS
from nf_core.workspace import Workspace, fingerprint, pick_roster, staleness_issues, week_of

SCRIPT = ROOT / "plugins" / "network-focus" / "scripts" / "load_roster.py"


def run_cli(home: Path, *args):
    p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                       env={**os.environ, "NF_HOME": str(home)})
    return p.returncode, json.loads(p.stdout.strip().splitlines()[-1]), p.stdout


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "Network Focus"
    (h / "inbox").mkdir(parents=True)
    (h / "briefs").mkdir()
    shutil.copy(TEMPLATE_GOALS, h / "goals.md")
    return h


def test_week_of():
    assert week_of(date(2026, 11, 23)) == date(2026, 11, 23)
    assert week_of(date(2026, 11, 25)) == date(2026, 11, 23)
    assert week_of(date(2026, 11, 21)) == date(2026, 11, 23)


def test_first_run_creates_folder(tmp_path):
    h = tmp_path / "Network Focus"
    code, out, _ = run_cli(h)
    assert code == 3 and out["status"] == "setup"
    assert (h / "goals.md").read_text() == TEMPLATE_GOALS.read_text()
    assert (h / "inbox").is_dir() and (h / "briefs").is_dir()
    assert "inbox" in out["message"]


def test_picks_newest_ignoring_lock_files(home, sample_xlsx):
    real = home / "inbox" / "real.xlsx"
    shutil.copy(sample_xlsx, real)
    os.utime(real, (time.time() - 100, time.time() - 100))
    (home / "inbox" / "~$real.xlsx").write_bytes(b"lock")
    (home / "inbox" / ".DS_Store").write_bytes(b"x")
    path, issues = pick_roster(Workspace(home), None)
    assert path == real and issues == []


def test_multiple_files_info(home, sample_xlsx):
    old, new = home / "inbox" / "old.xlsx", home / "inbox" / "new.xlsx"
    shutil.copy(sample_xlsx, old)
    shutil.copy(sample_xlsx, new)
    os.utime(old, (time.time() - 200, time.time() - 200))
    path, issues = pick_roster(Workspace(home), None)
    assert path == new and [i.code for i in issues] == ["MULTIPLE_FILES"] and "new.xlsx" in issues[0].message


def test_no_spreadsheet_blocks(home):
    code, out, _ = run_cli(home)
    assert code == 2 and out["status"] == "blocked" and str(home / "inbox") in out["message"]


def test_explicit_path_used(home, sample_xlsx):
    code, out, _ = run_cli(home, "--roster", str(sample_xlsx))
    assert code == 0 and out["status"] == "ok" and out["contacts"] == 25
    r = json.loads((home / ".work" / "roster.json").read_text())
    assert r["source"]["file_name"] == "network_roster_terragrid.xlsx"


def test_stale_file_warns(tmp_path, sample_xlsx):
    p = tmp_path / "r.xlsx"
    shutil.copy(sample_xlsx, p)
    ten_days_ago = time.time() - 10 * 86400
    os.utime(p, (ten_days_ago, ten_days_ago))
    as_of = date.fromtimestamp(ten_days_ago)
    issues = staleness_issues(p, fingerprint(p), [], date.today())
    assert [i.code for i in issues] == ["STALE_FILE"] and i_warn(issues)
    assert f"{as_of:%b} {as_of.day}" in issues[0].message


def i_warn(issues):
    return all(i.severity == "warn" for i in issues)


def test_reused_file_warns(tmp_path, sample_xlsx):
    p = tmp_path / "r.xlsx"
    shutil.copy(sample_xlsx, p)
    sha = fingerprint(p)
    last_week = [{"sha256": sha, "file_name": "r.xlsx", "run_date": "2026-11-16", "brief": "x.pdf"}]
    issues = staleness_issues(p, sha, last_week, date(2026, 11, 23))
    assert "REUSED_FILE" in [i.code for i in issues] and i_warn(issues)
    same_week = [{"sha256": sha, "file_name": "r.xlsx", "run_date": "2026-11-23", "brief": "x.pdf"}]
    assert "REUSED_FILE" not in [i.code for i in staleness_issues(p, sha, same_week, date(2026, 11, 25))]


def test_outputs_written(home, sample_xlsx):
    shutil.copy(sample_xlsx, home / "inbox")
    code, out, _ = run_cli(home, "--today", "2026-11-23")
    assert code == 0
    work = home / ".work"
    r = json.loads((work / "roster.json").read_text())
    assert len(r["contacts"]) == 25 and len(r["goals"]) == 3 and len(r["source"]["sha256"]) == 64
    assert r["source"]["week_of"] == "2026-11-23"
    assert r["contacts"][4]["name"] == "Reid Hoffman" and r["contacts"][4]["flags"]["dormant"] is True
    assert "Asked to see the full pitch." in r["contacts"][0]["text"]
    codes = {w["code"] for w in json.loads((work / "warnings.json").read_text())["warnings"]}
    assert {"GOAL_ORG_MISSING", "GOAL_CONTRADICTION", "AMBIGUOUS_REFERENCE"} <= codes


def test_blocking_error_message_plain(home, make_roster):
    bad = make_roster([["Marcus Wei"] + [""] * 8], headers=[h for h in HEADERS if h != "Notes"])
    code, out, raw = run_cli(home, "--roster", str(bad))
    assert code == 2 and "Traceback" not in raw and "Notes" in out["message"]


def test_clears_previous_work(home, sample_xlsx):
    (home / ".work").mkdir()
    (home / ".work" / "brief.json").write_text("{}")
    code, _, _ = run_cli(home, "--roster", str(sample_xlsx))
    assert code == 0 and not (home / ".work" / "brief.json").exists()
