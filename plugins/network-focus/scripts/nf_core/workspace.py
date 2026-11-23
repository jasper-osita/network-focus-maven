"""The chief of staff's Network Focus folder: goals, inbox, briefs, run history."""
import hashlib
import json
import os
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from .issues import Issue, block

SPREADSHEET_SUFFIXES = (".xlsx", ".csv", ".zip")
OTHER_SPREADSHEETS = (".xls", ".xlsm", ".xlsb", ".numbers", ".ods")
STALE_DAYS = 7


_FOLDER_IDS = {"Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"}


def _known_folder(name: str) -> Path | None:
    """A Windows known folder (follows OneDrive redirection of Documents/Desktop). None elsewhere or on failure."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        u = uuid.UUID(_FOLDER_IDS[name])
        guid = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        return None


def documents_dir() -> Path:
    if sys.platform == "win32":
        return _known_folder("Documents") or Path.home() / "Documents"
    return Path.home() / "Documents"


def nf_home() -> Path:
    env = os.environ.get("NF_HOME")
    return Path(env).expanduser() if env else documents_dir() / "Network Focus"


SETTINGS_FILE = "settings.json"


def load_settings(root: Path) -> dict:
    """<root>/settings.json, written by the installer. {} when missing or unreadable."""
    try:
        data = json.loads((Path(root) / SETTINGS_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(root: Path, data: dict) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".{SETTINGS_FILE}.tmp"
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, root / SETTINGS_FILE)


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)

    goals_path = property(lambda self: self.root / "goals.md")

    @property
    def roster_folder(self) -> Path | None:
        """The Google Drive folder the roster lives in, when the installer set one up."""
        folder = load_settings(self.root).get("roster_folder")
        return Path(folder) if isinstance(folder, str) and folder else None

    @property
    def inbox(self) -> Path:
        """Where rosters are read from and dropped files are saved: the Drive folder, else the local inbox."""
        return self.roster_folder or self.root / "inbox"
    briefs = property(lambda self: self.root / "briefs")
    work = property(lambda self: self.root / ".work")
    history_path = property(lambda self: self.root / ".history.json")


def ensure_workspace(ws: Workspace, template: Path) -> bool:
    """Create the folder on first run. Returns True when it was created just now."""
    created = not ws.root.exists()
    for d in (ws.root / "inbox", ws.briefs, ws.work):  # never the Drive folder: Drive may be signed out
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


DRIVE_NO_ACCESS = ("Your computer isn't letting Network Focus read the Network Focus folder in Google Drive ({folder}). "
                   "On a Mac, open System Settings → Privacy & Security → Files and Folders (or Full Disk Access) "
                   "and allow uv, then try again.")
DRIVE_UNREADABLE = ("I couldn't open the Network Focus folder in Google Drive ({folder}). Check the internet connection "
                    "and that Google Drive for desktop is running, then try again.")
GOOGLE_SHEET_MESSAGE = ("The roster in Google Drive is a Google Sheet, which I can't read. In Drive, open it and choose "
                        "File → Download → Microsoft Excel, then put that file in the Network Focus folder. Or keep "
                        "the roster as an Excel file.")


def _entries(ws: Workspace) -> list[tuple[Path, float]]:
    """Every visible file in the roster folder with its modified time. Drive errors become plain messages."""
    folder = ws.roster_folder
    try:
        if folder is not None and not folder.is_dir():
            raise block("DRIVE_FOLDER_MISSING",
                        f"I can't find the Network Focus folder in Google Drive ({folder}). Open Google Drive for "
                        "desktop and check you're signed in, then try again.")
        if not ws.inbox.exists():
            return []
        return [(f, f.stat().st_mtime) for f in ws.inbox.iterdir() if f.is_file() and not f.name.startswith(("~$", "."))]
    except PermissionError:
        raise block("DRIVE_NO_ACCESS", DRIVE_NO_ACCESS.format(folder=folder or ws.inbox))
    except OSError:
        raise block("DRIVE_UNREADABLE", DRIVE_UNREADABLE.format(folder=folder or ws.inbox))


def pick_roster(ws: Workspace, explicit: Path | None) -> tuple[Path, list[Issue]]:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            raise block("NO_SPREADSHEET", f"I couldn't find {p}. Check the file name, or drag the file into {ws.inbox}.")
        return p, []
    entries = _entries(ws)
    files = [f for f, _ in sorted(entries, key=lambda e: -e[1]) if f.suffix.lower() in SPREADSHEET_SUFFIXES]
    newest = max((t for f, t in entries if f.suffix.lower() in SPREADSHEET_SUFFIXES), default=None)
    sheets = [t for f, t in entries if f.suffix.lower() == ".gsheet"]
    if sheets and (newest is None or max(sheets) > newest):  # someone moved the roster into Google Sheets
        raise block("GOOGLE_SHEET", GOOGLE_SHEET_MESSAGE)
    if not files:
        other = [f for f, _ in entries if f.suffix.lower() in OTHER_SPREADSHEETS]
        if other:
            raise block("UNSUPPORTED_FILE",
                        f"{other[0].name} is in a format I can't read. Open it and save or export it as .xlsx or .csv "
                        "(in Excel: File → Save As → Excel Workbook), then put that copy in the inbox.")
        raise block("NO_SPREADSHEET",
                    f"There's no spreadsheet in {ws.inbox}. Drag this week's file into that folder "
                    "(or onto the Network Focus page), then run again.")
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


def staleness_issues(path: Path, sha: str, history: list[dict], today: date, as_of: date | None = None,
                     exact_dates: bool = False) -> list[Issue]:
    """exact_dates: the sheet stores last-contact dates, so its day counts can't be stale."""
    issues = []
    as_of = as_of or file_date(path)
    age = (today - as_of).days
    if age > STALE_DAYS and not exact_dates:
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
        data = json.loads(ws.history_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def record_run(ws: Workspace, entry: dict) -> None:
    history = load_history(ws)
    history.append(entry)
    ws.history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
