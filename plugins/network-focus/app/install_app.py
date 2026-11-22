# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""/network-focus:setup-app — install the Network Focus page on this computer (standard library only).
Mac: copies the page into ~/Library/Application Support/Network Focus, registers a LaunchAgent, adds a Desktop link.
Windows: copies it into %LOCALAPPDATA%\\Network Focus, adds a hidden-start script to the Startup folder, adds a
Desktop shortcut. Safe to run again: it repairs/updates."""
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
APP_FILES = ("server.py", "index.html", "progress.py", "dashboard_data.py", "roster_watch.py")
WIN_STARTUP_PARTS = ("AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from nf_core.drive import FOLDER_NAME, find_my_drive  # noqa: E402  (stdlib-only modules)
from nf_core.workspace import _known_folder, load_settings, save_settings  # noqa: E402


def background_allowed_tools(nf_home: Path, plugin_root: Path, windows: bool = False) -> str:
    """Spec §5.8: in background runs Claude may only read the Network Focus folder (and the plugin's own files),
    write inside its working folder, and run the plugin's own scripts. On the Mac `//` marks an absolute path
    (verified); on Windows the rules are relative to the run's folder (her Network Focus folder) and to home."""
    if windows:
        return ",".join(["Read(./**)", "Read(~/.claude/plugins/**)", "Edit(./.work/**)",
                         f'Bash(uv run "{plugin_root}/scripts/*)', "Agent", "Task"])
    return ",".join([
        f"Read(/{nf_home}/**)",
        f"Read(/{plugin_root}/**)",
        f"Edit(/{nf_home}/.work/**)",
        f'Bash(uv run "{plugin_root}/scripts/*)',
        "Agent", "Task",
    ])


def claude_args(nf_home: Path, plugin_root: Path, windows: bool = False) -> list[str]:
    return ["--output-format", "stream-json", "--verbose", "--permission-mode", "dontAsk",
            "--allowedTools", background_allowed_tools(nf_home, plugin_root, windows)]


def find_tool(name: str, extra: tuple | list = ()) -> str | None:
    """Apps started at login get a tiny PATH, so look in the usual install folders too."""
    candidates = [shutil.which(name), f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}",
                  str(Path.home() / ".local" / "bin" / name), str(Path.home() / ".local" / "bin" / f"{name}.exe"), *extra]
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


def _win_folder(name: str, home: Path) -> Path:
    """The real (possibly OneDrive-redirected) folder for the signed-in user; plain home/<name> otherwise."""
    use_real = home == Path.home() and not os.environ.get("NF_INSTALL_TEST")  # tests never touch real folders
    kf = _known_folder(name) if use_real else None
    return kf or home / name


def vbs_script(app_dir: Path, uv: str, server: Path, config: Path) -> str:
    """Starts the server with no console window. VBScript doubles quotes inside strings."""
    return ("' Starts the Network Focus page at sign-in, hidden. Created by Install Network Focus; safe to delete.\r\n"
            'Set sh = CreateObject("WScript.Shell")\r\n'
            f'sh.CurrentDirectory = "{app_dir}"\r\n'
            f'sh.Run """{uv}"" run ""{server}"" --config ""{config}""", 0, False\r\n')


def _stop_old_server(port: int, token: str | None) -> None:
    """Windows has no launchctl: ask a running page (with its token) to quit so the new files take over."""
    import time
    import urllib.request
    if not token or not _page_answers(port, wait_s=1):
        return
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", data=b"{}", method="POST",
                                 headers={"Origin": f"http://127.0.0.1:{port}", "Cookie": f"nf_token={token}",
                                          "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=3).close()
    except OSError:
        return
    deadline = time.time() + 5
    while time.time() < deadline and _page_answers(port, wait_s=0.5):
        time.sleep(0.3)


NO_DRIVE = ("Google Drive isn't set up on this computer. Install Google Drive for desktop, sign in, then run the "
            "installer again. Until then, drag spreadsheets onto the page as before.")


def setup_drive_folder(nf_home: Path, home: Path, system: str, drive_roots: list[Path] | None,
                       warnings: list[str]) -> Path | None:
    """Create My Drive/Network Focus, remember it in settings.json, and seed it with the local roster once."""
    if drive_roots is None and os.environ.get("NF_INSTALL_TEST") and system == "win32":
        drive_roots = []  # test runs never scan the machine's real drive letters
    drives = find_my_drive(home, system, drive_roots)
    if not drives:
        warnings.append(NO_DRIVE)
        return None
    if len(drives) > 1:
        warnings.append(f"Google Drive has more than one account on this computer. Using {drives[0].parent.name}.")
    folder = drives[0] / FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    save_settings(nf_home, {**load_settings(nf_home), "roster_folder": str(folder)})
    sheets = lambda d: [f for f in d.glob("*") if f.suffix.lower() in (".xlsx", ".csv")
                        and not f.name.startswith(("~$", "."))]
    local = sorted(sheets(nf_home / "inbox"), key=lambda f: f.stat().st_mtime)
    if local and not sheets(folder):
        shutil.copy2(local[-1], folder / local[-1].name)
    return folder


def install(plugin_root: Path, home: Path, port: int = 8765, launch: bool = True, system: str | None = None,
            nf_home: Path | None = None, drive_roots: list[Path] | None = None) -> dict:
    windows = (system or sys.platform) == "win32"
    if windows:
        app_dir = home / "AppData" / "Local" / "Network Focus"
        default_home, desktop = _win_folder("Documents", home) / "Network Focus", _win_folder("Desktop", home)
    else:
        app_dir = home / "Library" / "Application Support" / "Network Focus"
        default_home, desktop = home / "Documents" / "Network Focus", home / "Desktop"
    app_dir.mkdir(parents=True, exist_ok=True)
    for f in APP_FILES:
        shutil.copy(plugin_root / "app" / f, app_dir / f)
    for d in ("scripts", "templates"):
        shutil.copytree(plugin_root / d, app_dir / d, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    nf_home = Path(nf_home) if nf_home else default_home
    for d in ("inbox", "briefs", ".work"):
        (nf_home / d).mkdir(parents=True, exist_ok=True)
    if not (nf_home / "goals.md").exists():
        shutil.copy(plugin_root / "templates" / "goals.md", nf_home / "goals.md")
    (app_dir / "logs").mkdir(exist_ok=True)

    warnings = []
    roster_folder = setup_drive_folder(nf_home, home, "win32" if windows else "darwin", drive_roots, warnings)
    uv = find_tool("uv") or "uv"
    claude = find_tool("claude", [str(home / ".local" / "bin" / "claude"), str(home / ".claude" / "local" / "claude")])
    if not claude:
        warnings.append("The page needs the Claude Code command-line tool, which isn't installed yet. "
                        "Until it is, make briefs in the Claude app by typing 'make this week's network brief'.")

    cfg_path = app_dir / "config.json"
    old = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    cfg = {"port": port, "token": old.get("token") or secrets.token_urlsafe(24),
           "nf_home": str(nf_home), "claude_path": claude or "claude",
           "claude_args": claude_args(nf_home, plugin_root.resolve(), windows), "uv_path": uv,
           "scripts_dir": str(app_dir / "scripts")}
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    cfg_path.chmod(0o600)
    url = f"http://127.0.0.1:{port}/?t={cfg['token']}"

    if windows:
        vbs = home.joinpath(*WIN_STARTUP_PARTS, "Network Focus.vbs")
        vbs.parent.mkdir(parents=True, exist_ok=True)
        vbs.write_bytes(vbs_script(app_dir, uv, app_dir / "server.py", cfg_path).encode("utf-16"))  # BOM: non-ASCII paths
        shortcut = desktop / "Network Focus.url"
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        shortcut.write_text(f"[InternetShortcut]\r\nURL={url}\r\n", encoding="utf-8")
        if launch:
            _stop_old_server(port, old.get("token"))
            subprocess.Popen(["wscript.exe", str(vbs)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            if not _page_answers(port):
                warnings.append("The page didn't start straight away. Restart the computer and it will start on "
                                "sign-in; if it still won't open, run the installer again.")
        return {"url": url, "app_dir": str(app_dir), "startup": str(vbs), "shortcut": str(shortcut),
                "roster_folder": str(roster_folder) if roster_folder else None, "warnings": warnings}

    dirs = [str(Path(t).parent) for t in (uv, claude) if t and "/" in t]
    path_env = ":".join(dict.fromkeys(dirs + ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]))
    plist = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plist_xml(LABEL, uv, app_dir / "server.py", cfg_path, path_env, app_dir / "logs"))

    webloc = desktop / "Network Focus.webloc"
    webloc.parent.mkdir(parents=True, exist_ok=True)
    webloc.write_bytes(webloc_xml(url))

    if launch:
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
        r = subprocess.run(["launchctl", "bootstrap", domain, str(plist)], capture_output=True, text=True)
        if r.returncode != 0 or not _page_answers(port):
            warnings.append("The page didn't start straight away. Restart the Mac and it will start on login; "
                            "if it still won't open, run /network-focus:setup-app again.")
    return {"url": url, "app_dir": str(app_dir), "plist": str(plist), "webloc": str(webloc),
            "roster_folder": str(roster_folder) if roster_folder else None, "warnings": warnings}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-launch", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--nf-home", default="")
    a = ap.parse_args(argv)
    if sys.platform not in ("darwin", "win32") and not a.no_launch:
        print(json.dumps({"ok": False, "message": "The Network Focus page installs on a Mac or a Windows PC. On this "
                                                  "computer, make briefs in the Claude app instead."}))
        return 1
    r = install(Path(__file__).resolve().parents[1], Path.home(), a.port, launch=not a.no_launch,
                nf_home=Path(a.nf_home) if a.nf_home else None)
    print(json.dumps({"ok": True, "message": "Network Focus page installed. Double-click 'Network Focus' on your "
                                             "Desktop to open it.", **r}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
