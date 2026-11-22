"""Runs the real install.ps1 with a stand-in `claude` on Windows (GitHub Actions windows-latest). Skipped elsewhere."""
import os
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT
from test_install_script import PLUGIN, STUB_CLAUDE

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows installer runs on Windows only")
STARTUP = ("AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


@pytest.fixture
def env(tmp_path):
    home, bin_dir, state = tmp_path / "home", tmp_path / "bin", tmp_path / "state"
    for d in (home, bin_dir, state):
        d.mkdir()
    (bin_dir / "claude_stub.py").write_text(STUB_CLAUDE)
    (bin_dir / "claude.cmd").write_text(f'@"{sys.executable}" "%~dp0claude_stub.py" %*\r\n')
    uv_dir = os.path.dirname(shutil.which("uv"))
    e = {**os.environ, "USERPROFILE": str(home), "HOME": str(home),
         "LOCALAPPDATA": str(home / "AppData" / "Local"), "APPDATA": str(home / "AppData" / "Roaming"),
         "NF_INSTALL_TEST": "1", "STUB_STATE": str(state), "STUB_PLUGIN": str(PLUGIN),
         "PATH": os.pathsep.join([str(bin_dir), uv_dir, os.environ["PATH"]])}
    return {"env": e, "home": home, "state": state}


def run(env, *args):
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install.ps1"),
                        *args], env=env["env"], capture_output=True, text=True, encoding="utf-8", timeout=300)
    calls = (env["state"] / "calls.log").read_text() if (env["state"] / "calls.log").exists() else ""
    return p, calls


def app_dir(env):
    return env["home"] / "AppData" / "Local" / "Network Focus"


def test_ps1_fresh_install(env):
    p, calls = run(env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "auth login" in calls and "plugin marketplace add jasper-osita/network-focus-maven" in calls
    assert "plugin install network-focus@network-focus" in calls
    assert (app_dir(env) / "server.py").exists() and (env["home"] / "Desktop" / "Network Focus.url").exists()
    assert env["home"].joinpath(*STARTUP, "Network Focus.vbs").exists()
    assert (env["home"] / "Documents" / "Network Focus" / "goals.md").exists()
    assert "Done" in p.stdout and "5/5" in p.stdout


def test_ps1_rerun_updates(env):
    run(env)
    (env["state"] / "calls.log").unlink()
    p, calls = run(env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "auth login" not in calls and "marketplace add" not in calls and "plugin install" not in calls
    assert "plugin marketplace update network-focus" in calls and "plugin update network-focus@network-focus" in calls


def test_ps1_login_failure_stops(env):
    env["env"]["STUB_LOGIN_FAILS"] = "1"
    p, calls = run(env)
    assert p.returncode != 0 and "sign in" in (p.stdout + p.stderr).lower()
    assert "plugin install" not in calls


def test_ps1_uninstall_keeps_briefs(env):
    run(env)
    briefs = env["home"] / "Documents" / "Network Focus" / "briefs"
    (briefs / "2026-11-23-network-focus.pdf").write_bytes(b"%PDF")
    p, calls = run(env, "-Uninstall")
    assert p.returncode == 0, p.stdout + p.stderr
    assert not app_dir(env).exists() and not (env["home"] / "Desktop" / "Network Focus.url").exists()
    assert not env["home"].joinpath(*STARTUP, "Network Focus.vbs").exists()
    assert (briefs / "2026-11-23-network-focus.pdf").exists() and "plugin uninstall network-focus@network-focus" in calls
