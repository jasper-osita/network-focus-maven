"""Mid-week Update, in code: who is new or changed, which picks are locked, which slots are open,
and whether the model's answer follows the rules. The model only judges; it never decides what's allowed."""
import json
from pathlib import Path

from .brief_checks import _by_row, _check_move_and_numbers, _check_person, _norm
from .changes import diff_roster, identity
from .shape import Problem, check_shape

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"
UPDATE_SCHEMA = json.loads((SCHEMAS / "update.json").read_text(encoding="utf-8"))
MAX_FOCUS = 5


def main_goal(roster: dict) -> dict:
    g = min(roster["goals"], key=lambda g: g["id"])
    return {"id": g["id"], "title": g["title"]}


def load_marks(root: Path, week: str) -> dict[str, str]:
    try:
        data = json.loads((Path(root) / ".progress.json").read_text(encoding="utf-8"))
        marks = data.get(week, {}) if isinstance(data, dict) else {}
        return marks if isinstance(marks, dict) else {}
    except (OSError, ValueError):
        return {}


def latest_snapshot(briefs: Path) -> Path | None:
    """The newest brief's snapshot by week (same rule as the page's dashboard_data.latest_snapshot_path)."""
    best = None
    for f in Path(briefs).glob("*-network-focus.json"):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(s, dict) and isinstance(s.get("brief"), dict) and s.get("week_of"):
            if best is None or s["week_of"] > best[0]:
                best = (s["week_of"], f)
    return best[1] if best else None


def _is_done(marks: dict, row_id: int, name: str) -> bool:
    stored = marks.get(str(row_id))
    return isinstance(stored, str) and _norm(stored) == _norm(name)


def prep_update(snapshot: dict, roster: dict, marks: dict[str, str]) -> dict:
    old_people = snapshot.get("people", {})
    new_rows = {identity(c["name"], c.get("company", "")): c["row_id"] for c in roster["contacts"]}
    picks = []
    for section in ("focus", "dormant"):
        for rank, item in enumerate(snapshot["brief"].get(section, [])):
            company = old_people.get(str(item["row_id"]), {}).get("company") or item.get("who", "").split(", ")[-1]
            done = _is_done(marks, item["row_id"], item["name"])
            picks.append({"section": section, "rank": rank, "old_row_id": item["row_id"],
                          "row_id": None if item.get("missing") else new_rows.get(identity(item["name"], company or "")),
                          "name": item["name"], "goals": list(item.get("goals") or []), "done": done,
                          "locked": section == "dormant" or rank == 0 or done})
    picked = {p["row_id"] for p in picks if p["row_id"] is not None}
    diff = diff_roster(snapshot.get("roster_index") or {}, roster["contacts"])
    people = [{"row_id": p["row_id"], "name": p["name"], "kind": "new"} for p in diff["new"]]
    people += [{"row_id": p["row_id"], "name": p["name"], "kind": "changed"} for p in diff["changed"] if p["row_id"] not in picked]
    focus = [p for p in picks if p["section"] == "focus"]
    slots = [{"kind": "empty"} for _ in range(MAX_FOCUS - len(focus))]
    slots += [{"kind": "replace", "row_id": p["row_id"], "name": p["name"], "rank": p["rank"]}
              for p in sorted(focus, key=lambda p: -p["rank"]) if not p["locked"] and p["row_id"] is not None]
    return {"week_of": snapshot["week_of"], "main_goal": main_goal(roster), "picks": picks, "people": people,
            "listed_only": [p["name"] for p in diff["changed"] if p["row_id"] in picked], "open_slots": slots}


def validate_update(update: dict, roster: dict, update_input: dict) -> list[Problem]:
    problems = check_shape(update, UPDATE_SCHEMA, "")
    if any(p.code == "SCHEMA" for p in problems):
        return problems
    rows, goal_ids = _by_row(roster), {g["id"] for g in roster["goals"]}
    main_id = update_input["main_goal"]["id"]
    expected = {p["row_id"]: p["name"] for p in update_input["people"]}
    open_rows = {s["row_id"] for s in update_input["open_slots"] if s["kind"] == "replace"}
    has_empty = any(s["kind"] == "empty" for s in update_input["open_slots"])
    seen = set()
    for i, p in enumerate(update["people"]):
        where = f"people[{i}]"
        if p["row_id"] not in expected or p["row_id"] in seen:
            problems.append(Problem("UNEXPECTED_PERSON", where, f"{where}: {p['name']} isn't one of the new or changed "
                                    "people in update-input.json, or is listed twice. List each of them exactly once."))
            continue
        seen.add(p["row_id"])
        row = _check_person(p, where, rows, problems)
        if row is None:
            continue
        if p["tied_to_main_goal"] and not p["goal_link"].strip():
            problems.append(Problem("NO_GOAL_LINK", where, f"{where}: say how {row['name']} serves the main goal in goal_link."))
        if "beats" in p and p["beats"] not in open_rows:
            problems.append(Problem("BEATS_NOT_OPEN", where, f"{where}: beats must be the row_id of an open pick in "
                                    "open_slots. Done picks, the #1 and dormant picks can't be replaced."))
        pick = p.get("pick")
        if pick is None:
            if not p.get("consider", "").strip():
                problems.append(Problem("NO_CONSIDER_NOTE", where,
                                        f"{where}: {row['name']} has no pick, so write one sentence in consider."))
            continue
        if not p["tied_to_main_goal"] or not ("beats" in p or has_empty):
            problems.append(Problem("PICK_NOT_ALLOWED", where, f"{where}: only people tied to the main goal who beat an "
                                    "open pick (or can fill an empty slot) get a pick. Write a consider note instead."))
            continue
        pw = f"{where}.pick"
        if main_id not in pick["goals"]:
            problems.append(Problem("PICK_GOAL", pw, f"{pw}: goals must include the main goal ({main_id})."))
        for gid in pick["goals"]:
            if gid not in goal_ids:
                problems.append(Problem("UNKNOWN_GOAL", pw, f"{pw}: there is no goal {gid} in goals.md."))
        if row["flags"]["thin"] and pick["confidence"] != "low":
            problems.append(Problem("THIN_NOT_LOW", pw, f"{pw}: very little is known about {row['name']}, so confidence must be 'low'."))
        _check_person({"row_id": p["row_id"], "name": p["name"], "evidence": pick["evidence"]}, pw, rows, problems)
        _check_move_and_numbers(pick, row, pw, problems)
    for row_id, name in expected.items():
        if row_id not in seen:
            problems.append(Problem("MISSING_PERSON", "people", f"{name} (row {row_id}) is missing from people. "
                                    "Give every new or changed person an answer."))
    return problems


def _focus_goals(focus: list[dict]) -> set[int]:
    return {g for f in focus for g in (f.get("goals") or [])}


def apply_update(snapshot: dict, roster: dict, update_input: dict, update: dict, now: str) -> tuple[dict, dict[str, str], dict]:
    """Merge the model's answer into this week's brief under the rules. Whatever the model wrote, done picks, the #1
    and dormant picks never move, empty slots fill first, bumps go weakest-first, and no goal loses its only pick."""
    import copy
    brief = copy.deepcopy(snapshot["brief"])
    people_before = snapshot.get("people", {})
    by_old = {(p["section"], p["old_row_id"]): p for p in update_input["picks"]}
    questions = list(brief.get("update_questions", []))
    for section in ("focus", "dormant"):
        for item in brief.get(section, []):
            pick = by_old.get((section, item["row_id"]))
            if pick is None:
                continue
            if pick["row_id"] is None:
                if not item.get("missing"):
                    row = people_before.get(str(item["row_id"]), {})
                    item.update({"missing": True, "who": ", ".join(x for x in (row.get("role"), row.get("company")) if x)})
                    questions.append(f"{item['name']} is no longer in the roster. Remove them from this week's list?")
            else:
                item["row_id"] = pick["row_id"]
    new_rows = {identity(c["name"], c.get("company", "")): c["row_id"] for c in roster["contacts"]}
    old_people = snapshot.get("people", {})
    for item in brief.get("coming_up", []):
        company = old_people.get(str(item["row_id"]), {}).get("company", "")
        item["row_id"] = new_rows.get(identity(item["name"], company), item["row_id"])

    focus = brief["focus"]
    before = _focus_goals(focus)
    empties = sum(1 for s in update_input["open_slots"] if s["kind"] == "empty")
    replace = [s for s in update_input["open_slots"] if s["kind"] == "replace"]  # weakest first
    rank_of = {s["row_id"]: s["rank"] for s in replace}
    taken, added, bumped, refused, considering = set(), [], [], [], []
    title = update_input["main_goal"]["title"]
    for p in update["people"]:
        pick = p.get("pick")
        if not (p["tied_to_main_goal"] and pick):
            considering.append({"row_id": p["row_id"], "name": p["name"], "note": p.get("consider", "").strip()})
            continue
        item = {"row_id": p["row_id"], "name": p["name"], **pick, "new": True}
        if empties:
            focus.append(item)
            empties -= 1
            added.append(p["name"])
            continue
        floor = rank_of.get(p.get("beats"), 0)
        for s in replace:
            if s["row_id"] in taken or s["rank"] < floor:
                continue
            idx = next(i for i, f in enumerate(focus) if f["row_id"] == s["row_id"])
            trial = focus[:idx] + [item] + focus[idx + 1:]
            if before <= _focus_goals(trial):
                focus[idx] = item
                taken.add(s["row_id"])
                considering.append({"row_id": s["row_id"], "name": s["name"], "note": f"Moved here to make room for {p['name']}."})
                added.append(p["name"])
                bumped.append(s["name"])
                break
        else:
            refused.append(p["name"])
            considering.append({"row_id": p["row_id"], "name": p["name"],
                                "note": f"Tied to {title}, but no open slot could be freed this week."})
    placed = {f["row_id"] for f in focus if f.get("new")}
    fresh = {c["row_id"] for c in considering}
    brief["considering"] = [c for c in brief.get("considering", []) if c["row_id"] not in placed | fresh] + considering
    brief["updates"] = brief.get("updates", []) + [{"at": now, "added": added, "bumped": bumped}]
    if questions:
        brief["update_questions"] = questions
    marks = {str(p["row_id"]): p["name"] for p in update_input["picks"] if p["done"] and p["row_id"] is not None}
    return brief, marks, {"added": added, "bumped": bumped, "refused": refused}
