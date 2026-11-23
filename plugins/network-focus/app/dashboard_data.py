"""CEO dashboard data (standard library only): the newest brief snapshot plus what has been marked done.
Snapshots live in briefs/<week_of>-network-focus.json; progress in .progress.json as {week: {row_id: true}}."""
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from schedule import load_schedule, suggest

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
            s = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(s, dict) and isinstance(s.get("brief"), dict) and s.get("week_of"):
                snaps.append(s)
        except (OSError, ValueError):
            continue
    return sorted(snaps, key=lambda s: s["week_of"], reverse=True)


def roster_dir(nf_home: Path) -> Path:
    """Where rosters live: the Google Drive folder from settings.json, else the local inbox.
    Same rule as nf_core.workspace.Workspace.inbox, repeated here because the page server is stdlib-only."""
    try:
        folder = json.loads((Path(nf_home) / "settings.json").read_text(encoding="utf-8")).get("roster_folder")
    except (OSError, ValueError, AttributeError):
        folder = None
    return Path(folder) if isinstance(folder, str) and folder else Path(nf_home) / "inbox"


def latest_snapshot_path(nf_home: Path) -> Path | None:
    """The newest brief's snapshot file, by week (same rule as the dashboard)."""
    best = None
    for f in (Path(nf_home) / "briefs").glob(SNAPSHOT_GLOB):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(s, dict) and isinstance(s.get("brief"), dict) and s.get("week_of"):
            if best is None or s["week_of"] > best[0]:
                best = (s["week_of"], f)
    return best[1] if best else None


def load_progress(nf_home: Path) -> dict:
    try:
        data = json.loads((Path(nf_home) / PROGRESS_FILE).read_text(encoding="utf-8"))
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
    with os.fdopen(fd, "w", encoding="utf-8") as f:
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
        "role_company": ", ".join(x for x in (row.get("role"), row.get("company")) if x) or item.get("who", ""),
        "company": row.get("company", ""),
        "goals": [goals[str(g)] for g in item.get("goals", []) if str(g) in goals],
        "move": item.get("move", ""),
        "why": item.get("why", ""),
        "message": item.get("message", ""),
        "done": _marked(marks, item["row_id"], item.get("name") or row.get("name", "")),
        "new": bool(item.get("new")),
    }
    if "days_since_contact" in item:
        out["days"] = item["days_since_contact"]
    return out


def _goal_rings(snapshot: dict, marks: dict) -> list[dict]:
    """This week's moves per goal, and how many are done. A move serving two goals counts for both."""
    b = snapshot["brief"]
    picks = b.get("focus", []) + b.get("dormant", [])
    rings = []
    for gid, title in sorted(snapshot.get("goals", {}).items(), key=lambda kv: int(kv[0])):
        mine = [x for x in picks if int(gid) in (x.get("goals") or [])]
        rings.append({"id": int(gid), "title": title, "total": len(mine),
                      "done": sum(1 for x in mine if _marked(marks, x["row_id"], x.get("name", "")))})
    return [{"id": r["id"], "title": r["title"], "done": r["done"], "total": r["total"]} for r in rings]


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
    top, others = _person(focus[0], snap, marks), [_person(x, snap, marks) for x in focus[1:]]
    dormant = [_person(x, snap, marks) for x in snap["brief"].get("dormant", [])]
    plan = {p["row_id"]: p for p in suggest(snap["brief"])}
    for row, mine in load_schedule(nf_home, snap["week_of"]).items():  # the chief of staff's own times win
        if isinstance(mine, dict) and row.lstrip("-").isdigit() and int(row) in plan:
            plan[int(row)].update({k: v for k, v in mine.items() if k in ("when", "kind")})
            plan[int(row)]["minutes"] = 30 if plan[int(row)]["kind"] == "call" else 15
    for p in [top, *others, *dormant]:
        p.update({k: plan[p["row_id"]][k] for k in ("when", "kind", "minutes")} if p["row_id"] in plan else {})
    return {
        "week_of": snap["week_of"],
        "stale": snap["week_of"] != week_of(today).isoformat(),
        "pdf_url": f"/briefs/{stem}.pdf",
        "top": top,
        "others": others,
        "dormant": dormant,
        "questions": snap.get("questions", []),
        "going_quiet": snap.get("going_quiet", []),
        "banner": snap.get("banner", []),
        "progress": {**_score(snap, progress), "last_week": _score(earlier[0], progress) if earlier else None},
        "goals": _goal_rings(snap, marks),
        "considering": snap["brief"].get("considering", []),
        "updated_at": (snap["brief"].get("updates") or [{}])[-1].get("at"),
    }


DASHBOARD_FILE = "Network Focus dashboard.txt"  # .txt: Google Drive's file reader handles text/*, not .json


def export_dashboard(nf_home: Path, today: date) -> Path | None:
    """Save this week's dashboard into the Google Drive folder, where the CEO's live view reads it.
    Does nothing without a Drive folder or a brief. Never raises: the page works the same without it."""
    from datetime import datetime
    nf_home = Path(nf_home)
    folder = roster_dir(nf_home)
    try:
        if folder == nf_home / "inbox" or not folder.is_dir():
            return None
        payload = dashboard_payload(nf_home, today)
        if payload.get("empty"):
            return None
        doc = {"kind": "network-focus-dashboard", "version": 1,
               "exported_at": datetime.now().astimezone().isoformat(timespec="minutes"), **payload}
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".nf-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        os.replace(tmp, folder / DASHBOARD_FILE)
        return folder / DASHBOARD_FILE
    except OSError:
        return None
