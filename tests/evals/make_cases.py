"""Build the 6 end-to-end test cases from the TerraGrid sample, deterministically.
Run: uv run python tests/evals/make_cases.py"""
import csv
import json
import shutil
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "sample-data" / "network_roster_terragrid.xlsx"
CASES = Path(__file__).resolve().parent / "cases"

REAL_EXPECT = {
    "must_include": ["Diana Chen", "Marcus Wei"],
    "must_exclude": ["James Park", "Jensen Carlsson", "Jensen Huang", "Demis Hassabis", "Aaron Goldsmith"],
    "must_warn": ["GOAL_ORG_MISSING", "AMBIGUOUS_REFERENCE", "GOAL_CONTRADICTION"],
    "must_not_warn": [],
    "must_block": None,
}
NO_EXPECT = {"must_include": [], "must_exclude": [], "must_warn": [], "must_not_warn": [], "must_block": None}


def sample_rows() -> list[list]:
    wb = openpyxl.load_workbook(SAMPLE, data_only=True)
    return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]


def write_xlsx(path: Path, rows: list[list]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Network Roster"
    for r in rows:
        ws.append(r)
    wb.save(path)


def case(name: str, expected: dict, setup: dict | None = None) -> Path:
    d = CASES / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / "expected.json").write_text(json.dumps(expected, indent=2))
    (d / "setup.json").write_text(json.dumps(setup or {"mtime_days_ago": 0, "history_same_sha_days_ago": None}, indent=2))
    return d


def main() -> None:
    rows = sample_rows()
    header = rows[0]

    shutil.copy(SAMPLE, case("real-roster", REAL_EXPECT) / "roster.xlsx")

    keep = [i for i, h in enumerate(header) if h != "Notes"]
    renamed = [["Days" if h == "Days Since Last Contact" else h for h in (r[i] for i in keep)] if n == 0
               else [r[i] for i in keep] for n, r in enumerate(rows)]
    write_xlsx(case("missing-columns", {**NO_EXPECT, "must_block": "MISSING_COLUMNS"}) / "roster.xlsx", renamed)

    shutil.copy(SAMPLE, case("stale-reused", {**NO_EXPECT, "must_warn": ["STALE_FILE", "REUSED_FILE"]},
                             {"mtime_days_ago": 21, "history_same_sha_days_ago": 7}) / "roster.xlsx")

    dup = ["Diana Chen", "Head of Platform", "Notion", "event", 45, "email",
           "Met at a product leaders dinner. Talked about platform teams.", 2, "product", ""]
    write_xlsx(case("duplicate-diana", {**NO_EXPECT, "must_warn": ["DUPLICATE_NAME"]}) / "roster.xlsx", rows + [dup])

    alex = ["Alex Rivera", "Partner", "a16z", "event", 12, "event", "Met briefly.", 1, "investor", ""]
    write_xlsx(case("thin-target", {**NO_EXPECT, "must_not_warn": ["GOAL_ORG_MISSING"]}) / "roster.xlsx", rows + [alex])

    with open(case("csv-version", REAL_EXPECT) / "roster.csv", "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows([["" if v is None else v for v in r] for r in rows])
    print(f"Wrote {len(list(CASES.iterdir()))} cases to {CASES}")


if __name__ == "__main__":
    main()
