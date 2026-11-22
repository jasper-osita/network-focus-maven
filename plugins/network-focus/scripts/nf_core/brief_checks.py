"""Hard checks on what the model wrote. Every name, quote and number must trace back to the spreadsheet."""
import json
import re
import unicodedata
from pathlib import Path

from .checks import DORMANT_DAYS
from .shape import Problem, check_shape

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"
BRIEF_SCHEMA = json.loads((SCHEMAS / "brief.json").read_text(encoding="utf-8"))
SCOUT_SCHEMA = json.loads((SCHEMAS / "scout-output.json").read_text(encoding="utf-8"))

MIN_QUOTE_WORDS = 3
MIN_MOVE_WORDS = 8
MESSAGE_MIN_WORDS = 20
MESSAGE_MAX_WORDS = 120
PLACEHOLDER_CHARS = ("[", "{", "<")
_PLACEHOLDER_WORDS = re.compile(r"\b(?:todo|tbd|lorem)\b", re.I)
_ATTACHMENT = re.compile(r"\b(?:attached|attaching|attachment|enclosed)\b", re.I)
# In messages only "N days ago/since" or "been N days" states a fact; "in the next 2 days" doesn't.
_MSG_DAYS = re.compile(r"(\d+)\s+days?\s+(?:ago|since)\b|\bbeen\s+(\d+)\s+days?\b", re.I)
HONORIFICS = {"dr", "mr", "mrs", "ms", "mx", "prof", "sir", "dame"}
MOVE_WORDS = ("email", "call", "coffee", "meeting", "intro", "message", "note", "lunch", "dinner",
              "reply", "send", "ask")
_DAYS = re.compile(r"(\d+)\s+days?\b")
_TRANSLATE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                            "–": "-", "—": "-", " ": " "})


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(_TRANSLATE)
    return " ".join(s.split()).casefold()


def _quote_core(q: str) -> str:
    return _norm(q).strip(" .,;:!?\"'")


def _by_row(roster: dict) -> dict:
    return {c["row_id"]: c for c in roster["contacts"]}


def _check_person(item: dict, where: str, rows: dict, problems: list[Problem], evidence_field="evidence") -> dict | None:
    row = rows.get(item["row_id"])
    if row is None:
        problems.append(Problem("UNKNOWN_ROW", where, f"{where}: row {item['row_id']} isn't in the spreadsheet."))
        return None
    if _norm(item["name"]) != _norm(row["name"]):
        problems.append(Problem("NAME_MISMATCH", where,
                                f"{where}: row {row['row_id']} is {row['name']}, not {item['name']}."))
    for q in item.get(evidence_field, []):
        core = _quote_core(q)
        if len(core.split()) < MIN_QUOTE_WORDS:
            problems.append(Problem("QUOTE_TOO_SHORT", where,
                                    f"{where}: the quote '{q}' is too short to prove anything; quote 3+ words."))
        elif core not in _norm(row["text"]):
            problems.append(Problem("QUOTE_NOT_FOUND", where,
                                    f"{where}: '{q}' isn't in {row['name']}'s row. Quote the spreadsheet word for word."))
    return row


def first_name(name: str) -> str:
    """'Diana Chen', 'Dr. Diana Chen' and 'Chen, Diana' all give 'Diana'."""
    if "," in name:
        name = name.split(",", 1)[1]
    tokens = [t.strip(".,") for t in name.split()]
    tokens = [t for t in tokens if t and t.casefold() not in HONORIFICS]
    return tokens[0] if tokens else name.strip()


def _check_move_and_numbers(item: dict, row: dict, where: str, problems: list[Problem]) -> None:
    words = re.findall(r"[a-z]+", item["move"].lower())
    if len(words) < MIN_MOVE_WORDS or not any(w.startswith(MOVE_WORDS) for w in words):
        problems.append(Problem("VAGUE_MOVE", where,
                                f"{where}: the move '{item['move']}' isn't specific. Say what to do, through which "
                                "channel (email, call, coffee, intro...), and about what."))
    message = item.get("message", "")
    stated = [("why", n) for n in _DAYS.findall(item.get("why", ""))]
    stated += [("message", a or b) for a, b in _MSG_DAYS.findall(message)]
    for field, n in stated:
        if row.get("days_since_contact") is None or int(n) != row["days_since_contact"]:
            problems.append(Problem("NUMBER_MISMATCH", where,
                                    f"{where}.{field}: says {n} days, but {row['name']}'s row says "
                                    f"{row.get('days_since_contact')} days."))
    n_words = len(message.split())
    if not MESSAGE_MIN_WORDS <= n_words <= MESSAGE_MAX_WORDS:
        problems.append(Problem("MESSAGE_LENGTH", where,
                                f"{where}: the message is {n_words} words; write {MESSAGE_MIN_WORDS}-{MESSAGE_MAX_WORDS} "
                                "words she can paste and send."))
    first = first_name(row["name"])
    if first.casefold() not in message.casefold():
        problems.append(Problem("MESSAGE_NAME", where, f"{where}: the message should greet {first} by name."))
    if _ATTACHMENT.search(message):
        problems.append(Problem("MESSAGE_ATTACHMENT", where,
                                f"{where}: don't say anything is attached. She pastes this text; say she'll send it."))
    if any(ch in message for ch in PLACEHOLDER_CHARS) or _PLACEHOLDER_WORDS.search(message):
        problems.append(Problem("MESSAGE_PLACEHOLDER", where,
                                f"{where}: the message has a placeholder or markup ([, {{, <, TODO). "
                                "Write the finished text."))


def validate_brief(brief: dict, roster: dict) -> list[Problem]:
    problems = check_shape(brief, BRIEF_SCHEMA, "")
    for p in problems:
        if p.code == "COUNT" and p.where in ("focus", "dormant"):
            p.code = f"{p.where.upper()}_COUNT"
    if any(p.code == "SCHEMA" for p in problems):
        return problems
    rows = _by_row(roster)
    goal_ids = {g["id"] for g in roster["goals"]}
    seen: dict[int, str] = {}
    expected_week = roster.get("source", {}).get("week_of")
    if expected_week and brief["week_of"] != expected_week:
        problems.append(Problem("WEEK_MISMATCH", "week_of",
                                f"week_of is '{brief['week_of']}'; copy roster.json source.week_of exactly: '{expected_week}'."))

    def missing_handled(item, where) -> bool:
        """Code marks a pick 'missing' on Update when its row left the roster. Only then are its row checks skipped."""
        if not item.get("missing"):
            return False
        if item["row_id"] in rows:
            problems.append(Problem("MISSING_BUT_PRESENT", where,
                                    f"{where}: {item['name']} is still in the spreadsheet, so they can't be marked missing."))
        elif not brief.get("updates"):
            problems.append(Problem("MISSING_NOT_ALLOWED", where,
                                    f"{where}: only a mid-week Update can mark someone missing. Pick people from the spreadsheet."))
        return True

    def once(item, where):
        if item["row_id"] in seen:
            problems.append(Problem("DUPLICATE_PERSON", where,
                                    f"{where}: {item['name']} is already in {seen[item['row_id']]}. "
                                    "Each person appears once."))
        else:
            seen[item["row_id"]] = where

    for i, item in enumerate(brief["focus"]):
        where = f"focus[{i}]"
        once(item, where)
        if missing_handled(item, where):
            continue
        row = _check_person(item, where, rows, problems)
        if row is None:
            continue
        for gid in item["goals"]:
            if gid not in goal_ids:
                problems.append(Problem("UNKNOWN_GOAL", where, f"{where}: there is no goal {gid} in goals.md."))
        if row["flags"]["thin"] and item["confidence"] != "low":
            problems.append(Problem("THIN_NOT_LOW", where,
                                    f"{where}: very little is known about {row['name']}, so confidence must be 'low'."))
        _check_move_and_numbers(item, row, where, problems)

    for i, item in enumerate(brief["dormant"]):
        where = f"dormant[{i}]"
        once(item, where)
        if missing_handled(item, where):
            continue
        row = _check_person(item, where, rows, problems)
        if row is None:
            continue
        for gid in item["goals"]:
            if gid not in goal_ids:
                problems.append(Problem("UNKNOWN_GOAL", where, f"{where}: there is no goal {gid} in goals.md."))
        if row["flags"]["thin"]:
            problems.append(Problem("THIN_IN_DORMANT", where,
                                    f"{where}: very little is known about {row['name']}, so they can't be a dormant pick. "
                                    "Choose someone with real history."))
        days = row.get("days_since_contact")
        if days is None or days < DORMANT_DAYS:
            problems.append(Problem("NOT_DORMANT", where,
                                    f"{where}: {row['name']} was in touch {days} days ago; dormant means "
                                    f"{DORMANT_DAYS}+ days."))
        elif item["days_since_contact"] != days:
            problems.append(Problem("DAYS_MISMATCH", where,
                                    f"{where}: says {item['days_since_contact']} days, the row says {days}."))
        _check_move_and_numbers(item, row, where, problems)

    for i, item in enumerate(brief["coming_up"]):
        where = f"coming_up[{i}]"
        once(item, where)
        _check_person(item, where, rows, problems, evidence_field="none")

    focus_ids = {f["row_id"] for f in brief["focus"]}
    eligible = sum(1 for c in roster["contacts"] if c["flags"]["dormant"] and c["row_id"] not in focus_ids)
    if not any(p.code == "DORMANT_COUNT" for p in problems) and len(brief["dormant"]) < min(2, eligible):
        problems.append(Problem("DORMANT_COUNT", "dormant",
                                f"dormant has {len(brief['dormant'])} people; it needs {min(2, eligible)}-3."))

    covered = {g for f in brief["focus"] for g in f["goals"]} | {gap["goal_id"] for gap in brief["goal_gaps"]}
    for g in roster["goals"]:
        if g["id"] not in covered:
            problems.append(Problem("GOAL_NOT_COVERED", "focus",
                                    f"Goal {g['id']} ({g['title']}) has no pick. Add one, or explain in goal_gaps."))
    return problems


def validate_scout(scout: dict, roster: dict) -> list[Problem]:
    problems = check_shape(scout, SCOUT_SCHEMA, "")
    if any(p.code in ("SCHEMA", "COUNT") for p in problems):
        return problems
    rows = _by_row(roster)
    if scout["goal_id"] not in {g["id"] for g in roster["goals"]}:
        problems.append(Problem("UNKNOWN_GOAL", "goal_id", f"There is no goal {scout['goal_id']} in goals.md."))
    for i, item in enumerate(scout["candidates"]):
        _check_person(item, f"candidates[{i}]", rows, problems)
    return problems


def cited_rows(brief: dict, roster: dict, only_new: bool = False) -> dict:
    """The rows the fact-checker needs. only_new: just the picks an Update placed this time."""
    rows = _by_row(roster)
    ids = []
    for section in (("focus",) if only_new else ("focus", "dormant", "coming_up")):
        for item in brief.get(section, []):
            if only_new and not item.get("new"):
                continue
            if item["row_id"] in rows and item["row_id"] not in ids:
                ids.append(item["row_id"])
    return {"goals": [{"id": g["id"], "title": g["title"], "text": g["text"]} for g in roster["goals"]],
            "contacts": [rows[i] for i in ids]}
