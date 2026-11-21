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
