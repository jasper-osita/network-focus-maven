"""Turn Claude Code's stream-json events into progress steps the chief of staff understands."""
import json
import re

_SIGNED_OUT = re.compile(r"/login|not logged in|log ?in again|authenticat|invalid api key|unauthori[sz]ed", re.I)
_LIMIT = re.compile(r"usage limit|rate.?limit|\b429\b|overloaded|quota", re.I)
GENERIC = "Something went wrong making the brief. Click Check setup to see what to fix."


def progress_from_event(event: dict) -> str | None:
    if event.get("type") != "assistant":
        return None
    for block in event.get("message", {}).get("content", []):
        if block.get("type") != "tool_use":
            continue
        name, inp = block.get("name"), block.get("input", {})
        if name == "Bash":
            cmd = inp.get("command", "")
            if "load_roster.py" in cmd:
                return "Checking the data"
            if "render_pdf.py" in cmd:
                return "Making the PDF"
            if "update_prep.py" in cmd:
                return "Looking at who's new"
            if "apply_update.py" in cmd:
                return "Placing new people"
        elif name in ("Agent", "Task"):
            kind = inp.get("subagent_type", "")
            if kind.endswith("goal-scout"):
                desc = inp.get("description", "").strip()
                return f"Reviewing {desc}" if desc.lower().startswith("goal ") else f"Reviewing goal: {desc}".strip()
            if kind.endswith("fact-checker"):
                return "Fact-checking the picks"
    return None


def failure_message(result_text: str, stderr: str, event: dict | None = None) -> str:
    """Say why a run produced no brief, in words the chief of staff can act on."""
    event = event or {}
    blob = f"{result_text}\n{stderr}\n{json.dumps(event)}"
    if _SIGNED_OUT.search(blob):
        return "Claude is signed out. Open the Claude app, sign in, then try again."
    if _LIMIT.search(blob):
        return ("Claude's usage limit has been reached for now, so the brief stopped part-way. Try again once it "
                "resets (the Claude app shows when).")
    denials = event.get("permission_denials") or []
    if denials:
        d = denials[0] if isinstance(denials[0], dict) else {}
        inp = d.get("tool_input") or {}
        what = inp.get("file_path") or inp.get("command") or ""
        return (f"Claude wasn't allowed to use {d.get('tool_name', 'a tool')}{' on ' + what if what else ''}, so the "
                "brief stopped. Run Install Network Focus again to refresh the page's settings, then click Generate.")
    if event.get("subtype") == "error_max_turns":
        return "The brief took too many steps and stopped. Click Generate to try again."
    return result_text.strip() or GENERIC
