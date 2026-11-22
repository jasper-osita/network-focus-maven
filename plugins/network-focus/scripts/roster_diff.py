# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl"]
# ///
"""Who is new or changed in a roster file since a brief. Used by the Network Focus page every few minutes.
Prints one JSON line and always exits 0, so the page can read the answer whatever happened."""
import argparse
import json
import sys
from pathlib import Path

from nf_core.changes import diff_roster
from nf_core.issues import BlockingError
from nf_core.roster import read_roster


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", required=True)
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    try:
        snap = json.loads(Path(a.snapshot).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(json.dumps({"ok": False, "reason": "no_index"}))
        return 0
    index = snap.get("roster_index") if isinstance(snap, dict) else None
    if not isinstance(index, dict):
        print(json.dumps({"ok": False, "reason": "no_index"}))  # a brief from before change tracking
        return 0
    try:
        contacts, _ = read_roster(Path(a.roster))
    except BlockingError as e:
        print(json.dumps({"ok": False, "reason": "blocked", "message": e.issue.message}))
        return 0
    except Exception as e:  # a half-synced or locked file: report it, never crash the page's watcher
        print(json.dumps({"ok": False, "reason": "blocked", "message": f"Couldn't read {Path(a.roster).name}: {e}"}))
        return 0
    out = diff_roster(index, [c.to_dict() for c in contacts])
    print(json.dumps({"ok": True, "file": Path(a.roster).name, **out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
