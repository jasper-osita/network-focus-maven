# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check the model's work against the spreadsheet.
  validate_brief.py brief <brief.json> --roster <roster.json>
  validate_brief.py scout <scout.json> --roster <roster.json>
  validate_brief.py cited-rows <brief.json> --roster <roster.json> --out <cited-rows.json>
Prints {"ok": bool, "problems": [...]}. Exit 0 = ok, 1 = problems."""
import argparse
import json
import sys
from pathlib import Path

from nf_core.brief_checks import cited_rows, validate_brief, validate_scout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["brief", "scout", "cited-rows", "update"])
    ap.add_argument("file")
    ap.add_argument("--roster", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--input", default="", help="update mode: WORK/update-input.json")
    ap.add_argument("--only-new", action="store_true", help="cited-rows mode: only picks an Update just placed")
    a = ap.parse_args(argv)
    try:
        doc = json.loads(Path(a.file).read_text(encoding="utf-8"))
        roster = json.loads(Path(a.roster).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"ok": False, "problems": [{"code": "BAD_JSON", "where": a.file,
                                                     "message": f"Couldn't read {a.file} as JSON: {e}"}]}))
        return 1
    if a.mode == "cited-rows":
        out = Path(a.out) if a.out else Path(a.file).with_name("cited-rows.json")
        out.write_text(json.dumps(cited_rows(doc, roster, only_new=a.only_new), indent=2), encoding="utf-8")
        if a.only_new:  # the fact-checker should see only what this Update wrote, not Monday's picks
            only = {"week_of": doc.get("week_of"), "focus": [f for f in doc.get("focus", []) if f.get("new")],
                    "dormant": [], "coming_up": [], "goal_gaps": [], "extra_checks": []}
            (out.parent / "new-picks.json").write_text(json.dumps(only, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"ok": True, "problems": [], "out": str(out)}))
        return 0
    try:
        if a.mode == "update":
            from nf_core.update import validate_update
            problems = validate_update(doc, roster, json.loads(Path(a.input).read_text(encoding="utf-8")))
        else:
            problems = (validate_brief if a.mode == "brief" else validate_scout)(doc, roster)
    except (KeyError, TypeError) as e:
        print(json.dumps({"ok": False, "problems": [{"code": "SCHEMA", "where": a.file,
                                                     "message": f"Unexpected shape: {e}"}]}))
        return 1
    print(json.dumps({"ok": not problems, "problems": [p.to_dict() for p in problems]}, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
