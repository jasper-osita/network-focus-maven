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
