#!/usr/bin/env bash
# Build a Linux AppImage and .deb from a PyInstaller one-folder build.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.1.0}"
ARCH="$(uname -m)"
DIST="$ROOT/dist"
APP_NAME="Airlift Audio"

python -m PyInstaller packaging/airlift.spec --noconfirm

APPDIR="$ROOT/build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/lib/airlift-audio" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -a "$DIST/$APP_NAME/." "$APPDIR/usr/lib/airlift-audio/"
ln -sf "../lib/airlift-audio/$APP_NAME" "$APPDIR/usr/bin/airlift-audio"
cp airlift/assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/airlift-audio.png"
cp airlift/assets/icon.png "$APPDIR/airlift-audio.png"
cp packaging/linux/airlift-audio.desktop "$APPDIR/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE=$(dirname "$(readlink -f "$0")")
exec "$HERE/usr/lib/airlift-audio/Airlift Audio" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="$ROOT/build/appimagetool"
if [ ! -x "$TOOL" ]; then
    curl -L --fail -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$TOOL"
fi
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" \
    "$DIST/Airlift-Audio-${VERSION}-${ARCH}.AppImage"

# ---------------------------------------------------------------- .deb
DEB="$ROOT/build/deb"
rm -rf "$DEB"
mkdir -p "$DEB/DEBIAN" "$DEB/opt/airlift-audio" "$DEB/usr/bin" \
         "$DEB/usr/share/applications" \
         "$DEB/usr/share/icons/hicolor/256x256/apps"
cp -a "$DIST/$APP_NAME/." "$DEB/opt/airlift-audio/"
ln -sf "/opt/airlift-audio/$APP_NAME" "$DEB/usr/bin/airlift-audio"
cp packaging/linux/airlift-audio.desktop "$DEB/usr/share/applications/"
cp airlift/assets/icon.png "$DEB/usr/share/icons/hicolor/256x256/apps/airlift-audio.png"
SIZE_KB="$(du -sk "$DEB/opt/airlift-audio" | cut -f1)"

cat > "$DEB/DEBIAN/control" <<EOF
Package: airlift-audio
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: amd64
Installed-Size: ${SIZE_KB}
Maintainer: Airlift Audio contributors
Description: Local AI restoration for lossy and codec-damaged music
 Apollo-based restoration with a Qt interface and batch processing.
EOF

dpkg-deb --build --root-owner-group "$DEB" \
    "$DIST/airlift-audio_${VERSION}_amd64.deb"
echo "built: $DIST/Airlift-Audio-${VERSION}-${ARCH}.AppImage and .deb"
