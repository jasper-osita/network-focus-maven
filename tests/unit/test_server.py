import http.client
import json
import shutil
import sys
import threading
from pathlib import Path

import pytest

from conftest import ROOT, TEMPLATE_GOALS
from server import AppConfig, make_server

FAKE = str(Path(__file__).parent / "fake_claude.py")
TOKEN = "t" * 40


@pytest.fixture
def server(tmp_path, monkeypatch):
    home = tmp_path / "Network Focus"
    (home / "inbox").mkdir(parents=True)
    (home / "briefs").mkdir()
    shutil.copy(TEMPLATE_GOALS, home / "goals.md")
    shutil.copy(ROOT / "sample-data" / "network_roster_terragrid.xlsx", home / "inbox")
    fake = FAKE
    if sys.platform == "win32":  # Windows can't run a .py file directly
        fake = str(tmp_path / "fake_claude.cmd")
        Path(fake).write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n')
    cfg = AppConfig(port=0, token=TOKEN, nf_home=home, claude_path=fake, claude_args=[], uv_path="uv", log_dir=tmp_path / "logs",
                    scripts_dir=ROOT / "plugins" / "network-focus" / "scripts", watch_interval=0)
    srv = make_server(cfg)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(srv, method, path, *, host=None, cookie=True, origin=True, body=None, headers=None):
    port = srv.cfg.port
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", host or f"127.0.0.1:{port}")
    if cookie:
        conn.putheader("Cookie", f"nf_token={TOKEN}")
    if origin and method == "POST":
        conn.putheader("Origin", f"http://127.0.0.1:{port}")
    for k, v in (headers or {}).items():
        conn.putheader(k, v)
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else b"")
    conn.putheader("Content-Length", str(len(data)))
    conn.endheaders(data)
    r = conn.getresponse()
    return r.status, r.read(), dict(r.getheaders())


def sse(srv, run_id):
    _, raw, _ = call(srv, "GET", f"/api/run/{run_id}/events")
    return [json.loads(line[6:]) for line in raw.decode().splitlines() if line.startswith("data: ")]


def test_health_needs_nothing(server):
    assert call(server, "GET", "/health", cookie=False)[0] == 200


def test_rejects_wrong_host(server):
    assert call(server, "GET", "/api/status", host="evil.com")[0] == 403


def test_api_requires_token(server):
    assert call(server, "GET", "/api/status", cookie=False)[0] == 401
    status, body, _ = call(server, "GET", "/api/status")
    data = json.loads(body)
    assert status == 200 and data["inbox"][0]["name"] == "network_roster_terragrid.xlsx" and data["running"] is False


def test_index_sets_cookie(server):
    assert call(server, "GET", "/", cookie=False)[0] == 401
    status, body, headers = call(server, "GET", f"/?t={TOKEN}", cookie=False)
    assert status == 200 and b"Generate this week" in body
    assert "nf_token=" in headers["Set-Cookie"] and "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]


def test_post_requires_origin(server):
    assert call(server, "POST", "/api/run", origin=False, headers={"Origin": "https://evil.com"}, body={})[0] == 403


def test_upload_rules(server):
    assert call(server, "POST", "/api/upload", body=b"x", headers={"X-Filename": "virus.exe"})[0] == 400
    assert call(server, "POST", "/api/upload", body=b"x" * (11 * 1024 * 1024), headers={"X-Filename": "big.xlsx"})[0] == 413
    status, _, _ = call(server, "POST", "/api/upload", body=b"Name,Role\n", headers={"X-Filename": "../ok.csv"})
    assert status == 200 and (server.cfg.nf_home / "inbox" / "ok.csv").exists()


def test_path_traversal_blocked(server):
    assert call(server, "GET", "/briefs/../goals.md")[0] == 404
    assert call(server, "GET", "/briefs/%2e%2e%2fgoals.md")[0] == 404


def test_run_end_to_end_with_fake_claude(server):
    status, body, _ = call(server, "POST", "/api/run", body={})
    assert status == 200
    events = sse(server, json.loads(body)["run_id"])
    steps = [e["step"] for e in events if "step" in e]
    assert steps[0] == "Checking the data" and steps[-1] == "Making the PDF" and "Fact-checking the picks" in steps
    assert events[-1]["status"] == "done" and events[-1]["pdf_url"] == "/briefs/2026-11-23-network-focus.pdf"
    status, pdf, _ = call(server, "GET", events[-1]["pdf_url"])
    assert status == 200 and pdf.startswith(b"%PDF")


def test_single_run_at_a_time(server, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "slow")
    first = call(server, "POST", "/api/run", body={})
    assert first[0] == 200
    assert call(server, "POST", "/api/run", body={})[0] == 409
    sse(server, json.loads(first[1])["run_id"])  # let it finish


def test_signed_out_message(server, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "signed_out")
    _, body, _ = call(server, "POST", "/api/run", body={})
    final = sse(server, json.loads(body)["run_id"])[-1]
    assert final["status"] == "failed" and "signed out" in final["message"]


def test_check_endpoint(server):
    status, body, _ = call(server, "POST", "/api/check", body={})
    results = json.loads(body)["results"]
    assert status == 200 and any(r["name"] == "goals.md" and r["status"] == "ok" for r in results)


def test_hung_run_times_out_and_unlocks(server, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "hang")
    server.cfg.run_timeout = 2
    _, body, _ = call(server, "POST", "/api/run", body={})
    final = sse(server, json.loads(body)["run_id"])[-1]
    assert final["status"] == "failed" and "took too long" in final["message"]
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "ok")
    assert call(server, "POST", "/api/run", body={})[0] == 200


def test_bad_stream_lines_do_not_lock(server, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "weird")
    _, body, _ = call(server, "POST", "/api/run", body={})
    assert sse(server, json.loads(body)["run_id"])[-1]["status"] == "done"
    assert call(server, "POST", "/api/run", body={})[0] == 200


def test_upload_keeps_file_date(server):
    status, _, _ = call(server, "POST", "/api/upload", body=b"Name\n",
                        headers={"X-Filename": "dated.csv", "X-Last-Modified": "1700000000000"})
    assert status == 200 and int((server.cfg.nf_home / "inbox" / "dated.csv").stat().st_mtime) == 1700000000


def test_upload_non_ascii_name(server):
    status, _, _ = call(server, "POST", "/api/upload", body=b"Name\n",
                        headers={"X-Filename": "CEO%E2%80%99s%20network.csv"})
    assert status == 200 and (server.cfg.nf_home / "inbox" / "CEO\u2019s network.csv").exists()


def test_check_endpoint_survives_missing_uv(server):
    server.cfg.uv_path = "/nonexistent/uv"
    status, body, _ = call(server, "POST", "/api/check", body={})
    assert status == 200 and json.loads(body)["results"][0]["status"] == "fail"


def test_server_declares_python_version():
    assert 'requires-python = ">=3.11"' in (ROOT / "plugins" / "network-focus" / "app" / "server.py").read_text()


def put_snapshot(srv, brief_dict, roster_dict, warnings_dict):
    from nf_core.snapshot import build_snapshot
    snap = build_snapshot(brief_dict, roster_dict, warnings_dict)
    (srv.cfg.nf_home / "briefs" / f"{snap['week_of']}-network-focus.json").write_text(json.dumps(snap))


def test_dashboard_empty_then_filled(server, brief_dict, roster_dict, warnings_dict):
    status, body, _ = call(server, "GET", "/api/dashboard")
    assert status == 200 and json.loads(body) == {"empty": True}
    put_snapshot(server, brief_dict, roster_dict, warnings_dict)
    data = json.loads(call(server, "GET", "/api/dashboard")[1])
    assert data["top"]["name"] == "Diana Chen" and data["progress"]["total"] == 7


def test_dashboard_requires_token(server):
    assert call(server, "GET", "/api/dashboard", cookie=False)[0] == 401


def test_done_updates_progress(server, brief_dict, roster_dict, warnings_dict):
    put_snapshot(server, brief_dict, roster_dict, warnings_dict)
    status, body, _ = call(server, "POST", "/api/done", body={"row_id": 3, "done": True, "week_of": "2026-11-23"})
    assert status == 200 and json.loads(body)["progress"]["done"] == 1
    assert json.loads(call(server, "GET", "/api/dashboard")[1])["top"]["done"] is True


def test_done_rejects_unknown_row(server, brief_dict, roster_dict, warnings_dict):
    put_snapshot(server, brief_dict, roster_dict, warnings_dict)
    assert call(server, "POST", "/api/done", body={"row_id": 99, "done": True, "week_of": "2026-11-23"})[0] == 400
    assert call(server, "POST", "/api/done", body={"row_id": 3, "done": True})[0] == 400
    assert call(server, "POST", "/api/done", body={"row_id": 3, "done": True, "week_of": "2026-11-16"})[0] == 409
    assert call(server, "POST", "/api/done", body={"row_id": "3", "done": "yes"})[0] == 400
    assert call(server, "POST", "/api/done", body=b"{not json", headers={"Content-Type": "application/json"})[0] == 400


def test_done_requires_origin(server, brief_dict, roster_dict, warnings_dict):
    put_snapshot(server, brief_dict, roster_dict, warnings_dict)
    assert call(server, "POST", "/api/done", origin=False, headers={"Origin": "https://evil.com"},
                body={"row_id": 3, "done": True})[0] == 403


def test_index_has_both_tabs(server):
    status, body, _ = call(server, "GET", f"/?t={TOKEN}", cookie=False)
    page = body.decode()
    assert status == 200 and "This week" in page and "Make the brief" in page
    assert 'id="ring"' in page and "Copy message" in page and "Generate this week" in page
    assert 'id="heroMessage"' in page and "Preview" in page


def test_quit_endpoint_stops_server(server):
    assert call(server, "POST", "/api/quit", origin=False, body={})[0] == 403
    assert call(server, "POST", "/api/quit", body={})[0] == 200
    import time
    deadline = time.time() + 3
    while time.time() < deadline:
        try:
            call(server, "GET", "/health", cookie=False)
            time.sleep(0.1)
        except OSError:
            return
    raise AssertionError("server still answering after /api/quit")


def test_failed_run_explains_and_keeps_a_log(server, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error")
    _, body, _ = call(server, "POST", "/api/run", body={})
    final = sse(server, json.loads(body)["run_id"])[-1]
    assert final["status"] == "failed" and "usage limit" in final["message"]
    log = Path(final["log"])
    assert log.exists() and "error_during_execution" in log.read_text(encoding="utf-8") and "429" in log.read_text(encoding="utf-8")


# ---- Google Drive folder ----
def use_drive(srv, tmp_path):
    from nf_core.workspace import save_settings
    folder = tmp_path / "Drive" / "Network Focus"
    folder.mkdir(parents=True)
    shutil.copy(ROOT / "sample-data" / "network_roster_terragrid.xlsx", folder / "drive-roster.xlsx")
    save_settings(srv.cfg.nf_home, {"roster_folder": str(folder)})
    return folder


def test_status_lists_drive_folder(server, tmp_path):
    use_drive(server, tmp_path)
    data = json.loads(call(server, "GET", "/api/status")[1])
    assert [f["name"] for f in data["inbox"]] == ["drive-roster.xlsx"]


def test_upload_saves_into_drive_folder(server, tmp_path):
    folder = use_drive(server, tmp_path)
    assert call(server, "POST", "/api/upload", body=b"Name\n", headers={"X-Filename": "new.csv"})[0] == 200
    assert (folder / "new.csv").exists() and not (server.cfg.nf_home / "inbox" / "new.csv").exists()


def test_run_passes_drive_file(server, tmp_path):
    folder = use_drive(server, tmp_path)
    _, body, _ = call(server, "POST", "/api/run", body={"file": "drive-roster.xlsx"})
    sse(server, json.loads(body)["run_id"])
    argv = json.loads((server.cfg.nf_home / ".fake-argv.json").read_text(encoding="utf-8"))
    assert str(folder / "drive-roster.xlsx") in argv[1]


def test_index_has_goal_rings(server):
    page = call(server, "GET", f"/?t={TOKEN}", cookie=False)[1].decode()
    assert 'id="goalRings"' in page and 'id="considering"' in page


def test_roster_changes_endpoint(server, brief_dict, roster_dict, warnings_dict):
    assert call(server, "GET", "/api/roster-changes", cookie=False)[0] == 401
    assert json.loads(call(server, "GET", "/api/roster-changes")[1]) == {"changes": None}
    put_snapshot(server, brief_dict, roster_dict, warnings_dict)
    server.watch.run_diff = lambda roster, snap: {"ok": True, "file": roster.name, "changed": [], "removed": [],
                                                  "new": [{"row_id": 26, "name": "Ana Ruiz", "company": "a16z"}]}
    import time
    server.watch.check_once(time.time() + 1000)
    data = json.loads(call(server, "GET", "/api/roster-changes")[1])
    assert [p["name"] for p in data["changes"]["new"]] == ["Ana Ruiz"]


def test_index_has_roster_line(server):
    page = call(server, "GET", f"/?t={TOKEN}", cookie=False)[1].decode()
    assert 'id="rosterLine"' in page and 'id="updateBtn"' in page


# ---- Update ----
def put_current_snapshot(srv, brief_dict, roster_dict, warnings_dict, weeks_back=0):
    from datetime import date, timedelta
    from dashboard_data import week_of
    brief_dict["week_of"] = (week_of(date.today()) - timedelta(days=7 * weeks_back)).isoformat()
    put_snapshot(srv, brief_dict, roster_dict, warnings_dict)


def stub_changes(srv):
    import time
    srv.watch.run_diff = lambda roster, snap: {"ok": True, "file": roster.name, "changed": [], "removed": [],
                                               "new": [{"row_id": 26, "name": "Ana Ruiz", "company": "a16z"}]}
    srv.watch.check_once(time.time() + 1000)


def test_update_refused_when_nothing_changed(server, brief_dict, roster_dict, warnings_dict):
    put_current_snapshot(server, brief_dict, roster_dict, warnings_dict)
    status, body, _ = call(server, "POST", "/api/run", body={"mode": "update"})
    assert status == 409 and json.loads(body)["message"] == "Nobody new or changed since this week's brief."


def test_update_refused_when_brief_is_stale(server, brief_dict, roster_dict, warnings_dict):
    put_current_snapshot(server, brief_dict, roster_dict, warnings_dict, weeks_back=1)
    stub_changes(server)
    status, body, _ = call(server, "POST", "/api/run", body={"mode": "update"})
    assert status == 409 and "Click Generate" in json.loads(body)["message"]


def test_unknown_run_mode_400(server):
    assert call(server, "POST", "/api/run", body={"mode": "delete-everything"})[0] == 400


def test_update_run_uses_update_skill(server, monkeypatch, brief_dict, roster_dict, warnings_dict):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "update")
    put_current_snapshot(server, brief_dict, roster_dict, warnings_dict)
    stub_changes(server)
    status, body, _ = call(server, "POST", "/api/run", body={"mode": "update"})
    assert status == 200
    events = sse(server, json.loads(body)["run_id"])
    assert events[-1]["status"] == "done" and "Looking at who's new" in [e.get("step") for e in events]
    argv = json.loads((server.cfg.nf_home / ".fake-argv.json").read_text(encoding="utf-8"))
    assert argv[1] == "/network-focus:update"


def test_status_survives_unreadable_drive(server, tmp_path, monkeypatch):
    import pathlib
    folder = use_drive(server, tmp_path)
    real = pathlib.Path.glob
    monkeypatch.setattr(pathlib.Path, "glob", lambda self, pat: (_ for _ in ()).throw(PermissionError(1, "denied"))
                        if self == folder else real(self, pat))
    status, body, _ = call(server, "GET", "/api/status")
    assert status == 200 and json.loads(body)["inbox"] == []


# ---- spreadsheet tab and write-back ----
def test_sheet_endpoint_reads_and_writes(server):
    data = json.loads(call(server, "GET", "/api/sheet")[1])
    assert data["ok"] is True and len(data["rows"]) == 25 and data["rows"][0]["done"] == ""
    status, body, _ = call(server, "POST", "/api/sheet", body={"name": "Diana Chen", "company": "Stripe", "done": True,
                                                               "comment": "Asked for intros."})
    assert status == 200 and json.loads(body)["ok"] is True
    diana = next(r for r in json.loads(call(server, "GET", "/api/sheet")[1])["rows"] if r["name"] == "Diana Chen")
    assert diana["done"] and diana["comments"] == "Asked for intros."
    assert call(server, "POST", "/api/sheet", body={"name": "Diana Chen"})[0] == 400


def test_done_also_marks_the_sheet(server, brief_dict, roster_dict, warnings_dict):
    put_current_snapshot(server, brief_dict, roster_dict, warnings_dict)
    from datetime import date
    from dashboard_data import week_of
    status, body, _ = call(server, "POST", "/api/done", body={"row_id": 3, "done": True, "week_of": week_of(date.today()).isoformat()})
    assert status == 200 and json.loads(body)["sheet"]["ok"] is True
    diana = next(r for r in json.loads(call(server, "GET", "/api/sheet")[1])["rows"] if r["name"] == "Diana Chen")
    assert diana["done"]


def test_index_has_sheet_tab(server):
    page = call(server, "GET", f"/?t={TOKEN}", cookie=False)[1].decode()
    assert 'id="tabSheet"' in page and 'id="sheetTable"' in page


def test_done_refreshes_the_live_dashboard_file(server, tmp_path, brief_dict, roster_dict, warnings_dict):
    from datetime import date
    from dashboard_data import DASHBOARD_FILE, week_of
    folder = use_drive(server, tmp_path)
    put_current_snapshot(server, brief_dict, roster_dict, warnings_dict)
    call(server, "POST", "/api/done", body={"row_id": 3, "done": True, "week_of": week_of(date.today()).isoformat()})
    data = json.loads((folder / DASHBOARD_FILE).read_text(encoding="utf-8"))
    assert data["top"]["name"] == "Diana Chen" and data["top"]["done"] is True


# ---- calendar ----
def test_dashboard_has_times_and_they_can_change(server, brief_dict, roster_dict, warnings_dict):
    from datetime import date
    from dashboard_data import week_of
    put_current_snapshot(server, brief_dict, roster_dict, warnings_dict)
    week = week_of(date.today()).isoformat()
    top = json.loads(call(server, "GET", "/api/dashboard")[1])["top"]
    assert top["when"].startswith(week) and top["kind"] in ("call", "email")
    status, _, _ = call(server, "POST", "/api/schedule", body={"row_id": 3, "week_of": week, "when": week + "T16:30", "kind": "call"})
    top = json.loads(call(server, "GET", "/api/dashboard")[1])["top"]
    assert status == 200 and top["when"] == week + "T16:30" and top["kind"] == "call"
    assert call(server, "POST", "/api/schedule", body={"row_id": 3, "week_of": week, "when": "next tuesday"})[0] == 400
    assert call(server, "POST", "/api/schedule", body={"row_id": 99, "week_of": week, "when": week + "T10:00"})[0] == 400


def test_ics_download(server, brief_dict, roster_dict, warnings_dict):
    put_current_snapshot(server, brief_dict, roster_dict, warnings_dict)
    status, body, headers = call(server, "GET", "/api/ics?row_id=3")
    assert status == 200 and headers["Content-Type"].startswith("text/calendar") and "attachment" in headers["Content-Disposition"]
    assert b"SUMMARY:" in body and b"Diana Chen" in body
    assert call(server, "GET", "/api/ics?row_id=3", cookie=False)[0] == 401


def test_index_has_calendar_tab(server):
    page = call(server, "GET", f"/?t={TOKEN}", cookie=False)[1].decode()
    assert 'id="tabCalendar"' in page and 'id="calendarWeek"' in page


def test_page_script_parses():
    """A clashing name or typo in index.html's script blanks the whole page; Python tests alone wouldn't notice."""
    import shutil as sh
    import subprocess as sp
    node = sh.which("node")
    if not node:
        pytest.skip("node isn't installed")
    html = (ROOT / "plugins" / "network-focus" / "app" / "index.html").read_text(encoding="utf-8")
    script = html.split("<script>")[1].split("</script>")[0]
    r = sp.run([node, "-e", "new Function(require('fs').readFileSync(0, 'utf8'))"], input=script, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
