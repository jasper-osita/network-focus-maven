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


def test_failure_message_usage_limit():
    ev = {"type": "result", "subtype": "error_during_execution", "is_error": True}
    assert "usage limit" in failure_message("", 'API Error: 429 {"type":"rate_limit_error"}', ev)
    assert "usage limit" in failure_message("Claude AI usage limit reached|1764000000", "", {})


def test_failure_message_permission_denied():
    ev = {"subtype": "success", "result": "", "permission_denials": [
        {"tool_name": "Write", "tool_input": {"file_path": "/Users/x/Documents/Network Focus/.work/brief.json"}}]}
    msg = failure_message("", "", ev)
    assert "wasn't allowed" in msg and "Write" in msg and "Install Network Focus" in msg


def test_failure_message_max_turns():
    assert "too many steps" in failure_message("", "", {"subtype": "error_max_turns"})


def test_failure_message_keeps_skill_explanation():
    text = "I couldn't make a brief I'm confident in this week: the quotes didn't match."
    assert failure_message(text, "", {"subtype": "success"}) == text


def test_update_step_names():
    assert progress_from_event(tool_event("Bash", command='uv run "/x/scripts/update_prep.py" --work W')) == "Looking at who's new"
    assert progress_from_event(tool_event("Bash", command='uv run "/x/scripts/apply_update.py" --work W')) == "Placing new people"
