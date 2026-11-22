import json
import plistlib
import sys

import pytest

import install_app
from conftest import ROOT

PLUGIN = ROOT / "plugins" / "network-focus"
posix_paths = pytest.mark.skipif(sys.platform == "win32", reason="checks the Mac layout's POSIX paths; runs on macOS CI")


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"


def test_install_copies_and_configures(home):
    r = install_app.install(PLUGIN, home, launch=False, system="darwin")
    app = home / "Library" / "Application Support" / "Network Focus"
    assert r["app_dir"] == str(app)
    for f in ("server.py", "index.html", "progress.py", "dashboard_data.py", "roster_watch.py", "scripts/check_setup.py",
              "scripts/roster_diff.py", "scripts/nf_core/roster.py"):
        assert (app / f).exists(), f
    cfg = json.loads((app / "config.json").read_text())
    assert len(cfg["token"]) >= 32 and cfg["port"] == 8765
    assert cfg["nf_home"] == str(home / "Documents" / "Network Focus")
    assert cfg["scripts_dir"] == str(app / "scripts")


def test_token_survives_reinstall(home):
    install_app.install(PLUGIN, home, launch=False, system="darwin")
    app = home / "Library" / "Application Support" / "Network Focus"
    first = json.loads((app / "config.json").read_text())["token"]
    install_app.install(PLUGIN, home, launch=False, system="darwin")
    assert json.loads((app / "config.json").read_text())["token"] == first


@posix_paths
def test_plist_has_absolute_paths(home):
    r = install_app.install(PLUGIN, home, launch=False, system="darwin")
    p = plistlib.loads(open(r["plist"], "rb").read())
    assert p["Label"] == "com.networkfocus.app" and p["RunAtLoad"] and p["KeepAlive"]
    assert all(a.startswith("/") for a in p["ProgramArguments"] if "/" in a)
    assert p["ProgramArguments"][0].startswith("/") and p["ProgramArguments"][-1].endswith("config.json")
    assert "/usr/bin" in p["EnvironmentVariables"]["PATH"]


@posix_paths
def test_webloc_url(home):
    r = install_app.install(PLUGIN, home, launch=False, system="darwin")
    url = plistlib.loads(open(r["webloc"], "rb").read())["URL"]
    assert url.startswith("http://127.0.0.1:8765/?t=") and r["url"] == url
    assert r["webloc"].endswith("Desktop/Network Focus.webloc")


def test_missing_claude_still_installs(home, monkeypatch):
    real = install_app.find_tool
    monkeypatch.setattr(install_app, "find_tool", lambda name, extra=(): None if name == "claude" else real(name, extra))
    r = install_app.install(PLUGIN, home, launch=False, system="darwin")
    assert any("Claude Code" in w for w in r["warnings"])
    assert (home / "Desktop" / "Network Focus.webloc").exists()


def test_install_prepares_operator_folder(home):
    install_app.install(PLUGIN, home, launch=False, system="darwin")
    nf = home / "Documents" / "Network Focus"
    assert (nf / "inbox").is_dir() and (nf / "briefs").is_dir() and (nf / "goals.md").exists()
    assert (home / "Library" / "Application Support" / "Network Focus" / "templates" / "goals.md").exists()


@posix_paths
def test_background_permissions_scoped(home):
    install_app.install(PLUGIN, home, launch=False, system="darwin")
    cfg = json.loads((home / "Library" / "Application Support" / "Network Focus" / "config.json").read_text())
    tools = cfg["claude_args"][cfg["claude_args"].index("--allowedTools") + 1]
    rules = tools.split(",")
    assert "Read" not in rules and "Write" not in rules and "Edit" not in rules and "Bash(uv run *)" not in rules
    assert any(r.startswith("Read(/") and "Documents/Network" in r for r in rules)
    assert any(r.startswith("Edit(/") and r.endswith(".work/**)") for r in rules)
    assert any(r.startswith('Bash(uv run "') and "/scripts/" in r for r in rules)


WIN_STARTUP = ("AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def test_windows_layout(home):
    r = install_app.install(PLUGIN, home, launch=False, system="win32")
    app = home / "AppData" / "Local" / "Network Focus"
    assert (app / "server.py").exists() and (app / "scripts" / "check_setup.py").exists()
    vbs = home.joinpath(*WIN_STARTUP, "Network Focus.vbs")
    assert vbs.exists() and r["startup"] == str(vbs)
    shortcut = home / "Desktop" / "Network Focus.url"
    assert shortcut.read_text().startswith("[InternetShortcut]") and "URL=http://127.0.0.1:8765/?t=" in shortcut.read_text()
    assert not (home / "Library").exists() and (home / "Documents" / "Network Focus" / "goals.md").exists()
    cfg = json.loads((app / "config.json").read_text())
    tools = cfg["claude_args"][cfg["claude_args"].index("--allowedTools") + 1].split(",")
    assert "Read(./**)" in tools and "Edit(./.work/**)" in tools and not any(t.startswith("Read(//") for t in tools)
    assert any(t.startswith('Bash(uv run "') and t.endswith('/scripts/*)') for t in tools)


def test_windows_layout_idempotent(home):
    install_app.install(PLUGIN, home, launch=False, system="win32")
    app = home / "AppData" / "Local" / "Network Focus"
    token = json.loads((app / "config.json").read_text())["token"]
    install_app.install(PLUGIN, home, launch=False, system="win32")
    assert json.loads((app / "config.json").read_text())["token"] == token
    assert [p.name for p in (home / "Desktop").iterdir()] == ["Network Focus.url"]
    assert [p.name for p in home.joinpath(*WIN_STARTUP).iterdir()] == ["Network Focus.vbs"]


def test_vbs_quotes_paths(tmp_path):
    home = tmp_path / "Mária Ñoño"
    install_app.install(PLUGIN, home, launch=False, system="win32")
    raw = home.joinpath(*WIN_STARTUP, "Network Focus.vbs").read_bytes()
    assert raw.startswith(b"\xff\xfe"), "UTF-16 with BOM so WSH reads non-ASCII paths"
    text = raw.decode("utf-16")
    server = home / "AppData" / "Local" / "Network Focus" / "server.py"
    assert f'""{server}""' in text and ", 0, False" in text


# ---- Google Drive folder ----
import os  # noqa: E402

from nf_core.workspace import load_settings  # noqa: E402


def _mac_drive(home):
    d = home / "Library" / "CloudStorage" / "GoogleDrive-x@y.com" / "My Drive"
    d.mkdir(parents=True)
    return d


def test_install_creates_drive_folder(home):
    drive = _mac_drive(home)
    r = install_app.install(PLUGIN, home, launch=False, system="darwin")
    folder = drive / "Network Focus"
    assert r["roster_folder"] == str(folder) and folder.is_dir()
    assert load_settings(home / "Documents" / "Network Focus")["roster_folder"] == str(folder)
    assert not any("Google Drive" in w for w in r["warnings"])


def test_install_copies_local_roster_once(home, sample_xlsx):
    drive = _mac_drive(home)
    inbox = home / "Documents" / "Network Focus" / "inbox"
    inbox.mkdir(parents=True)
    local = inbox / "roster.xlsx"
    local.write_bytes(sample_xlsx.read_bytes())
    os.utime(local, (1_700_000_000, 1_700_000_000))
    install_app.install(PLUGIN, home, launch=False, system="darwin")
    copied = drive / "Network Focus" / "roster.xlsx"
    assert copied.read_bytes() == local.read_bytes() and int(copied.stat().st_mtime) == 1_700_000_000
    copied.unlink()
    (drive / "Network Focus" / "newer.csv").write_text("Name\n", encoding="utf-8")
    install_app.install(PLUGIN, home, launch=False, system="darwin")
    assert not copied.exists()


def test_install_without_drive_warns(home):
    r = install_app.install(PLUGIN, home, launch=False, system="darwin")
    assert r["roster_folder"] is None
    assert any("Google Drive isn't set up on this computer" in w for w in r["warnings"])
    assert (home / "Documents" / "Network Focus" / "inbox").is_dir()


def test_install_more_than_one_drive_warns(home):
    _mac_drive(home)
    (home / "Library" / "CloudStorage" / "GoogleDrive-z@y.com" / "My Drive").mkdir(parents=True)
    r = install_app.install(PLUGIN, home, launch=False, system="darwin")
    assert r["roster_folder"].endswith("GoogleDrive-x@y.com/My Drive/Network Focus".replace("/", os.sep))
    assert any("more than one account" in w for w in r["warnings"])


def test_install_windows_drive_root(home, tmp_path):
    g = tmp_path / "G"
    (g / "My Drive").mkdir(parents=True)
    r = install_app.install(PLUGIN, home, launch=False, system="win32", drive_roots=[g])
    assert r["roster_folder"] == str(g / "My Drive" / "Network Focus")
    assert (g / "My Drive" / "Network Focus").is_dir()


# ---- relaunching the page on a Mac re-install ----
class FakeLaunchctl:
    """Stands in for launchctl: the old job lingers for a moment after bootout, and bootstrap fails until it's gone."""
    def __init__(self, linger=2, fail_bootstraps=2):
        self.calls, self.linger, self.fail = [], linger, fail_bootstraps

    def __call__(self, cmd, **kw):
        import subprocess
        self.calls.append(cmd[1])
        if cmd[1] == "print":
            self.linger -= 1
            return subprocess.CompletedProcess(cmd, 0 if self.linger >= 0 else 113, "", "")
        if cmd[1] == "bootstrap":
            self.fail -= 1
            return subprocess.CompletedProcess(cmd, 5 if self.fail >= 0 else 0, "", "Bootstrap failed: 5: Input/output error")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_relaunch_waits_for_old_page_and_retries(tmp_path):
    fake = FakeLaunchctl(linger=2, fail_bootstraps=2)
    assert install_app.relaunch_mac("gui/501", tmp_path / "x.plist", runner=fake, sleep=lambda s: None) is True
    assert fake.calls[0] == "bootout" and fake.calls.count("print") == 3 and fake.calls.count("bootstrap") == 3


def test_relaunch_gives_up_after_retries(tmp_path):
    fake = FakeLaunchctl(linger=0, fail_bootstraps=99)
    assert install_app.relaunch_mac("gui/501", tmp_path / "x.plist", runner=fake, sleep=lambda s: None) is False
    assert fake.calls.count("bootstrap") == 4
