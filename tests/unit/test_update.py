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


# ---------------------------------------------------------------- apply
from nf_core.brief_checks import validate_brief  # noqa: E402
from nf_core.update import apply_update  # noqa: E402

NOW = "2026-11-25T10:50"


def applied(snapshot, roster, update, marks=None):
    inp = prep_update(snapshot, roster, marks or {})
    return apply_update(snapshot, roster, inp, update, NOW)


def names(items):
    return [x["name"] for x in items]


def untied(row_id, name, note="Strong fit, nothing tying them to the round yet.", evidence=("Met at a dinner",)):
    return {"row_id": row_id, "name": name, "tied_to_main_goal": False, "evidence": list(evidence), "goal_link": "", "consider": note}


def test_apply_fills_empty_slot_first(snapshot, roster_dict):
    snapshot["brief"]["focus"] = snapshot["brief"]["focus"][:4]
    brief, _, summary = applied(snapshot, roster_plus(roster_dict, ANA), ana_update())
    assert names(brief["focus"]) == ["Diana Chen", "Marcus Wei", "Reid Hoffman", "Paul Christiano", "Ana Ruiz"]
    assert brief["focus"][4]["new"] is True and summary == {"added": ["Ana Ruiz"], "bumped": [], "refused": []}
    assert brief["updates"] == [{"at": NOW, "added": ["Ana Ruiz"], "bumped": []}]


def test_apply_bumps_weakest_open_pick(snapshot, roster_dict):
    brief, _, summary = applied(snapshot, roster_plus(roster_dict, ANA), ana_update(beats=6))
    assert names(brief["focus"]) == ["Diana Chen", "Marcus Wei", "Reid Hoffman", "Paul Christiano", "Ana Ruiz"]
    assert summary["bumped"] == ["Sarah Guo"] and brief["focus"][4]["new"] is True
    assert {"row_id": 5, "name": "Sarah Guo", "note": "Moved here to make room for Ana Ruiz."} in brief["considering"]
    assert validate_brief(brief, roster_plus(roster_dict, ANA)) == []


def test_apply_never_bumps_done_or_top(snapshot, roster_dict):
    marks = {"2": "Marcus Wei", "6": "Reid Hoffman", "4": "Paul Christiano", "5": "Sarah Guo"}
    brief, _, summary = applied(snapshot, roster_plus(roster_dict, ANA), ana_update(beats=3), marks)
    assert summary["refused"] == ["Ana Ruiz"] and names(brief["focus"]) == names(snapshot["brief"]["focus"])


def test_apply_uses_weakest_open_slot_not_model_target(snapshot, roster_dict):
    brief, _, summary = applied(snapshot, roster_plus(roster_dict, ANA), ana_update(beats=6), {"6": "Reid Hoffman"})
    assert summary["bumped"] == ["Sarah Guo"] and "Reid Hoffman" in names(brief["focus"])


def test_apply_keeps_goal_coverage(snapshot, roster_dict):
    f = snapshot["brief"]["focus"]
    f[4]["goals"] = [1]                      # Sarah: Series C only
    f[3], f[4] = f[4], f[3]                  # Paul (the only AI-safety pick) is now the weakest
    brief, _, summary = applied(snapshot, roster_plus(roster_dict, ANA), ana_update(beats=6))
    assert summary["bumped"] == ["Sarah Guo"] and "Paul Christiano" in names(brief["focus"])
    marks = {"2": "Marcus Wei", "6": "Reid Hoffman", "5": "Sarah Guo"}
    brief, _, summary = applied(snapshot, roster_plus(roster_dict, ANA), ana_update(beats=4), marks)
    assert summary["refused"] == ["Ana Ruiz"] and "Paul Christiano" in names(brief["focus"])
    note = next(c["note"] for c in brief["considering"] if c["name"] == "Ana Ruiz")
    assert "no open slot could be freed this week" in note


def test_apply_untied_goes_to_considering(snapshot, roster_dict):
    tom = dict(row_id=26, name="Tom Park", company="Figma", role="Engineering Director", tags=["cto-candidate"])
    brief, _, summary = applied(snapshot, roster_plus(roster_dict, tom), {"people": [untied(26, "Tom Park", "Strong CTO fit; rank him Monday.")]})
    assert summary == {"added": [], "bumped": [], "refused": []}
    assert brief["considering"] == [{"row_id": 26, "name": "Tom Park", "note": "Strong CTO fit; rank him Monday."}]
    assert names(brief["focus"]) == names(snapshot["brief"]["focus"])


def test_apply_remaps_rows_and_marks(snapshot, roster_dict):
    brief, marks, _ = applied(snapshot, roster_plus(roster_dict, shift=1), {"people": [untied(1, "Zed Top")]}, {"2": "Marcus Wei"})
    assert next(x["row_id"] for x in brief["focus"] if x["name"] == "Marcus Wei") == 3
    assert next(x["row_id"] for x in brief["dormant"] if x["name"] == "Priya Mehta") == 17
    assert marks == {"3": "Marcus Wei"}


def test_apply_missing_pick_kept_with_question(snapshot, roster_dict):
    brief, _, _ = applied(snapshot, roster_plus(roster_dict, ANA, drop=("Paul Christiano",)),
                          {"people": [untied(26, "Ana Ruiz")]})
    paul = next(x for x in brief["focus"] if x["name"] == "Paul Christiano")
    assert paul["missing"] is True and paul["row_id"] == -4 and paul["who"] == "Researcher, ARC Evals"
    assert brief["update_questions"] == ["Paul Christiano is no longer in the roster. Remove them from this week's list?"]


def test_apply_considering_accumulates_and_dedupes(snapshot, roster_dict):
    snapshot["brief"]["considering"] = [{"row_id": 99, "name": "Old Person", "note": "From Tuesday."},
                                        {"row_id": 26, "name": "Ana Ruiz", "note": "Older note."}]
    brief, _, _ = applied(snapshot, roster_plus(roster_dict, ANA), {"people": [untied(26, "Ana Ruiz", "Newer note.")]})
    assert brief["considering"] == [{"row_id": 99, "name": "Old Person", "note": "From Tuesday."},
                                    {"row_id": 26, "name": "Ana Ruiz", "note": "Newer note."}]
    brief, _, _ = applied(snapshot, roster_plus(roster_dict, ANA), ana_update(beats=6))
    assert "Ana Ruiz" not in names(brief["considering"])


def write_work(home, snapshot, roster, update, marks=None):
    work = home / ".work"
    (home / "briefs").mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    (home / "briefs" / f"{snapshot['week_of']}-network-focus.json").write_text(json.dumps(snapshot), encoding="utf-8")
    inp = prep_update(snapshot, roster, marks or {})
    for name, doc in (("roster.json", roster), ("update-input.json", inp), ("update.json", update)):
        (work / name).write_text(json.dumps(doc), encoding="utf-8")
    if marks:
        (home / ".progress.json").write_text(json.dumps({snapshot["week_of"]: marks}), encoding="utf-8")
    return work


def run_apply(work):
    p = subprocess.run([sys.executable, str(SCRIPTS / "apply_update.py"), "--work", str(work), "--now", NOW],
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])


def test_apply_update_cli_refuses_invalid(tmp_path, snapshot, roster_dict):
    work = write_work(tmp_path / "NF", snapshot, roster_plus(roster_dict, ANA), ana_update(evidence=["Not in the row at all"]))
    code, out = run_apply(work)
    assert code == 1 and out["ok"] is False and out["problems"] and not (work / "brief.json").exists()


def test_apply_update_cli_writes_brief_and_keeps_old_marks(tmp_path, snapshot, roster_dict):
    home = tmp_path / "NF"
    work = write_work(home, snapshot, roster_plus(roster_dict, shift=1),
                      {"people": [untied(1, "Zed Top", evidence=["Old friend from school days"])]}, {"2": "Marcus Wei"})
    code, out = run_apply(work)
    assert code == 0 and out == {"ok": True, "added": [], "bumped": [], "refused": []}
    assert json.loads((work / "brief.json").read_text(encoding="utf-8"))["updates"][0]["at"] == NOW
    marks = json.loads((home / ".progress.json").read_text(encoding="utf-8"))["2026-11-23"]
    assert marks == {"2": "Marcus Wei", "3": "Marcus Wei"}


def test_cited_rows_only_new(tmp_path, snapshot, roster_dict):
    r = roster_plus(roster_dict, ANA)
    brief, _, _ = applied(snapshot, r, ana_update(beats=6))
    for name, doc in (("brief.json", brief), ("roster.json", r)):
        (tmp_path / name).write_text(json.dumps(doc), encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPTS / "validate_brief.py"), "cited-rows", str(tmp_path / "brief.json"),
                    "--roster", str(tmp_path / "roster.json"), "--out", str(tmp_path / "cited.json"), "--only-new"],
                   capture_output=True, text=True, check=True)
    assert [c["name"] for c in json.loads((tmp_path / "cited.json").read_text(encoding="utf-8"))["contacts"]] == ["Ana Ruiz"]


# ---------------------------------------------------------------- review fixes
def roster_deleted(roster, name):
    """Delete a row the way a spreadsheet does: every row below it moves up by one."""
    r = copy.deepcopy(roster)
    gone = next(c["row_id"] for c in r["contacts"] if c["name"] == name)
    r["contacts"] = [c for c in r["contacts"] if c["name"] != name]
    for c in r["contacts"]:
        if c["row_id"] > gone:
            c["row_id"] -= 1
    return r


def slot_row(inp, name):
    return next(s["row_id"] for s in inp["open_slots"] if s.get("name") == name)


def test_apply_deleted_middle_row_never_collides(snapshot, roster_dict):
    r = roster_deleted(roster_plus(roster_dict, ANA), "Paul Christiano")   # Sarah moves from row 5 to row 4
    inp = prep_update(snapshot, r, {})
    brief, _, summary = apply_update(snapshot, r, inp, ana_update(row_id=25, beats=slot_row(inp, "Reid Hoffman")), NOW)
    paul = next(x for x in brief["focus"] if x["name"] == "Paul Christiano")
    assert paul["missing"] is True and paul["row_id"] == -4 and paul["who"] == "Researcher, ARC Evals"
    assert summary["bumped"] == ["Sarah Guo"] and "Sarah Guo" not in names(brief["focus"])
    assert names(brief["focus"]) == ["Diana Chen", "Marcus Wei", "Reid Hoffman", "Paul Christiano", "Ana Ruiz"]
    ids = [x["row_id"] for x in brief["focus"] + brief["dormant"]]
    assert len(ids) == len(set(ids)) and validate_brief(brief, r) == []


def test_apply_deleted_top_stays_top(snapshot, roster_dict):
    r = roster_deleted(roster_plus(roster_dict, ANA), "Diana Chen")       # Paul moves onto Diana's old row 3
    inp = prep_update(snapshot, r, {"3": "Diana Chen"})
    brief, marks, summary = apply_update(snapshot, r, inp, ana_update(row_id=25, beats=slot_row(inp, "Reid Hoffman")), NOW)
    assert brief["focus"][0]["name"] == "Diana Chen" and brief["focus"][0]["row_id"] == -3
    assert summary["bumped"] == ["Sarah Guo"] and "Paul Christiano" in names(brief["focus"])
    assert marks["-3"] == "Diana Chen" and validate_brief(brief, r) == []


def test_apply_deleted_coming_up_person_is_dropped_with_question(snapshot, roster_dict):
    r = roster_deleted(roster_plus(roster_dict, ANA), "Maya Patel")
    brief, _, _ = applied(snapshot, r, {"people": [untied(25, "Ana Ruiz")]})
    assert brief["coming_up"] == [] and any(q.startswith("Maya Patel is no longer in the roster") for q in brief["update_questions"])
    assert validate_brief(brief, r) == []


def test_prep_matches_names_with_curly_quotes(snapshot, roster_dict):
    r = roster_plus(roster_dict, ANA)
    next(c for c in r["contacts"] if c["row_id"] == 2)["name"] = "Marcus O'Wei"
    snapshot["people"]["2"]["name"] = "Marcus O'Wei"           # the row, as the snapshot saved it
    snapshot["brief"]["focus"][1]["name"] = "Marcus O’Wei"   # the model wrote a curly apostrophe
    assert picks_by_name(prep_update(snapshot, r, {}))["Marcus O’Wei"]["row_id"] == 2


def test_apply_update_cli_recomputes_slots_and_marks(tmp_path, snapshot, roster_dict):
    home = tmp_path / "NF"
    r = roster_plus(roster_dict, ANA)
    work = write_work(home, snapshot, r, ana_update(beats=6))
    inp = json.loads((work / "update-input.json").read_text(encoding="utf-8"))
    inp["open_slots"].append({"kind": "replace", "row_id": 3, "name": "Diana Chen", "rank": 0})  # tampered
    (work / "update-input.json").write_text(json.dumps(inp), encoding="utf-8")
    (home / ".progress.json").write_text(json.dumps({"2026-11-23": {"5": "Sarah Guo"}}), encoding="utf-8")  # ticked meanwhile
    code, out = run_apply(work)
    brief = json.loads((work / "brief.json").read_text(encoding="utf-8"))
    assert code == 0 and out["bumped"] == ["Paul Christiano"]
    assert brief["focus"][0]["name"] == "Diana Chen" and "Sarah Guo" in names(brief["focus"])


def test_locked_picks_checked_before_render(snapshot, roster_dict):
    from nf_core.update import locked_violations
    r = roster_plus(roster_dict, ANA)
    brief, _, _ = applied(snapshot, r, ana_update(beats=6))
    assert locked_violations(snapshot, brief, {}) == []
    swapped = copy.deepcopy(brief)
    swapped["focus"][0], swapped["focus"][4] = swapped["focus"][4], swapped["focus"][0]
    assert [p.code for p in locked_violations(snapshot, swapped, {})] == ["LOCKED_PICK_MOVED"]
    dropped = copy.deepcopy(brief)
    dropped["focus"] = [f for f in dropped["focus"] if f["name"] != "Marcus Wei"]
    assert [p.code for p in locked_violations(snapshot, dropped, {"2": "Marcus Wei"})] == ["LOCKED_PICK_MOVED"]
    no_dormant = copy.deepcopy(brief)
    no_dormant["dormant"] = no_dormant["dormant"][:1]
    assert [p.code for p in locked_violations(snapshot, no_dormant, {})] == ["LOCKED_PICK_MOVED"]


def test_cited_rows_only_new_writes_new_picks_brief(tmp_path, snapshot, roster_dict):
    r = roster_plus(roster_dict, ANA)
    brief, _, _ = applied(snapshot, r, ana_update(beats=6))
    for name, doc in (("brief.json", brief), ("roster.json", r)):
        (tmp_path / name).write_text(json.dumps(doc), encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPTS / "validate_brief.py"), "cited-rows", str(tmp_path / "brief.json"),
                    "--roster", str(tmp_path / "roster.json"), "--out", str(tmp_path / "cited.json"), "--only-new"],
                   capture_output=True, text=True, check=True)
    only = json.loads((tmp_path / "new-picks.json").read_text(encoding="utf-8"))
    assert names(only["focus"]) == ["Ana Ruiz"] and only["dormant"] == [] and only["coming_up"] == []
