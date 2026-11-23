import json
import os
import subprocess
import sys
from datetime import date

import openpyxl
import pytest

from conftest import ROOT, TWO_ROWS
from nf_core.roster import read_roster
from nf_core.sheet import SheetError, read_sheet, set_cells

DAY = date(2026, 11, 25)
CLI = ROOT / "plugins" / "network-focus" / "scripts" / "sheet.py"


def cells(path):
    ws = openpyxl.load_workbook(path).worksheets[0]
    return [[c.value for c in row] for row in ws.iter_rows()]


def test_set_done_adds_columns_and_writes_date(make_roster):
    path = make_roster(TWO_ROWS)
    before = cells(path)
    set_cells(path, "Diana Chen", "Stripe", done=True, comment=None, today=DAY)
    after = cells(path)
    assert after[0][-2:] == ["Done", "Comments"] and after[0][:-2] == before[0]
    assert after[2][-2:] == ["Nov 25, 2026", None] and after[1][-2] is None   # Diana ticked, Marcus not
    assert after[2][:-2] == before[2]                                            # nothing else touched
    assert [c.name for c in read_roster(path)[0]] == ["Marcus Wei", "Diana Chen"]


def test_untick_clears_and_comment_is_saved(make_roster):
    path = make_roster(TWO_ROWS)
    set_cells(path, "Diana Chen", "Stripe", done=True, comment=None, today=DAY)
    set_cells(path, "diana chen", "stripe", done=False, comment="Called Tuesday; intros coming.", today=DAY)
    assert cells(path)[2][-2:] == [None, "Called Tuesday; intros coming."]
    assert len(cells(path)[0]) == 12  # columns added once, not again


def test_csv_round_trip(make_roster):
    path = make_roster(TWO_ROWS, fmt="csv")
    set_cells(path, "Marcus Wei", "Sequoia Capital", done=True, comment="Deck sent.", today=DAY)
    rows = read_sheet(path)["rows"]
    assert rows[0]["name"] == "Marcus Wei" and rows[0]["done"] == "Nov 25, 2026" and rows[0]["comments"] == "Deck sent."
    assert [c.name for c in read_roster(path)[0]] == ["Marcus Wei", "Diana Chen"]


def test_refuses_when_open_in_excel(make_roster):
    path = make_roster(TWO_ROWS)
    (path.parent / f"~${path.name}").write_bytes(b"lock")
    before = cells(path)
    with pytest.raises(SheetError) as e:
        set_cells(path, "Diana Chen", "Stripe", done=True, comment=None, today=DAY)
    assert "open in Excel" in e.value.message and cells(path) == before


def test_unknown_person(make_roster):
    with pytest.raises(SheetError) as e:
        set_cells(make_roster(TWO_ROWS), "Ana Ruiz", "a16z", done=True, comment=None, today=DAY)
    assert "isn't in" in e.value.message


def test_read_sheet_rows(make_roster):
    path = make_roster(TWO_ROWS)
    set_cells(path, "Diana Chen", "Stripe", done=True, comment="Intro to two candidates.", today=DAY)
    sheet = read_sheet(path)
    assert sheet["file"] == path.name and len(sheet["rows"]) == 2
    diana = sheet["rows"][1]
    assert diana == {"row_id": 3, "name": "Diana Chen", "role": "CTO", "company": "Stripe", "days": 28, "strength": 4,
                     "tags": "cto-search, mentor", "last_contact": "", "done": "Nov 25, 2026", "comments": "Intro to two candidates."}
    assert read_sheet(make_roster(TWO_ROWS, name="fresh"))["rows"][0]["done"] == ""


def test_sheet_cli_set_and_read(tmp_path, make_roster):
    home = tmp_path / "NF"
    (home / "inbox").mkdir(parents=True)
    path = make_roster(TWO_ROWS)
    os.replace(path, home / "inbox" / "roster.xlsx")
    env = {**os.environ, "NF_HOME": str(home)}
    run = lambda *a: json.loads(subprocess.run([sys.executable, str(CLI), *a], capture_output=True, text=True,
                                               encoding="utf-8", env=env).stdout.strip().splitlines()[-1])
    assert run("set", "--name", "Diana Chen", "--company", "Stripe", "--done", "yes")["ok"] is True
    out = run("read")
    assert out["ok"] is True and out["rows"][1]["done"] != ""
    assert run("set", "--name", "Nobody", "--company", "X", "--done", "yes")["ok"] is False


# ---- dates instead of day counts ----
from nf_core.sheet import convert_dates  # noqa: E402


def test_convert_dates_adds_column_and_formulas(make_roster):
    path = make_roster(TWO_ROWS)
    assert convert_dates(path, date(2026, 11, 22)) is True
    ws = openpyxl.load_workbook(path).worksheets[0]
    head = [c.value for c in ws[1]]
    col = head.index("Last Contact Date") + 1
    assert ws.cell(row=2, column=col).value.date() == date(2026, 11, 6)        # Marcus: 16 days before Nov 22
    assert str(ws.cell(row=2, column=head.index("Days Since Last Contact") + 1).value).startswith("=TODAY()-")
    marcus = read_roster(path, today=date(2026, 11, 30))[0][0]
    assert marcus.days_since_contact == 24 and marcus.last_contact == "2026-11-06"
    assert convert_dates(path, date(2026, 11, 22)) is False                    # only once


def test_convert_dates_csv(make_roster):
    path = make_roster(TWO_ROWS, fmt="csv")
    assert convert_dates(path, date(2026, 11, 22)) is True
    diana = read_roster(path, today=date(2026, 11, 22))[0][1]
    assert diana.last_contact == "2026-10-25" and diana.days_since_contact == 28


def test_convert_dates_refuses_when_open_in_excel(make_roster):
    path = make_roster(TWO_ROWS)
    (path.parent / f"~${path.name}").write_bytes(b"lock")
    with pytest.raises(SheetError):
        convert_dates(path, date(2026, 11, 22))
