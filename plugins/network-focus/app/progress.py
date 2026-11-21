"""Turn Claude Code's stream-json events into progress steps the chief of staff understands."""
import re

_SIGNED_OUT = re.compile(r"/login|not logged in|log ?in again|authenticat|invalid api key|unauthori[sz]ed", re.I)


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
        elif name in ("Agent", "Task"):
            kind = inp.get("subagent_type", "")
            if kind.endswith("goal-scout"):
                desc = inp.get("description", "").strip()
                return f"Reviewing {desc}" if desc.lower().startswith("goal ") else f"Reviewing goal: {desc}".strip()
            if kind.endswith("fact-checker"):
                return "Fact-checking the picks"
    return None


def failure_message(result_text: str, stderr: str) -> str:
    if _SIGNED_OUT.search(f"{result_text}\n{stderr}"):
        return "Claude is signed out. Open the Claude app, sign in, then try again."
    return result_text.strip() or "Something went wrong making the brief. Click Check setup to see what to fix."
