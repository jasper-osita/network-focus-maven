# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl"]
# ///
"""The page's Spreadsheet tab: `read` prints the roster as rows; `set` writes Done / Comments for one person.
Uses the same roster file the brief uses (the newest in the roster folder). Prints one JSON line, always exits 0."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from nf_core.issues import BlockingError
from nf_core.sheet import SheetError, read_sheet, set_cells
from nf_core.workspace import Workspace, nf_home, pick_roster


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["read", "set"])
    ap.add_argument("--roster", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--company", default="")
    ap.add_argument("--done", choices=["yes", "no"])
    ap.add_argument("--comment")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        path = Path(a.roster) if a.roster else pick_roster(Workspace(nf_home()), None)[0]
        if a.action == "read":
            out = {"ok": True, **read_sheet(path)}
        else:
            done = None if a.done is None else a.done == "yes"
            set_cells(path, a.name, a.company, done, a.comment, date.today())
            out = {"ok": True, "file": path.name}
    except (BlockingError, SheetError) as e:
        out = {"ok": False, "message": getattr(e, "message", None) or e.issue.message}
    except OSError:
        out = {"ok": False, "message": "I couldn't open the spreadsheet. If it's in Google Drive, check the internet "
                                       "connection, then try again."}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
