# One-click installer: design

**Status:** approved in conversation · 2026-11-22

**Intent.** The chief of staff should install Network Focus by double-clicking one file, not by following setup steps.

**Goals**
- One click installs or updates everything: helpers, Claude sign-in check, plugin, page, Desktop link.
- It ends by opening the dashboard.
- Running it again repairs or updates. `--uninstall` removes the page and the Desktop link but keeps her briefs.

**Non-goals:** Apple code-signing (needs a paid developer account), Windows.

**Anti-goals:** asking her to type anything except signing in to Claude; leaving a half-installed state without saying what to do.

**Approaches**

| Option | Verdict |
|---|---|
| A. Double-clickable `.command` that runs `install.sh` | **Chosen**, with B as backup |
| B. One line pasted into Terminal (`curl … \| bash`) | Backup when macOS blocks A, since Gatekeeper doesn't block it |
| C. Claude installs it on her Mac via Remote Control | Not available: no Mac is connected to this session |
| D. Everything in a claude.ai artifact | Rejected for generation: can't read local files, run scripts or run sub-agents, and wouldn't be a Claude Code skill. Kept as a PRD next step for the CEO's read-only view. |

**Design**
- `install.sh` (repo root) runs five numbered steps with plain messages, logging to `~/Library/Logs/NetworkFocus-install.log`:
  1. **Helpers.** Install `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`) and Claude Code (`curl -fsSL https://claude.ai/install.sh | bash`) only if they're missing.
  2. **Sign-in.** If `claude auth status --json` doesn't show `"loggedIn": true`, run `claude auth login`, then re-check. If it still isn't signed in, stop with a message.
  3. **Plugin.** Add the marketplace `jasper-osita/network-focus-maven`, or update it if present. Install `network-focus@network-focus`, or update it if present.
  4. **Page.** Read `installPath` from `claude plugin list --json`, then run `uv run "<installPath>/app/install_app.py"`, which sets up the folder, LaunchAgent and Desktop link.
  5. **Open.** `open` the dashboard URL and print "Done", plus the Monday steps.
- `Install Network Focus.command` (repo root, plus a copy in `deliverables/`) runs the `install.sh` beside it, or downloads the latest from GitHub. It keeps the window open at the end.
- **Test mode** (`NF_INSTALL_TEST=1`) skips the macOS check, `launchctl` and `open`, so the script is tested on Linux with stand-in `claude` and `curl` programs.
- **Docs:**
  - HANDOFF's one-time setup becomes three lines: double-click, sign in, done. It keeps the Gatekeeper "Open Anyway" note and the one-line backup.
  - PRD gets a "next step" line for the artifact CEO view.
  - README and VIDEO-OUTLINE mention the installer.

**Left to the builder:** the exact wording of the messages.
