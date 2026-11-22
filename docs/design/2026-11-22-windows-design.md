# Windows support: design

**Status:** approved in conversation (option 1) · 2026-11-22

**Why.** Jasper doesn't know whether the chief of staff uses a Mac or a Windows PC. Network Focus has to install and run on both, using the same one-click approach.

**Goals**
- On Windows, double-clicking `Install Network Focus.cmd` does what the Mac installer does: helpers, Claude sign-in, plugin, page, Desktop shortcut, then opens the dashboard. `-Uninstall` keeps the briefs.
- On both systems, the brief, the dashboard and the setup check find her real Documents folder, including OneDrive-redirected Documents on Windows.
- Both systems are tested on real machines: GitHub Actions runs the unit tests on Ubuntu, macOS and Windows, and the installer tests on macOS (bash) and Windows (PowerShell).

**Non-goals:** code-signing, Linux desktops, WSL.

**Anti-goals:** a console window left open on Windows for the background page; a Windows change that breaks the Mac path, which has already been verified with a real run.

**Approach (Windows equivalents)**

| Mac | Windows |
|---|---|
| `install.sh` + `.command` | `install.ps1` (PowerShell 5.1 compatible) + `Install Network Focus.cmd` (runs with `-ExecutionPolicy Bypass`, falls back to the raw GitHub URL) |
| `~/Library/Application Support/Network Focus` | `%LOCALAPPDATA%\Network Focus` |
| LaunchAgent | a `Network Focus.vbs` in the user's Startup folder, which runs the server hidden. It's started straight away after install, and needs no admin rights. |
| `~/Desktop/Network Focus.webloc` | `Desktop\Network Focus.url` (`[InternetShortcut]`), in the real Desktop known folder |
| `~/Documents/Network Focus` | the Documents known folder (`SHGetKnownFolderPath`, OneDrive-aware) + `\Network Focus` |
| Helpers via curl | `irm https://astral.sh/uv/install.ps1 \| iex`, `irm https://claude.ai/install.ps1 \| iex`. If Git for Windows (which Claude Code's shell needs) is missing, `winget install Git.Git` |
| Log: `~/Library/Logs/NetworkFocus-install.log` | `%LOCALAPPDATA%\Network Focus\install.log` |

- **Background-run permissions on Windows** use cwd-relative and home-relative rules: `Read(./**)` (cwd = her folder), `Read(~/.claude/plugins/**)`, `Edit(./.work/**)`, and `Bash(uv run "<plugin>/scripts/*)`. The Mac keeps its verified absolute `//` rules. **This needs checking on the first signed-in Windows run.**
- **PDF fonts** add `C:/Windows/Fonts/msyh.ttc` (Chinese).
- **SmartScreen** may say "Windows protected your PC". The handoff covers it: **More info → Run anyway**, with a one-line PowerShell backup.
- **Deliverable:** `deliverables/Install Network Focus.zip` holds `Mac - Install Network Focus.command` and `Windows - Install Network Focus.cmd`.

**Left to the builder:** exact message wording, and the structure of the test stand-ins.
