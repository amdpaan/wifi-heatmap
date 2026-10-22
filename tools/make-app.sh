#!/bin/sh
# Builds "Wi-Fi Heatmap.app" (opens the dashboard) with the antenna-bot icon into the given folder.
# Usage: tools/make-app.sh <destination folder, e.g. ~/Applications>
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$1"
NAME="Wi-Fi Heatmap"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
APP="$TMP/$NAME.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# An explicit deployment target: swiftc's default can be newer than the running macOS, and then
# Finder/Dock refuse to launch the app (error -10825) even though the binary runs fine.
swiftc -O -target "$(uname -m)-apple-macos14.0" -o "$APP/Contents/MacOS/wifi-heatmap-app" "$REPO/app/main.swift"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>com.wifiheatmap.app</string>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleExecutable</key><string>wifi-heatmap-app</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

/usr/bin/python3 "$REPO/tools/icon.py" "$TMP/icon.png"
SET="$TMP/AppIcon.iconset"
mkdir "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$TMP/icon.png" --out "$SET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z $d $d "$TMP/icon.png" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o "$APP/Contents/Resources/AppIcon.icns"

codesign --force --sign - "$APP" >/dev/null 2>&1 || true

mkdir -p "$DEST"
rm -rf "$DEST/$NAME.app"
cp -R "$APP" "$DEST/"
# Tell Finder/Launchpad/Spotlight about it (and refresh the icon on updates).
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$DEST/$NAME.app" 2>/dev/null || true
touch "$DEST/$NAME.app"
echo "$DEST/$NAME.app"
