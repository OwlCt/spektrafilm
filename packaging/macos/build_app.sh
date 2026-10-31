#!/bin/bash
# Build a double-clickable Spektrafilm.app for the Mac this script runs on.
#
# The GUI stack is installed into a relocatable conda prefix (micromamba),
# then wrapped as an ad-hoc signed .app. conda-forge supplies the native
# packages that have no current Intel PyPI wheel (numba 0.64 / llvmlite and
# rawpy 0.26). Everything else comes from pip, matching pyproject.toml.
#
# The prefix is created at a long path so conda-unpack can later rewrite it
# to a normal user path (the new path must be no longer than the build path).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

log() {
  printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

disk() {
  df -h / | awk 'NR==1 || NR==2'
}

ARCH="$(uname -m)"
case "$ARCH" in
  arm64)
    MAMBA_ARCH="osx-arm64"
    CONDA_SUBDIR="osx-arm64"
    ;;
  x86_64)
    MAMBA_ARCH="osx-64"
    CONDA_SUBDIR="osx-64"
    ;;
  *)
    echo "unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -n 1)"
if [[ -z "$VERSION" ]]; then
  echo "could not read version from pyproject.toml" >&2
  exit 1
fi

WORK="$ROOT/dist/work"
APP="$ROOT/dist/Spektrafilm.app"
TAR="$WORK/env.tar.gz"
PAD="$(printf 'p%.0s' {1..150})"
ENV="$WORK/$PAD/env"
MAMBA_ROOT="$WORK/mamba-root"
MM="$WORK/micromamba"

log "building Spektrafilm $VERSION for $ARCH"
disk

mkdir -p "$WORK" "$APP/Contents/MacOS" "$APP/Contents/Resources"

log "compiling app launcher"
clang -O2 -Wall -Wextra -o "$APP/Contents/MacOS/spektrafilm" packaging/macos/launcher.c

log "freeing disk (Xcode and simulators) before installing scientific wheels"
sudo rm -rf /Applications/Xcode_*.app /Applications/Xcode.app /Library/Developer/CoreSimulator || true
rm -rf "$HOME/Library/Developer/Xcode/DerivedData" || true
disk

if [[ ! -x "$MM" ]]; then
  log "downloading micromamba ($MAMBA_ARCH)"
  curl -fL --retry 5 --retry-delay 2 \
    -o "$MM" \
    "https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-${MAMBA_ARCH}"
  chmod +x "$MM"
fi

export MAMBA_ROOT_PREFIX="$MAMBA_ROOT"
export CONDA_SUBDIR="$CONDA_SUBDIR"
export MAMBA_NO_BANNER=1

log "creating Python 3.13 prefix (path length ${#ENV})"
rm -rf "$ENV"
"$MM" create -y -p "$ENV" -c conda-forge --override-channels --channel-priority strict \
  "python=3.13" \
  pip \
  setuptools \
  wheel \
  "numpy>=2.4,<2.5" \
  "scipy>=1.17,<1.18" \
  "numba>=0.64,<0.65" \
  "scikit-image>=0.26,<0.27" \
  "matplotlib-base>=3.10,<3.11" \
  "pillow>=12.1,<12.2" \
  "rawpy>=0.26.1,<0.27" \
  ca-certificates \
  certifi

PY="$ENV/bin/python"
log "conda prefix ready: $("$PY" -c 'import sys, numpy, numba, scipy, rawpy; print(sys.version); print("numpy", numpy.__version__, "numba", numba.__version__, "scipy", scipy.__version__, "rawpy", rawpy.__version__)')"

log "checking conda-managed native packages before pip"
"$PY" - << 'PY'
import importlib.metadata as md
required = ("numpy", "scipy", "numba", "llvmlite", "rawpy", "scikit-image")
missing = []
for name in required:
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        missing.append(name)
        continue
    print(f"{dist.metadata['Name']}=={dist.version}")
if missing:
    raise SystemExit("conda prefix is missing distributions: " + ", ".join(missing))
PY

log "writing pip constraints for conda-managed native packages"
"$PY" - "$WORK/constraints.txt" << 'PY'
import importlib.metadata as md
import sys

names = [
    "numpy",
    "scipy",
    "numba",
    "llvmlite",
    "scikit-image",
    "rawpy",
    "pillow",
    "matplotlib",
]
lines = []
for name in names:
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        print(f"constraint skip {name}", file=sys.stderr)
        continue
    lines.append(f"{dist.metadata['Name']}=={dist.version}")
path = sys.argv[1]
with open(path, "w", encoding="utf-8") as handle:
    handle.write("\n".join(lines) + "\n")
print("\n".join(lines))
PY

log "pip installing the project and the remaining wheels"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install --no-cache-dir -c "$WORK/constraints.txt" "$ROOT"
"$PY" -m pip install --no-cache-dir conda-pack

log "pruning PySide6 modules the GUI does not import"
"$PY" - << 'PY'
import os
import pathlib
import shutil

import PySide6

root = pathlib.Path(PySide6.__file__).resolve().parent
needles = (
    "QtWebEngine",
    "QtWebView",
    "QtPdf",
    "Qt3D",
    "QtQuick3D",
    "QtMultimedia",
    "QtSpatialAudio",
    "QtTextToSpeech",
    "QtVirtualKeyboard",
    "QtRemoteObjects",
    "QtScxml",
    "QtSensors",
    "QtSerialPort",
    "QtBluetooth",
    "QtNfc",
    "QtPositioning",
    "QtLocation",
    "QtCharts",
    "QtDataVisualization",
    "QtGraphs",
    "QtHttpServer",
    "QtWebChannel",
    "QtWebSockets",
    "QtDesigner",
)
removed = []
for dirpath, dirnames, filenames in os.walk(root, topdown=False):
    for name in filenames + dirnames:
        if not any(needle in name for needle in needles):
            continue
        path = pathlib.Path(dirpath) / name
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
            removed.append(str(path))
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(str(path))
print(f"removed {len(removed)} PySide6 paths")
PY

log "dropping large test suites that are not needed at runtime"
rm -rf \
  "$ENV/lib/python3.13/site-packages/pandas/tests" \
  "$ENV/lib/python3.13/site-packages/dask/tests" \
  || true

log "in-place import smoke (before packing)"
export QT_API=pyside6
export QT_QPA_PLATFORM=offscreen
export MPLBACKEND=Agg
export NUMBA_NUM_THREADS=1
export PYTHONNOUSERSITE=1
export PYTHONUNBUFFERED=1
perl -e 'alarm shift; exec @ARGV' 1200 "$PY" packaging/macos/smoke_check.py

log "packing prefix"
# Keep the micromamba package cache until pack finishes. conda-pack reads
# has_prefix metadata from that cache; pip packages (including the pruned
# PySide6 tree) are copied from the prefix itself.
"$PY" "$ENV/bin/conda-pack" -p "$ENV" -o "$TAR" --ignore-missing-files --compress-level 1 -j 3 --force
ls -lh "$TAR"

log "removing build prefix"
rm -rf "$ENV" "$MAMBA_ROOT"
disk

log "assembling Spektrafilm.app"
rm -rf "$APP/Contents/Resources/python"
mkdir -p "$APP/Contents/Resources/python"
tar -xzf "$TAR" -C "$APP/Contents/Resources/python"
cp packaging/macos/launch.sh "$APP/Contents/Resources/launch.sh"
cp packaging/macos/smoke_check.py "$APP/Contents/Resources/smoke_check.py"
cp packaging/macos/relocate_prefix.py "$APP/Contents/Resources/relocate_prefix.py"
cp packaging/macos/codesign_bundle.sh "$APP/Contents/Resources/codesign_bundle.sh"
chmod +x "$APP/Contents/Resources/launch.sh" "$APP/Contents/Resources/codesign_bundle.sh" "$APP/Contents/MacOS/spektrafilm"

cat > "$APP/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>spektrafilm</string>
  <key>CFBundleIdentifier</key>
  <string>org.spektrafilm.desktop</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Spektrafilm</string>
  <key>CFBundleDisplayName</key>
  <string>Spektrafilm</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>${VERSION}</string>
  <key>CFBundleVersion</key>
  <string>${VERSION}</string>
  <key>CFBundleSignature</key>
  <string>????</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>LSApplicationCategoryType</key>
  <string>public.app-category.photography</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSRequiresAquaSystemAppearance</key>
  <false/>
  <key>NSHumanReadableCopyright</key>
  <string>spektrafilm is licensed under GPLv3</string>
</dict>
</plist>
PLIST

log "relocated-app smoke (conda-unpack + bundled executable)"
rm -f "$APP/Contents/Resources/installed-prefix.txt"
perl -e 'alarm shift; exec @ARGV' 2400 "$APP/Contents/MacOS/spektrafilm" --smoke

log "restoring the packed prefix so the download relocates on the user's Mac"
rm -rf "$APP/Contents/Resources/python"
mkdir -p "$APP/Contents/Resources/python"
tar -xzf "$TAR" -C "$APP/Contents/Resources/python"
rm -f "$APP/Contents/Resources/installed-prefix.txt"
rm -rf "$TAR" "$WORK/constraints.txt"

log "ad-hoc signing the downloadable bundle"
/bin/bash packaging/macos/codesign_bundle.sh "$APP"

log "bundle size"
du -sh "$APP"
disk
file "$APP/Contents/MacOS/spektrafilm" "$APP/Contents/Resources/python/bin/python"
log "Spektrafilm.app ready at $APP"
