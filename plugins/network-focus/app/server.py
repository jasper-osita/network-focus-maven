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
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from progress import failure_message, progress_from_event

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

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        d = json.loads(Path(path).read_text())
        return cls(port=d["port"], token=d["token"], nf_home=Path(d["nf_home"]), claude_path=d["claude_path"],
                   claude_args=d.get("claude_args", list(DEFAULT_CLAUDE_ARGS)), uv_path=d.get("uv_path", "uv"),
                   scripts_dir=Path(d.get("scripts_dir", HERE / "scripts")), run_timeout=d.get("run_timeout", 900))


class Run:
    def __init__(self, cfg: AppConfig, file: str | None):
        self.id, self.cfg, self.file = uuid.uuid4().hex[:12], cfg, file
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
        prompt = "/network-focus:brief" + (f" {cfg.nf_home / 'inbox' / self.file}" if self.file else "")
        result_text, stderr, last, timed_out = "", "", None, threading.Event()
        try:
            with tempfile.TemporaryFile(mode="w+") as err:  # a file, so a chatty stderr can't block stdout
                p = subprocess.Popen([cfg.claude_path, "-p", prompt, *cfg.claude_args], cwd=cfg.nf_home,
                                     env={**os.environ, "NF_HOME": str(cfg.nf_home)}, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=err, text=True)
                watchdog = threading.Timer(cfg.run_timeout, lambda: (timed_out.set(), p.kill()))
                watchdog.daemon = True
                watchdog.start()
                try:
                    for line in p.stdout:
                        try:
                            ev = json.loads(line)
                        except ValueError:
                            continue
                        if not isinstance(ev, dict):
                            continue
                        if ev.get("type") == "result":
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
            try:
                pdfs = sorted((f for f in (cfg.nf_home / "briefs").glob("*.pdf") if f.stat().st_mtime >= started - 1),
                              key=lambda f: f.stat().st_mtime)
                if timed_out.is_set():
                    self.add({"status": "failed", "message": "That took too long, so I stopped it. "
                                                             "Click Generate to try again."})
                elif pdfs:
                    self.add({"status": "done", "pdf_url": f"/briefs/{pdfs[-1].name}", "summary": result_text})
                else:
                    self.add({"status": "failed", "message": failure_message(result_text, stderr)})
            finally:
                self.done = True


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
                inbox = sorted((f for f in (cfg.nf_home / "inbox").glob("*") if f.suffix.lower() in UPLOAD_SUFFIXES
                                and not f.name.startswith(("~$", "."))), key=lambda f: -f.stat().st_mtime)
                briefs = sorted((cfg.nf_home / "briefs").glob("*.pdf"), key=lambda f: -f.stat().st_mtime)
                run = state["run"]
                return self._json(200, {
                    "inbox": [{"name": f.name, "modified": time.strftime("%b %d, %Y", time.localtime(f.stat().st_mtime))}
                              for f in inbox],
                    "briefs": [{"name": f.name, "url": f"/briefs/{f.name}"} for f in briefs],
                    "running": bool(run and not run.done)})
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
                (cfg.nf_home / "inbox").mkdir(parents=True, exist_ok=True)
                dest = cfg.nf_home / "inbox" / name
                dest.write_bytes(self.rfile.read(length))
                try:  # keep the spreadsheet's own date, so the stale-data warning still works
                    mtime = int(self.headers.get("X-Last-Modified", "")) / 1000
                    if 0 < mtime < time.time() + 86400:
                        os.utime(dest, (mtime, mtime))
                except ValueError:
                    pass
                return self._json(200, {"saved": name})
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            if url.path == "/api/run":
                file = Path(body.get("file") or "").name or None
                if file and not (cfg.nf_home / "inbox" / file).is_file():
                    return self._json(400, {"message": f"{file} isn't in the inbox any more."})
                with state_lock:
                    if state["run"] and not state["run"].done:
                        return self._json(409, {"message": "A brief is already being made. Give it a minute."})
                    run = Run(cfg, file)
                    state["run"] = state["runs"][run.id] = run
                run.start()
                return self._json(200, {"run_id": run.id})
            if url.path == "/api/check":
                try:
                    p = subprocess.run([cfg.uv_path, "run", str(cfg.scripts_dir / "check_setup.py"), "--json",
                                        "--port", str(cfg.port)], capture_output=True, text=True,
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
    return srv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.json"))
    srv = make_server(AppConfig.load(Path(ap.parse_args().config)))
    print(f"Network Focus page on http://127.0.0.1:{srv.cfg.port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
