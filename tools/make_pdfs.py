"""Build-time: turn docs/PRD.md and docs/HANDOFF.md into styled PDFs in deliverables/, and check page counts.
Run: uv run --with markdown python tools/make_pdfs.py"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = {"PRD.md": ("PRD.pdf", 2, 9.4, "0.5in,0.6in"), "HANDOFF.md": ("Handoff.pdf", 1, 8.6, "0.4in,0.5in")}
CSS = """
body { font-family: -apple-system, 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #2b2b2b;
       font-size: %(size)spt; line-height: 1.38; }
h1 { color: #1f2a44; font-size: 1.75em; margin: 0 0 .15em; }
h2 { color: #b08d57; font-size: 1.2em; margin: .9em 0 .3em; border-bottom: 1px solid #eadfcd; padding-bottom: 2px; }
h3 { color: #1f2a44; font-size: 1.05em; margin: .7em 0 .2em; }
p, li { margin: .25em 0; } ul, ol { margin: .2em 0 .2em 1.2em; padding: 0; }
table { border-collapse: collapse; width: 100%%; margin: .35em 0; font-size: .93em; }
th { background: #f3ebdd; text-align: left; } th, td { border: 1px solid #e6dfd2; padding: 3px 6px; vertical-align: top; }
code { font-family: Menlo, Consolas, monospace; font-size: .9em; background: #f6f3ee; padding: 0 3px; border-radius: 3px; }
pre { background: #f6f3ee; padding: 6px 8px; border-radius: 4px; font-size: .85em; line-height: 1.3; overflow: hidden; }
pre code { background: none; padding: 0; }
strong { color: #1f2a44; }
"""


def pages(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    return int(re.search(r"Pages:\s+(\d+)", out).group(1))


def main() -> int:
    (ROOT / "deliverables").mkdir(exist_ok=True)
    ok = True
    for src, (dest, max_pages, size, margin) in DOCS.items():
        body = markdown.markdown((ROOT / "docs" / src).read_text(), extensions=["tables", "fenced_code"])
        html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS % {'size': size}}</style></head><body>{body}</body></html>"
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(html)
        out = ROOT / "deliverables" / dest
        subprocess.run(["node", str(ROOT / "tools" / "print_pdf.js"), f.name, str(out), margin], check=True)
        n = pages(out)
        ok &= n <= max_pages
        print(f"{dest}: {n} page(s) (max {max_pages}) {'OK' if n <= max_pages else 'TOO LONG'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
