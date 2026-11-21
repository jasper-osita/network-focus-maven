import http.client
import json
import shutil
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
    cfg = AppConfig(port=0, token=TOKEN, nf_home=home, claude_path=FAKE, claude_args=[], uv_path="uv",
                    scripts_dir=ROOT / "plugins" / "network-focus" / "scripts")
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
