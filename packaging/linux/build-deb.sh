#!/usr/bin/env bash
set -euo pipefail
VERSION="${1:-0.2.0}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PKG="$ROOT/build/deb/studio-sync_${VERSION}_amd64"
rm -rf "$PKG"
install -Dm755 "$ROOT/dist/StudioSync" "$PKG/opt/studio-sync/StudioSync"
install -Dm644 "$ROOT/packaging/linux/studio-sync.desktop" "$PKG/usr/share/applications/studio-sync.desktop"
mkdir -p "$PKG/DEBIAN" "$ROOT/release"
sed "s/@VERSION@/$VERSION/g" "$ROOT/packaging/linux/control" > "$PKG/DEBIAN/control"
dpkg-deb --build "$PKG" "$ROOT/release/StudioSync-Linux-amd64.deb"
