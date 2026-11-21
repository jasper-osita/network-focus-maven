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
def sample_xlsx() -> Path:
    return SAMPLE


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
