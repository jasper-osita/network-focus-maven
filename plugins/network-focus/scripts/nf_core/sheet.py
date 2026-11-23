"""The roster as a table for the dashboard's Spreadsheet tab, plus the two columns the page writes back:
Done (the date a move was marked done) and Comments. Every other cell is left exactly as it was."""
import csv
import os
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from .changes import identity
from .roster import HEADER_SCAN_ROWS, _HEADER_KEYS, _cell_str, _norm_header, read_roster
from .workspace import fmt_date

DONE, COMMENTS = "Done", "Comments"


class SheetError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _open_in_excel(path: Path) -> bool:
    """Excel keeps a '~$' lock file next to a workbook it has open (long names lose their first two letters)."""
    return any(f.name.startswith("~$") and path.name.endswith(f.name[2:]) for f in path.parent.glob("~$*"))


def _header(table: list[list]) -> tuple[int, dict[str, int]]:
    """Where the header row is, and the column of each field, including Done and Comments if they exist yet."""
    for i, row in enumerate(table[:HEADER_SCAN_ROWS]):
        cols = {}
        for j, h in enumerate(row):
            key = _HEADER_KEYS.get(_norm_header(h)) or {"done": "done", "comments": "comments"}.get(_norm_header(h))
            if key and key not in cols:
                cols[key] = j
        if "name" in cols:
            return i, cols
    raise SheetError("I couldn't find the header row in the spreadsheet.")


def _is_real_xlsx(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return "[Content_Types].xml" in z.namelist()
    except zipfile.BadZipFile:
        return False


def _load(path: Path) -> list[list]:
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [row for row in csv.reader(f)]
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()


def read_sheet(path: Path) -> dict:
    path = Path(path)
    contacts, _ = read_roster(path)  # the same rows, numbers and checks as the brief
    extra: dict[int, tuple[str, str]] = {}
    if path.suffix.lower() == ".csv" or _is_real_xlsx(path):
        table = _load(path)
        h, cols = _header(table)
        for i, row in enumerate(table[h + 1:], start=h + 2):
            get = lambda k: _cell_str(row[cols[k]]) if k in cols and cols[k] < len(row) else ""
            extra[i] = (get("done"), get("comments"))
    rows = [{"row_id": c.row_id, "name": c.name, "role": c.role, "company": c.company, "days": c.days_since_contact,
             "strength": c.strength, "tags": ", ".join(c.tags), "last_contact": c.last_contact,
             "done": extra.get(c.row_id, ("", ""))[0],
             "comments": extra.get(c.row_id, ("", ""))[1]} for c in contacts]
    return {"file": path.name, "rows": rows}


def set_cells(path: Path, name: str, company: str, done: bool | None, comment: str | None, today: date) -> None:
    """Write Done (today's date, or empty) and/or Comments for one person, found by name and company."""
    path = Path(path)
    if _open_in_excel(path):
        raise SheetError(f"{path.name} is open in Excel. Close it, then try again to save this in the spreadsheet too.")
    who = identity(name, company)
    done_value = (fmt_date(today) if done else None) if done is not None else ...
    if path.suffix.lower() == ".csv":
        table = _load(path)
        h, cols = _header(table)
        width = max(len(r) for r in table)
        for key, title in (("done", DONE), ("comments", COMMENTS)):
            if key not in cols:
                cols[key] = width
                width += 1
                table[h] = table[h] + [""] * (width - 1 - len(table[h])) + [title]
        target = next((r for r in table[h + 1:] if len(r) > cols["name"] and identity(
            r[cols["name"]], r[cols["company"]] if cols.get("company", 99) < len(r) else "") == who), None)
        if target is None:
            raise SheetError(f"{name} isn't in {path.name} any more, so only the dashboard was updated.")
        target.extend([""] * (width - len(target)))
        if done_value is not ...:
            target[cols["done"]] = done_value or ""
        if comment is not None:
            target[cols["comments"]] = comment
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".nf-", suffix=".csv")
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(table)
        os.replace(tmp, path)
        return
    if not _is_real_xlsx(path):
        raise SheetError(f"{path.name} is a zipped copy, so I can't write to it. Unzip it and keep the .xlsx in the folder.")
    import openpyxl
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[0]
    table = [[c.value for c in row] for row in ws.iter_rows(max_row=HEADER_SCAN_ROWS)]
    h, cols = _header(table)
    hr = h + 1  # openpyxl rows count from 1
    next_col = ws.max_column + 1
    for key, title in (("done", DONE), ("comments", COMMENTS)):
        if key not in cols:
            ws.cell(row=hr, column=next_col, value=title)
            cols[key] = next_col - 1
            next_col += 1
    for r in range(hr + 1, ws.max_row + 1):
        n = ws.cell(row=r, column=cols["name"] + 1).value
        c = ws.cell(row=r, column=cols["company"] + 1).value if "company" in cols else ""
        if n and identity(str(n), str(c or "")) == who:
            if done_value is not ...:  # assign .value: ws.cell(value=None) would leave the old value in place
                ws.cell(row=r, column=cols["done"] + 1).value = done_value
            if comment is not None:
                ws.cell(row=r, column=cols["comments"] + 1).value = comment or None
            break
    else:
        raise SheetError(f"{name} isn't in {path.name} any more, so only the dashboard was updated.")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".nf-", suffix=".xlsx")
    os.close(fd)
    wb.save(tmp)
    os.replace(tmp, path)


LAST_CONTACT = "Last Contact Date"


def convert_dates(path: Path, as_of: date) -> bool:
    """Once per roster: add a Last Contact Date column (as_of minus each day count) and, in Excel files, turn the day
    counts into =TODAY()-date formulas so they stay right. Returns False if the column is already there."""
    from datetime import timedelta
    path = Path(path)
    if _open_in_excel(path):
        raise SheetError(f"{path.name} is open in Excel, so I couldn't add the Last Contact Date column yet.")
    if path.suffix.lower() == ".csv":
        table = _load(path)
        h, cols = _header(table)
        if "last_contact" in cols or "days_since_contact" not in cols:
            return False
        width = max(len(r) for r in table)
        table[h] = table[h] + [""] * (width - len(table[h])) + [LAST_CONTACT]
        for r in table[h + 1:]:
            r.extend([""] * (width - len(r)))
            days = _cell_str(r[cols["days_since_contact"]]) if cols["days_since_contact"] < len(r) else ""
            r.append((as_of - timedelta(days=int(days))).isoformat() if days.isdigit() else "")
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".nf-", suffix=".csv")
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(table)
        os.replace(tmp, path)
        return True
    if not _is_real_xlsx(path):
        raise SheetError(f"{path.name} is a zipped copy, so I couldn't add the Last Contact Date column.")
    import openpyxl
    from openpyxl.utils import get_column_letter
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[0]
    h, cols = _header([[c.value for c in row] for row in ws.iter_rows(max_row=HEADER_SCAN_ROWS)])
    if "last_contact" in cols or "days_since_contact" not in cols:
        return False
    hr, dc, lc = h + 1, cols["days_since_contact"] + 1, ws.max_column + 1
    ws.cell(row=hr, column=lc).value = LAST_CONTACT
    for r in range(hr + 1, ws.max_row + 1):
        days = ws.cell(row=r, column=dc).value
        if isinstance(days, (int, float)) and not isinstance(days, bool) and days >= 0:
            cell = ws.cell(row=r, column=lc)
            cell.value = as_of - timedelta(days=int(days))
            cell.number_format = "mmm d, yyyy"
            ws.cell(row=r, column=dc).value = f"=TODAY()-{get_column_letter(lc)}{r}"
            ws.cell(row=r, column=dc).number_format = "0"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".nf-", suffix=".xlsx")
    os.close(fd)
    wb.save(tmp)
    os.replace(tmp, path)
    return True
