from nf_core.changes import identity, roster_index, row_fingerprint


def contact(**kw):
    base = {"row_id": 1, "name": "Marcus Wei", "role": "Partner", "company": "Sequoia Capital", "how_known": "investor",
            "days_since_contact": 16, "channel": "email", "summary": "Asked to see the full pitch.", "strength": 3,
            "tags": ["investor", "series-c"], "notes": "Warm intro."}
    return {**base, **kw}


def test_identity_distinguishes_company():
    assert identity("Diana  Chen", "Stripe") == identity("diana chen", "stripe ")
    assert identity("Diana Chen", "Stripe") != identity("Diana Chen", "Google")


def test_fingerprint_ignores_days():
    assert row_fingerprint(contact(days_since_contact=10)) == row_fingerprint(contact(days_since_contact=40))
    assert row_fingerprint(contact(row_id=9)) == row_fingerprint(contact())
    assert row_fingerprint(contact(notes="Term sheet due Friday.")) != row_fingerprint(contact())
    assert row_fingerprint(contact(tags=["series-c", "investor"])) == row_fingerprint(contact())


def test_roster_index_duplicate_keeps_first():
    idx = roster_index([contact(), contact(row_id=2, notes="Second copy."), contact(row_id=3, name="Diana Chen", company="Stripe")])
    assert len(idx) == 2
    assert idx[identity("Marcus Wei", "Sequoia Capital")] == {"name": "Marcus Wei", "fp": row_fingerprint(contact())}


# ---- diff ----
import copy  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from conftest import ROOT, TWO_ROWS, build_roster_dict  # noqa: E402
from nf_core.changes import diff_roster  # noqa: E402

DIFF_CLI = ROOT / "plugins" / "network-focus" / "scripts" / "roster_diff.py"


def test_diff_new_changed_removed():
    before = build_roster_dict()["contacts"]
    after = [copy.deepcopy(c) for c in before if c["name"] != "Lin Wang"]
    for c in after:
        c["days_since_contact"] = (c["days_since_contact"] or 0) + 3
    next(c for c in after if c["name"] == "Marcus Wei")["notes"] = "Term sheet due Friday."
    after.append({**copy.deepcopy(after[0]), "row_id": 26, "name": "Ana Ruiz", "company": "Andreessen Horowitz"})
    d = diff_roster(roster_index(before), after)
    assert [p["name"] for p in d["new"]] == ["Ana Ruiz"] and d["new"][0] == {"row_id": 26, "name": "Ana Ruiz", "company": "Andreessen Horowitz"}
    assert [p["name"] for p in d["changed"]] == ["Marcus Wei"]
    assert d["removed"] == [{"name": "Lin Wang"}]


def _run_diff(roster, snapshot_path):
    p = subprocess.run([sys.executable, str(DIFF_CLI), "--roster", str(roster), "--snapshot", str(snapshot_path)],
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])


def test_roster_diff_cli_no_index(tmp_path, make_roster):
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"version": 1, "week_of": "2026-11-23", "brief": {}}), encoding="utf-8")
    assert _run_diff(make_roster(TWO_ROWS), snap) == (0, {"ok": False, "reason": "no_index"})


def test_roster_diff_cli_reports_new(tmp_path, make_roster):
    roster = make_roster(TWO_ROWS)
    first = {"name": "Marcus Wei", "role": "Partner", "company": "Sequoia Capital", "how_known": "investor",
             "channel": "email", "summary": TWO_ROWS[0]["Last Contact Summary"], "strength": 3,
             "tags": ["investor", "series-c", "warm"], "notes": "Warm intro from Patrick at Greylock."}
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"version": 2, "roster_index": roster_index([first])}), encoding="utf-8")
    code, out = _run_diff(roster, snap)
    assert code == 0 and out["ok"] is True and out["file"] == roster.name
    assert [p["name"] for p in out["new"]] == ["Diana Chen"] and out["changed"] == [] and out["removed"] == []


def test_roster_diff_cli_blocked_file(tmp_path):
    bad = tmp_path / "roster.csv"
    bad.write_text("Just,Some,Columns\n1,2,3\n", encoding="utf-8")
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"version": 2, "roster_index": {}}), encoding="utf-8")
    code, out = _run_diff(bad, snap)
    assert code == 0 and out["ok"] is False and out["reason"] == "blocked" and out["message"]
