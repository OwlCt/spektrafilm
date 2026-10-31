#!/bin/bash
# Spektrafilm.app startup. Relocates the bundled prefix on first launch
# (and after the app is moved to a shorter path), then starts the GUI.
# Pass --smoke, or set SPEKTRAFILM_SMOKE=1, to import the pipeline headless.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RES="$SCRIPT_DIR"
CONTENTS_DIR="$(cd "$RES/.." && pwd)"
APP_DIR="$(cd "$CONTENTS_DIR/.." && pwd)"
ENV="$RES/python"
PY="$ENV/bin/python"
PREFIX_FILE="$RES/installed-prefix.txt"

log() {
  printf 'spektrafilm: %s\n' "$*" >&2
}

if [[ ! -x "$PY" ]]; then
  log "bundled Python is missing ($PY)"
  exit 1
fi

if [[ ! -w "$ENV/bin" ]]; then
  log "the app is running from a read-only location."
  log "macOS App Translocation does this to quarantined downloads."
  log "Quit, move Spektrafilm.app to its final folder (for example /Applications),"
  log "then clear quarantine and open it again:"
  log "  xattr -cr \"$APP_DIR\""
  exit 1
fi

CURRENT="$(cd "$ENV" && pwd)"

if [[ ! -f "$PREFIX_FILE" ]]; then
  log "first launch: rewriting bundled library paths (this can take a few minutes)"
  if [[ -f "$ENV/bin/conda-unpack" ]]; then
    if ! "$PY" "$ENV/bin/conda-unpack"; then
      log "bundled Python could not run conda-unpack; trying /usr/bin/python3"
      /usr/bin/python3 "$ENV/bin/conda-unpack"
    fi
  fi
  printf '%s\n' "$CURRENT" > "$PREFIX_FILE"
  log "ad-hoc signing the bundle"
  /bin/bash "$RES/codesign_bundle.sh" "$APP_DIR" || log "ad-hoc codesign reported errors; Gatekeeper may still warn"
elif [[ "$(cat "$PREFIX_FILE")" != "$CURRENT" ]]; then
  OLD="$(cat "$PREFIX_FILE")"
  log "app moved; rewriting paths"
  "$PY" "$RES/relocate_prefix.py" "$OLD" "$CURRENT"
  printf '%s\n' "$CURRENT" > "$PREFIX_FILE"
  log "ad-hoc signing the bundle"
  /bin/bash "$RES/codesign_bundle.sh" "$APP_DIR" || log "ad-hoc codesign reported errors; Gatekeeper may still warn"
fi

# Finder launches often have no LANG. Follow the macOS language list so a
# Chinese system opens the GUI in Simplified Chinese unless SPEKTRAFILM_LANG
# was set explicitly.
if [[ -z "${SPEKTRAFILM_LANG:-}" ]]; then
  apple_langs="$(defaults read -g AppleLanguages 2>/dev/null || true)"
  case "$apple_langs" in
    *zh-Hans*|*zh_CN*|*zh-CN*|*\"zh\"*)
      export SPEKTRAFILM_LANG=zh_CN
      ;;
  esac
fi

export QT_API="${QT_API:-pyside6}"
export PYTHONNOUSERSITE=1
export PYTHONUNBUFFERED=1
export MPLBACKEND="${MPLBACKEND:-Agg}"

# Help Qt find the cocoa / offscreen plugins inside the PySide6 wheel.
if QT_PLUGINS="$("$PY" -c 'import pathlib, PySide6; print(pathlib.Path(PySide6.__file__).resolve().parent / "Qt" / "plugins")' 2>/dev/null)"; then
  if [[ -d "$QT_PLUGINS" ]]; then
    export QT_PLUGIN_PATH="$QT_PLUGINS"
  fi
fi

if [[ "${1:-}" == "--smoke" || "${SPEKTRAFILM_SMOKE:-}" == "1" ]]; then
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
  export NUMBA_NUM_THREADS="${NUMBA_NUM_THREADS:-1}"
  exec "$PY" "$RES/smoke_check.py"
fi

exec "$PY" -c 'from spektrafilm_gui.app import main; main()'
