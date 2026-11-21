"""Data-quality checks: facts about the roster and goals that code can be sure of."""
import re
from collections import defaultdict

from .goals import Goal, OrgRef
from .issues import Issue
from .roster import Contact

DORMANT_DAYS = 60
NEAR_DORMANT_DAYS = 53
THIN_MAX_STRENGTH = 1
THIN_MIN_WORDS = 10

# Lookahead so matches can overlap: in "Intro from Patrick at Greylock" the pair "Patrick at Greylock" is still seen.
_REFERENCE = re.compile(r"(?=\b([A-Z][a-z]+)\s+(?:at|from)\s+([A-Z][\w&-]*(?:\s+[A-Z][\w&-]*)*))")


def flags_for(c: Contact) -> dict[str, bool]:
    days = c.days_since_contact
    return {
        "dormant": days is not None and days >= DORMANT_DAYS,
        "near_dormant": days is not None and NEAR_DORMANT_DAYS <= days < DORMANT_DAYS,
        "thin": c.strength is not None and c.strength <= THIN_MAX_STRENGTH
                and len(c.summary.split()) < THIN_MIN_WORDS,
    }


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def org_matches(org: OrgRef, c: Contact) -> bool:
    have = _tokens(c.company) | _tokens(" ".join(c.tags))
    for term in org.terms():
        want = _tokens(term)
        if want and want <= have:
            return True
    return False


def _known_org(org: OrgRef, contacts: list[Contact], goals: list[Goal]) -> bool:
    """True when the phrase names a company in the roster or an organization named in the goals."""
    if any(org_matches(org, c) for c in contacts):
        return True
    phrase = _tokens(org.name)
    return any(t and (t <= phrase or phrase <= t)
               for g in goals for o in g.key_orgs + g.no_contacts_yet for t in map(_tokens, o.terms()))


def _who(cs: list[Contact]) -> str:
    return ", ".join(f"{c.name} ({c.company or 'no company listed'})" for c in cs)


def _rows_text(rows: list[int]) -> str:
    return " and ".join(str(r) for r in rows) if len(rows) <= 2 else ", ".join(str(r) for r in rows)


def run_checks(contacts: list[Contact], goals: list[Goal]) -> list[Issue]:
    issues: list[Issue] = []

    # 1. Organizations named in goals but absent from the roster (unless goals already say "no contacts yet").
    seen_missing = set()
    for g in goals:
        expected_absent = {o.name.lower() for o in g.no_contacts_yet}
        for org in g.key_orgs:
            if org.name.lower() in expected_absent or org.name.lower() in seen_missing:
                continue
            if not any(org_matches(org, c) for c in contacts):
                seen_missing.add(org.name.lower())
                issues.append(Issue("GOAL_ORG_MISSING", "warn",
                                    f"Goal {g.id} mentions {org.name}, but nobody at {org.name} is in the network list. "
                                    f"Who is the contact there? Add them so next week's brief can include them."))

    # 2. Goals say "no contacts yet at X", but the roster has someone there.
    for g in goals:
        for org in g.no_contacts_yet:
            found = [c for c in contacts if org_matches(org, c)]
            if found:
                rows = [c.row_id for c in found]
                issues.append(Issue("GOAL_CONTRADICTION", "warn",
                                    f"The goals say there's no contact at {org.name} yet, but {_who(found)} "
                                    f"{'is' if len(found) == 1 else 'are'} in the network. Is that the way in? "
                                    "If so, update goals.md.", rows))

    # 3. "<First> at <Org>" in notes/summary where that first name isn't at that org.
    by_first = defaultdict(list)
    for c in contacts:
        by_first[c.name.split()[0]].append(c)
    for owner in contacts:
        for text in (owner.notes, owner.summary):
            for first, org_phrase in _REFERENCE.findall(text):
                same_first = [c for c in by_first.get(first, []) if c is not owner]
                if not same_first:
                    continue
                org = OrgRef(org_phrase)
                if not _known_org(org, contacts, goals):
                    continue  # "Saw Reid at Davos": a place or event, not an organization in her world
                if any(org_matches(org, c) for c in same_first):
                    continue
                at_org = [c for c in contacts if org_matches(org, c) and c is not owner]
                only = "the only" if len(same_first) == 1 else f"the {first}s in the network are"
                where = (f"The {org_phrase} contact is {_who(at_org)}." if at_org
                         else f"Nobody at {org_phrase} is in the network list.")
                issues.append(Issue("AMBIGUOUS_REFERENCE", "warn",
                                    f"{owner.name}'s notes mention \"{first} at {org_phrase}\", but {only} "
                                    f"{first + ' in the network is ' if len(same_first) == 1 else ''}"
                                    f"{_who(same_first)}. {where} Who made the intro?", [owner.row_id]))

    # 4. Exact duplicate names, then shared first/last names.
    by_full = defaultdict(list)
    for c in contacts:
        by_full[c.name.lower()].append(c)
    for dupes in by_full.values():
        if len(dupes) > 1:
            rows = [c.row_id for c in dupes]
            issues.append(Issue("DUPLICATE_NAME", "warn",
                                f"{dupes[0].name} appears {len(dupes)} times (rows {_rows_text(rows)}: "
                                f"{', '.join(c.company or 'no company' for c in dupes)}). If it's the same person, "
                                "merge the rows; if not, add something to tell them apart.", rows))
    first_seen: dict[str, Contact] = {}
    for c in contacts:
        first_seen.setdefault(c.name.lower(), c)
    unique = list(first_seen.values())
    for label, key in (("first", lambda c: c.name.split()[0]), ("last", lambda c: c.name.split()[-1])):
        groups = defaultdict(list)
        for c in unique:
            if len(c.name.split()) > 1:
                groups[key(c)].append(c)
        for name, group in groups.items():
            if len(group) > 1:
                issues.append(Issue("NAME_COLLISION", "info",
                                    f"{len(group)} people share the {label} name {name}: {_who(group)}. "
                                    "The brief always uses full names and companies.", [c.row_id for c in group]))

    # 5. Thin context and contacts about to go dormant.
    thin = [c for c in contacts if flags_for(c)["thin"]]
    if thin:
        issues.append(Issue("THIN_CONTEXT", "info",
                            f"Very little is known about {', '.join(c.name for c in thin)} (strength 1, short notes). "
                            "They're only picked if a goal clearly needs them, and marked low-confidence.",
                            [c.row_id for c in thin]))
    for c in contacts:
        if flags_for(c)["near_dormant"]:
            issues.append(Issue("NEAR_DORMANT", "info",
                                f"{c.name} ({c.days_since_contact} days) becomes dormant within a week.", [c.row_id]))
    return issues
