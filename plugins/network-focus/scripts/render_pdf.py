# /// script
# requires-python = ">=3.11"
# dependencies = ["reportlab"]
# ///
"""Last step of the brief: validate .work/brief.json again, then write briefs/<week>-network-focus.pdf + .md.
Refuses to render a brief that fails its checks. Exit 0 = ok, 1 = failed checks, 4 = too long for one page."""
import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

from nf_core.brief_checks import validate_brief
from nf_core.render import render_markdown, render_pdf
from nf_core.snapshot import build_snapshot
from nf_core.workspace import Workspace, record_run


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--today", default="")
    a = ap.parse_args(argv)
    work = Path(a.work)
    ws = Workspace(work.parent)
    brief, roster, warnings = (json.loads((work / n).read_text(encoding="utf-8")) for n in ("brief.json", "roster.json", "warnings.json"))
    problems = validate_brief(brief, roster)
    if problems:
        print(json.dumps({"ok": False, "message": "The brief didn't pass its checks, so no PDF was made.",
                          "problems": [p.to_dict() for p in problems]}))
        return 1
    ws.briefs.mkdir(parents=True, exist_ok=True)
    stem = f"{brief['week_of']}-network-focus"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_pdf = Path(tmp) / f"{stem}.pdf"
        pages = render_pdf(brief, roster, warnings, tmp_pdf)
        if pages > 1:
            print(json.dumps({"ok": False, "too_long": True, "pages": pages,
                              "message": "The brief is too long for one page. Shorten the why and move text "
                                         "(one sentence each) and render again."}))
            return 4
        pdf, md = ws.briefs / f"{stem}.pdf", ws.briefs / f"{stem}.md"
        pdf.write_bytes(tmp_pdf.read_bytes())
    md.write_text(render_markdown(brief, roster, warnings), encoding="utf-8")
    snap = ws.briefs / f"{stem}.json"  # the CEO dashboard reads this; .work/ is cleared every run
    snap.write_text(json.dumps(build_snapshot(brief, roster, warnings), indent=2, ensure_ascii=False), encoding="utf-8")
    today = date.fromisoformat(a.today) if a.today else date.today()
    record_run(ws, {"sha256": roster["source"]["sha256"], "file_name": roster["source"]["file_name"],
                    "run_date": today.isoformat(), "brief": pdf.name})
    print(json.dumps({"ok": True, "pdf": str(pdf), "md": str(md)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
