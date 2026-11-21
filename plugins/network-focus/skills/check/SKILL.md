---
name: check
description: Check the Network Focus setup and explain in plain English how to fix anything wrong. Use when the brief fails, something seems broken, or she asks to check the setup.
allowed-tools: Bash(uv run *), Bash(/opt/homebrew/bin/uv run *), Bash(~/.local/bin/uv run *)
---

Run: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/check_setup.py"`

If `uv` isn't found, try `/opt/homebrew/bin/uv run` and then `~/.local/bin/uv run`.

Show her the output exactly as printed. Then, in one or two plain sentences, tell her what to do first, which is the fix under the first ❌ line. If every line is ✅ or ℹ️, tell her the setup looks fine.

If `uv` can't be found anywhere, tell her: "One small tool called uv isn't installed. The handoff guide's Install section shows the one line to set it up. Ask whoever set up Network Focus for you if you'd like a hand."
