"""A self-contained JSON copy of each brief, saved next to the PDF, for the CEO dashboard.
The dashboard reads this instead of .work/, which every run clears."""

BANNER_CODES = ("STALE_FILE", "REUSED_FILE")
SNAPSHOT_VERSION = 1


def questions_for(brief: dict, roster: dict, warnings: dict) -> list[str]:
    """The 'Check before the meeting' items, in the order the PDF prints them."""
    goals = {g["id"]: g["title"] for g in roster["goals"]}
    items = [w["message"] for w in warnings.get("warnings", [])
             if w["severity"] == "warn" and w["code"] not in BANNER_CODES]
    items += [f"No pick for Goal {g['goal_id']} ({goals.get(g['goal_id'], '?')}): {g['note']}"
              for g in brief.get("goal_gaps", [])]
    items += list(brief.get("extra_checks", []))
    return items


def build_snapshot(brief: dict, roster: dict, warnings: dict) -> dict:
    rows = {c["row_id"]: c for c in roster["contacts"]}
    ws = warnings.get("warnings", [])
    picked = [x["row_id"] for sec in ("focus", "dormant", "coming_up") for x in brief.get(sec, [])]
    quiet = [r for w in ws if w["code"] == "NEAR_DORMANT" for r in w.get("rows", []) if r not in picked]
    people = {str(r): {k: rows[r].get(k) for k in ("name", "role", "company", "days_since_contact")}
              for r in picked + quiet if r in rows}
    return {
        "version": SNAPSHOT_VERSION,
        "week_of": brief["week_of"],
        "source": {"file_name": roster["source"]["file_name"], "as_of": roster["source"]["as_of"]},
        "goals": {str(g["id"]): g["title"] for g in roster["goals"]},
        "people": people,
        "brief": brief,
        "questions": questions_for(brief, roster, warnings),
        "banner": [w["message"] for w in ws if w["code"] in BANNER_CODES],
        "going_quiet": [{"row_id": r, "name": rows[r]["name"], "days_since_contact": rows[r]["days_since_contact"]}
                        for r in quiet if r in rows],
    }
