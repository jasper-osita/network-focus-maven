"""When to make each move: a suggested time for every pick (code, no model), changes the chief of staff saves,
and calendar invites (.ics) that open in Google Calendar, Outlook or Apple Calendar. Standard library only."""
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCHEDULE_FILE = ".schedule.json"
_CALL = re.compile(r"\b(call|coffee|meet|meeting|lunch|dinner|zoom)\b", re.I)
_WRITE = re.compile(r"\b(email|e-mail|note|message|send|write|reply|text|intro)\b", re.I)
# Morning slots Mon-Fri for focus picks in priority order (the #1 first), then afternoons for dormant notes.
FOCUS_SLOTS = [(0, 10), (1, 10), (2, 10), (3, 10), (4, 10), (0, 14), (2, 14), (4, 14)]
DORMANT_SLOTS = [(1, 14), (3, 14), (4, 15), (0, 15), (2, 15)]


def kind_of(move: str) -> str:
    """'call' or 'email': whichever channel the move names first."""
    c, w = _CALL.search(move or ""), _WRITE.search(move or "")
    if c and (not w or c.start() < w.start()):
        return "call"
    return "email"


def suggest(brief: dict) -> list[dict]:
    monday = date.fromisoformat(brief["week_of"])
    plan = []
    for items, slots in ((brief.get("focus", []), FOCUS_SLOTS), (brief.get("dormant", []), DORMANT_SLOTS)):
        for item, (day, hour) in zip(items, slots):
            kind = kind_of(item.get("move", ""))
            when = datetime.combine(monday + timedelta(days=day), datetime.min.time()).replace(hour=hour)
            plan.append({"row_id": item["row_id"], "name": item["name"], "kind": kind,
                         "when": when.strftime("%Y-%m-%dT%H:%M"), "minutes": 30 if kind == "call" else 15})
    return plan


def load_schedule(nf_home: Path, week: str) -> dict:
    try:
        data = json.loads((Path(nf_home) / SCHEDULE_FILE).read_text(encoding="utf-8"))
        week_data = data.get(week, {}) if isinstance(data, dict) else {}
        return week_data if isinstance(week_data, dict) else {}
    except (OSError, ValueError):
        return {}


def set_when(nf_home: Path, week: str, row_id: int, when: str, kind: str | None = None) -> None:
    """Save the chief of staff's own time (and call/email) for one move this week. Written atomically."""
    nf_home = Path(nf_home)
    try:
        data = json.loads((nf_home / SCHEDULE_FILE).read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    week_data = data.get(week) if isinstance(data.get(week), dict) else {}
    entry = {"when": when}
    if kind in ("call", "email"):
        entry["kind"] = kind
    week_data[str(row_id)] = entry
    data[week] = week_data
    fd, tmp = tempfile.mkstemp(dir=nf_home, prefix=".schedule-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, nf_home / SCHEDULE_FILE)


def valid_when(value) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M")
        return True
    except (TypeError, ValueError):
        return False


def _esc(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def ics_for(item: dict, uid: str) -> str:
    """One calendar invite. Times are 'floating' (no time zone), so they land at that clock time wherever she is."""
    start = datetime.strptime(item["when"], "%Y-%m-%dT%H:%M")
    end = start + timedelta(minutes=item.get("minutes") or 15)
    verb = "Call" if item.get("kind") == "call" else "Email"
    desc = item.get("move", "")
    if item.get("message"):
        desc += "\n\nReady-to-send message:\n" + item["message"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Network Focus//EN", "BEGIN:VEVENT",
             f"UID:{uid}", f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
             f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
             f"SUMMARY:{_esc(verb + ' ' + item['name'])}", f"DESCRIPTION:{_esc(desc)}",
             "BEGIN:VALARM", "TRIGGER:-PT10M", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(verb + ' ' + item['name'])}", "END:VALARM",
             "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"
