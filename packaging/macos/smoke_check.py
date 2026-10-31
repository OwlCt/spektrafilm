"""Headless check that the bundled app can import the film pipeline.

Run via Spektrafilm.app/Contents/MacOS/spektrafilm --smoke
(QT_QPA_PLATFORM=offscreen is set by the launcher).
"""

from __future__ import annotations

import os
import struct
import sys
import traceback

os.environ.setdefault("QT_API", "pyside6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("NUMBA_NUM_THREADS", "1")
os.environ.setdefault("PYTHONNOUSERSITE", "1")


def step(label: str, fn):
    print(f"smoke: {label}", flush=True)
    try:
        return fn()
    except Exception:
        print(f"smoke FAIL: {label}", file=sys.stderr, flush=True)
        traceback.print_exc()
        raise SystemExit(1)


def check_native_modules() -> None:
    import numpy
    import scipy
    import numba
    from numba import njit
    import llvmlite
    import OpenImageIO
    import rawpy
    import exiv2
    import lensfunpy
    import pyfftw
    import colour
    import PIL
    import skimage

    @njit
    def add_one(value):
        return value + 1

    result = int(add_one(1))
    if result != 2:
        raise RuntimeError(f"numba JIT returned {result}")
    print(
        "smoke: versions",
        f"numpy={numpy.__version__}",
        f"scipy={scipy.__version__}",
        f"numba={numba.__version__}",
        f"llvmlite={llvmlite.__version__}",
        f"OpenImageIO={getattr(OpenImageIO, '__version__', 'ok')}",
        f"rawpy={rawpy.__version__}",
        f"colour={colour.__version__}",
        f"PIL={PIL.__version__}",
        f"skimage={skimage.__version__}",
        f"pyfftw={pyfftw.__version__}",
        f"exiv2={getattr(exiv2, '__version__', 'ok')}",
        f"lensfunpy={getattr(lensfunpy, '__version__', 'ok')}",
        flush=True,
    )


def check_package_data() -> None:
    from importlib.resources import files

    from spektrafilm.profiles.io import list_profiles, load_profile

    profiles = list_profiles()
    if "kodak_portra_400" not in profiles:
        raise RuntimeError(f"bundled profiles missing kodak_portra_400 ({len(profiles)} found)")
    load_profile("kodak_portra_400")

    asset = files("spektrafilm_gui").joinpath("assets", "virtual_paper_watermark.png")
    data = asset.read_bytes()
    if len(data) < 8:
        raise RuntimeError(f"GUI asset missing or empty: {asset}")
    icc = files("spektrafilm.data.icc")
    if not any(True for _ in icc.iterdir()):
        raise RuntimeError("spektrafilm.data.icc is empty")
    print(f"smoke: {len(profiles)} profiles, asset {len(data)} bytes", flush=True)


def check_pipeline_and_gui() -> None:
    import spektrafilm.runtime.api
    import spektrafilm.utils.io
    import spektrafilm.utils.raw_file_processor
    import spektrafilm_gui.app

    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    print(f"smoke: Qt platform {app.platformName()}", flush=True)

    import napari

    print(f"smoke: napari {napari.__version__}", flush=True)
    print(f"smoke: entry {spektrafilm_gui.app.main.__name__} api {spektrafilm.runtime.api.__name__}", flush=True)


def main() -> None:
    print(
        f"smoke: python {sys.version.split()[0]} machine={os.uname().machine} "
        f"pointer={struct.calcsize('P') * 8}",
        flush=True,
    )
    step("native modules and numba JIT", check_native_modules)
    step("package data", check_package_data)
    step("pipeline, Qt, and napari imports", check_pipeline_and_gui)
    print("SMOKE_OK", flush=True)


if __name__ == "__main__":
    main()
