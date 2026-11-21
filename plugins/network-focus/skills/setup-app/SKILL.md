---
name: setup-app
description: Install, repair or update the Network Focus page on this Mac. It's a simple web page with one button that makes the weekly brief, opened from a link on the Desktop. Use when asked to set up the Network Focus page or app, or when the page won't open.
allowed-tools: Bash(uv run *), Bash(/opt/homebrew/bin/uv run *), Bash(~/.local/bin/uv run *)
---

Run exactly this, as a single command: `uv run "${CLAUDE_PLUGIN_ROOT}/app/install_app.py"`

If `uv` isn't found, try `/opt/homebrew/bin/uv run` and then `~/.local/bin/uv run`.

It prints one line of JSON. Don't show her the JSON. Instead:
- If `ok` is true, tell her: "The Network Focus page is set up. Double-click **Network Focus** on your Desktop to open it. It starts by itself whenever the Mac starts, and you can bookmark it." Then pass on each item in `warnings` in plain words.
- If `ok` is false, pass on the `message` in plain words.

Running this again is always safe. It repairs or updates the page, and the Desktop link keeps working.
