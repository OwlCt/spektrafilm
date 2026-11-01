#!/bin/bash
# Linux x86_64 bundle: PyInstaller onedir, tar.gz, and an AppImage.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

log "installing Qt/system libraries"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  libglib2.0-0 libgl1 libegl1 libxkbcommon0 libdbus-1-3 libfontconfig1 \
  libxcb1 libx11-6 libxext6 libxi6 file

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${PATH}"

log "creating Python 3.13 environment"
uv python install 3.13
uv venv --python 3.13 "$ROOT/.venv"
uv pip install --python "$ROOT/.venv/bin/python" --upgrade pip
uv pip install --python "$ROOT/.venv/bin/python" --no-cache-dir "$ROOT" pyinstaller pillow

export QT_API=pyside6
export QT_QPA_PLATFORM=offscreen
export MPLBACKEND=Agg
export PYTHONNOUSERSITE=1

log "building PyInstaller onedir"
"$ROOT/.venv/bin/pyinstaller" --noconfirm --clean --onedir --name Spektrafilm \
  --add-data "packaging/macos/smoke_check.py:." \
  --add-data "src/spektrafilm_gui/assets/app_icon.png:spektrafilm_gui/assets" \
  --collect-all spektrafilm \
  --collect-all spektrafilm_gui \
  --collect-all spektrafilm_lut_creator \
  --collect-all napari \
  --collect-all vispy \
  --collect-all magicgui \
  --collect-all npe2 \
  --collect-all numba \
  --collect-all llvmlite \
  --collect-all colour \
  --collect-all OpenImageIO \
  --collect-all rawpy \
  --collect-all exiv2 \
  --collect-all lensfunpy \
  --collect-all pyfftw \
  --collect-all PySide6 \
  --collect-submodules scipy \
  --collect-submodules skimage \
  --copy-metadata napari \
  --copy-metadata numpy \
  --copy-metadata scipy \
  --copy-metadata numba \
  --copy-metadata PySide6 \
  --copy-metadata colour-science \
  --exclude-module tkinter \
  --exclude-module PySide6.QtWebEngine \
  --exclude-module PySide6.QtWebEngineCore \
  --exclude-module PySide6.QtWebEngineWidgets \
  --exclude-module PySide6.Qt3DCore \
  --exclude-module PySide6.Qt3DRender \
  --exclude-module PySide6.QtPdf \
  --exclude-module PySide6.QtPdfWidgets \
  packaging/linux/entry.py

log "removing unused Qt modules from the bundle"
find dist/Spektrafilm -iname '*WebEngine*' -prune -exec rm -rf {} + || true
find dist/Spektrafilm -iname '*Qt3D*' -prune -exec rm -rf {} + || true
find dist/Spektrafilm -iname '*QtPdf*' -prune -exec rm -rf {} + || true

cp packaging/linux/spektrafilm.desktop dist/Spektrafilm/spektrafilm.desktop
cp src/spektrafilm_gui/assets/app_icon.png dist/Spektrafilm/spektrafilm.png

log "offscreen smoke test"
SPEKTRAFILM_CONFIG_DIR="$(mktemp -d)" QT_QPA_PLATFORM=offscreen \
  ./dist/Spektrafilm/Spektrafilm --smoke

log "packing tar.gz"
tar -C dist -czf dist/Spektrafilm-linux-x86_64.tar.gz Spektrafilm
ls -lh dist/Spektrafilm-linux-x86_64.tar.gz

log "building AppImage"
rm -rf "$ROOT/.venv" "$ROOT/build"
APPDIR="$ROOT/dist/Spektrafilm.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -a dist/Spektrafilm/. "$APPDIR/usr/bin/"
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export QT_API="${QT_API:-pyside6}"
export PYTHONNOUSERSITE=1
export PATH="$HERE/usr/bin:$PATH"
exec "$HERE/usr/bin/Spektrafilm" "$@"
EOF
chmod +x "$APPDIR/AppRun"
cp packaging/linux/spektrafilm.desktop "$APPDIR/spektrafilm.desktop"
cp src/spektrafilm_gui/assets/app_icon.png "$APPDIR/spektrafilm.png"
cp src/spektrafilm_gui/assets/app_icon.png "$APPDIR/.DirIcon"

TOOL="$ROOT/dist/appimagetool-x86_64.AppImage"
curl -fL --retry 5 -o "$TOOL" \
  https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x "$TOOL"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$ROOT/dist/Spektrafilm-linux-x86_64.AppImage"
chmod +x "$ROOT/dist/Spektrafilm-linux-x86_64.AppImage"
ls -lh "$ROOT/dist/Spektrafilm-linux-x86_64.AppImage"

log "AppImage smoke test"
SPEKTRAFILM_CONFIG_DIR="$(mktemp -d)" QT_QPA_PLATFORM=offscreen APPIMAGE_EXTRACT_AND_RUN=1 \
  "$ROOT/dist/Spektrafilm-linux-x86_64.AppImage" --smoke
log "Linux bundle ready"
