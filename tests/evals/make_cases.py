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
BASE_BRIEF = ROOT / "tests" / "unit" / "fixtures" / "valid_brief.json"
NO_UPDATE = {"must_place": [], "must_consider": [], "must_keep": [], "must_refuse": []}
ANA = ["Ana Ruiz", "Partner", "Andreessen Horowitz", "investor", 5, "email",
       "Asked for a Series C call before Friday after seeing the teaser deck.", 3, "investor, series-c",
       "Met at a founders dinner; wants to see the full deck."]
TOM = ["Tom Park", "Engineering Director", "Figma", "former colleague", 10, "call",
       "Scaled engineering from 40 to 220 people. Open to a conversation about a bigger role.", 3, "cto-candidate",
       "Would want an intro to the board first."]


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


def update_case(name: str, expected: dict, rows: list[list], marks: dict, brief: dict) -> None:
    """A mid-week Update case: Monday's brief (base_brief.json, made from the sample roster), the ticks so far,
    and this week's changed roster."""
    d = case(name, {**NO_UPDATE, **expected}, {"kind": "update", "marks": marks})
    (d / "base_brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False))
    write_xlsx(d / "roster.xlsx", rows)


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
    base = json.loads(BASE_BRIEF.read_text())
    update_case("update-series-c-newcomer", {"must_place": ["Ana Ruiz"], "must_keep": ["Diana Chen"]},
                rows + [ANA], {}, base)
    update_case("update-cto-newcomer", {"must_consider": ["Tom Park"], "must_keep": ["Diana Chen"]},
                rows + [TOM], {}, base)
    floor = json.loads(BASE_BRIEF.read_text())
    sarah = next(f for f in floor["focus"] if f["name"] == "Sarah Guo")
    sarah["goals"] = [1]  # Paul Christiano is now the only AI-safety pick
    done = {str(f["row_id"]): f["name"] for f in floor["focus"][1:] if f["name"] != "Paul Christiano"}
    update_case("update-coverage-floor", {"must_refuse": ["Ana Ruiz"], "must_keep": ["Paul Christiano"]},
                rows + [ANA], done, floor)
    print(f"Wrote {len(list(CASES.iterdir()))} cases to {CASES}")


if __name__ == "__main__":
    main()
