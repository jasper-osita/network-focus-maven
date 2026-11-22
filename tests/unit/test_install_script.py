"""Runs the real install.sh against stand-in `claude` and `curl` programs (macOS-only steps are skipped in test mode)."""
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import sys

from conftest import ROOT

PLUGIN = ROOT / "plugins" / "network-focus"
UV_DIR = str(Path(shutil.which("uv")).parent)
needs_bash = pytest.mark.skipif(sys.platform == "win32", reason="bash installer runs on macOS/Linux")

STUB_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
st = Path(os.environ["STUB_STATE"]); st.mkdir(exist_ok=True)
args = sys.argv[1:]
with open(st / "calls.log", "a") as f:
    f.write(" ".join(args) + "\n")
def has(name): return (st / name).exists()
def touch(name): (st / name).write_text("1")
if args[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": has("logged_in")}))
elif args[:2] == ["auth", "login"]:
    if os.environ.get("STUB_LOGIN_FAILS"):
        sys.exit(1)
    touch("logged_in")
elif args[:3] == ["plugin", "marketplace", "list"]:
    print(json.dumps([{"name": "network-focus"}] if has("marketplace") else []))
elif args[:3] == ["plugin", "marketplace", "add"]:
    touch("marketplace")
elif args[:2] == ["plugin", "list"]:
    print(json.dumps([{"id": "network-focus@network-focus", "installPath": os.environ["STUB_PLUGIN"]}]
                     if has("installed") else []))
elif args[:2] == ["plugin", "install"]:
    touch("installed")
elif args[:2] == ["plugin", "uninstall"]:
    (st / "installed").unlink(missing_ok=True)
'''

STUB_CURL = r'''#!/usr/bin/env bash
echo "curl $*" >> "$STUB_STATE/calls.log"
# pretend to be an installer script that drops the claude stand-in into ~/.local/bin
echo 'mkdir -p "$HOME/.local/bin" && cp "$STUB_CLAUDE_SRC" "$HOME/.local/bin/claude" && chmod +x "$HOME/.local/bin/claude"'
'''


def write_exec(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def env(tmp_path):
    home, bin_dir, state = tmp_path / "home", tmp_path / "bin", tmp_path / "state"
    for d in (home, bin_dir, state):
        d.mkdir()
    src = tmp_path / "claude-src"
    write_exec(src, STUB_CLAUDE)
    shutil.copy(src, bin_dir / "claude")
    write_exec(bin_dir / "curl", STUB_CURL)
    e = {**os.environ, "HOME": str(home), "NF_INSTALL_TEST": "1", "STUB_STATE": str(state), "STUB_PLUGIN": str(PLUGIN),
         "STUB_CLAUDE_SRC": str(src), "UV_CACHE_DIR": str(Path.home() / ".cache" / "uv"),
         "PATH": f"{bin_dir}:{UV_DIR}:/usr/local/bin:/usr/bin:/bin"}
    return {"env": e, "home": home, "bin": bin_dir, "state": state}


def run(env, *args):
    p = subprocess.run(["bash", str(ROOT / "install.sh"), *args], env=env["env"], capture_output=True, text=True, encoding="utf-8",
                       timeout=180)
    calls = (env["state"] / "calls.log").read_text() if (env["state"] / "calls.log").exists() else ""
    return p, calls


def app_dir(env):
    return env["home"] / "Library" / "Application Support" / "Network Focus"


@needs_bash
def test_fresh_install(env):
    p, calls = run(env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "auth login" in calls and "plugin marketplace add jasper-osita/network-focus-maven" in calls
    assert "plugin install network-focus@network-focus" in calls
    assert (app_dir(env) / "server.py").exists() and (env["home"] / "Desktop" / "Network Focus.webloc").exists()
    assert (env["home"] / "Documents" / "Network Focus" / "goals.md").exists()
    assert "Done" in p.stdout and "5/5" in p.stdout
    assert (env["home"] / "Library" / "Logs" / "NetworkFocus-install.log").exists()


@needs_bash
def test_rerun_updates(env):
    run(env)
    (env["state"] / "calls.log").unlink()
    p, calls = run(env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "auth login" not in calls and "marketplace add" not in calls and "plugin install" not in calls
    assert "plugin marketplace update network-focus" in calls and "plugin update network-focus@network-focus" in calls


@needs_bash
def test_login_failure_stops(env):
    env["env"]["STUB_LOGIN_FAILS"] = "1"
    p, calls = run(env)
    assert p.returncode != 0 and "sign in" in (p.stdout + p.stderr).lower()
    assert "plugin install" not in calls and not app_dir(env).exists()


@needs_bash
def test_missing_helper_installed(env):
    (env["bin"] / "claude").unlink()
    p, calls = run(env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "claude.ai/install.sh" in calls and "astral.sh" not in calls


@needs_bash
def test_uninstall_keeps_briefs(env):
    run(env)
    briefs = env["home"] / "Documents" / "Network Focus" / "briefs"
    (briefs / "2026-11-23-network-focus.pdf").write_bytes(b"%PDF")
    p, calls = run(env, "--uninstall")
    assert p.returncode == 0, p.stdout + p.stderr
    assert not app_dir(env).exists() and not (env["home"] / "Desktop" / "Network Focus.webloc").exists()
    assert not (env["home"] / "Library" / "LaunchAgents" / "com.networkfocus.app.plist").exists()
    assert (briefs / "2026-11-23-network-focus.pdf").exists()
    assert "plugin uninstall network-focus@network-focus" in calls


@needs_bash
def test_command_file():
    cmd = ROOT / "Install Network Focus.command"
    text = cmd.read_text()
    assert os.access(cmd, os.X_OK) and text.startswith("#!/bin/bash")
    assert "install.sh" in text and "https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.sh" in text


def test_deliverable_zip_has_both_installers():
    import zipfile
    with zipfile.ZipFile(ROOT / "deliverables" / "Install Network Focus.zip") as z:
        mac = z.getinfo("Mac - Install Network Focus.command")
        assert (mac.external_attr >> 16) & 0o111, "unzipped Mac installer must stay double-clickable"
        assert z.read(mac) == (ROOT / "Install Network Focus.command").read_bytes(), "zip is out of date"
        assert z.read("Windows - Install Network Focus.cmd") == (ROOT / "Install Network Focus.cmd").read_bytes()


def test_windows_cmd_file():
    text = (ROOT / "Install Network Focus.cmd").read_bytes().decode()
    assert "\r\n" in text and "-ExecutionPolicy Bypass" in text and "install.ps1" in text
    assert "https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.ps1" in text
    ps1 = (ROOT / "install.ps1").read_bytes()
    assert ps1.isascii(), "PowerShell 5.1 misreads non-ASCII in BOM-less files"
