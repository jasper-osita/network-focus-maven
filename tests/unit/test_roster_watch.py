import json
import os

import pytest

from nf_core.workspace import save_settings
from roster_watch import RosterWatch

T = 1_800_000_000.0  # a fixed "now"


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "NF"
    (h / "inbox").mkdir(parents=True)
    (h / "briefs").mkdir()
    snap = h / "briefs" / "2026-11-23-network-focus.json"
    snap.write_text(json.dumps({"week_of": "2026-11-23", "brief": {"focus": []}, "roster_index": {}}), encoding="utf-8")
    os.utime(snap, (T - 3600, T - 3600))
    return h


class Diff:
    def __init__(self, result=None):
        self.calls, self.result = [], result or {"ok": True, "file": "r.xlsx", "new": [{"row_id": 26, "name": "Ana Ruiz", "company": "a16z"}],
                                                 "changed": [], "removed": []}

    def __call__(self, roster, snapshot):
        self.calls.append((roster, snapshot))
        return self.result


def put(folder, name="roster.xlsx", mtime=T):
    f = folder / name
    f.write_bytes(b"x")
    os.utime(f, (mtime, mtime))
    return f


def test_watch_waits_for_steady_file(home):
    put(home / "inbox")
    diff = Diff()
    w = RosterWatch(home, diff, interval=120)
    w.check_once(T)
    assert diff.calls == [] and w.state() == {"changes": None}
    w.check_once(T + 120)
    assert len(diff.calls) == 1 and diff.calls[0][0] == home / "inbox" / "roster.xlsx"
    ch = w.state()["changes"]
    assert ch["new"][0]["name"] == "Ana Ruiz" and ch["file"] == "roster.xlsx" and ch["modified"] == T


def test_watch_old_file_is_steady_at_once(home):
    put(home / "inbox", mtime=T - 600)
    diff = Diff()
    RosterWatch(home, diff, interval=120).check_once(T)
    assert len(diff.calls) == 1


def test_watch_ignores_lock_files(home):
    put(home / "inbox", "~$roster.xlsx", mtime=T - 600)
    put(home / "inbox", ".hidden.csv", mtime=T - 600)
    diff = Diff()
    w = RosterWatch(home, diff, interval=120)
    w.check_once(T)
    assert diff.calls == [] and w.state() == {"changes": None}


def test_watch_no_repeat_diff(home):
    put(home / "inbox", mtime=T - 600)
    diff = Diff()
    w = RosterWatch(home, diff, interval=120)
    for t in (T, T + 120, T + 240):
        w.check_once(t)
    assert len(diff.calls) == 1


def test_watch_rediffs_after_new_snapshot(home):
    put(home / "inbox", mtime=T - 600)
    diff = Diff()
    w = RosterWatch(home, diff, interval=120)
    w.check_once(T)
    os.utime(home / "briefs" / "2026-11-23-network-focus.json", (T, T))
    w.check_once(T + 120)
    assert len(diff.calls) == 2


def test_watch_survives_missing_folder(home, tmp_path):
    save_settings(home, {"roster_folder": str(tmp_path / "gone")})
    diff = Diff()
    w = RosterWatch(home, diff, interval=120)
    w.check_once(T)
    assert diff.calls == [] and w.state() == {"changes": None}


def test_watch_reads_drive_folder(home, tmp_path):
    folder = tmp_path / "Drive"
    folder.mkdir()
    put(folder, mtime=T - 600)
    save_settings(home, {"roster_folder": str(folder)})
    diff = Diff()
    RosterWatch(home, diff, interval=120).check_once(T)
    assert diff.calls[0][0] == folder / "roster.xlsx"


def test_watch_reports_none_when_nothing_new(home):
    put(home / "inbox", mtime=T - 600)
    w = RosterWatch(home, Diff({"ok": True, "file": "roster.xlsx", "new": [], "changed": [], "removed": [{"name": "X"}]}), interval=120)
    w.check_once(T)
    assert w.state() == {"changes": None}


def test_watch_no_snapshot_no_diff(home):
    (home / "briefs" / "2026-11-23-network-focus.json").unlink()
    put(home / "inbox", mtime=T - 600)
    diff = Diff()
    w = RosterWatch(home, diff, interval=120)
    w.check_once(T)
    assert diff.calls == [] and w.state() == {"changes": None}


def test_watch_diff_error_is_contained(home):
    put(home / "inbox", mtime=T - 600)

    def boom(roster, snapshot):
        raise RuntimeError("uv missing")
    w = RosterWatch(home, boom, interval=120)
    w.check_once(T)
    assert w.state() == {"changes": None}


def test_watch_rediffs_after_folder_blip(home):
    f = put(home / "inbox", mtime=T - 600)
    diff = Diff()
    w = RosterWatch(home, diff, interval=120)
    w.check_once(T)
    f.rename(home / "away.xlsx")                       # Drive unmounted while the laptop slept
    w.check_once(T + 120)
    assert w.state() == {"changes": None}
    (home / "away.xlsx").rename(f)
    w.check_once(T + 240)
    assert len(diff.calls) == 2 and w.state()["changes"] is not None


def test_watch_retries_failed_diff(home):
    put(home / "inbox", mtime=T - 600)
    results = [{"ok": False, "reason": "error"}, Diff().result]
    calls = []

    def flaky(roster, snap):
        calls.append(roster)
        return results[len(calls) - 1]
    w = RosterWatch(home, flaky, interval=120)
    w.check_once(T)
    w.check_once(T + 120)
    assert len(calls) == 2 and w.state()["changes"]["new"][0]["name"] == "Ana Ruiz"
