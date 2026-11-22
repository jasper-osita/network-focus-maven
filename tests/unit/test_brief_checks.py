import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT, TEMPLATE_GOALS
from nf_core.brief_checks import cited_rows, validate_brief, validate_scout
from nf_core.checks import flags_for
from nf_core.goals import parse_goals
from nf_core.roster import read_roster

FIXTURE = Path(__file__).parent / "fixtures" / "valid_brief.json"
CLI = ROOT / "plugins" / "network-focus" / "scripts" / "validate_brief.py"


@pytest.fixture(scope="module")
def roster():
    contacts, _ = read_roster(ROOT / "sample-data" / "network_roster_terragrid.xlsx")
    return {"source": {"week_of": "2026-11-23"},
            "goals": [g.to_dict() for g in parse_goals(TEMPLATE_GOALS.read_text())],
            "contacts": [{**c.to_dict(), "text": c.text(), "flags": flags_for(c)} for c in contacts]}


@pytest.fixture
def brief():
    return json.loads(FIXTURE.read_text())


def msg(first):
    return (f"Hi {first}, I wanted to follow up on our last conversation and ask whether you would be open "
            "to a short call this week about something specific I think you can help with.")


def codes(problems):
    return [p.code for p in problems]


def contact(roster, name):
    return next(c for c in roster["contacts"] if c["name"] == name)


def test_valid_brief_passes(brief, roster):
    assert validate_brief(brief, roster) == []


def test_focus_count(brief, roster):
    two = copy.deepcopy(brief)
    two["focus"] = two["focus"][:2]
    two["goal_gaps"] = [{"goal_id": 3, "note": "x"}]
    assert "FOCUS_COUNT" in codes(validate_brief(two, roster))
    six = copy.deepcopy(brief)
    six["focus"].append(copy.deepcopy(six["focus"][0]) | {"row_id": 20, "name": "Holly Liu",
                                                          "evidence": ["Monthly advisor call"]})
    assert "FOCUS_COUNT" in codes(validate_brief(six, roster))


def test_unknown_row_and_name_mismatch(brief, roster):
    b = copy.deepcopy(brief)
    b["focus"][0]["row_id"] = 99
    assert "UNKNOWN_ROW" in codes(validate_brief(b, roster))
    b = copy.deepcopy(brief)
    b["focus"][0]["name"] = "Diana Chan"
    assert "NAME_MISMATCH" in codes(validate_brief(b, roster))


def test_quote_must_be_verbatim(brief, roster):
    b = copy.deepcopy(brief)
    b["focus"][0]["evidence"] = ["offered to introduce 5 candidates"]
    p = validate_brief(b, roster)
    assert codes(p) == ["QUOTE_NOT_FOUND"] and p[0].where == "focus[0]"
    b["focus"][0]["evidence"] = ["  MENTIONED she   knows 3–4 strong candidates. "]  # case, spaces, en dash
    b["focus"][1]["evidence"] = ["“Asked to see the full pitch”"]  # curly quotes
    assert validate_brief(b, roster) == []


def test_short_quote_rejected(brief, roster):
    b = copy.deepcopy(brief)
    b["focus"][1]["evidence"] = ["investor"]
    assert codes(validate_brief(b, roster)) == ["QUOTE_TOO_SHORT"]


def test_dormant_rules(brief, roster):
    b = copy.deepcopy(brief)
    lin = contact(roster, "Lin Wang")
    b["dormant"][1] = {"row_id": lin["row_id"], "name": "Lin Wang", "days_since_contact": 59,
                       "why": "Casual Anthropic researcher she checks in with quarterly.",
                       "move": "Send Lin a short note asking for an intro to two Anthropic researchers.",
                       "evidence": ["Quarterly check-in note"], "message": msg("Lin")}
    assert "NOT_DORMANT" in codes(validate_brief(b, roster))
    b = copy.deepcopy(brief)
    b["dormant"][0]["days_since_contact"] = 100
    assert "DAYS_MISMATCH" in codes(validate_brief(b, roster))


def test_duplicate_person(brief, roster):
    b = copy.deepcopy(brief)
    b["dormant"][0] = {"row_id": 6, "name": "Reid Hoffman", "days_since_contact": 81,
                       "why": "Strongest investor relationship.", "move": "Email Reid a personal note asking for a call.",
                       "evidence": ["Strongest investor relationship she has"], "message": msg("Reid")}
    assert "DUPLICATE_PERSON" in codes(validate_brief(b, roster))


def test_thin_needs_low_confidence(brief, roster):
    b = copy.deepcopy(brief)
    b["focus"][4] = {"row_id": 10, "name": "Anjali Sharma", "goals": [1], "why": "Stealth founder met once.",
                     "move": "Email Anjali a short note asking what she is building now.",
                     "risk": "Unknown.", "evidence": ["Met at conference. Exchanged cards"], "confidence": "medium",
                     "message": msg("Anjali")}
    b["focus"][3]["goals"] = [3]
    assert "THIN_NOT_LOW" in codes(validate_brief(b, roster))
    b["focus"][4]["confidence"] = "low"
    assert "THIN_NOT_LOW" not in codes(validate_brief(b, roster))


def test_days_in_text_checked(brief, roster):
    b = copy.deepcopy(brief)
    b["focus"][2]["why"] = "Her strongest investor relationship, quiet for 90 days."
    assert codes(validate_brief(b, roster)) == ["NUMBER_MISMATCH"]


def test_vague_move(brief, roster):
    b = copy.deepcopy(brief)
    b["focus"][0]["move"] = "Reconnect."
    assert codes(validate_brief(b, roster)) == ["VAGUE_MOVE"]


def test_goal_coverage(brief, roster):
    b = copy.deepcopy(brief)
    b["focus"] = [f for f in b["focus"] if f["name"] not in ("Paul Christiano", "Sarah Guo")]
    assert codes(validate_brief(b, roster)) == ["GOAL_NOT_COVERED"]
    b["goal_gaps"] = [{"goal_id": 3, "note": "No warm AI-safety contact this week."}]
    assert validate_brief(b, roster) == []


def test_dormant_count_relaxed_when_few_eligible(brief, roster):
    r = copy.deepcopy(roster)
    for c in r["contacts"]:
        if c["flags"]["dormant"] and c["name"] not in ("Priya Mehta", "Reid Hoffman"):
            c["flags"]["dormant"] = False
            c["days_since_contact"] = 30
    b = copy.deepcopy(brief)
    b["dormant"] = b["dormant"][:1]
    assert validate_brief(b, r) == []
    assert "DORMANT_COUNT" in codes(validate_brief(b, roster))


def test_scout_validation(roster):
    good = {"goal_id": 2, "concerns": [], "candidates": [
        {"row_id": 3, "name": "Diana Chen", "fit": "Knows CTO candidates.", "move": "Email her for intros.",
         "risk": "Offer goes cold.", "evidence": ["knows 3-4 strong candidates"], "confidence": "high", "timing": "now"}]}
    assert validate_scout(good, roster) == []
    assert "SCHEMA" in codes(validate_scout({"goal_id": 2, "concerns": []}, roster))


def test_cited_rows_only_cited(brief, roster):
    out = cited_rows(brief, roster)
    assert [c["row_id"] for c in out["contacts"]] == [3, 2, 6, 4, 5, 16, 19, 25]


def test_cli_exit_codes(tmp_path, brief, roster):
    rp, good, bad = tmp_path / "roster.json", tmp_path / "good.json", tmp_path / "bad.json"
    rp.write_text(json.dumps(roster))
    good.write_text(json.dumps(brief))
    bad.write_text(json.dumps({**brief, "focus": brief["focus"][:1]}))
    run = lambda f: subprocess.run([sys.executable, str(CLI), "brief", str(f), "--roster", str(rp)],
                                   capture_output=True, text=True)
    g, b = run(good), run(bad)
    assert g.returncode == 0 and json.loads(g.stdout)["ok"] is True
    assert b.returncode == 1 and json.loads(b.stdout)["ok"] is False and json.loads(b.stdout)["problems"]


def test_thin_contact_rejected_in_dormant(brief, roster):
    b = copy.deepcopy(brief)
    b["dormant"][1] = {"row_id": 11, "name": "Jensen Huang", "days_since_contact": 199,
                       "why": "NVIDIA CEO met briefly at GTC.", "move": "Email Jensen a short note asking for a call about AI.",
                       "evidence": ["Met briefly at GTC"], "message": msg("Jensen")}
    assert "THIN_IN_DORMANT" in codes(validate_brief(b, roster))


def test_week_of_must_match(brief, roster):
    for bad in ("2025-01-06", "Nov 23, 2026"):
        assert "WEEK_MISMATCH" in codes(validate_brief({**brief, "week_of": bad}, roster))


def test_message_rules(brief, roster):
    b = copy.deepcopy(brief); b["focus"][0]["message"] = "Hi Diana, quick one."
    assert codes(validate_brief(b, roster)) == ["MESSAGE_LENGTH"]
    b = copy.deepcopy(brief); b["focus"][0]["message"] = b["focus"][0]["message"].replace("Diana", "there")
    assert codes(validate_brief(b, roster)) == ["MESSAGE_NAME"]
    b = copy.deepcopy(brief); b["focus"][0]["message"] += " [Your name]"
    assert codes(validate_brief(b, roster)) == ["MESSAGE_PLACEHOLDER"]
    b = copy.deepcopy(brief); b["dormant"][0]["message"] += " It has been 90 days."
    assert codes(validate_brief(b, roster)) == ["NUMBER_MISMATCH"]
    b = copy.deepcopy(brief); del b["dormant"][1]["message"]
    assert "SCHEMA" in codes(validate_brief(b, roster))
