import copy
import json
from datetime import date

import pytest

from dashboard_data import dashboard_payload, load_progress, set_done, week_of
from nf_core.snapshot import build_snapshot


def write_snapshot(home, snap):
    (home / "briefs").mkdir(parents=True, exist_ok=True)
    (home / "briefs" / f"{snap['week_of']}-network-focus.json").write_text(json.dumps(snap))


@pytest.fixture
def snapshot(brief_dict, roster_dict, warnings_dict):
    return build_snapshot(brief_dict, roster_dict, warnings_dict)


@pytest.fixture
def home_with_snapshot(tmp_path, snapshot):
    home = tmp_path / "Network Focus"
    write_snapshot(home, snapshot)
    return home


def test_week_of_matches_workspace_rule():
    assert week_of(date(2026, 11, 25)) == date(2026, 11, 23) and week_of(date(2026, 11, 21)) == date(2026, 11, 23)


def test_no_snapshot_is_empty(tmp_path):
    assert dashboard_payload(tmp_path, date(2026, 11, 23)) == {"empty": True}


def test_payload_top_and_progress(home_with_snapshot):
    set_done(home_with_snapshot, "2026-11-23", 3, True, "Diana Chen")
    p = dashboard_payload(home_with_snapshot, date(2026, 11, 23))
    assert p["top"]["name"] == "Diana Chen" and p["top"]["done"] is True and p["top"]["goals"] == ["Hire a CTO"]
    assert p["top"]["role_company"] == "CTO, Stripe" and p["top"]["message"].startswith("Hi Diana")
    assert len(p["others"]) == 4 and len(p["dormant"]) == 2 and p["dormant"][0]["days"] == 128
    assert p["progress"] == {"done": 1, "total": 7, "last_week": None} and p["stale"] is False
    assert [g["name"] for g in p["going_quiet"]] == ["Lin Wang", "Patrick Collison"]
    assert p["pdf_url"] == "/briefs/2026-11-23-network-focus.pdf" and p["week_of"] == "2026-11-23"


def test_last_week_score(home_with_snapshot, snapshot):
    old = copy.deepcopy(snapshot)
    old["week_of"] = old["brief"]["week_of"] = "2026-11-16"
    write_snapshot(home_with_snapshot, old)
    for r, n in ((3, "Diana Chen"), (2, "Marcus Wei"), (6, "Reid Hoffman")):
        set_done(home_with_snapshot, "2026-11-16", r, True, n)
    p = dashboard_payload(home_with_snapshot, date(2026, 11, 23))
    assert p["week_of"] == "2026-11-23" and p["progress"]["last_week"] == {"done": 3, "total": 7}


def test_stale_brief_flagged(home_with_snapshot):
    assert dashboard_payload(home_with_snapshot, date(2026, 12, 1))["stale"] is True


def test_progress_ignores_rows_not_in_brief(home_with_snapshot):
    set_done(home_with_snapshot, "2026-11-23", 99, True, "Nobody")
    assert dashboard_payload(home_with_snapshot, date(2026, 11, 23))["progress"]["done"] == 0


def test_missing_message_tolerated(home_with_snapshot, snapshot):
    del snapshot["brief"]["focus"][0]["message"]
    write_snapshot(home_with_snapshot, snapshot)
    assert dashboard_payload(home_with_snapshot, date(2026, 11, 23))["top"]["message"] == ""


def test_corrupt_progress_file_ignored(home_with_snapshot):
    (home_with_snapshot / ".progress.json").write_text("{")
    assert dashboard_payload(home_with_snapshot, date(2026, 11, 23))["progress"]["done"] == 0
    set_done(home_with_snapshot, "2026-11-23", 3, True, "Diana Chen")
    assert load_progress(home_with_snapshot) == {"2026-11-23": {"3": "Diana Chen"}}


def test_undo_done(home_with_snapshot):
    set_done(home_with_snapshot, "2026-11-23", 3, True, "Diana Chen")
    set_done(home_with_snapshot, "2026-11-23", 3, False, "Diana Chen")
    assert dashboard_payload(home_with_snapshot, date(2026, 11, 23))["progress"]["done"] == 0


def test_marks_follow_the_person_not_the_row(home_with_snapshot, snapshot):
    set_done(home_with_snapshot, "2026-11-23", 3, True, "Diana Chen")
    # same-week re-run after a row was deleted: Diana moves to row 2, Marcus to row 3
    for it in snapshot["brief"]["focus"]:
        it["row_id"] = {3: 2, 2: 3}.get(it["row_id"], it["row_id"])
    snapshot["people"]["2"], snapshot["people"]["3"] = snapshot["people"]["3"], snapshot["people"]["2"]
    write_snapshot(home_with_snapshot, snapshot)
    p = dashboard_payload(home_with_snapshot, date(2026, 11, 23))
    done = {x["name"]: x["done"] for x in [p["top"], *p["others"]]}
    assert done["Diana Chen"] is False and done["Marcus Wei"] is False and p["progress"]["done"] == 0


def test_goal_rings(home_with_snapshot):
    set_done(home_with_snapshot, "2026-11-23", 3, True, "Diana Chen")
    set_done(home_with_snapshot, "2026-11-23", 5, True, "Sarah Guo")
    goals = dashboard_payload(home_with_snapshot, date(2026, 11, 23))["goals"]
    assert goals == [{"id": 1, "title": "Raise Series C", "done": 1, "total": 5},
                     {"id": 2, "title": "Hire a CTO", "done": 1, "total": 1},
                     {"id": 3, "title": "Build relationships in AI safety", "done": 1, "total": 2}]


def test_goal_with_no_move_has_zero_total(tmp_path, snapshot):
    snapshot["brief"]["focus"] = [f for f in snapshot["brief"]["focus"] if 2 not in f["goals"]]
    write_snapshot(tmp_path, snapshot)
    goals = dashboard_payload(tmp_path, date(2026, 11, 23))["goals"]
    assert goals[1] == {"id": 2, "title": "Hire a CTO", "done": 0, "total": 0}


def test_old_snapshot_dormant_without_goals_still_loads(tmp_path, snapshot):
    for d in snapshot["brief"]["dormant"]:
        del d["goals"]
    snapshot["version"] = 1
    write_snapshot(tmp_path, snapshot)
    p = dashboard_payload(tmp_path, date(2026, 11, 23))
    assert p["goals"][0]["total"] == 3 and p["progress"]["total"] == 7


def test_person_role_falls_back_to_who(tmp_path, snapshot):
    item = snapshot["brief"]["focus"][1]
    item.update({"row_id": 99, "missing": True, "who": "Partner, Sequoia Capital", "new": True})
    snapshot["brief"]["considering"] = [{"row_id": 7, "name": "Tom Park", "note": "Strong CTO fit."}]
    snapshot["brief"]["updates"] = [{"at": "2026-11-25T10:50", "added": [], "bumped": []}]
    write_snapshot(tmp_path, snapshot)
    p = dashboard_payload(tmp_path, date(2026, 11, 23))
    assert p["others"][0]["role_company"] == "Partner, Sequoia Capital" and p["others"][0]["new"] is True
    assert p["top"]["new"] is False and p["considering"][0]["name"] == "Tom Park"
    assert p["updated_at"] == "2026-11-25T10:50"
