# Spike findings (Task 0) — 2026-11-21, Claude Code 2.1.330, Linux container

Throwaway plugin `spike` (skill `hello`, agent `echo`, script `probe.py`) run headless. Result: success, 13 s, ~$0.20.

| Question | Finding |
|---|---|
| AGENT_TOOL | Stream shows tool_use name **`Agent`**; the init event's tool list names it `Task`. **Allow both** in `allowed-tools` / `--allowedTools`. |
| Plugin agent subagent_type | **`<plugin>:<agent>`**, e.g. `spike:echo` → we use `network-focus:goal-scout`, `network-focus:fact-checker`. |
| Parallel dispatch | Two `Agent` tool_use blocks in **one** assistant message → ran in parallel. Works from a plugin skill. |
| `${CLAUDE_PLUGIN_ROOT}` in SKILL.md | **Substituted** with the absolute plugin path. `${CLAUDE_SKILL_DIR}` also substituted. |
| `uv run` + PEP 723 inline deps | **Works**: `openpyxl 3.1.5` installed on the fly. (uv prints a harmless `UV_NATIVE_TLS` deprecation warning in this container only.) |
| HEADLESS_FLAGS | `--output-format stream-json --verbose --permission-mode dontAsk --allowedTools "Read,Write,Bash(uv run *),Agent,Task" < /dev/null` (stdin redirect avoids a 3 s wait warning). For JSON result only: `--output-format json`. |
| Slash command name | `/spike:hello` → ours is `/network-focus:brief`. Init event lists it under `slash_commands`. |

## Event shapes (stream-json)
- init: `{"type":"system","subtype":"init","plugins":[{name,path,source,version}],"plugin_errors":null,"slash_commands":[...],"agents":[...]}`
- Bash call: `{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"uv run \".../scripts/probe.py\" banana","description":"..."}}]}}`
- Agent call: `{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Agent","input":{"description":"Echo number 1","subagent_type":"spike:echo","prompt":"1"}}]}}`
- Tool result: `{"type":"user","message":{"content":[{"type":"tool_result","content":"...","is_error":false}]}}`
- Final: `{"type":"result","subtype":"success","is_error":false,"result":"<final text>","duration_ms":13010,"total_cost_usd":0.198}`

## Not testable here (Mac only, Task 14)
§11 risks 4–8: adding a marketplace from the desktop chat box, desktop app finding `uv`, permission prompts in Manual mode, `claude -p` on a subscription login, LaunchAgent PATH.
