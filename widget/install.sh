#!/bin/bash
# One-time setup of the PSA10 menu bar widget. Safe to run again (e.g. after moving the repo).
#   bash "<repo>/widget/install.sh"
set -eu
WIDGET_DIR="$(cd "$(dirname "$0")" && pwd -P)"
REPO="$(cd "$WIDGET_DIR/.." && pwd -P)"
P="$HOME/.psa10"
mkdir -p "$P/state"
ok() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
todo() { printf '  \033[33m→\033[0m %s\n' "$1"; }

echo "PSA10 widget setup (repo: $REPO)"

# 1. Space-free path to the widget scripts (SwiftBar's bash= parameter can't take spaces).
ln -sfn "$WIDGET_DIR" "$P/widget"
chmod +x "$WIDGET_DIR"/*.sh
ok "~/.psa10/widget -> $WIDGET_DIR"

# 2. The procedures' commands find the repo with  ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker
#    (the desktop app's mount point). The same link on the Mac lets Claude Code run them verbatim.
mkdir -p "$HOME/mnt"
ln -sfn "$REPO" "$HOME/mnt/psa10-tracker"
ok "~/mnt/psa10-tracker -> repo (so the procedures' commands work unchanged)"

# 3. Claude Code project config: the remote tools can't write .claude/, so it lives in widget/claude/
#    and is linked in here (a git pull keeps it current).
mkdir -p "$REPO/.claude"
ln -sfn ../widget/claude/skills "$REPO/.claude/skills"
ln -sfn ../widget/claude/settings.json "$REPO/.claude/settings.json"
ok ".claude/skills and .claude/settings.json -> widget/claude/"

# 4. PATH and claude from your login shell (SwiftBar and Terminal scripts start with a bare PATH).
LOGIN_PATH=$("${SHELL:-/bin/zsh}" -lic 'printf %s "$PATH"' 2>/dev/null | tail -1 || true)
CLAUDE=$("${SHELL:-/bin/zsh}" -lic 'command -v claude' 2>/dev/null | tail -1 || true)
for c in "$CLAUDE" "$HOME/.local/bin/claude" "$HOME/.claude/local/claude" /opt/homebrew/bin/claude /usr/local/bin/claude "$HOME/.homebrew/bin/claude"; do
  if [ -n "$c" ] && [ -x "$c" ]; then CLAUDE="$c"; break; fi; CLAUDE=""
done
{
  echo "export PATH=\"${LOGIN_PATH:-/usr/bin:/bin}:\$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin\""
  echo "CLAUDE_BIN=\"${CLAUDE:-claude}\""
} > "$P/env"
if [ -n "$CLAUDE" ]; then
  ok "Claude Code: $CLAUDE ($("$CLAUDE" --version 2>/dev/null | head -1))"
else
  todo "Claude Code not found. Install it:  curl -fsSL https://claude.ai/install.sh | bash   then run this again."
fi

# 5. SwiftBar plugin stub.
if [ -d /Applications/SwiftBar.app ] || [ -d "$HOME/Applications/SwiftBar.app" ]; then
  PLUGDIR=$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null || true)
  if [ -z "$PLUGDIR" ]; then
    PLUGDIR="$P/swiftbar-plugins"
    mkdir -p "$PLUGDIR"
    defaults write com.ameba.SwiftBar PluginDirectory "$PLUGDIR"
  fi
  PLUGDIR="${PLUGDIR/#\~/$HOME}"
  mkdir -p "$PLUGDIR"
  cp "$WIDGET_DIR/swiftbar-plugin.1m.sh" "$PLUGDIR/psa10.1m.sh"
  chmod +x "$PLUGDIR/psa10.1m.sh"
  ok "SwiftBar plugin installed in $PLUGDIR"
  open -g "swiftbar://refreshallplugins" 2>/dev/null || open -a SwiftBar
else
  todo "SwiftBar not installed:  brew install --cask swiftbar   (or swiftbar.app), then run this again."
fi

echo
echo "Remaining one-time steps (see widget/README.md):"
echo "  • claude, then /login with your claude.ai account (Chrome needs it), then /chrome → Enabled check."
echo "  • In Chrome: Claude extension installed and signed in; sign in to psacard.com once."
echo "  • First run: allow SwiftBar to control Terminal, and Terminal/SwiftBar to access Documents, when macOS asks."
