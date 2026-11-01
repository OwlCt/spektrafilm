"""PyInstaller entry for the Linux bundle."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


os.environ.setdefault("QT_API", "pyside6")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("PYTHONNOUSERSITE", "1")


def _prepare_bundled_fonts() -> None:
    if not sys.platform.startswith("linux"):
        return
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "fonts" / "fonts.conf")
    candidates.append(Path(sys.executable).resolve().parent / "_internal" / "fonts" / "fonts.conf")
    for conf in candidates:
        if conf.is_file():
            os.environ.setdefault("FONTCONFIG_FILE", str(conf))
            return


_prepare_bundled_fonts()


def _smoke_script() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "smoke_check.py"
    return Path(__file__).resolve().parents[1] / "macos" / "smoke_check.py"


def main() -> int:
    _prepare_bundled_fonts()
    if "--quit-check" in sys.argv:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ.setdefault("NUMBA_NUM_THREADS", "1")
        from spektrafilm_gui.app import quit_check

        quit_check()
        return 0
    if "--smoke" in sys.argv:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ.setdefault("NUMBA_NUM_THREADS", "1")
        script = _smoke_script()
        sys.argv = [str(script)]
        runpy.run_path(str(script), run_name="__main__")
        return 0
    from spektrafilm_gui.app import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
