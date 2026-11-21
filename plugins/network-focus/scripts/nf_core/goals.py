"""Parse goals.md: plain Markdown a non-technical person can edit, with labeled lines code can read."""
import re
from dataclasses import asdict, dataclass, field

from .issues import block

MAX_GOALS = 5
_HEADER = re.compile(r"^##\s*Goal\s+(\d+)\s*:\s*(.*)$", re.IGNORECASE)
_LABEL = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)$")


@dataclass
class OrgRef:
    name: str
    aliases: list[str] = field(default_factory=list)

    def terms(self) -> list[str]:
        return [self.name, *self.aliases]


@dataclass
class Goal:
    id: int
    title: str
    text: str
    key_orgs: list[OrgRef] = field(default_factory=list)
    no_contacts_yet: list[OrgRef] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _split_outside_parens(s: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in s:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _org_list(value: str) -> list[OrgRef]:
    orgs = []
    for part in _split_outside_parens(value):
        m = re.match(r"^(.*?)\s*\((.*)\)\s*$", part)
        if m:
            orgs.append(OrgRef(m.group(1).strip(), [a.strip() for a in m.group(2).split(",") if a.strip()]))
        else:
            orgs.append(OrgRef(part))
    return orgs


def parse_goals(text: str) -> list[Goal]:
    lines = text.splitlines()
    goals: list[Goal] = []
    current: dict | None = None
    for n, line in enumerate(lines, start=1):
        m = _HEADER.match(line.strip())
        if m:
            title = m.group(2).strip()
            if not title:
                raise block("GOALS_MALFORMED",
                            f"goals.md line {n}: '{line.strip()}' has no goal name after the colon. "
                            "Write it like '## Goal 2: Hire a CTO'.")
            current = {"id": int(m.group(1)), "title": title, "body": [], "key": [], "none": []}
            goals.append(current)
            continue
        if current is None:
            continue  # comments / intro text before the first goal
        current["body"].append(line)
        lm = _LABEL.match(line)
        if lm:
            label = lm.group(1).strip().lower()
            if label == "key organizations":
                current["key"] = _org_list(lm.group(2))
            elif label == "no contacts yet at":
                current["none"] = _org_list(lm.group(2))
    if not goals:
        raise block("GOALS_MALFORMED",
                    "goals.md has no goals in it. Each goal starts with a line like '## Goal 1: Raise Series C'.")
    if len(goals) > MAX_GOALS:
        raise block("GOALS_MALFORMED",
                    f"goals.md has {len(goals)} goals. Keep it to {MAX_GOALS} goals or fewer so the brief stays focused.")
    return [Goal(g["id"], g["title"], "\n".join(g["body"]).strip(), g["key"], g["none"]) for g in goals]
