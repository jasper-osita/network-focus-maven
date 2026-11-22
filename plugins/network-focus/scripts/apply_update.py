# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Update step 5: check the model's WORK/update.json, then merge it into this week's brief under the rules and write
WORK/brief.json. Done ticks are re-keyed to the new row numbers. Prints one JSON line. Exit 0 = ok, 1 = fix update.json."""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from nf_core.update import apply_update, latest_snapshot, load_marks, prep_update, validate_update


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--snapshot", default="")
    ap.add_argument("--now", default="")
    a = ap.parse_args(argv)
    work = Path(a.work)
    root = work.parent
    roster, update = (json.loads((work / n).read_text(encoding="utf-8")) for n in ("roster.json", "update.json"))
    snap_path = Path(a.snapshot) if a.snapshot else latest_snapshot(root / "briefs")
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    # Recomputed, not read from update-input.json: the locks and slots come from code and the latest ticks.
    inp = prep_update(snap, roster, load_marks(root, snap["week_of"]))
    problems = validate_update(update, roster, inp)
    if problems:
        print(json.dumps({"ok": False, "message": "update.json doesn't follow the rules yet; nothing was changed.",
                          "problems": [p.to_dict() for p in problems]}))
        return 1
    now = a.now or datetime.now().strftime("%Y-%m-%dT%H:%M")
    brief, marks, summary = apply_update(snap, roster, inp, update, now)
    (work / "brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    if marks:  # add the new row numbers; old keys stay right for the old brief, and the name check guards them after
        prog_path = root / ".progress.json"
        try:
            prog = json.loads(prog_path.read_text(encoding="utf-8"))
            prog = prog if isinstance(prog, dict) else {}
        except (OSError, ValueError):
            prog = {}
        week = prog.get(snap["week_of"]) if isinstance(prog.get(snap["week_of"]), dict) else {}
        prog[snap["week_of"]] = {**week, **marks}
        tmp = root / ".progress-update.tmp"
        tmp.write_text(json.dumps(prog, indent=2), encoding="utf-8")
        os.replace(tmp, prog_path)
    print(json.dumps({"ok": True, **summary}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
