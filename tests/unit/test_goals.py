import pytest

from nf_core.goals import parse_goals
from nf_core.issues import BlockingError


def test_parses_template(template_text):
    g = parse_goals(template_text)
    assert [x.title for x in g] == ["Raise Series C", "Hire a CTO", "Build relationships in AI safety"]
    assert [x.id for x in g] == [1, 2, 3]
    assert [o.name for o in g[0].key_orgs] == ["Sequoia", "a16z", "Greylock"]
    assert g[0].key_orgs[1].aliases == ["Andreessen Horowitz"]
    assert [o.name for o in g[2].no_contacts_yet] == ["MIRI", "ARC", "academic AI safety groups"]
    assert g[2].no_contacts_yet[2].aliases == ["academic"]
    assert g[2].no_contacts_yet[1].terms() == ["ARC", "Alignment Research Center"]
    assert g[1].key_orgs == [] and "Deadline: this quarter" in g[1].text


def test_no_goals_blocks():
    with pytest.raises(BlockingError) as e:
        parse_goals("hello")
    assert e.value.issue.code == "GOALS_MALFORMED" and "## Goal 1:" in e.value.issue.message


def test_header_without_title_names_line(template_text):
    broken = template_text.replace("## Goal 2: Hire a CTO", "## Goal 2:")
    line_no = broken.splitlines().index("## Goal 2:") + 1
    with pytest.raises(BlockingError) as e:
        parse_goals(broken)
    assert e.value.issue.code == "GOALS_MALFORMED" and f"line {line_no}" in e.value.issue.message


def test_more_than_five_goals_blocks():
    text = "\n".join(f"## Goal {i}: Goal number {i}\nDeadline: soon\n" for i in range(1, 7))
    with pytest.raises(BlockingError) as e:
        parse_goals(text)
    assert "5 goals or fewer" in e.value.issue.message


def test_labels_case_insensitive():
    g = parse_goals("## Goal 1: Raise money\nkey ORGANIZATIONS: Sequoia, Greylock\n")
    assert [o.name for o in g[0].key_orgs] == ["Sequoia", "Greylock"]


def test_comment_lines_ignored():
    g = parse_goals("# The CEO's goals\n# edit me: carefully\n\n## Goal 1: Raise money\nDeadline: Q3\n")
    assert len(g) == 1 and g[0].title == "Raise money" and g[0].key_orgs == []
