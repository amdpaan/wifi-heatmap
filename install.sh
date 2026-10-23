#!/bin/sh
# Installs the wifi-heatmap command for the current user, builds the Wi-Fi helper app and the
# "Wi-Fi Heatmap" app (opens the dashboard), and, with --agent, a launchd agent that keeps the dashboard
# running from login. Safe to re-run (also after `git pull`).
#
#   ./install.sh                # the command (~/.local/bin/wifi-heatmap), the helper app, ~/Applications/Wi-Fi Heatmap.app
#   ./install.sh --agent        # + start `wifi-heatmap serve` at login (127.0.0.1:8766, this Mac only)
#   ./install.sh --agent --lan  # ... and also reachable from your phone on the same Wi-Fi, with a private link
#                               #     (the dashboard's Phone button shows it as a QR code)
set -eu

REPO="$(cd "$(dirname "$0")" && pwd)"
SUPPORT="${WIFI_HEATMAP_HOME:-$HOME/Library/Application Support/wifi-heatmap}"
AGENTS="$HOME/Library/LaunchAgents"
LABEL="com.wifiheatmap.serve"
PLIST="$AGENTS/$LABEL.plist"
CLI="$REPO/bin/wifi-heatmap"
UID_="$(id -u)"

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }

APPS="$HOME/Applications"

AGENT=0
LAN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --agent) AGENT=1 ;;
    --lan) LAN=1 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done
[ "$LAN" = 0 ] || [ "$AGENT" = 1 ] || { echo "--lan goes with --agent: ./install.sh --agent --lan"; exit 1; }

[ -x /usr/bin/python3 ] && /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' \
  || { echo "Python 3.9+ not found. Install the Command Line Tools: xcode-select --install"; exit 1; }

mkdir -p "$HOME/.local/bin" "$SUPPORT/logs"
say "Linking wifi-heatmap into ~/.local/bin"
ln -sf "$CLI" "$HOME/.local/bin/wifi-heatmap"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "  Add ~/.local/bin to your PATH to run plain \`wifi-heatmap\`." ;; esac

if [ "${WIFI_HEATMAP_NO_HELPER:-0}" = 1 ]; then
  echo "  (WIFI_HEATMAP_NO_HELPER=1: not building the helper app)"
else
  command -v swiftc >/dev/null 2>&1 || { echo "swiftc not found. Install the Command Line Tools: xcode-select --install"; exit 1; }
  say "Building the Wi-Fi helper app"
  WIFI_HEATMAP_HOME="$SUPPORT" "$REPO/tools/build-helper.sh" >/dev/null
fi

if [ "${WIFI_HEATMAP_NO_APP:-0}" = 1 ]; then
  echo "  (WIFI_HEATMAP_NO_APP=1: not building Wi-Fi Heatmap.app)"
else
  say "Building Wi-Fi Heatmap.app in ~/Applications (opens the dashboard)"
  "$REPO/tools/make-app.sh" "$APPS" >/dev/null
fi

if [ "$AGENT" = 0 ]; then
  echo "Done. Next: \`wifi-heatmap now\` (allow Location when asked), then \`wifi-heatmap serve\`."
  exit 0
fi

if [ "$LAN" = 1 ]; then
  SERVE_ARGS="<string>--lan</string>"
  say "Writing $LABEL (dashboard from login, on this Mac and your phone on the same Wi-Fi)"
else
  SERVE_ARGS=""
  say "Writing $LABEL (dashboard on http://127.0.0.1:8766/ from login, this Mac only)"
fi
mkdir -p "$AGENTS"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$CLI</string><string>serve</string><string>--no-open</string>$SERVE_ARGS
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>ProcessType</key><string>Background</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>WIFI_HEATMAP_HOME</key><string>$SUPPORT</string>
  </dict>
  <key>StandardOutPath</key><string>$SUPPORT/logs/serve.log</string>
  <key>StandardErrorPath</key><string>$SUPPORT/logs/serve.log</string>
</dict></plist>
PLIST
plutil -lint "$PLIST" >/dev/null

if [ "${WIFI_HEATMAP_NO_LAUNCHCTL:-0}" = 1 ]; then
  echo "  (WIFI_HEATMAP_NO_LAUNCHCTL=1: not loading it)"
  exit 0
fi
# bootout returns before the old job has fully stopped; wait, then retry bootstrap.
launchctl bootout "gui/$UID_/$LABEL" 2>/dev/null || true
for _ in 1 2 3 4 5; do
  launchctl bootstrap "gui/$UID_" "$PLIST" 2>/dev/null && break
  sleep 1
done
launchctl print "gui/$UID_/$LABEL" >/dev/null 2>&1 || { echo "  Couldn't load the agent. Try: launchctl bootstrap gui/$UID_ \"$PLIST\""; exit 1; }
echo "Done. Dashboard: http://127.0.0.1:8766/ (or open Wi-Fi Heatmap from Launchpad)   Log: $SUPPORT/logs/serve.log"
[ "$LAN" = 0 ] || echo "  For your phone: press Phone on the dashboard and scan the QR code. macOS may ask once to allow incoming connections for python3: allow it."
