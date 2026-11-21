import os
import zipfile

import pytest

from conftest import HEADERS, TWO_ROWS
from nf_core.issues import BlockingError
from nf_core.roster import read_roster


def test_reads_sample_xlsx(sample_xlsx):
    contacts, issues = read_roster(sample_xlsx)
    assert len(contacts) == 25 and issues == []
    m = contacts[0]
    assert (m.row_id, m.name, m.days_since_contact, m.strength) == (2, "Marcus Wei", 16, 3)
    assert m.tags == ["investor", "series-c", "warm"]
    assert "Asked to see the full pitch." in m.text()


def test_reads_csv_with_bom(make_roster):
    contacts, issues = read_roster(make_roster(TWO_ROWS, fmt="csv"))
    assert issues == []
    assert [(c.row_id, c.name, c.days_since_contact, c.strength) for c in contacts] == [
        (2, "Marcus Wei", 16, 3), (3, "Diana Chen", 28, 4)]
    assert contacts[1].tags == ["cto-search", "mentor"]


def test_missing_columns_blocks(make_roster):
    headers = ["Days" if h == "Days Since Last Contact" else h for h in HEADERS if h != "Notes"]
    path = make_roster([["Marcus Wei", "Partner", "Sequoia", "investor", 16, "email", "x y z", 3, "investor"]],
                       headers=headers)
    with pytest.raises(BlockingError) as e:
        read_roster(path)
    assert e.value.issue.code == "MISSING_COLUMNS"
    assert "Notes" in e.value.issue.message and "Days Since Last Contact" in e.value.issue.message


def test_header_found_below_title_row(make_roster):
    messy = [f"  {h.lower()} " for h in HEADERS]
    rows = [[r[h] for h in HEADERS] for r in TWO_ROWS]
    contacts, issues = read_roster(make_roster(rows, headers=messy, title_row=True))
    assert len(contacts) == 2 and issues == []
    assert contacts[0].row_id == 3


def test_numbers_as_text_and_floats(make_roster):
    rows = []
    for days, strength in [("16", "3"), (16.0, 3.0), (" 16 ", " 3 ")]:
        r = dict(TWO_ROWS[0])
        r["Days Since Last Contact"], r["Relationship Strength (1-5)"] = days, strength
        rows.append(r)
    contacts, issues = read_roster(make_roster(rows))
    assert [c.days_since_contact for c in contacts] == [16, 16, 16]
    assert [c.strength for c in contacts] == [3, 3, 3]
    assert issues == []


def test_bad_cells_warn(make_roster):
    a, b = dict(TWO_ROWS[0]), dict(TWO_ROWS[1])
    a["Days Since Last Contact"] = "two weeks"
    b["Relationship Strength (1-5)"] = 7
    contacts, issues = read_roster(make_roster([a, b]))
    assert contacts[0].days_since_contact is None and contacts[1].strength is None
    assert [i.code for i in issues] == ["BAD_CELL", "BAD_CELL"]
    assert issues[0].severity == "warn" and issues[0].rows == [2]
    assert "two weeks" in issues[0].message and "row 2" in issues[0].message.lower()


def test_blank_rows_skipped_silently(make_roster):
    blank = {h: None for h in HEADERS}
    contacts, issues = read_roster(make_roster([TWO_ROWS[0], blank, TWO_ROWS[1], blank, blank]))
    assert [c.name for c in contacts] == ["Marcus Wei", "Diana Chen"] and issues == []


def test_empty_file_blocks(make_roster):
    with pytest.raises(BlockingError) as e:
        read_roster(make_roster([]))
    assert e.value.issue.code == "FILE_EMPTY"


def test_unsupported_extension_blocks(tmp_path):
    p = tmp_path / "roster.numbers"
    p.write_bytes(b"whatever")
    with pytest.raises(BlockingError) as e:
        read_roster(p)
    assert e.value.issue.code == "UNSUPPORTED_FILE"
    assert "Export it as .xlsx or .csv" in e.value.issue.message


def test_zip_wrapper_unwrapped(tmp_path, sample_xlsx):
    p = tmp_path / "roster.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.write(sample_xlsx, "network_roster_terragrid.xlsx")
    contacts, _ = read_roster(p)
    assert len(contacts) == 25


def test_drive_style_double_wrap(tmp_path, sample_xlsx):
    p = tmp_path / "download.xlsx"  # a zip *named* .xlsx, holding the real .xlsx
    with zipfile.ZipFile(p, "w") as z:
        z.write(sample_xlsx, "network_roster_terragrid.xlsx")
    contacts, _ = read_roster(p)
    assert len(contacts) == 25


def test_zip_with_two_files_blocks(tmp_path, sample_xlsx):
    p = tmp_path / "two.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.write(sample_xlsx, "a.xlsx")
        z.write(sample_xlsx, "b.xlsx")
    with pytest.raises(BlockingError) as e:
        read_roster(p)
    assert e.value.issue.code == "FILE_UNREADABLE" and "unzip" in e.value.issue.message.lower()


def test_corrupt_file_blocks(tmp_path):
    p = tmp_path / "broken.xlsx"
    p.write_bytes(os.urandom(512))
    with pytest.raises(BlockingError) as e:
        read_roster(p)
    assert e.value.issue.code == "FILE_UNREADABLE" and "broken.xlsx" in e.value.issue.message
