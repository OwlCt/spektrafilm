#!/bin/bash
# Linux x86_64 bundle: PyInstaller onedir, tar.gz, and an AppImage.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

log "installing Qt/system libraries"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  libglib2.0-0 libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 \
  libdbus-1-3 libfontconfig1 libxcb1 libx11-6 libxext6 libxi6 \
  libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-xkb1 \
  libxcb-render0 libxcb-shape0 libxcb-xfixes0 libxcb-randr0 \
  libxcb-image0 libxcb-shm0 libxcb-sync1 libxcb-util1 \
  fonts-noto-cjk patchelf file

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
SVG_DIST="$("$ROOT/.venv/bin/python" -c 'import importlib.metadata as md
for name in ("napari-svg", "napari_svg"):
    try:
        print(md.distribution(name).metadata["Name"])
        break
    except md.PackageNotFoundError:
        continue
else:
    raise SystemExit("napari-svg is not installed")')"
"$ROOT/.venv/bin/pyinstaller" --noconfirm --clean --onedir --name Spektrafilm \
  --add-data "packaging/macos/smoke_check.py:." \
  --add-data "src/spektrafilm_gui/assets/app_icon.png:spektrafilm_gui/assets" \
  --collect-all spektrafilm \
  --collect-all spektrafilm_gui \
  --collect-all spektrafilm_lut_creator \
  --collect-all napari \
  --collect-all napari_builtins \
  --collect-all napari_svg \
  --collect-submodules napari_builtins \
  --collect-submodules napari_svg \
  --hidden-import napari_builtins \
  --hidden-import napari_builtins.io \
  --hidden-import napari_svg \
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
  --copy-metadata "$SVG_DIST" \
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

log "bundling xcb, EGL, and a CJK font into the app directory"
"$ROOT/.venv/bin/python" packaging/linux/bundle_runtime_libs.py dist/Spektrafilm
internal="$(find "$ROOT/dist/Spektrafilm" -name base_library.zip -printf '%h\n' -quit)"
if [[ -z "$internal" ]]; then
  internal="$ROOT/dist/Spektrafilm/_internal"
fi
font_dir="$internal/fonts"
mkdir -p "$font_dir"
font_file="$(find /usr/share/fonts -type f \( -iname 'NotoSansCJK-Regular.ttc' -o -iname 'NotoSansCJK-Regular.otf' -o -iname 'NotoSansCJKsc-Regular.otf' \) | head -n 1)"
if [[ -z "$font_file" ]]; then
  echo "Noto CJK font was not installed" >&2
  exit 1
fi
cp "$font_file" "$font_dir/"
cp packaging/linux/fonts.conf "$font_dir/fonts.conf"
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
FONTCONF="$(find "$HERE/usr/bin" -path '*/fonts/fonts.conf' -print -quit 2>/dev/null || true)"
if [ -n "$FONTCONF" ]; then
  export FONTCONFIG_FILE="$FONTCONF"
fi
QTLIB="$(find "$HERE/usr/bin" -name 'libQt6Core.so*' -print -quit 2>/dev/null || true)"
if [ -n "$QTLIB" ]; then
  export LD_LIBRARY_PATH="$(dirname "$QTLIB")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
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
