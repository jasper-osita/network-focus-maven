import copy
import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT
from nf_core.checks import flags_for
from nf_core.roster import Contact
from nf_core.snapshot import build_snapshot
from nf_core.update import load_marks, main_goal, prep_update, validate_update

SCRIPTS = ROOT / "plugins" / "network-focus" / "scripts"


def person(row_id, name, company, **kw):
    c = Contact(row_id=row_id, name=name, company=company, role=kw.get("role", "Partner"), how_known=kw.get("how_known", "investor"),
                days_since_contact=kw.get("days", 5), channel="email",
                summary=kw.get("summary", "Asked for a Series C call before Friday after a dinner together."),
                strength=kw.get("strength", 3), tags=kw.get("tags", ["investor", "series-c"]), notes=kw.get("notes", "Met at a dinner."))
    return {**c.to_dict(), "text": c.text(), "flags": flags_for(c)}


ANA = dict(row_id=26, name="Ana Ruiz", company="Andreessen Horowitz")


def roster_plus(roster, *extra, shift=0, drop=(), change=None):
    r = copy.deepcopy(roster)
    contacts = [c for c in r["contacts"] if c["name"] not in drop]
    if shift:
        for c in contacts:
            c["row_id"] += shift
        contacts.insert(0, person(1, "Zed Top", "Top Co", tags=["friend"], summary="Old friend from school days, catch up soon."))
    for name, notes in (change or {}).items():
        c = next(c for c in contacts if c["name"] == name)
        c["notes"] = notes
        c["text"] = Contact(**{k: c[k] for k in Contact.__dataclass_fields__}).text()
    r["contacts"] = contacts + [person(**e) if isinstance(e, dict) else e for e in extra]
    return r


@pytest.fixture
def snapshot(brief_dict, roster_dict, warnings_dict):
    return build_snapshot(brief_dict, roster_dict, warnings_dict)


def picks_by_name(inp):
    return {p["name"]: p for p in inp["picks"]}


# ---------------------------------------------------------------- prep
def test_main_goal_is_lowest_id(roster_dict):
    r = copy.deepcopy(roster_dict)
    r["goals"] = list(reversed(r["goals"]))
    assert main_goal(r) == {"id": 1, "title": "Raise Series C"}


def test_prep_maps_rows_by_identity(snapshot, roster_dict):
    inp = prep_update(snapshot, roster_plus(roster_dict, shift=1), {})
    assert all(p["row_id"] == p["old_row_id"] + 1 for p in inp["picks"])
    assert [p["name"] for p in inp["people"]] == ["Zed Top"] and inp["people"][0]["kind"] == "new"


def test_prep_locks_done_top_and_dormant(snapshot, roster_dict):
    inp = prep_update(snapshot, roster_plus(roster_dict, ANA), {"2": "Marcus Wei"})
    p = picks_by_name(inp)
    assert p["Marcus Wei"]["done"] and p["Marcus Wei"]["locked"]
    assert p["Diana Chen"]["locked"] and not p["Diana Chen"]["done"] and p["Diana Chen"]["rank"] == 0
    assert p["Priya Mehta"]["locked"] and p["Priya Mehta"]["section"] == "dormant"
    assert not any(p[n]["locked"] for n in ("Reid Hoffman", "Paul Christiano", "Sarah Guo"))
    assert inp["main_goal"] == {"id": 1, "title": "Raise Series C"} and inp["week_of"] == "2026-11-23"


def test_prep_open_slots_order(snapshot, roster_dict):
    snapshot["brief"]["focus"] = snapshot["brief"]["focus"][:4]  # Diana, Marcus, Reid, Paul
    inp = prep_update(snapshot, roster_plus(roster_dict, ANA), {"6": "Reid Hoffman"})
    assert inp["open_slots"] == [{"kind": "empty"},
                                 {"kind": "replace", "row_id": 4, "name": "Paul Christiano", "rank": 3},
                                 {"kind": "replace", "row_id": 2, "name": "Marcus Wei", "rank": 1}]


def test_prep_lists_changed_picks_only(snapshot, roster_dict):
    r = roster_plus(roster_dict, change={"Marcus Wei": "Term sheet due Friday.", "Lin Wang": "Now leads evals."})
    inp = prep_update(snapshot, r, {})
    assert inp["listed_only"] == ["Marcus Wei"]
    assert [(p["name"], p["kind"]) for p in inp["people"]] == [("Lin Wang", "changed")]


def test_prep_missing_pick_row_none(snapshot, roster_dict):
    inp = prep_update(snapshot, roster_plus(roster_dict, drop=("Paul Christiano",)), {})
    assert picks_by_name(inp)["Paul Christiano"]["row_id"] is None
    assert all(s.get("name") != "Paul Christiano" for s in inp["open_slots"])


def test_load_marks(tmp_path):
    assert load_marks(tmp_path, "2026-11-23") == {}
    (tmp_path / ".progress.json").write_text(json.dumps({"2026-11-23": {"2": "Marcus Wei"}}), encoding="utf-8")
    assert load_marks(tmp_path, "2026-11-23") == {"2": "Marcus Wei"} and load_marks(tmp_path, "2026-11-30") == {}
    (tmp_path / ".progress.json").write_text("{oops", encoding="utf-8")
    assert load_marks(tmp_path, "2026-11-23") == {}


# ---------------------------------------------------------------- validate
ANA_MSG = ("Hi Ana, thank you for asking about our Series C over dinner. I'd love to set up the call you mentioned "
           "before Friday. Would Wednesday or Thursday afternoon work for 30 minutes? I can walk you through where the round stands.")


def ana_update(**over):
    p = {"row_id": 26, "name": "Ana Ruiz", "tied_to_main_goal": True, "evidence": ["Asked for a Series C call"],
         "goal_link": "A partner at a16z asking about the Series C.", "beats": 4,
         "pick": {"goals": [1], "why": "Ana asked for a Series C call before Friday.",
                  "move": "Email Ana this week to book the Series C call she asked for before Friday.",
                  "risk": "The a16z door the goals call for could close if the call slips past Friday.",
                  "evidence": ["Asked for a Series C call before Friday"], "confidence": "high", "message": ANA_MSG}}
    p.update(over)
    return {"people": [p]}


@pytest.fixture
def ana_case(snapshot, roster_dict):
    r = roster_plus(roster_dict, ANA)
    return r, prep_update(snapshot, r, {})


def test_validate_update_accepts_good_answer(ana_case):
    r, inp = ana_case
    assert validate_update(ana_update(), r, inp) == []


def test_validate_update_quote_must_exist(ana_case):
    r, inp = ana_case
    codes = [p.code for p in validate_update(ana_update(evidence=["Wants to lead the round"]), r, inp)]
    assert "QUOTE_NOT_FOUND" in codes


def test_validate_update_every_person_once(ana_case):
    r, inp = ana_case
    assert "MISSING_PERSON" in [p.code for p in validate_update({"people": []}, r, inp)]
    extra = ana_update()
    extra["people"].append({"row_id": 3, "name": "Diana Chen", "tied_to_main_goal": False,
                            "evidence": ["Offered to help with CTO search"], "goal_link": "", "consider": "Already a pick."})
    assert "UNEXPECTED_PERSON" in [p.code for p in validate_update(extra, r, inp)]


def test_validate_update_pick_needs_main_goal(ana_case):
    r, inp = ana_case
    u = ana_update()
    u["people"][0]["pick"]["goals"] = [2]
    assert "PICK_GOAL" in [p.code for p in validate_update(u, r, inp)]


def test_validate_update_pick_message_rules(ana_case):
    r, inp = ana_case
    u = ana_update()
    u["people"][0]["pick"]["message"] = ANA_MSG.replace("Hi Ana, thank", "Thank")
    assert "MESSAGE_NAME" in [p.code for p in validate_update(u, r, inp)]


def test_validate_update_not_placed_needs_note(ana_case):
    r, inp = ana_case
    u = ana_update(tied_to_main_goal=False, goal_link="")
    del u["people"][0]["pick"], u["people"][0]["beats"]
    assert "NO_CONSIDER_NOTE" in [p.code for p in validate_update(u, r, inp)]
    u["people"][0]["consider"] = "A strong investor, but nothing ties them to the round yet."
    assert validate_update(u, r, inp) == []


def test_validate_update_tie_rules(ana_case):
    r, inp = ana_case
    assert "NO_GOAL_LINK" in [p.code for p in validate_update(ana_update(goal_link=" "), r, inp)]
    assert "PICK_NOT_ALLOWED" in [p.code for p in validate_update(ana_update(tied_to_main_goal=False), r, inp)]
    assert "BEATS_NOT_OPEN" in [p.code for p in validate_update(ana_update(beats=3), r, inp)]  # Diana is the #1


# ---------------------------------------------------------------- CLI
def make_home(tmp_path, snapshot, roster):
    home = tmp_path / "NF"
    (home / ".work").mkdir(parents=True)
    (home / "briefs").mkdir()
    (home / "briefs" / f"{snapshot['week_of']}-network-focus.json").write_text(json.dumps(snapshot), encoding="utf-8")
    (home / ".work" / "roster.json").write_text(json.dumps(roster), encoding="utf-8")
    return home


def run_prep(home):
    p = subprocess.run([sys.executable, str(SCRIPTS / "update_prep.py"), "--work", str(home / ".work")],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "NF_HOME": str(home)})
    return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])


def test_update_prep_cli_ok(tmp_path, snapshot, roster_dict):
    home = make_home(tmp_path, snapshot, roster_plus(roster_dict, ANA))
    code, out = run_prep(home)
    assert (code, out) == (0, {"status": "ok", "people": 1})
    assert json.loads((home / ".work" / "update-input.json").read_text(encoding="utf-8"))["people"][0]["name"] == "Ana Ruiz"


def test_update_prep_cli_nothing(tmp_path, snapshot, roster_dict):
    code, out = run_prep(make_home(tmp_path, snapshot, roster_dict))
    assert code == 0 and out == {"status": "nothing", "message": "Nobody new or changed since this week's brief."}


def test_update_prep_cli_blocked_when_stale(tmp_path, snapshot, roster_dict):
    snapshot["week_of"] = snapshot["brief"]["week_of"] = "2026-11-16"
    code, out = run_prep(make_home(tmp_path, snapshot, roster_plus(roster_dict, ANA)))
    assert code == 2 and out["status"] == "blocked" and "Click Generate instead" in out["message"]


def test_update_prep_cli_blocked_without_index(tmp_path, snapshot, roster_dict):
    del snapshot["roster_index"]
    code, out = run_prep(make_home(tmp_path, snapshot, roster_plus(roster_dict, ANA)))
    assert code == 2 and "before the page could track changes" in out["message"]


def test_validate_cli_update_mode(tmp_path, snapshot, roster_dict):
    r = roster_plus(roster_dict, ANA)
    work = tmp_path / "w"
    work.mkdir()
    for name, doc in (("roster.json", r), ("update-input.json", prep_update(snapshot, r, {})), ("update.json", ana_update())):
        (work / name).write_text(json.dumps(doc), encoding="utf-8")
    p = subprocess.run([sys.executable, str(SCRIPTS / "validate_brief.py"), "update", str(work / "update.json"),
                        "--roster", str(work / "roster.json"), "--input", str(work / "update-input.json")],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0 and json.loads(p.stdout)["ok"] is True
