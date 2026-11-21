import copy
import json
import subprocess
import sys

import pytest

from conftest import ROOT
from nf_core.render import pdf_safe, render_markdown, render_pdf

CLI = ROOT / "plugins" / "network-focus" / "scripts" / "render_pdf.py"


def warn_level(w):
    return [x for x in w["warnings"] if x["severity"] == "warn"]


def test_markdown_sections(brief_dict, roster_dict, warnings_dict):
    md = render_markdown(brief_dict, roster_dict, warnings_dict)
    for h in ["THIS WEEK", "DORMANT BUT HIGH-LEVERAGE", "COMING UP", "CHECK BEFORE THE MEETING"]:
        assert h in md
    for w in warn_level(warnings_dict):
        assert w["message"] in md
    assert "Diana Chen" in md and "CTO, Stripe" in md and "Week of Nov 23, 2026" in md


def test_info_items_only_in_also_noted(brief_dict, roster_dict, warnings_dict):
    md = render_markdown(brief_dict, roster_dict, warnings_dict)
    info = [x["message"] for x in warnings_dict["warnings"] if x["severity"] == "info"]
    assert all(m in md.split("Also noted")[1] for m in info)


def test_stale_banner_on_top(brief_dict, roster_dict, warnings_dict):
    md = render_markdown(brief_dict, roster_dict, warnings_dict)
    assert md.index("22 days ago") < md.index("THIS WEEK")


def test_pdf_one_page(tmp_path, brief_dict, roster_dict, warnings_dict):
    out = tmp_path / "b.pdf"
    assert render_pdf(brief_dict, roster_dict, warnings_dict, out) == 1
    assert out.read_bytes().startswith(b"%PDF")


def test_pdf_safe():
    s = pdf_safe("→ ≥ ✓ 李伟 Bouchard “quoted” — ok")
    s.encode("cp1252")
    assert "->" in s and ">=" in s and "Bouchard" in s and "—" in s


def setup_work(tmp_path, brief, roster, warnings):
    home = tmp_path / "Network Focus"
    work = home / ".work"
    work.mkdir(parents=True)
    (home / "briefs").mkdir()
    for name, doc in (("brief.json", brief), ("roster.json", roster), ("warnings.json", warnings)):
        (work / name).write_text(json.dumps(doc))
    return home


def run_cli(home, *args):
    p = subprocess.run([sys.executable, str(CLI), "--work", str(home / ".work"), *args],
                       capture_output=True, text=True)
    return p.returncode, json.loads(p.stdout)


def test_overlong_brief_exit_4(tmp_path, brief_dict, roster_dict, warnings_dict):
    b = copy.deepcopy(brief_dict)
    for f in b["focus"]:
        f["why"] = " ".join(["This contact matters a great deal for the goal this quarter."] * 20)
    home = setup_work(tmp_path, b, roster_dict, warnings_dict)
    code, out = run_cli(home, "--today", "2026-11-23")
    assert code == 4 and "too long" in out["message"]
    assert list((home / "briefs").iterdir()) == []


def test_refuses_invalid_brief(tmp_path, brief_dict, roster_dict, warnings_dict):
    b = copy.deepcopy(brief_dict)
    b["focus"] = b["focus"][:2]
    home = setup_work(tmp_path, b, roster_dict, warnings_dict)
    code, out = run_cli(home)
    assert code == 1 and out["ok"] is False and out["problems"]
    assert list((home / "briefs").iterdir()) == []


def test_records_history_and_names(tmp_path, brief_dict, roster_dict, warnings_dict):
    home = setup_work(tmp_path, brief_dict, roster_dict, warnings_dict)
    code, out = run_cli(home, "--today", "2026-11-23")
    assert code == 0 and out["ok"] is True
    assert (home / "briefs" / "2026-11-23-network-focus.pdf").exists()
    assert (home / "briefs" / "2026-11-23-network-focus.md").exists()
    hist = json.loads((home / ".history.json").read_text())
    assert len(hist) == 1 and hist[0]["sha256"] == roster_dict["source"]["sha256"] and hist[0]["run_date"] == "2026-11-23"
