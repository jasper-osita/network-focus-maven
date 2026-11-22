#!/usr/bin/env bash
# Network Focus installer for macOS. Installs or updates everything, then opens the CEO dashboard.
#   Double-click "Install Network Focus.command", or paste into Terminal:
#   curl -fsSL https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.sh | bash
#   Uninstall (keeps your briefs):  bash install.sh --uninstall
set -uo pipefail

REPO="jasper-osita/network-focus-maven"
PLUGIN_ID="network-focus@network-focus"
MARKETPLACE="network-focus"
LABEL="com.networkfocus.app"
TEST_MODE="${NF_INSTALL_TEST:-}"

LOG_DIR="$HOME/Library/Logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/NetworkFocus-install.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== Network Focus installer · $(date) ==="

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  ✓ %s\n' "$*"; }
fail() {
  printf '\n  ✗ %s\n' "$1"
  [ -n "${2:-}" ] && printf '    What to do: %s\n' "$2"
  printf '    (Details are saved in %s)\n\n' "$LOG"
  exit 1
}
py() { uv run --quiet --no-project python -c "$@"; }  # uv brings its own Python; macOS's python3 may not exist

if [ "$(uname)" != "Darwin" ] && [ -z "$TEST_MODE" ]; then
  fail "Network Focus installs on a Mac." "Run this on the Mac the chief of staff uses."
fi

# ---------------------------------------------------------------- uninstall
if [ "${1:-}" = "--uninstall" ]; then
  step "Removing Network Focus (your briefs in Documents › Network Focus are kept)…"
  if [ -z "$TEST_MODE" ]; then
    launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  fi
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist" "$HOME/Desktop/Network Focus.webloc"
  rm -rf "$HOME/Library/Application Support/Network Focus"
  if command -v claude >/dev/null 2>&1; then
    claude plugin uninstall "$PLUGIN_ID" >/dev/null 2>&1 || true
  fi
  ok "Removed the page, the Desktop link and the plugin."
  ok "Your folder Documents › Network Focus is still there."
  exit 0
fi

echo
echo "Installing Network Focus. This takes a few minutes; you'll only need to sign in to Claude."

# ---------------------------------------------------------------- 1. helpers
step "1/5  Checking the helper programs…"
if command -v uv >/dev/null 2>&1; then
  ok "uv is already installed."
else
  echo "  Installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh || fail "Couldn't install uv." "Check the internet connection and run the installer again."
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || fail "uv didn't install." "Run the installer again; if it repeats, send the log to whoever set this up."
  ok "Installed uv."
fi
if command -v claude >/dev/null 2>&1; then
  ok "Claude Code is already installed."
else
  echo "  Installing Claude Code…"
  curl -fsSL https://claude.ai/install.sh | bash || fail "Couldn't install Claude Code." "Check the internet connection and run the installer again."
  export PATH="$HOME/.local/bin:$PATH"
  command -v claude >/dev/null 2>&1 || fail "Claude Code didn't install." "Run the installer again; if it repeats, send the log to whoever set this up."
  ok "Installed Claude Code."
fi

# ---------------------------------------------------------------- 2. sign in
step "2/5  Checking you're signed in to Claude…"
signed_in() { claude auth status --json 2>/dev/null | grep -q '"loggedIn": *true'; }
if signed_in; then
  ok "Already signed in."
else
  echo "  Your browser will open. Sign in to Claude there, then come back to this window."
  # When run as `curl … | bash`, stdin is the script itself, so sign-in must read from the terminal.
  if [ -r /dev/tty ] && [ -z "$TEST_MODE" ]; then claude auth login </dev/tty || true; else claude auth login || true; fi
  signed_in || fail "You're not signed in to Claude yet." "Run the installer again and finish signing in when the browser opens."
  ok "Signed in."
fi

# ---------------------------------------------------------------- 3. plugin
step "3/5  Installing the Network Focus plugin…"
if claude plugin marketplace list --json 2>/dev/null | grep -q "\"$MARKETPLACE\""; then
  claude plugin marketplace update "$MARKETPLACE" >/dev/null || fail "Couldn't refresh Network Focus from GitHub." "Check the internet connection and run the installer again."
else
  claude plugin marketplace add "$REPO" >/dev/null || fail "Couldn't reach Network Focus on GitHub." "Check the internet connection and run the installer again."
fi
if claude plugin list --json 2>/dev/null | grep -q "\"$PLUGIN_ID\""; then
  claude plugin update "$PLUGIN_ID" >/dev/null || fail "Couldn't update the plugin." "Run the installer again."
  ok "Updated the plugin."
else
  claude plugin install "$PLUGIN_ID" >/dev/null || fail "Couldn't install the plugin." "Run the installer again."
  ok "Installed the plugin."
fi
PLUGIN_DIR="$(claude plugin list --json 2>/dev/null | py '
import json, sys
print(next((p["installPath"] for p in json.load(sys.stdin) if p.get("id") == "'"$PLUGIN_ID"'"), ""))')"
[ -n "$PLUGIN_DIR" ] && [ -f "$PLUGIN_DIR/app/install_app.py" ] || fail "Couldn't find the installed plugin." "Run the installer again."

# ---------------------------------------------------------------- 4. page
step "4/5  Setting up the Network Focus page and your folder…"
EXTRA=""
[ -n "$TEST_MODE" ] && EXTRA="--no-launch"
RESULT="$(uv run --quiet "$PLUGIN_DIR/app/install_app.py" $EXTRA)" || fail "Couldn't set up the page." "Run the installer again; if it repeats, send the log to whoever set this up."
URL="$(printf '%s' "$RESULT" | tail -n 1 | py 'import json, sys; print(json.load(sys.stdin).get("url", ""))')"
printf '%s' "$RESULT" | tail -n 1 | py '
import json, sys
for w in json.load(sys.stdin).get("warnings", []):
    print("  ! " + w)'
ok "Folder: Documents › Network Focus"
if printf '%s' "$RESULT" | tail -n 1 | py 'import json, sys; sys.exit(0 if json.load(sys.stdin).get("roster_folder") else 1)'; then
  ok "Roster folder: Google Drive › My Drive › Network Focus"
fi
ok "Desktop link: Network Focus"

# ---------------------------------------------------------------- 5. open
step "5/5  Opening the dashboard…"
if [ -z "$TEST_MODE" ] && [ -n "$URL" ]; then
  open "$URL" || true
fi
ok "Done. Network Focus is installed."
echo
echo "Every Monday: double-click Network Focus on the Desktop, drop in this week's spreadsheet"
echo "on the 'Make the brief' tab, and click Generate. The dashboard shows the CEO's #1 for the week."
exit 0
