#!/bin/sh
# Builds "WiFi Heatmap Helper.app" (the CoreWLAN reader, helper/main.swift) into the data folder,
# or into the folder given.
#
# It's signed with a local self-signed certificate (created once in your login keychain). Ad-hoc
# signatures change with every build, so macOS would forget the Location approval each time; with a
# stable certificate it's kept across rebuilds. The certificate never leaves this Mac.
# WIFI_HEATMAP_ADHOC=1 signs ad-hoc instead (CI).
#
# Usage: tools/build-helper.sh [destination folder]
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-${WIFI_HEATMAP_HOME:-$HOME/Library/Application Support/wifi-heatmap}}"
NAME="WiFi Heatmap Helper"
ID="com.wifiheatmap.helper"
CERT="wifi-heatmap helper (local)"
KC="$HOME/Library/Keychains/login.keychain-db"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
APP="$TMP/$NAME.app"
mkdir -p "$APP/Contents/MacOS"

# An explicit deployment target: swiftc's default can be newer than the running macOS, and then
# `open` refuses to launch the app (error -10825) even though the binary runs fine.
swiftc -O -target "$(uname -m)-apple-macos14.0" -o "$APP/Contents/MacOS/wifi-heatmap-helper" "$REPO/helper/main.swift"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>$ID</string>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleExecutable</key><string>wifi-heatmap-helper</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
  <key>NSLocationWhenInUseUsageDescription</key><string>wifi-heatmap reads which access point (BSSID) you're connected to. Your location is never read or stored.</string>
  <key>NSLocationUsageDescription</key><string>wifi-heatmap reads which access point (BSSID) you're connected to. Your location is never read or stored.</string>
</dict></plist>
PLIST

if [ "${WIFI_HEATMAP_ADHOC:-}" = 1 ]; then
  codesign --force --sign - --identifier "$ID" "$APP" 2>/dev/null
else
  if ! security find-certificate -c "$CERT" "$KC" >/dev/null 2>&1; then
    echo "  Creating the local signing certificate \"$CERT\" in your login keychain"
    cat > "$TMP/cert.cnf" <<CNF
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = $CERT
[ext]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
CNF
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -config "$TMP/cert.cnf" \
      -keyout "$TMP/key.pem" -out "$TMP/cert.pem" 2>/dev/null
    PASS="$(openssl rand -hex 16)"
    openssl pkcs12 -export -inkey "$TMP/key.pem" -in "$TMP/cert.pem" -name "$CERT" \
      -passout "pass:$PASS" -out "$TMP/id.p12" 2>/dev/null
    security import "$TMP/id.p12" -k "$KC" -P "$PASS" -T /usr/bin/codesign >/dev/null
  fi
  codesign --force --sign "$CERT" --identifier "$ID" "$APP" 2>/dev/null
fi

mkdir -p "$DEST"
rm -rf "$DEST/$NAME.app"
cp -R "$APP" "$DEST/"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$DEST/$NAME.app" 2>/dev/null || true
echo "$DEST/$NAME.app"
