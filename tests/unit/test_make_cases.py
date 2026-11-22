import json

import pytest

from conftest import ROOT
from nf_core.issues import BlockingError
from nf_core.roster import read_roster

CASES = ROOT / "tests" / "evals" / "cases"
NAMES = ["real-roster", "missing-columns", "stale-reused", "duplicate-diana", "thin-target", "csv-version"]


def roster_file(case):
    return next(p for p in (CASES / case).iterdir() if p.stem == "roster")


@pytest.mark.parametrize("case", NAMES)
def test_case_dirs_complete(case):
    exp = json.loads((CASES / case / "expected.json").read_text())
    setup = json.loads((CASES / case / "setup.json").read_text())
    assert set(exp) == {"must_include", "must_exclude", "must_warn", "must_not_warn", "must_block"}
    assert set(setup) == {"mtime_days_ago", "history_same_sha_days_ago"}
    assert roster_file(case).exists()


def test_case_contents():
    with pytest.raises(BlockingError):
        read_roster(roster_file("missing-columns"))
    dup, _ = read_roster(roster_file("duplicate-diana"))
    assert len(dup) == 26 and [c.name for c in dup].count("Diana Chen") == 2
    thin, _ = read_roster(roster_file("thin-target"))
    alex = next(c for c in thin if c.name == "Alex Rivera")
    assert alex.company == "a16z" and alex.strength == 1
    csv_rows, _ = read_roster(roster_file("csv-version"))
    assert roster_file("csv-version").suffix == ".csv" and len(csv_rows) == 25
    assert json.loads((CASES / "stale-reused" / "setup.json").read_text()) == {
        "mtime_days_ago": 21, "history_same_sha_days_ago": 7}


UPDATE_NAMES = ["update-series-c-newcomer", "update-cto-newcomer", "update-coverage-floor"]


@pytest.mark.parametrize("case", UPDATE_NAMES)
def test_update_cases_built(case):
    setup = json.loads((CASES / case / "setup.json").read_text())
    exp = json.loads((CASES / case / "expected.json").read_text())
    assert setup["kind"] == "update" and isinstance(setup["marks"], dict)
    assert set(exp) == {"must_place", "must_consider", "must_keep", "must_refuse"}
    base = json.loads((CASES / case / "base_brief.json").read_text())
    assert len(base["focus"]) == 5 and all("goals" in d for d in base["dormant"])
    names = [c.name for c in read_roster(roster_file(case))[0]]
    assert len(names) == 26 and names[-1] in ("Ana Ruiz", "Tom Park")


def test_coverage_case_leaves_one_open_ai_safety_pick():
    base = json.loads((CASES / "update-coverage-floor" / "base_brief.json").read_text())
    marks = json.loads((CASES / "update-coverage-floor" / "setup.json").read_text())["marks"]
    open_picks = [f for f in base["focus"][1:] if str(f["row_id"]) not in marks]
    assert [f["name"] for f in open_picks] == ["Paul Christiano"] and open_picks[0]["goals"] == [3]
    assert all(3 not in f["goals"] for f in base["focus"] if f["name"] != "Paul Christiano")
