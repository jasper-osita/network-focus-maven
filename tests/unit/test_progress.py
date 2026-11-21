from progress import failure_message, progress_from_event


def tool_event(name, **inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def test_progress_mapping():
    assert progress_from_event(tool_event("Bash", command='uv run "/x/scripts/load_roster.py" --roster ""')) == "Checking the data"
    assert progress_from_event(tool_event("Agent", subagent_type="network-focus:goal-scout",
                                          description="Scout goal 2 CTO hire")) == "Reviewing goal: Scout goal 2 CTO hire"
    assert progress_from_event(tool_event("Agent", subagent_type="network-focus:goal-scout",
                                          description="Goal 1: Raise Series C")) == "Reviewing Goal 1: Raise Series C"
    assert progress_from_event(tool_event("Task", subagent_type="network-focus:fact-checker",
                                          description="Fact-check")) == "Fact-checking the picks"
    assert progress_from_event(tool_event("Bash", command='uv run "/x/scripts/render_pdf.py" --work W')) == "Making the PDF"
    assert progress_from_event(tool_event("Read", file_path="/x/roster.json")) is None
    assert progress_from_event({"type": "system", "subtype": "init"}) is None
    assert progress_from_event({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}) is None


def test_failure_message_signed_out():
    assert "signed out" in failure_message("Invalid API key · Please run /login", "")
    assert "signed out" in failure_message("", "Error: not logged in")
    assert failure_message("There's no spreadsheet in the inbox.", "") == "There's no spreadsheet in the inbox."
    assert "Check setup" in failure_message("", "")
