#!/bin/sh
# Regenerates docs/screenshots from the demo (made-up campus and data only).
# Usage: tools/screenshots.sh
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$REPO/docs/screenshots"
PORT=8797
TMP="$(mktemp -d)"
"$REPO/bin/wifi-heatmap" serve --demo --no-open --port "$PORT" >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; rm -rf "$TMP"' EXIT
swiftc -O -target "$(uname -m)-apple-macos14.0" -o "$TMP/screenshot" "$REPO/tools/screenshot.swift"
sleep 1
URL="http://127.0.0.1:$PORT/"
MOODS='document.body.replaceChildren(); const row = document.createElement("div");
row.style.cssText = "display:flex;gap:36px;padding:28px 36px;background:var(--paper);width:max-content";
document.body.append(row);
[["great", 4], ["ok", 3], ["poor", 2], ["dead", 1], ["idle", 0]].forEach(([m, l]) => {
  const w = document.createElement("div"); w.style.cssText = "text-align:center;font:600 15px -apple-system;color:var(--muted)";
  const b = document.createElement("span"); b.id = "bot"; w.append(b); row.append(w);
  drawBot(); setBot(m, l, false); b.removeAttribute("id"); b.style.width = "96px";
  w.append(document.createTextNode({great: "great spot", ok: "ok", poor: "poor", dead: "dead zone", idle: "no data yet"}[m]));
})'

shot() { "$TMP/screenshot" "$URL" "$@"; }
shot 1200 900 "$TMP/dash-light.png" light
shot 1200 900 "$TMP/dash-dark.png" dark
shot 1200 760 "$TMP/detail.png" light "openDetail('cafeteria')"
shot 390 844 "$TMP/phone.png" dark
shot 760 230 "$TMP/moods.png" light "$MOODS"
mkdir -p "$OUT"
for f in dash-light dash-dark detail phone; do
  sips -s format jpeg -s formatOptions 82 "$TMP/$f.png" --out "$OUT/$f.jpg" >/dev/null
done
cp "$TMP/moods.png" "$OUT/moods.png"
ls -1 "$OUT"
