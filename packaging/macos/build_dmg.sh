#!/usr/bin/env bash
# Build a macOS .app + .dmg (run on macOS, arm64 or x86_64).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.1.4}"
ARCH="$(uname -m)"
DIST="$ROOT/dist"

# --- .icns from the generated PNG -------------------------------------------
ICONSET="$ROOT/build/icon.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" airlift/assets/icon_1024.png \
        --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    sips -z "$((size * 2))" "$((size * 2))" airlift/assets/icon_1024.png \
        --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o airlift/assets/icon.icns

python -m PyInstaller packaging/airlift.spec --noconfirm

APP="$DIST/Airlift Audio.app"
if [ ! -d "$APP" ]; then
    echo "error: $APP not found" >&2
    exit 1
fi

DMG="$DIST/Airlift-Audio-${VERSION}-macos-${ARCH}.dmg"
rm -f "$DMG"
hdiutil create -volname "Airlift Audio" -srcfolder "$APP" \
    -ov -format UDZO "$DMG"
echo "built: $DMG"
