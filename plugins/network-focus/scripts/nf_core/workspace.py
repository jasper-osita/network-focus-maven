"""The chief of staff's Network Focus folder: goals, inbox, briefs, run history."""
import hashlib
import json
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

from .issues import Issue, block

SPREADSHEET_SUFFIXES = (".xlsx", ".csv", ".zip")
OTHER_SPREADSHEETS = (".xls", ".xlsm", ".xlsb", ".numbers", ".ods")
STALE_DAYS = 7


def nf_home() -> Path:
    env = os.environ.get("NF_HOME")
    return Path(env).expanduser() if env else Path.home() / "Documents" / "Network Focus"


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)

    goals_path = property(lambda self: self.root / "goals.md")
    inbox = property(lambda self: self.root / "inbox")
    briefs = property(lambda self: self.root / "briefs")
    work = property(lambda self: self.root / ".work")
    history_path = property(lambda self: self.root / ".history.json")


def ensure_workspace(ws: Workspace, template: Path) -> bool:
    """Create the folder on first run. Returns True when it was created just now."""
    created = not ws.root.exists()
    for d in (ws.inbox, ws.briefs, ws.work):
        d.mkdir(parents=True, exist_ok=True)
    if not ws.goals_path.exists():
        shutil.copy(template, ws.goals_path)
    return created


def fmt_date(d: date) -> str:
    return f"{d:%b} {d.day}, {d.year}"


def week_of(today: date) -> date:
    """Monday of this week (Mon–Fri) or of next week (Sat/Sun)."""
    wd = today.weekday()
    return today + timedelta(days=7 - wd) if wd >= 5 else today - timedelta(days=wd)


def pick_roster(ws: Workspace, explicit: Path | None) -> tuple[Path, list[Issue]]:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            raise block("NO_SPREADSHEET", f"I couldn't find {p}. Check the file name, or drag the file into {ws.inbox}.")
        return p, []
    files = [f for f in ws.inbox.iterdir()
             if f.is_file() and f.suffix.lower() in SPREADSHEET_SUFFIXES
             and not f.name.startswith(("~$", "."))] if ws.inbox.exists() else []
    if not files:
        other = [f for f in ws.inbox.iterdir() if f.is_file() and f.suffix.lower() in OTHER_SPREADSHEETS
                 and not f.name.startswith(("~$", "."))] if ws.inbox.exists() else []
        if other:
            raise block("UNSUPPORTED_FILE",
                        f"{other[0].name} is in a format I can't read. Open it and save or export it as .xlsx or .csv "
                        "(in Excel: File → Save As → Excel Workbook), then put that copy in the inbox.")
        raise block("NO_SPREADSHEET",
                    f"There's no spreadsheet in {ws.inbox}. Drag this week's file into that folder "
                    "(or onto the Network Focus page), then run again.")
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    issues = []
    if len(files) > 1:
        issues.append(Issue("MULTIPLE_FILES", "info",
                            f"Using {files[0].name}, the newest of {len(files)} spreadsheets in the inbox. "
                            "Move older ones out of the inbox to avoid mix-ups."))
    return files[0], issues


def fingerprint(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_date(path: Path) -> date:
    return date.fromtimestamp(Path(path).stat().st_mtime)


def staleness_issues(path: Path, sha: str, history: list[dict], today: date) -> list[Issue]:
    issues = []
    as_of = file_date(path)
    age = (today - as_of).days
    if age > STALE_DAYS:
        issues.append(Issue("STALE_FILE", "warn",
                            f"This spreadsheet's file date is {fmt_date(as_of)} ({age} days ago). "
                            f"'Days since last contact' counts from when it was exported, so every number may be "
                            f"about {age} days low. Export a fresh copy if you can."))
    this_week = week_of(today)
    earlier = [h for h in history if h.get("sha256") == sha
               and week_of(date.fromisoformat(h["run_date"])) != this_week
               and date.fromisoformat(h["run_date"]) < today]
    if earlier:
        last = max(date.fromisoformat(h["run_date"]) for h in earlier)
        issues.append(Issue("REUSED_FILE", "warn",
                            f"This is the exact same spreadsheet used for the brief on {fmt_date(last)}. "
                            "Nothing in it has changed since then. Export a fresh copy if you can."))
    return issues


def load_history(ws: Workspace) -> list[dict]:
    try:
        data = json.loads(ws.history_path.read_text())
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def record_run(ws: Workspace, entry: dict) -> None:
    history = load_history(ws)
    history.append(entry)
    ws.history_path.write_text(json.dumps(history, indent=2))
