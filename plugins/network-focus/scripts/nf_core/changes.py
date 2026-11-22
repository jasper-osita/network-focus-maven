"""Who is new or changed in the roster since a brief was made. Pure code: no model involved."""
import hashlib
import json

FINGERPRINT_FIELDS = ("role", "how_known", "channel", "summary", "strength", "tags", "notes")


def _clean(s) -> str:
    return " ".join(str(s or "").split())


def identity(name: str, company: str) -> str:
    """The same person across exports, whatever row they're on. Row numbers shift when rows are added."""
    return f"{_clean(name).casefold()}|{_clean(company).casefold()}"


def row_fingerprint(contact: dict) -> str:
    """Changes when anything about the relationship changes. Days since contact are left out: every export moves them."""
    values = []
    for f in FINGERPRINT_FIELDS:
        v = contact.get(f)
        if f == "tags":
            v = sorted(_clean(t).casefold() for t in (v or []))
        elif isinstance(v, str):
            v = _clean(v)
        values.append(v)
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()


def roster_index(contacts: list[dict]) -> dict[str, dict]:
    """{identity: {"name", "fp"}} for every contact. A duplicate row keeps the first, like the roster loader."""
    index: dict[str, dict] = {}
    for c in contacts:
        index.setdefault(identity(c["name"], c.get("company", "")), {"name": c["name"], "fp": row_fingerprint(c)})
    return index
