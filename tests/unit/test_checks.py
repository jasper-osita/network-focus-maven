import pytest

from nf_core.checks import flags_for, org_matches, run_checks
from nf_core.goals import OrgRef, parse_goals
from nf_core.roster import Contact, read_roster


@pytest.fixture
def contacts(sample_xlsx):
    return read_roster(sample_xlsx)[0]


@pytest.fixture
def goals(template_text):
    return parse_goals(template_text)


@pytest.fixture
def issues(contacts, goals):
    return run_checks(contacts, goals)


@pytest.fixture
def by_name(contacts):
    return {c.name: c for c in contacts}


def of(issues, code):
    return [i for i in issues if i.code == code]


def test_flags(by_name):
    f = {n: flags_for(c) for n, c in by_name.items()}
    assert f["Reid Hoffman"]["dormant"] and not f["Lin Wang"]["dormant"]
    assert f["Lin Wang"]["near_dormant"] and not f["Reid Hoffman"]["near_dormant"]
    assert f["Anjali Sharma"]["thin"] and f["Jensen Huang"]["thin"] and not f["Marcus Wei"]["thin"]


def test_org_matching(contacts, goals, by_name):
    arc, sequoia, a16z = goals[2].key_orgs[2], goals[0].key_orgs[0], goals[0].key_orgs[1]
    academic = goals[2].no_contacts_yet[2]
    assert [c.name for c in contacts if org_matches(arc, c)] == ["Paul Christiano"]
    assert [c.name for c in contacts if org_matches(sequoia, c)] == ["Marcus Wei"]
    assert [c.name for c in contacts if org_matches(academic, c)] == ["Yifan Zhou"]
    assert [c.name for c in contacts if org_matches(a16z, c)] == []


def test_missing_key_org_warns(issues):
    miss = of(issues, "GOAL_ORG_MISSING")
    assert len(miss) == 1 and "a16z" in miss[0].message and miss[0].severity == "warn"


def test_contradiction_warns(issues):
    c = of(issues, "GOAL_CONTRADICTION")
    msgs = " ".join(i.message for i in c)
    assert "Paul Christiano" in msgs and "ARC" in msgs and "Yifan Zhou" in msgs
    assert all(i.severity == "warn" for i in c)


def test_ambiguous_reference(issues):
    a = of(issues, "AMBIGUOUS_REFERENCE")
    assert len(a) == 1 and a[0].rows == [2] and a[0].severity == "warn"
    assert all(s in a[0].message for s in ["Patrick at Greylock", "Patrick Collison", "Reid Hoffman"])


def test_no_false_positive_on_capitalized_words(goals):
    people = [
        Contact(2, "Sarah Guo", company="Conviction VC", summary="Coffee at AI Engineer Summit."),
        Contact(3, "David Liu", company="Google", notes="Met at Lattice conference. Coffee at Blue Bottle."),
        Contact(4, "Reid Hoffman", company="Greylock"),
        Contact(5, "Marcus Wei", company="Sequoia", notes="Intro from Reid at Greylock."),
    ]
    assert of(run_checks(people, goals), "AMBIGUOUS_REFERENCE") == []


def test_name_collisions_info(issues):
    col = of(issues, "NAME_COLLISION")
    assert all(i.severity == "info" for i in col)
    assert any("David Liu" in i.message and "David Park" in i.message for i in col)
    assert any("Jensen Huang" in i.message and "Jensen Carlsson" in i.message for i in col)


def test_duplicate_full_name_warns(contacts, goals):
    dup = Contact(27, "Diana Chen", role="Head of Platform", company="Notion", days_since_contact=45)
    d = of(run_checks(contacts + [dup], goals), "DUPLICATE_NAME")
    assert len(d) == 1 and d[0].rows == [3, 27] and d[0].severity == "warn"
    assert of(run_checks(contacts + [dup], goals), "NAME_COLLISION") == of(run_checks(contacts, goals), "NAME_COLLISION")


def test_near_dormant_and_thin_info(issues):
    near = of(issues, "NEAR_DORMANT")
    assert [n.rows for n in near] == [[12], [13]] and all(n.severity == "info" for n in near)
    assert "Lin Wang" in near[0].message and "Patrick Collison" in near[1].message  # 59 and 53 days
    thin = of(issues, "THIN_CONTEXT")
    assert len(thin) == 1 and thin[0].rows == [10, 11]
