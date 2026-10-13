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

# 1. Space-free path to the widget scripts (the menu bar app and Terminal commands use it).
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

# 4. PATH and claude from your login shell (the menu bar app and Terminal scripts start with a bare PATH).
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

# 5. The menu bar app (PSA10Bar), built here from widget/app/PSA10Bar.swift.
if ! xcrun --find swiftc >/dev/null 2>&1; then
  todo "Swift compiler missing. Run:  xcode-select --install   (Command Line Tools), then run this again."
else
  APP="$P/PSA10Bar.app"
  mkdir -p "$APP/Contents/MacOS"
  cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>com.psa10.bar</string>
  <key>CFBundleName</key><string>PSA10Bar</string>
  <key>CFBundleExecutable</key><string>PSA10Bar</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSAppleEventsUsageDescription</key><string>Opens a Terminal window to run the price check.</string>
  <key>NSDocumentsFolderUsageDescription</key><string>Reads the psa10-tracker repo to show the last snapshot.</string>
</dict></plist>
PLIST
  echo "  … building PSA10Bar (takes ~30 s the first time)"
  if xcrun swiftc -O -o "$APP/Contents/MacOS/PSA10Bar" "$WIDGET_DIR/app/PSA10Bar.swift" 2> "$P/state/build.log"; then
    codesign --force --sign - "$APP" >/dev/null 2>&1 || true
    ok "PSA10Bar built: $APP"
    AGENT="$HOME/Library/LaunchAgents/com.psa10.bar.plist"
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.psa10.bar</string>
  <key>ProgramArguments</key><array><string>$APP/Contents/MacOS/PSA10Bar</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ProcessType</key><string>Interactive</string>
</dict></plist>
PLIST
    launchctl bootout "gui/$(id -u)/com.psa10.bar" 2>/dev/null || true
    pkill -x PSA10Bar 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$AGENT"
    ok "PSA10Bar running, and starts at login (Quit in its bubble stops it until next login)"
  else
    todo "Build failed; the compiler output is in ~/.psa10/state/build.log (send it to Claude)."
  fi
fi

# 6. Retire the SwiftBar plugin from the first version, if it's there.
PLUGDIR=$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null || true)
PLUGDIR="${PLUGDIR/#\~/$HOME}"
if [ -n "$PLUGDIR" ] && [ -f "$PLUGDIR/psa10.1m.sh" ]; then
  rm -f "$PLUGDIR/psa10.1m.sh"
  open -g "swiftbar://refreshallplugins" 2>/dev/null || true
  ok "old SwiftBar plugin removed (you can quit or uninstall SwiftBar if you don't use it otherwise)"
fi

echo
echo "Remaining one-time steps (see widget/README.md):"
echo "  • claude, then /login with your claude.ai account (Chrome needs it), then /chrome → Enabled check."
echo "  • In Chrome: Claude extension installed and signed in; sign in to psacard.com once."
echo "  • First click: allow PSA10Bar to access Documents and to control Terminal when macOS asks."
