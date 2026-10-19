#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ARCH="${1:-AppleSilicon}"
mkdir -p "$ROOT/release"
hdiutil create -volname "Studio Sync" -srcfolder "$ROOT/dist/Studio Sync.app" -ov -format UDZO "$ROOT/release/StudioSync-macOS-${ARCH}.dmg"
