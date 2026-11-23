# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Network Focus page: a tiny local web server (Python standard library only) that runs the same
/network-focus:brief skill in the background with `claude -p`, and shows progress and the PDF.

Security: listens on 127.0.0.1 only; rejects requests whose Host or Origin isn't this page; every API call
needs the setup token (from the Desktop link, then an HttpOnly cookie); one run at a time."""
import argparse
import hmac
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import date
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from dashboard_data import dashboard_payload, export_dashboard, roster_dir, set_done
from progress import failure_message, progress_from_event
from roster_watch import RosterWatch
from schedule import ics_for, set_when, valid_when

HERE = Path(__file__).resolve().parent
MAX_UPLOAD = 10 * 1024 * 1024
DRAIN_LIMIT = 50 * 1024 * 1024
UPLOAD_SUFFIXES = (".xlsx", ".csv")
DEFAULT_CLAUDE_ARGS = ["--output-format", "stream-json", "--verbose", "--permission-mode", "dontAsk",
                       "--allowedTools", "Read,Write,Edit,Bash(uv run *),Agent,Task"]


@dataclass
class AppConfig:
    port: int
    token: str
    nf_home: Path
    claude_path: str
    claude_args: list[str] = field(default_factory=lambda: list(DEFAULT_CLAUDE_ARGS))
    uv_path: str = "uv"
    scripts_dir: Path = HERE / "scripts"
    run_timeout: int = 900  # seconds; a hung run is stopped so the page never stays locked
    log_dir: Path = HERE / "logs"  # last-run.log: the full record of the latest run, for troubleshooting
    watch_interval: int = 120  # seconds between roster-folder checks; 0 turns the background check off (tests)

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(port=d["port"], token=d["token"], nf_home=Path(d["nf_home"]), claude_path=d["claude_path"],
                   claude_args=d.get("claude_args", list(DEFAULT_CLAUDE_ARGS)), uv_path=d.get("uv_path", "uv"),
                   scripts_dir=Path(d.get("scripts_dir", HERE / "scripts")), run_timeout=d.get("run_timeout", 900),
                   log_dir=Path(d.get("log_dir", HERE / "logs")), watch_interval=d.get("watch_interval", 120))


def _start_tree(cmd: list[str], **kw) -> subprocess.Popen:
    """Start `cmd` in its own process group so a hung run can be stopped with everything it started."""
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(cmd, **kw)


def _kill_tree(p: subprocess.Popen) -> None:
    """Killing only the parent can leave a child holding the output pipe open (always so on Windows .cmd shims)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=10)
        else:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        try:
            p.kill()
        except OSError:
            pass


RUN_MODES = ("brief", "update")


class Run:
    def __init__(self, cfg: AppConfig, file: str | None, mode: str = "brief", on_done=None):
        self.id, self.cfg, self.file = uuid.uuid4().hex[:12], cfg, file
        self.mode, self.on_done = mode, on_done
        self.events: list[dict] = []
        self.done = False
        self.lock = threading.Lock()

    def add(self, ev: dict) -> None:
        with self.lock:
            self.events.append(ev)

    def start(self) -> None:
        threading.Thread(target=self._go, daemon=True).start()

    def _go(self) -> None:
        cfg, started = self.cfg, time.time()
        if self.mode == "update":
            prompt = "/network-focus:update"
        else:
            prompt = "/network-focus:brief" + (f" {roster_dir(cfg.nf_home) / self.file}" if self.file else "")
        button = "Update" if self.mode == "update" else "Generate"
        result_text, stderr, last, timed_out, final = "", "", None, threading.Event(), {}
        log_path = cfg.log_dir / "last-run.log"
        try:
            cfg.log_dir.mkdir(parents=True, exist_ok=True)
            log = open(log_path, "w", encoding="utf-8")
        except OSError:
            log = None
        try:
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as err:  # a file, so a chatty stderr can't block stdout
                p = _start_tree([cfg.claude_path, "-p", prompt, *cfg.claude_args], cwd=cfg.nf_home,
                                     env={**os.environ, "NF_HOME": str(cfg.nf_home)}, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=err, text=True, encoding="utf-8", errors="replace")
                watchdog = threading.Timer(cfg.run_timeout, lambda: (timed_out.set(), _kill_tree(p)))
                watchdog.daemon = True
                watchdog.start()
                try:
                    for line in p.stdout:
                        if log:
                            log.write(line)
                        try:
                            ev = json.loads(line)
                        except ValueError:
                            continue
                        if not isinstance(ev, dict):
                            continue
                        if ev.get("type") == "result":
                            final = ev
                            result_text = str(ev.get("result", ""))
                        step = progress_from_event(ev)
                        if step and step != last:
                            self.add({"step": step})
                            last = step
                    p.wait()
                finally:
                    watchdog.cancel()
                err.seek(0)
                stderr = err.read()
        except OSError as e:
            stderr = str(e)
            result_text = "I couldn't start Claude. Click Check setup, or run /network-focus:setup-app again."
        except Exception as e:  # never leave the page locked
            stderr = repr(e)
            result_text = "Something went wrong making the brief. Click Generate to try again."
        finally:
            if log:
                try:
                    log.write(f"\n--- stderr ---\n{stderr}\n")
                    log.close()
                except OSError:
                    pass
            try:
                pdfs = sorted((f for f in (cfg.nf_home / "briefs").glob("*.pdf") if f.stat().st_mtime >= started - 1),
                              key=lambda f: f.stat().st_mtime)
                if timed_out.is_set():
                    self.add({"status": "failed", "message": "That took too long, so I stopped it. "
                                                             f"Click {button} to try again."})
                elif pdfs:
                    if self.on_done:
                        try:
                            self.on_done()  # e.g. re-check the roster so the "Roster updated" line clears now
                        except Exception:
                            pass
                    self.add({"status": "done", "pdf_url": f"/briefs/{pdfs[-1].name}", "summary": result_text})
                else:
                    self.add({"status": "failed", "message": failure_message(result_text, stderr, final),
                              "log": str(log_path)})
            finally:
                self.done = True


def diff_runner(cfg: AppConfig):
    """Runs roster_diff.py (it needs openpyxl, which this stdlib-only server doesn't have)."""
    def run(roster: Path, snapshot: Path) -> dict:
        try:
            p = subprocess.run([cfg.uv_path, "run", "--quiet", str(cfg.scripts_dir / "roster_diff.py"),
                                "--roster", str(roster), "--snapshot", str(snapshot)], capture_output=True, text=True,
                               encoding="utf-8", env={**os.environ, "NF_HOME": str(cfg.nf_home)}, timeout=120)
            return json.loads(p.stdout.strip().splitlines()[-1])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            return {"ok": False, "reason": "error"}
    return run


def sheet_cmd(cfg: AppConfig, args: list[str]) -> dict:
    """Runs sheet.py (it needs openpyxl, which this stdlib-only server doesn't have)."""
    try:
        p = subprocess.run([cfg.uv_path, "run", "--quiet", str(cfg.scripts_dir / "sheet.py"), *args], capture_output=True,
                           text=True, encoding="utf-8", env={**os.environ, "NF_HOME": str(cfg.nf_home)}, timeout=120)
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return {"ok": False, "message": "I couldn't reach the spreadsheet. Click Check setup to see what's wrong."}


def make_server(cfg: AppConfig) -> ThreadingHTTPServer:
    state = {"run": None, "runs": {}}
    state_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "NetworkFocus"

        def log_message(self, *a):  # keep the console quiet
            pass

        # --- guards -------------------------------------------------------------------------------
        def _hosts(self):
            return {f"127.0.0.1:{cfg.port}", f"localhost:{cfg.port}"}

        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in self._hosts()

        def _token_ok(self, query_token: str | None = None) -> bool:
            c = SimpleCookie(self.headers.get("Cookie", ""))
            given = query_token or (c["nf_token"].value if "nf_token" in c else "")
            return bool(given) and hmac.compare_digest(given, cfg.token)

        def _origin_ok(self) -> bool:
            return self.headers.get("Origin", "") in {f"http://{h}" for h in self._hosts()}

        # --- responses ----------------------------------------------------------------------------
        def _send(self, code: int, body: bytes = b"", ctype="application/json", extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj).encode())

        # --- GET ----------------------------------------------------------------------------------
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/health":
                return self._send(200, b"ok", "text/plain")
            if not self._host_ok():
                return self._send(403, b"forbidden", "text/plain")
            if url.path == "/":
                t = parse_qs(url.query).get("t", [None])[0]
                if not self._token_ok(t):
                    return self._send(401, b"Open Network Focus from the link on your Desktop.", "text/plain")
                cookie = f"nf_token={cfg.token}; HttpOnly; SameSite=Strict; Path=/"
                return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8",
                                  {"Set-Cookie": cookie})
            if not self._token_ok():
                return self._send(401, b"unauthorized", "text/plain")
            if url.path == "/api/status":
                try:
                    inbox = sorted((f for f in roster_dir(cfg.nf_home).glob("*") if f.suffix.lower() in UPLOAD_SUFFIXES
                                    and not f.name.startswith(("~$", "."))), key=lambda f: -f.stat().st_mtime)
                except OSError:  # Drive signed out, offline, or blocked by the Mac's privacy settings
                    inbox = []
                briefs = sorted((cfg.nf_home / "briefs").glob("*.pdf"), key=lambda f: -f.stat().st_mtime)
                run = state["run"]
                return self._json(200, {
                    "inbox": [{"name": f.name, "modified": time.strftime("%b %d, %Y", time.localtime(f.stat().st_mtime))}
                              for f in inbox],
                    "briefs": [{"name": f.name, "url": f"/briefs/{f.name}"} for f in briefs],
                    "running": bool(run and not run.done)})
            if url.path == "/api/sheet":
                return self._json(200, sheet_cmd(cfg, ["read"]))
            if url.path == "/api/ics":
                payload = dashboard_payload(cfg.nf_home, date.today())
                row = parse_qs(url.query).get("row_id", [""])[0]
                person = None if payload.get("empty") else next(
                    (p for p in [payload["top"], *payload["others"], *payload["dormant"]] if str(p["row_id"]) == row), None)
                if not person or not person.get("when"):
                    return self._send(404, b"not found", "text/plain")
                safe = "".join(ch for ch in f"{'Call' if person['kind'] == 'call' else 'Email'} {person['name']}"
                               if ch.isascii() and (ch.isalnum() or ch in " -")) or "Network Focus"
                body = ics_for(person, f"{payload['week_of']}-{person['row_id']}@network-focus").encode("utf-8")
                return self._send(200, body, "text/calendar; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="{safe}.ics"'})
            if url.path == "/api/roster-changes":
                return self._json(200, self.server.watch.state())
            if url.path == "/api/dashboard":
                return self._json(200, dashboard_payload(cfg.nf_home, date.today()))
            if url.path.startswith("/api/run/") and url.path.endswith("/events"):
                return self._events(url.path.split("/")[3])
            if url.path.startswith("/briefs/"):
                name = unquote(url.path[len("/briefs/"):])
                f = cfg.nf_home / "briefs" / name
                if "/" in name or "\\" in name or name.startswith(".") or not f.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctype = "application/pdf" if f.suffix == ".pdf" else "text/markdown; charset=utf-8"
                return self._send(200, f.read_bytes(), ctype)
            return self._send(404, b"not found", "text/plain")

        def _done(self, body: dict):
            row_id, done, week = body.get("row_id"), body.get("done"), body.get("week_of")
            if type(row_id) is not int or type(done) is not bool or not isinstance(week, str):
                return self._json(400, {"message": "Expected a row number, true/false and the week."})
            payload = dashboard_payload(cfg.nf_home, date.today())
            if payload.get("empty"):
                return self._json(400, {"message": "There's no brief yet."})
            if week != payload["week_of"]:
                return self._json(409, {"message": "A newer brief has been made. Reload the page."})
            picks = {p["row_id"]: p["name"] for p in [payload["top"], *payload["others"], *payload["dormant"]]}
            if row_id not in picks:
                return self._json(400, {"message": "That person isn't in this week's brief any more. Reload the page."})
            set_done(cfg.nf_home, payload["week_of"], row_id, done, picks[row_id])
            person = next(p for p in [payload["top"], *payload["others"], *payload["dormant"]] if p["row_id"] == row_id)
            sheet = sheet_cmd(cfg, ["set", "--name", person["name"], "--company", person.get("company", ""),
                                    "--done", "yes" if done else "no"])
            export_dashboard(cfg.nf_home, date.today())  # the CEO's live view reads this from Google Drive
            return self._json(200, {"progress": dashboard_payload(cfg.nf_home, date.today())["progress"], "sheet": sheet})

        def _events(self, run_id: str):
            run = state["runs"].get(run_id)
            if not run:
                return self._send(404, b"no such run", "text/plain")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            sent = 0
            try:
                while True:
                    with run.lock:
                        new, finished = run.events[sent:], run.done
                    for ev in new:
                        self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
                    sent += len(new)
                    self.wfile.flush()
                    if finished and sent == len(run.events):
                        break
                    time.sleep(0.25)
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

        # --- POST ---------------------------------------------------------------------------------
        def do_POST(self):
            if not self._host_ok() or not self._origin_ok():
                return self._send(403, b"forbidden", "text/plain")
            if not self._token_ok():
                return self._send(401, b"unauthorized", "text/plain")
            length = int(self.headers.get("Content-Length", "0") or 0)
            url = urlparse(self.path)
            if url.path == "/api/upload":
                name = Path(unquote(self.headers.get("X-Filename", ""))).name
                if length > MAX_UPLOAD:
                    remaining = length if length <= DRAIN_LIMIT else 0  # read it so the browser gets our message
                    while remaining > 0:
                        chunk = self.rfile.read(min(65536, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                    self.close_connection = True
                    return self._json(413, {"message": "That file is over 10 MB. Is it the right spreadsheet?"})
                if not name or name.startswith(".") or Path(name).suffix.lower() not in UPLOAD_SUFFIXES:
                    return self._json(400, {"message": "Only .xlsx or .csv spreadsheets can be added."})
                folder = roster_dir(cfg.nf_home)
                if folder == cfg.nf_home / "inbox":
                    folder.mkdir(parents=True, exist_ok=True)
                elif not folder.is_dir():
                    return self._json(409, {"message": "The Network Focus folder in Google Drive isn't there. Open "
                                                       "Google Drive for desktop and check you're signed in."})
                dest = folder / name
                try:
                    dest.write_bytes(self.rfile.read(length))
                except OSError:
                    return self._json(409, {"message": "I couldn't save the file in the Network Focus folder. Click "
                                                       "Check setup to see what's wrong."})
                try:  # keep the spreadsheet's own date, so the stale-data warning still works
                    mtime = int(self.headers.get("X-Last-Modified", "")) / 1000
                    if 0 < mtime < time.time() + 86400:
                        os.utime(dest, (mtime, mtime))
                except ValueError:
                    pass
                return self._json(200, {"saved": name})
            try:
                body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                return self._json(400, {"message": "That request wasn't valid. Reload the page and try again."})
            if not isinstance(body, dict):
                return self._json(400, {"message": "That request wasn't valid. Reload the page and try again."})
            if url.path == "/api/done":
                return self._done(body)
            if url.path == "/api/schedule":
                row_id, week, when, kind = body.get("row_id"), body.get("week_of"), body.get("when"), body.get("kind")
                if type(row_id) is not int or not isinstance(week, str) or not valid_when(when) \
                        or kind not in (None, "call", "email"):
                    return self._json(400, {"message": "Expected a person, the week, and a date and time."})
                payload = dashboard_payload(cfg.nf_home, date.today())
                if payload.get("empty") or week != payload["week_of"]:
                    return self._json(409, {"message": "A newer brief has been made. Reload the page."})
                if row_id not in {p["row_id"] for p in [payload["top"], *payload["others"], *payload["dormant"]]}:
                    return self._json(400, {"message": "That person isn't in this week's brief any more. Reload the page."})
                set_when(cfg.nf_home, week, row_id, when, kind)
                export_dashboard(cfg.nf_home, date.today())
                return self._json(200, {"ok": True})
            if url.path == "/api/sheet":
                name, company = body.get("name"), body.get("company")
                done, comment = body.get("done"), body.get("comment")
                if not isinstance(name, str) or not isinstance(company, str) or (done is None and comment is None) \
                        or (done is not None and type(done) is not bool) or (comment is not None and not isinstance(comment, str)):
                    return self._json(400, {"message": "Expected a name, a company, and done or a comment."})
                args = ["set", "--name", name, "--company", company]
                if done is not None:
                    args += ["--done", "yes" if done else "no"]
                if comment is not None:
                    args += ["--comment", comment[:2000]]
                return self._json(200, sheet_cmd(cfg, args))
            if url.path == "/api/quit":  # the installer restarts the page this way on Windows (no launchctl there)
                self._json(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if url.path == "/api/run":
                mode = body.get("mode", "brief")
                if mode not in RUN_MODES:
                    return self._json(400, {"message": "That isn't something the page can run."})
                if mode == "update":
                    payload = dashboard_payload(cfg.nf_home, date.today())
                    if payload.get("empty") or payload.get("stale"):
                        return self._json(409, {"message": "This week's brief hasn't been made yet. Click Generate instead."})
                    if self.server.watch.state()["changes"] is None:
                        return self._json(409, {"message": "Nobody new or changed since this week's brief."})
                file = Path(body.get("file") or "").name or None if mode == "brief" else None
                if file and not (roster_dir(cfg.nf_home) / file).is_file():
                    return self._json(400, {"message": f"{file} isn't in the inbox any more."})
                with state_lock:
                    if state["run"] and not state["run"].done:
                        return self._json(409, {"message": "A brief is already being made. Give it a minute."})
                    watch = self.server.watch
                    run = Run(cfg, file, mode, on_done=lambda: (export_dashboard(cfg.nf_home, date.today()),
                                                                watch.check_once(time.time())))
                    state["run"] = state["runs"][run.id] = run
                run.start()
                return self._json(200, {"run_id": run.id})
            if url.path == "/api/check":
                try:
                    p = subprocess.run([cfg.uv_path, "run", str(cfg.scripts_dir / "check_setup.py"), "--json",
                                        "--port", str(cfg.port)], capture_output=True, text=True, encoding="utf-8",
                                       env={**os.environ, "NF_HOME": str(cfg.nf_home)}, timeout=120)
                    return self._json(200, {"results": json.loads(p.stdout.strip().splitlines()[-1])})
                except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, IndexError):
                    return self._json(200, {"results": [{"name": "Setup check", "status": "fail",
                                                         "detail": "The check couldn't run.",
                                                         "fix": "Run /network-focus:setup-app in the Claude app."}]})
            return self._send(404, b"not found", "text/plain")

    srv = ThreadingHTTPServer(("127.0.0.1", cfg.port), Handler)
    srv.daemon_threads = True
    cfg.port = srv.server_address[1]
    srv.cfg = cfg
    srv.watch = RosterWatch(cfg.nf_home, diff_runner(cfg), interval=cfg.watch_interval or 120)
    export_dashboard(cfg.nf_home, date.today())  # bring the live view up to date when the page starts
    if cfg.watch_interval:
        srv.watch.start()
    return srv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.json"))
    srv = make_server(AppConfig.load(Path(ap.parse_args().config)))
    print(f"Network Focus page on http://127.0.0.1:{srv.cfg.port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
