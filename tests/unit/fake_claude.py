#!/usr/bin/env python3
"""Stands in for `claude -p` in server tests: prints canned stream-json and writes a PDF, like a real run."""
import json
import os
import sys
import time
from pathlib import Path

mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
home = Path(os.environ["NF_HOME"])
(home / ".fake-argv.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")


def emit(obj):
    print(json.dumps(obj), flush=True)
    time.sleep(0.05)


def tool(name, **inp):
    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})


emit({"type": "system", "subtype": "init", "plugins": [{"name": "network-focus"}]})
if mode == "hang":
    time.sleep(30)
if mode == "weird":
    print("[1, 2]", flush=True)
    print('"just a string"', flush=True)
if mode == "error":
    print('API Error: 429 {"type":"error","error":{"type":"rate_limit_error"}}', file=sys.stderr, flush=True)
    emit({"type": "result", "subtype": "error_during_execution", "is_error": True})
    sys.exit(1)
if mode == "signed_out":
    emit({"type": "result", "subtype": "error", "is_error": True, "result": "Invalid API key · Please run /login"})
    sys.exit(1)
tool("Bash", command='uv run "/p/scripts/load_roster.py" --roster ""')
if mode == "update":
    tool("Bash", command='uv run "/p/scripts/update_prep.py" --work "/w"')
    tool("Bash", command='uv run "/p/scripts/apply_update.py" --work "/w"')
    tool("Bash", command='uv run "/p/scripts/render_pdf.py" --work "/w"')
    (home / "briefs").mkdir(parents=True, exist_ok=True)
    (home / "briefs" / "2026-11-23-network-focus.pdf").write_bytes(b"%PDF-1.4 fake updated brief")
    emit({"type": "result", "subtype": "success", "is_error": False, "result": "Brief updated: ..."})
    sys.exit(0)
for i, g in enumerate(["Series C", "CTO hire", "AI safety"], 1):
    tool("Agent", subagent_type="network-focus:goal-scout", description=f"Scout goal {i} {g}", prompt="...")
tool("Agent", subagent_type="network-focus:fact-checker", description="Fact-check the brief", prompt="...")
if mode == "slow":
    time.sleep(2)
tool("Bash", command='uv run "/p/scripts/render_pdf.py" --work "/w"')
(home / "briefs").mkdir(parents=True, exist_ok=True)
(home / "briefs" / "2026-11-23-network-focus.pdf").write_bytes(b"%PDF-1.4 fake brief")
emit({"type": "result", "subtype": "success", "is_error": False, "result": "Brief ready: ..."})
