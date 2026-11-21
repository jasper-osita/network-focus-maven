# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""/network-focus:setup-app — install the Network Focus page on this Mac (standard library only).
Copies the page into ~/Library/Application Support/Network Focus, registers it as a login item (LaunchAgent)
so it starts by itself, and puts a 'Network Focus' link on the Desktop. Safe to run again: it repairs/updates."""
import argparse
import json
import os
import plistlib
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "com.networkfocus.app"
APP_FILES = ("server.py", "index.html", "progress.py")


def background_allowed_tools(nf_home: Path, plugin_root: Path) -> str:
    """Spec §5.8: in background runs Claude may only read the Network Focus folder (and the plugin's own files),
    write inside its working folder, and run the plugin's own scripts. `//` marks an absolute path in a rule."""
    return ",".join([
        f"Read(/{nf_home}/**)",
        f"Read(/{plugin_root}/**)",
        f"Edit(/{nf_home}/.work/**)",
        f'Bash(uv run "{plugin_root}/scripts/*)',
        "Agent", "Task",
    ])


def claude_args(nf_home: Path, plugin_root: Path) -> list[str]:
    return ["--output-format", "stream-json", "--verbose", "--permission-mode", "dontAsk",
            "--allowedTools", background_allowed_tools(nf_home, plugin_root)]


def find_tool(name: str, extra: tuple | list = ()) -> str | None:
    """Mac apps started by launchd get a tiny PATH, so look in the usual install folders too."""
    candidates = [shutil.which(name), f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}",
                  str(Path.home() / ".local" / "bin" / name), *extra]
    return next((c for c in candidates if c and Path(c).is_file() and os.access(c, os.X_OK)), None)


def _page_answers(port: int, wait_s: float = 15) -> bool:
    import time
    import urllib.request
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.5)
    return False


def plist_xml(label: str, uv: str, server: Path, config: Path, path_env: str, log_dir: Path) -> bytes:
    return plistlib.dumps({
        "Label": label,
        "ProgramArguments": [uv, "run", str(server), "--config", str(config)],
        "WorkingDirectory": str(server.parent),
        "EnvironmentVariables": {"PATH": path_env},
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / "server.log"),
        "StandardErrorPath": str(log_dir / "server.log"),
    })


def webloc_xml(url: str) -> bytes:
    return plistlib.dumps({"URL": url})


def install(plugin_root: Path, home: Path, port: int = 8765, launch: bool = True) -> dict:
    app_dir = home / "Library" / "Application Support" / "Network Focus"
    app_dir.mkdir(parents=True, exist_ok=True)
    for f in APP_FILES:
        shutil.copy(plugin_root / "app" / f, app_dir / f)
    for d in ("scripts", "templates"):
        shutil.copytree(plugin_root / d, app_dir / d, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    nf_home = home / "Documents" / "Network Focus"
    for d in ("inbox", "briefs", ".work"):
        (nf_home / d).mkdir(parents=True, exist_ok=True)
    if not (nf_home / "goals.md").exists():
        shutil.copy(plugin_root / "templates" / "goals.md", nf_home / "goals.md")
    (app_dir / "logs").mkdir(exist_ok=True)

    warnings = []
    uv = find_tool("uv") or "uv"
    claude = find_tool("claude", [str(home / ".local" / "bin" / "claude"), str(home / ".claude" / "local" / "claude")])
    if not claude:
        warnings.append("The page needs the Claude Code command-line tool, which isn't installed yet. "
                        "Until it is, make briefs in the Claude app by typing 'make this week's network brief'.")

    cfg_path = app_dir / "config.json"
    old = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    cfg = {"port": port, "token": old.get("token") or secrets.token_urlsafe(24),
           "nf_home": str(nf_home), "claude_path": claude or "claude",
           "claude_args": claude_args(nf_home, plugin_root.resolve()), "uv_path": uv, "scripts_dir": str(app_dir / "scripts")}
    cfg_path.write_text(json.dumps(cfg, indent=2))
    cfg_path.chmod(0o600)

    dirs = [str(Path(t).parent) for t in (uv, claude) if t and "/" in t]
    path_env = ":".join(dict.fromkeys(dirs + ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]))
    plist = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plist_xml(LABEL, uv, app_dir / "server.py", cfg_path, path_env, app_dir / "logs"))

    url = f"http://127.0.0.1:{port}/?t={cfg['token']}"
    webloc = home / "Desktop" / "Network Focus.webloc"
    webloc.parent.mkdir(parents=True, exist_ok=True)
    webloc.write_bytes(webloc_xml(url))

    if launch:
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
        r = subprocess.run(["launchctl", "bootstrap", domain, str(plist)], capture_output=True, text=True)
        if r.returncode != 0 or not _page_answers(port):
            warnings.append("The page didn't start straight away. Restart the Mac and it will start on login; "
                            "if it still won't open, run /network-focus:setup-app again.")
    return {"url": url, "app_dir": str(app_dir), "plist": str(plist), "webloc": str(webloc), "warnings": warnings}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-launch", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    if sys.platform != "darwin" and not a.no_launch:
        print(json.dumps({"ok": False, "message": "The Network Focus page installs on a Mac only. On this computer, "
                                                  "make briefs in the Claude app instead."}))
        return 1
    r = install(Path(__file__).resolve().parents[1], Path.home(), a.port, launch=not a.no_launch)
    print(json.dumps({"ok": True, "message": "Network Focus page installed. Double-click 'Network Focus' on your "
                                             "Desktop to open it.", **r}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
