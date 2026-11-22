# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Update step 2: compare the fresh roster (WORK/roster.json) with this week's brief and write WORK/update-input.json:
who's new or changed, which picks are locked, which slots are open. Prints one JSON line.
Exit 0 = ok or nothing to do (see status), 2 = blocked (message says what to do)."""
import argparse
import json
import sys
from pathlib import Path

from nf_core.update import latest_snapshot, load_marks, prep_update


def emit(obj: dict, code: int) -> int:
    print(json.dumps(obj))
    return code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--snapshot", default="")
    a = ap.parse_args(argv)
    work = Path(a.work)
    root = work.parent
    roster = json.loads((work / "roster.json").read_text(encoding="utf-8"))
    snap_path = Path(a.snapshot) if a.snapshot else latest_snapshot(root / "briefs")
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path and snap_path.exists() else None
    if not snap or snap.get("week_of") != roster["source"]["week_of"]:
        return emit({"status": "blocked", "message": "This week's brief hasn't been made yet. Click Generate instead."}, 2)
    if not isinstance(snap.get("roster_index"), dict):
        return emit({"status": "blocked", "message": "This week's brief was made before the page could track changes. "
                                                     "Click Generate once, then Update will work."}, 2)
    inp = prep_update(snap, roster, load_marks(root, snap["week_of"]))
    if not inp["people"]:
        return emit({"status": "nothing", "message": "Nobody new or changed since this week's brief."}, 0)
    (work / "update-input.json").write_text(json.dumps(inp, indent=2, ensure_ascii=False), encoding="utf-8")
    return emit({"status": "ok", "people": len(inp["people"])}, 0)


if __name__ == "__main__":
    sys.exit(main())
