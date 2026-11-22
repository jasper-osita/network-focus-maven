# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl"]
# ///
"""Step 1 of the brief: read the spreadsheet + goals.md, run every data check, write .work/roster.json and
.work/warnings.json. Prints one JSON line. Exit 0 = ok, 2 = blocked (message says why), 3 = first-run setup."""
import argparse
import json
import shutil
import sys
import traceback
from datetime import date
from pathlib import Path

from nf_core.checks import flags_for, run_checks
from nf_core.goals import parse_goals
from nf_core.issues import BlockingError
from nf_core.roster import read_roster
from nf_core.workspace import (Workspace, ensure_workspace, file_date, fingerprint, load_history, nf_home,
                               pick_roster, staleness_issues, week_of)

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "goals.md"


def emit(status: str, message: str, exit_code: int, **extra) -> int:
    print(json.dumps({"status": status, "message": message, **extra}))
    return exit_code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", default="")
    ap.add_argument("--today", default="")
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    ws = Workspace(nf_home())
    try:
        created = ensure_workspace(ws, TEMPLATE)
        for old in ws.work.iterdir():  # never let last week's files leak into this run
            shutil.rmtree(old) if old.is_dir() else old.unlink()
        if created and not args.roster:
            return emit("setup", f"I set up your Network Focus folder at {ws.root}. Put this week's spreadsheet in "
                                 f"the inbox folder ({ws.inbox}) and run the brief again. The CEO's goals are in "
                                 "goals.md there; check they're still right.", 3, work_dir=str(ws.work))
        goals = parse_goals(ws.goals_path.read_text(encoding="utf-8"))
        roster_path, pick_issues = pick_roster(ws, Path(args.roster) if args.roster else None)
        contacts, cell_issues = read_roster(roster_path)
        sha = fingerprint(roster_path)
        stale = staleness_issues(roster_path, sha, load_history(ws), today)
        warnings = stale + pick_issues + cell_issues + run_checks(contacts, goals)
        roster = {
            "source": {"path": str(roster_path), "file_name": roster_path.name, "sha256": sha,
                       "as_of": file_date(roster_path).isoformat(), "week_of": week_of(today).isoformat()},
            "goals": [g.to_dict() for g in goals],
            "contacts": [{**c.to_dict(), "text": c.text(), "flags": flags_for(c)} for c in contacts],
        }
        (ws.work / "roster.json").write_text(json.dumps(roster, indent=2), encoding="utf-8")
        (ws.work / "warnings.json").write_text(json.dumps({"warnings": [w.to_dict() for w in warnings]}, indent=2), encoding="utf-8")
        n_warn = sum(w.severity == "warn" for w in warnings)
        return emit("ok", f"Loaded {len(contacts)} contacts from {roster_path.name}. "
                          f"{n_warn} things to check with the CEO.", 0,
                    work_dir=str(ws.work), contacts=len(contacts), warnings=n_warn)
    except BlockingError as e:
        return emit("blocked", e.issue.message, 2, code=e.issue.code, work_dir=str(ws.work))
    except PermissionError:
        return emit("blocked", "Your computer isn't letting Network Focus open the spreadsheet. On a Mac, open System "
                               "Settings → Privacy & Security → Files and Folders (or Full Disk Access) and allow uv, "
                               "then try again.", 2, code="NO_ACCESS", work_dir=str(ws.work))
    except OSError:
        return emit("blocked", "I couldn't open the spreadsheet. If it's in Google Drive, check the internet "
                               "connection and that Google Drive for desktop is running, then try again.", 2,
                    code="UNREADABLE", work_dir=str(ws.work))
    except Exception:
        try:
            ws.work.mkdir(parents=True, exist_ok=True)
            (ws.work / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        return emit("blocked", f"Something unexpected went wrong reading the spreadsheet. "
                               "Run /network-focus:check for details.", 2, code="UNEXPECTED", work_dir=str(ws.work))


if __name__ == "__main__":
    sys.exit(main())
