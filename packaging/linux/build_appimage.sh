#!/usr/bin/env bash
# Build a Linux AppImage and .deb from a PyInstaller one-folder build.
#
# CPU (default):  bash packaging/linux/build_appimage.sh
# CUDA variant:   VARIANT=cuda bash packaging/linux/build_appimage.sh
#                 (needs a CUDA torch wheel, e.g. ~/.venvs/airlift-dev)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.1.3}"
ARCH="$(uname -m)"
PYTHON="${PYTHON:-python}"
DIST="$ROOT/dist"

VARIANT="${VARIANT:-cpu}"
case "$VARIANT" in
    cpu)
        SPEC="packaging/airlift.spec"
        APP_NAME="Airlift Audio"
        PACKAGE="airlift-audio"
        BIN_NAME="airlift-audio"
        ICON_NAME="airlift-audio"
        OUT_SLUG="Airlift-Audio"
        INSTALL_DIR="airlift-audio"
        GATE_ARGS=()
        ;;
    cuda)
        SPEC="packaging/airlift-cuda.spec"
        APP_NAME="Airlift Audio CUDA"
        PACKAGE="airlift-audio-cuda"
        BIN_NAME="airlift-audio-cuda"
        ICON_NAME="airlift-audio-cuda"
        OUT_SLUG="Airlift-Audio-CUDA"
        INSTALL_DIR="airlift-audio-cuda"
        GATE_ARGS=(--allow-cuda)
        ;;
    *)
        echo "Unknown VARIANT='$VARIANT' (use cpu or cuda)" >&2
        exit 2
        ;;
esac

case "$ARCH" in
    x86_64) DEB_ARCH="amd64" ;;
    aarch64|arm64) DEB_ARCH="arm64" ;;
    *) DEB_ARCH="$ARCH" ;;
esac

"$PYTHON" packaging/check_release.py "${GATE_ARGS[@]}"
"$PYTHON" -m PyInstaller "$SPEC" --noconfirm

APPDIR="$ROOT/build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/lib/$INSTALL_DIR" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -a "$DIST/$APP_NAME/." "$APPDIR/usr/lib/$INSTALL_DIR/"
ln -sf "../lib/$INSTALL_DIR/$APP_NAME" "$APPDIR/usr/bin/$BIN_NAME"
cp airlift/assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/$ICON_NAME.png"
cp airlift/assets/icon.png "$APPDIR/$ICON_NAME.png"
cp packaging/linux/airlift-audio.desktop "$APPDIR/$ICON_NAME.desktop"
sed -i \
    -e "s/^Name=.*/Name=$APP_NAME/" \
    -e "s/^Exec=.*/Exec=$BIN_NAME %F/" \
    -e "s/^Icon=.*/Icon=$ICON_NAME/" \
    -e "s/^StartupWMClass=.*/StartupWMClass=$ICON_NAME/" \
    "$APPDIR/$ICON_NAME.desktop"

cat > "$APPDIR/AppRun" <<EOF
#!/bin/sh
HERE=\$(dirname "\$(readlink -f "\$0")")
exec "\$HERE/usr/lib/$INSTALL_DIR/$APP_NAME" "\$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="$ROOT/build/appimagetool"
if [ ! -x "$TOOL" ]; then
    curl -L --fail -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$TOOL"
fi
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" \
    "$DIST/${OUT_SLUG}-${VERSION}-${ARCH}.AppImage"

# ---------------------------------------------------------------- .deb
DEB="$ROOT/build/deb-$VARIANT"
rm -rf "$DEB"
mkdir -p "$DEB/DEBIAN" "$DEB/opt/$INSTALL_DIR" "$DEB/usr/bin" \
         "$DEB/usr/share/applications" \
         "$DEB/usr/share/icons/hicolor/256x256/apps"
cp -a "$DIST/$APP_NAME/." "$DEB/opt/$INSTALL_DIR/"
ln -sf "/opt/$INSTALL_DIR/$APP_NAME" "$DEB/usr/bin/$BIN_NAME"
cp "$APPDIR/$ICON_NAME.desktop" "$DEB/usr/share/applications/"
cp airlift/assets/icon.png "$DEB/usr/share/icons/hicolor/256x256/apps/$ICON_NAME.png"
SIZE_KB="$(du -sk "$DEB/opt/$INSTALL_DIR" | cut -f1)"

cat > "$DEB/DEBIAN/control" <<EOF
Package: ${PACKAGE}
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${DEB_ARCH}
Installed-Size: ${SIZE_KB}
Maintainer: Airlift Audio contributors
Description: Local AI restoration for lossy and codec-damaged music
 Apollo-based restoration with a Qt interface and batch processing.
EOF

dpkg-deb --build --root-owner-group "$DEB" \
    "$DIST/${PACKAGE}_${VERSION}_${DEB_ARCH}.deb"
echo "built: $DIST/${OUT_SLUG}-${VERSION}-${ARCH}.AppImage and ${PACKAGE}_${VERSION}_${DEB_ARCH}.deb"
