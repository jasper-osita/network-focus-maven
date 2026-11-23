import csv
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "sample-data" / "network_roster_terragrid.xlsx"
TEMPLATE_GOALS = ROOT / "plugins" / "network-focus" / "templates" / "goals.md"

HEADERS = [
    "Name", "Role", "Company", "How She Knows Them", "Days Since Last Contact",
    "Last Contact Channel", "Last Contact Summary", "Relationship Strength (1-5)", "Tags", "Notes",
]

TWO_ROWS = [
    dict(zip(HEADERS, ["Marcus Wei", "Partner", "Sequoia Capital", "investor", 16, "email",
                       "Warm email exchange after she sent her teaser deck. Asked to see the full pitch.",
                       3, "investor, series-c, warm", "Warm intro from Patrick at Greylock."])),
    dict(zip(HEADERS, ["Diana Chen", "CTO", "Stripe", "mentor", 28, "call",
                       "Offered to help with CTO search. Mentioned she knows 3-4 strong candidates.",
                       4, "cto-search, mentor", "CEO never followed up after the offer."])),
]


@pytest.fixture
def sample_xlsx(tmp_path) -> Path:
    """A copy: the loader adds a Last Contact Date column to the roster it reads, so never hand it the repo's file."""
    import shutil
    copy = tmp_path / "sample" / SAMPLE.name
    copy.parent.mkdir()
    shutil.copy2(SAMPLE, copy)
    return copy


@pytest.fixture
def template_text() -> str:
    return TEMPLATE_GOALS.read_text()


@pytest.fixture
def make_roster(tmp_path):
    """Write a roster file. rows: dicts keyed by HEADERS, or lists of raw cell values (for custom headers)."""
    def _make(rows, fmt="xlsx", headers=None, title_row=False, name="roster"):
        headers = list(headers or HEADERS)
        path = tmp_path / f"{name}.{fmt}"
        table = []
        if title_row:
            table.append(["TerraGrid network export"] + [None] * (len(headers) - 1))
        table.append(headers)
        for r in rows:
            table.append([r.get(h) for h in HEADERS] if isinstance(r, dict) else list(r))
        if fmt == "xlsx":
            wb = openpyxl.Workbook()
            ws = wb.active
            for row in table:
                ws.append(row)
            wb.save(path)
        else:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerows(table)
        return path
    return _make


def build_roster_dict(week_of="2026-11-23", as_of="2026-11-21"):
    from nf_core.checks import flags_for
    from nf_core.goals import parse_goals
    from nf_core.roster import read_roster
    contacts, _ = read_roster(SAMPLE)
    return {"source": {"path": str(SAMPLE), "file_name": SAMPLE.name, "sha256": "ab" * 32,
                       "as_of": as_of, "week_of": week_of},
            "goals": [g.to_dict() for g in parse_goals(TEMPLATE_GOALS.read_text())],
            "contacts": [{**c.to_dict(), "text": c.text(), "flags": flags_for(c)} for c in contacts]}


def build_warnings():
    from nf_core.checks import run_checks
    from nf_core.goals import parse_goals
    from nf_core.issues import Issue
    from nf_core.roster import read_roster
    contacts, _ = read_roster(SAMPLE)
    issues = run_checks(contacts, parse_goals(TEMPLATE_GOALS.read_text()))
    stale = Issue("STALE_FILE", "warn", "This spreadsheet's file date is Nov 1, 2026 (22 days ago).")
    return {"warnings": [i.to_dict() for i in [stale, *issues]]}


@pytest.fixture
def roster_dict():
    return build_roster_dict()


@pytest.fixture
def warnings_dict():
    return build_warnings()


@pytest.fixture
def brief_dict():
    import json
    return json.loads((Path(__file__).parent / "fixtures" / "valid_brief.json").read_text())
