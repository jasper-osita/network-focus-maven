import json
from datetime import date

from schedule import ics_for, load_schedule, set_when, suggest


def test_suggest_puts_the_top_pick_first_and_spreads_the_week(brief_dict):
    plan = suggest(brief_dict)
    assert [(p["name"], p["when"], p["kind"]) for p in plan] == [
        ("Diana Chen", "2026-11-23T10:00", "email"),     # the #1 on Monday morning
        ("Marcus Wei", "2026-11-24T10:00", "email"),
        ("Reid Hoffman", "2026-11-25T10:00", "email"),
        ("Paul Christiano", "2026-11-26T10:00", "email"),
        ("Sarah Guo", "2026-11-27T10:00", "email"),
        ("Priya Mehta", "2026-11-24T14:00", "email"),    # dormant notes go in the afternoons
        ("Brian Armstrong", "2026-11-26T14:00", "email"),
    ]
    assert all(p["minutes"] == 15 for p in plan)


def test_call_moves_are_calls(brief_dict):
    brief_dict["focus"][1]["move"] = "Call Marcus this week to walk through the full deck before Q3."
    marcus = next(p for p in suggest(brief_dict) if p["name"] == "Marcus Wei")
    assert marcus["kind"] == "call" and marcus["minutes"] == 30


def test_changed_times_are_kept_per_week(tmp_path):
    set_when(tmp_path, "2026-11-23", 3, "2026-11-25T16:30", "call")
    assert load_schedule(tmp_path, "2026-11-23") == {"3": {"when": "2026-11-25T16:30", "kind": "call"}}
    assert load_schedule(tmp_path, "2026-11-30") == {}
    (tmp_path / ".schedule.json").write_text("{broken", encoding="utf-8")
    assert load_schedule(tmp_path, "2026-11-23") == {}


def test_ics_invite(brief_dict):
    item = {"name": "Diana Chen", "kind": "call", "when": "2026-11-23T10:00", "minutes": 30,
            "move": "Call Diana; ask for intros.", "message": "Hi Diana, thank you, again."}
    ics = ics_for(item, "3@network-focus")
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    for line in ("BEGIN:VEVENT", "DTSTART:20261123T100000", "DTEND:20261123T103000", "SUMMARY:Call Diana Chen"):
        assert line + "\r\n" in ics
    assert "Call Diana\; ask for intros." in ics and "thank you\\, again." in ics   # escaped per RFC 5545
