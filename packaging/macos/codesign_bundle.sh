#!/bin/bash
# Ad-hoc sign a Spektrafilm.app bundle. No Apple Developer ID.
# Hardened runtime is intentionally off so Numba's JIT can run.

set -euo pipefail

APP="${1:-}"
if [[ -z "$APP" || ! -d "$APP" ]]; then
  echo "usage: codesign_bundle.sh Spektrafilm.app" >&2
  exit 2
fi

# Quarantine and Finder metadata make codesign reject the bundle.
xattr -cr "$APP" 2>/dev/null || true

# --deep is deprecated for Developer ID bundles. For this ad-hoc bundle it
# re-signs nested Mach-O files in one pass, which matters because the prefix
# rewrite invalidates signatures on Apple Silicon.
codesign --force --sign - --timestamp=none --deep "$APP"
codesign --verify --verbose=2 "$APP"
echo "ad-hoc signature ok: $APP"
