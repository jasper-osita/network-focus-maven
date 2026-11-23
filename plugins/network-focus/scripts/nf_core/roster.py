"""Read the CEO's network spreadsheet (.xlsx / .csv, optionally zipped) into Contacts."""
import csv
import re
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .issues import Issue, block

# field name -> header as the chief of staff sees it
REQUIRED_COLUMNS: dict[str, str] = {
    "name": "Name",
    "role": "Role",
    "company": "Company",
    "how_known": "How She Knows Them",
    "days_since_contact": "Days Since Last Contact",
    "channel": "Last Contact Channel",
    "summary": "Last Contact Summary",
    "strength": "Relationship Strength (1-5)",
    "tags": "Tags",
    "notes": "Notes",
}
# optional: once present, days are counted from this date (the sheet's own day-count column becomes a formula)
OPTIONAL_COLUMNS: dict[str, str] = {"last_contact": "Last Contact Date"}
SUPPORTED = (".xlsx", ".csv", ".zip")
HEADER_SCAN_ROWS = 5


@dataclass
class Contact:
    row_id: int
    name: str
    role: str = ""
    company: str = ""
    how_known: str = ""
    days_since_contact: int | None = None
    channel: str = ""
    summary: str = ""
    strength: int | None = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    last_contact: str = ""  # ISO date, when the sheet has a Last Contact Date column

    def text(self) -> str:
        """Everything a claim about this contact may quote from."""
        return " | ".join([self.role, self.company, self.how_known, self.summary, ", ".join(self.tags), self.notes])

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_header(h) -> str:
    s = re.sub(r"\(.*?\)", " ", str(h or "")).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


_HEADER_KEYS = {_norm_header(v): k for k, v in {**REQUIRED_COLUMNS, **OPTIONAL_COLUMNS}.items()}


def _cell_date(v):
    """A date from an Excel date cell, or from text like 2026-11-06 / Nov 6, 2026. None if it isn't one."""
    from datetime import date as _d, datetime as _dt
    if isinstance(v, _dt):
        return v.date()
    if isinstance(v, _d):
        return v
    s = _cell_str(v)
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return _dt.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _cell_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).split())


def _cell_int(v) -> int | None:
    """Excel gives 16, 16.0, '16' or ' 16 '. Returns None when it isn't a whole number."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else None
    s = str(v).strip()
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() else None


def _unwrap_zip(path: Path, tmp: Path) -> Path:
    with zipfile.ZipFile(path) as z:
        if "[Content_Types].xml" in z.namelist():
            return path  # a real .xlsx
        inner = [n for n in z.namelist()
                 if n.lower().endswith((".xlsx", ".csv")) and not Path(n).name.startswith(("~$", "."))
                 and not n.startswith("__MACOSX/")]
        if len(inner) != 1:
            raise block("FILE_UNREADABLE",
                        f"{path.name} is a zip file with {len(inner)} spreadsheets inside. "
                        "Unzip it (double-click it) and put just this week's spreadsheet in the inbox.")
        out = tmp / Path(inner[0]).name
        out.write_bytes(z.read(inner[0]))
        return out


def _read_table(path: Path) -> list[list]:
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [row for row in csv.reader(f)]
    import openpyxl  # only needed for xlsx
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()


def read_roster(path: Path, today=None) -> tuple[list[Contact], list[Issue]]:
    from datetime import date as _d
    today = today or _d.today()
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED:
        raise block("UNSUPPORTED_FILE",
                    f"{path.name} isn't a spreadsheet file I can read. Export it as .xlsx or .csv "
                    "(in Numbers or Excel: File → Export) and put that file in the inbox.")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            real = path
            if zipfile.is_zipfile(path):
                real = _unwrap_zip(path, Path(tmp))
            elif path.suffix.lower() in (".xlsx", ".zip"):
                raise ValueError("not a zip-based xlsx")
            table = _read_table(real)
    except Exception as exc:
        if hasattr(exc, "issue"):
            raise
        raise block("FILE_UNREADABLE",
                    f"I couldn't open {path.name}. It may be damaged or still downloading. "
                    "Open it in Excel, save it again as .xlsx, and put the new copy in the inbox.") from exc
    return _parse_table(table, path.name, today)


def _parse_table(table: list[list], file_name: str, today=None) -> tuple[list[Contact], list[Issue]]:
    header_idx, colmap = None, {}
    for i, row in enumerate(table[:HEADER_SCAN_ROWS]):
        keys = {_HEADER_KEYS.get(_norm_header(h)): j for j, h in enumerate(row) if _HEADER_KEYS.get(_norm_header(h))}
        if "name" in keys:
            header_idx, colmap = i, keys
            break
    missing = [REQUIRED_COLUMNS[k] for k in REQUIRED_COLUMNS if k not in colmap]
    if header_idx is None or missing:
        missing = missing or list(REQUIRED_COLUMNS.values())
        raise block("MISSING_COLUMNS",
                    f"{file_name} is missing these columns: {', '.join(missing)}. "
                    "Add them back (or fix the header spelling) in the first row, then run again.")

    contacts: list[Contact] = []
    issues: list[Issue] = []
    for i, row in enumerate(table[header_idx + 1:], start=header_idx + 2):
        cell = {k: (row[j] if j < len(row) else None) for k, j in colmap.items()}
        if all(_cell_str(v) == "" for v in cell.values()):
            continue  # blank row
        row_id = i
        name = _cell_str(cell["name"])
        days = _cell_int(cell["days_since_contact"])
        last = _cell_date(cell.get("last_contact")) if "last_contact" in cell else None
        if last is not None and today is not None and last <= today:
            days = (today - last).days  # a real date beats a day count that was right only on export day
        if days is None or days < 0:
            if _cell_str(cell["days_since_contact"]):
                issues.append(Issue("BAD_CELL", "warn",
                                    f"Row {row_id} ({name}): 'Days Since Last Contact' is "
                                    f"'{_cell_str(cell['days_since_contact'])}', expected a whole number. "
                                    "This person can't be counted as dormant until it's fixed.", [row_id]))
            days = None
        strength = _cell_int(cell["strength"])
        if strength is not None and not 1 <= strength <= 5:
            strength = None
        if strength is None and _cell_str(cell["strength"]):
            issues.append(Issue("BAD_CELL", "warn",
                                f"Row {row_id} ({name}): 'Relationship Strength' is "
                                f"'{_cell_str(cell['strength'])}', expected 1 to 5.", [row_id]))
        if not name:
            issues.append(Issue("BAD_CELL", "warn", f"Row {row_id} has no name, so it was skipped.", [row_id]))
            continue
        contacts.append(Contact(
            row_id=row_id, name=name, role=_cell_str(cell["role"]), company=_cell_str(cell["company"]),
            how_known=_cell_str(cell["how_known"]), days_since_contact=days, channel=_cell_str(cell["channel"]),
            summary=_cell_str(cell["summary"]), strength=strength,
            tags=[t.strip() for t in _cell_str(cell["tags"]).split(",") if t.strip()],
            notes=_cell_str(cell["notes"]), last_contact=last.isoformat() if last else "",
        ))
    if not contacts:
        raise block("FILE_EMPTY",
                    f"{file_name} has the right columns but no contacts in it. "
                    "Check you exported the right sheet, then run again.")
    return contacts, issues
