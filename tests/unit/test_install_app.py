import json
import plistlib

import pytest

import install_app
from conftest import ROOT

PLUGIN = ROOT / "plugins" / "network-focus"


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"


def test_install_copies_and_configures(home):
    r = install_app.install(PLUGIN, home, launch=False)
    app = home / "Library" / "Application Support" / "Network Focus"
    assert r["app_dir"] == str(app)
    for f in ("server.py", "index.html", "progress.py", "scripts/check_setup.py", "scripts/nf_core/roster.py"):
        assert (app / f).exists(), f
    cfg = json.loads((app / "config.json").read_text())
    assert len(cfg["token"]) >= 32 and cfg["port"] == 8765
    assert cfg["nf_home"] == str(home / "Documents" / "Network Focus")
    assert cfg["scripts_dir"] == str(app / "scripts")


def test_token_survives_reinstall(home):
    install_app.install(PLUGIN, home, launch=False)
    app = home / "Library" / "Application Support" / "Network Focus"
    first = json.loads((app / "config.json").read_text())["token"]
    install_app.install(PLUGIN, home, launch=False)
    assert json.loads((app / "config.json").read_text())["token"] == first


def test_plist_has_absolute_paths(home):
    r = install_app.install(PLUGIN, home, launch=False)
    p = plistlib.loads(open(r["plist"], "rb").read())
    assert p["Label"] == "com.networkfocus.app" and p["RunAtLoad"] and p["KeepAlive"]
    assert all(a.startswith("/") for a in p["ProgramArguments"] if "/" in a)
    assert p["ProgramArguments"][0].startswith("/") and p["ProgramArguments"][-1].endswith("config.json")
    assert "/usr/bin" in p["EnvironmentVariables"]["PATH"]


def test_webloc_url(home):
    r = install_app.install(PLUGIN, home, launch=False)
    url = plistlib.loads(open(r["webloc"], "rb").read())["URL"]
    assert url.startswith("http://127.0.0.1:8765/?t=") and r["url"] == url
    assert r["webloc"].endswith("Desktop/Network Focus.webloc")


def test_missing_claude_still_installs(home, monkeypatch):
    real = install_app.find_tool
    monkeypatch.setattr(install_app, "find_tool", lambda name, extra=(): None if name == "claude" else real(name, extra))
    r = install_app.install(PLUGIN, home, launch=False)
    assert any("Claude Code" in w for w in r["warnings"])
    assert (home / "Desktop" / "Network Focus.webloc").exists()
