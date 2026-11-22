# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl"]
# ///
"""/network-focus:check — a plain-English health check the chief of staff can run when something goes wrong.
Prints one line per check (✅ / ❌ with a fix / ℹ️). --json prints the same as JSON. Exit 1 if anything failed."""
import argparse
import json
import shutil
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from nf_core.goals import parse_goals
from nf_core.issues import BlockingError
from nf_core.roster import read_roster
from nf_core.workspace import Workspace, ensure_workspace, file_date, nf_home, pick_roster

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "goals.md"

CLAUDE_PATHS = ["/opt/homebrew/bin/claude", "/usr/local/bin/claude", str(Path.home() / ".local/bin/claude"),
                str(Path.home() / ".local/bin/claude.exe"), str(Path.home() / ".claude/local/claude")]


@dataclass
class CheckResult:
    name: str
    status: str  # ok | fail | info
    detail: str
    fix: str = ""


def _tools(port: int) -> list[CheckResult]:
    claude = shutil.which("claude") or next((p for p in CLAUDE_PATHS if Path(p).exists()), None)
    out = [CheckResult("Claude command-line tool", "info",
                       f"Found at {claude} (only the Network Focus page needs it)." if claude else
                       "Not found. Only the Network Focus page needs it; the Claude app works without it.")]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
            running = r.status == 200
    except OSError:
        running = False
    out.append(CheckResult("Network Focus page", "info",
                           "Running." if running else
                           "Not running. That only matters if you use the page; restart the computer or run "
                           "/network-focus:setup-app to start it."))
    return out


def setup_checks(home: Path, port: int = 8765) -> list[CheckResult]:
    ws = Workspace(home)
    if not ws.root.exists():
        return [CheckResult("Network Focus folder", "fail", f"There's no folder at {ws.root}.",
                            "Type 'make this week's network brief' once and it will create the folder for you.")] \
            + _tools(port)
    res = [CheckResult("Network Focus folder", "ok", f"Found at {ws.root}.")]
    had_goals = ws.goals_path.exists()
    if TEMPLATE.exists():
        ensure_workspace(ws, TEMPLATE)  # a folder made in Finder gets its inbox, briefs and starter goals

    if not ws.goals_path.exists():
        res.append(CheckResult("goals.md", "fail", "goals.md is missing.",
                               "Run /network-focus:setup-app once; it adds the starter goals. "
                               "Then open goals.md and check the goals are still right."))
    elif not had_goals:
        res.append(CheckResult("goals.md", "ok", "goals.md was missing, so I added the starter goals. "
                                                 "Open it and check they're still right."))
    else:
        try:
            goals = parse_goals(ws.goals_path.read_text())
            res.append(CheckResult("goals.md", "ok", f"{len(goals)} goals: " + "; ".join(g.title for g in goals)))
        except BlockingError as e:
            res.append(CheckResult("goals.md", "fail", e.issue.message, "Open goals.md and fix that line."))

    try:
        path, _ = pick_roster(ws, None)
        age = (date.today() - file_date(path)).days
        when = "today" if age <= 0 else "yesterday" if age == 1 else f"{age} days ago"
        res.append(CheckResult("Spreadsheet in inbox", "ok", f"{path.name}, saved {when}."))
        try:
            contacts, _ = read_roster(path)
            res.append(CheckResult("Spreadsheet columns", "ok", f"{len(contacts)} contacts, all 10 columns found."))
        except BlockingError as e:
            res.append(CheckResult("Spreadsheet columns", "fail", e.issue.message,
                                   "Fix the spreadsheet as described, save it, and put it back in the inbox."))
    except BlockingError as e:
        if e.issue.code == "NO_SPREADSHEET":
            res.append(CheckResult("Spreadsheet in inbox", "info",
                                   f"No spreadsheet yet, which is normal before the first brief. Drag this week's file "
                                   f"onto the Network Focus page, or into {ws.inbox}."))
        else:
            res.append(CheckResult("Spreadsheet in inbox", "fail", e.issue.message,
                                   "Save it as .xlsx or .csv and put that copy in the inbox."))

    try:
        ws.briefs.mkdir(parents=True, exist_ok=True)
        probe = ws.briefs / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        res.append(CheckResult("Briefs folder", "ok", f"Briefs are saved in {ws.briefs}."))
    except OSError:
        res.append(CheckResult("Briefs folder", "fail", f"I can't save files in {ws.briefs}.",
                               "Check the folder isn't locked or read-only (Finder → Get Info)."))
    return res + _tools(port)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    results = setup_checks(nf_home(), a.port)
    if a.json:
        print(json.dumps([asdict(r) for r in results]))
    else:
        for r in results:
            icon = {"ok": "✅", "fail": "❌", "info": "ℹ️"}[r.status]
            print(f"{icon} {r.name}: {r.detail}")
            if r.fix:
                print(f"   Fix: {r.fix}")
    return 1 if any(r.status == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
