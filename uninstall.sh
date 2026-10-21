#!/bin/sh
# Removes the launchd agent and the command. Keeps your data (and the helper app in it) unless you pass
# --purge, which also deletes the local signing certificate from your login keychain.
set -u
UID_="$(id -u)"
SUPPORT="${WIFI_HEATMAP_HOME:-$HOME/Library/Application Support/wifi-heatmap}"
LABEL="com.wifiheatmap.serve"
CERT="wifi-heatmap helper (local)"
[ "${WIFI_HEATMAP_NO_LAUNCHCTL:-0}" = 1 ] || launchctl bootout "gui/$UID_/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist" "$HOME/.local/bin/wifi-heatmap"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$SUPPORT"
  security delete-certificate -c "$CERT" "$HOME/Library/Keychains/login.keychain-db" >/dev/null 2>&1 || true
  echo "Removed everything: your places, samples, map, the helper app and its signing certificate."
else
  echo "Uninstalled. Your data is still in: $SUPPORT  (run with --purge to delete it)"
fi
