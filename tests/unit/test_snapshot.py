import json

from nf_core.render import render_markdown
from nf_core.snapshot import build_snapshot, questions_for


def test_build_snapshot(brief_dict, roster_dict, warnings_dict):
    s = build_snapshot(brief_dict, roster_dict, warnings_dict)
    assert s["version"] == 2 and s["week_of"] == "2026-11-23" and s["goals"]["2"] == "Hire a CTO"
    assert s["people"]["3"] == {"name": "Diana Chen", "role": "CTO", "company": "Stripe", "days_since_contact": 28}
    assert [g["name"] for g in s["going_quiet"]] == ["Lin Wang", "Patrick Collison"]
    assert any("a16z" in q for q in s["questions"]) and any("22 days ago" in b for b in s["banner"])
    assert s["source"] == {"file_name": roster_dict["source"]["file_name"], "as_of": "2026-11-21", "sha256": "ab" * 32}
    assert s["brief"]["focus"][0]["message"].startswith("Hi Diana")
    json.dumps(s)


def test_questions_match_pdf_check_box(brief_dict, roster_dict, warnings_dict):
    md = render_markdown(brief_dict, roster_dict, warnings_dict)
    box = md.split("## CHECK BEFORE THE MEETING")[1].split("##")[0]
    assert all(q in box for q in questions_for(brief_dict, roster_dict, warnings_dict))


def test_snapshot_has_roster_index(brief_dict, roster_dict, warnings_dict):
    snap = build_snapshot(brief_dict, roster_dict, warnings_dict)
    assert snap["version"] == 2 and len(snap["roster_index"]) == 25
    assert snap["source"]["sha256"] == "ab" * 32


def test_questions_include_update_questions(brief_dict, roster_dict, warnings_dict):
    brief_dict["update_questions"] = ["Reid Hoffman is no longer in the roster. Remove them from this week's list?"]
    assert build_snapshot(brief_dict, roster_dict, warnings_dict)["questions"][-1].startswith("Reid Hoffman is no longer")
