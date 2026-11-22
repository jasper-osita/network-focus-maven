"""CEO dashboard data (standard library only): the newest brief snapshot plus what has been marked done.
Snapshots live in briefs/<week_of>-network-focus.json; progress in .progress.json as {week: {row_id: true}}."""
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

SNAPSHOT_GLOB = "*-network-focus.json"
PROGRESS_FILE = ".progress.json"


def week_of(today: date) -> date:
    """Monday of this week (Mon–Fri) or of next week (Sat/Sun). Same rule as nf_core.workspace.week_of."""
    wd = today.weekday()
    return today + timedelta(days=7 - wd) if wd >= 5 else today - timedelta(days=wd)


def _snapshots(nf_home: Path) -> list[dict]:
    snaps = []
    for f in (Path(nf_home) / "briefs").glob(SNAPSHOT_GLOB):
        try:
            s = json.loads(f.read_text())
            if isinstance(s, dict) and isinstance(s.get("brief"), dict) and s.get("week_of"):
                snaps.append(s)
        except (OSError, ValueError):
            continue
    return sorted(snaps, key=lambda s: s["week_of"], reverse=True)


def load_progress(nf_home: Path) -> dict:
    try:
        data = json.loads((Path(nf_home) / PROGRESS_FILE).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _norm(name) -> str:
    return " ".join(str(name).split()).casefold()


def _marked(marks: dict, row_id: int, name: str) -> bool:
    """A mark counts only for the same person: rows shift if the spreadsheet is edited and re-run mid-week."""
    stored = marks.get(str(row_id))
    return isinstance(stored, str) and _norm(stored) == _norm(name)


def set_done(nf_home: Path, week: str, row_id: int, done: bool, name: str) -> None:
    """Record a move as done (or not), keyed by row and name. Written atomically so a crash can't half-write it."""
    data = load_progress(nf_home)
    week_marks = data.get(week) if isinstance(data.get(week), dict) else {}
    if done:
        week_marks[str(row_id)] = name
    else:
        week_marks.pop(str(row_id), None)
    data[week] = week_marks
    fd, tmp = tempfile.mkstemp(dir=nf_home, prefix=".progress-", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, Path(nf_home) / PROGRESS_FILE)


def pick_ids(snapshot: dict) -> set[int]:
    b = snapshot["brief"]
    return {x["row_id"] for x in b.get("focus", []) + b.get("dormant", [])}


def _score(snapshot: dict, progress: dict) -> dict:
    marks = progress.get(snapshot["week_of"], {})
    marks = marks if isinstance(marks, dict) else {}
    b = snapshot["brief"]
    picks = b.get("focus", []) + b.get("dormant", [])
    return {"done": sum(1 for x in picks if _marked(marks, x["row_id"], x.get("name", ""))), "total": len(picks)}


def _person(item: dict, snapshot: dict, marks: dict) -> dict:
    row = snapshot.get("people", {}).get(str(item["row_id"]), {})
    goals = snapshot.get("goals", {})
    out = {
        "row_id": item["row_id"],
        "name": item.get("name") or row.get("name", ""),
        "role_company": ", ".join(x for x in (row.get("role"), row.get("company")) if x),
        "goals": [goals[str(g)] for g in item.get("goals", []) if str(g) in goals],
        "move": item.get("move", ""),
        "why": item.get("why", ""),
        "message": item.get("message", ""),
        "done": _marked(marks, item["row_id"], item.get("name") or row.get("name", "")),
    }
    if "days_since_contact" in item:
        out["days"] = item["days_since_contact"]
    return out


def dashboard_payload(nf_home: Path, today: date) -> dict:
    snaps = _snapshots(nf_home)
    if not snaps or not snaps[0]["brief"].get("focus"):
        return {"empty": True}
    snap, progress = snaps[0], load_progress(nf_home)
    marks = progress.get(snap["week_of"], {})
    marks = marks if isinstance(marks, dict) else {}
    focus = snap["brief"]["focus"]
    stem = f"{snap['week_of']}-network-focus"  # render_pdf writes the PDF next to the snapshot
    earlier = [s for s in snaps[1:] if s["week_of"] < snap["week_of"]]
    return {
        "week_of": snap["week_of"],
        "stale": snap["week_of"] != week_of(today).isoformat(),
        "pdf_url": f"/briefs/{stem}.pdf",
        "top": _person(focus[0], snap, marks),
        "others": [_person(x, snap, marks) for x in focus[1:]],
        "dormant": [_person(x, snap, marks) for x in snap["brief"].get("dormant", [])],
        "questions": snap.get("questions", []),
        "going_quiet": snap.get("going_quiet", []),
        "banner": snap.get("banner", []),
        "progress": {**_score(snap, progress), "last_week": _score(earlier[0], progress) if earlier else None},
    }
