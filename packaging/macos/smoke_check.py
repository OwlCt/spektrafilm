"""Headless check that the bundled app can import the film pipeline.

Run via Spektrafilm.app/Contents/MacOS/spektrafilm --smoke
(QT_QPA_PLATFORM=offscreen is set by the launcher).
"""

from __future__ import annotations

import os
import platform
import struct
import subprocess
import sys
import tempfile
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


def check_napari_plugins() -> None:
    import logging
    from importlib.resources import files

    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    loggers = [
        logging.getLogger(),
        logging.getLogger("npe2"),
        logging.getLogger("npe2.manifest"),
        logging.getLogger("npe2.manifest.schema"),
        logging.getLogger("napari"),
    ]
    previous_levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    try:
        manifest_text = files("napari_builtins").joinpath("builtins.yaml").read_text(encoding="utf-8")
        if "napari.get_reader" not in manifest_text:
            raise RuntimeError("napari_builtins/builtins.yaml is missing the builtin reader")
        import napari_svg

        if napari_svg.__file__ is None:
            raise RuntimeError("napari_svg was imported from a namespace with no file")
        import napari
        from npe2.manifest.schema import PluginManifest

        results = list(PluginManifest.discover())
        print(f"smoke: napari {napari.__version__} manifests {len(results)}", flush=True)
    finally:
        for logger, level in zip(loggers, previous_levels, strict=True):
            logger.removeHandler(handler)
            logger.setLevel(level)

    forbidden = (
        "could not be imported",
        "Cannot find module 'napari_svg'",
        "Could not find file 'builtins.yaml'",
    )
    leaked = [line for line in messages if any(marker in line for marker in forbidden)]
    if leaked:
        raise RuntimeError("napari plugin discovery failed:\n" + "\n".join(leaked))

    reader_registered = False
    svg_registered = False
    errors: list[str] = []
    names: list[str] = []
    for item in results:
        manifest = item[0]
        error = item[2]
        if error is not None:
            errors.append(str(error))
            continue
        if manifest is None:
            continue
        name = str(getattr(manifest, "name", ""))
        names.append(name)
        if "svg" in name:
            svg_registered = True
        contributions = getattr(manifest, "contributions", None)
        commands = getattr(contributions, "commands", None) if contributions is not None else None
        for command in commands or []:
            if getattr(command, "id", "") == "napari.get_reader":
                reader_registered = True
    if errors:
        raise RuntimeError("napari manifest import failed: " + " | ".join(errors[:8]))
    if not reader_registered:
        raise RuntimeError(f"napari builtin reader is not registered ({names})")
    if not svg_registered:
        raise RuntimeError(f"napari-svg is not registered ({names})")
    print("smoke: napari builtin reader and napari-svg are registered", flush=True)


def check_window_close_exits() -> None:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_API"] = "pyside6"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["QT_OPENGL"] = "software"
    env["NUMBA_NUM_THREADS"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["SPEKTRAFILM_SKIP_WARMUP"] = "1"
    env["SPEKTRAFILM_IN_QUIT_CHECK"] = "1"
    env.setdefault("SPEKTRAFILM_CONFIG_DIR", tempfile.mkdtemp(prefix="spektrafilm-quit-"))
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--quit-check"]
    else:
        command = [sys.executable, "-c", "from spektrafilm_gui.app import quit_check; quit_check()"]
    print(f"smoke: quit check via {command[0]}", flush=True)
    try:
        completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        raise RuntimeError("quit check still running after 600s\n" + (stdout + stderr)[-4000:]) from exc
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0 or "QUIT_OK" not in (completed.stdout or "") or "LINGERING_THREADS" in output:
        raise RuntimeError(f"quit check failed with {completed.returncode}\n" + output[-4000:])
    print("smoke: closing the window ended the process", flush=True)


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


def _manifest_texts():
    from spektrafilm_gui.param_manifest import (
        ALL_MANIFESTS,
        DISPLAY_PANEL_FIELDS,
        INPUT_IMAGE_FIELDS,
        SIMULATION_FIELDS,
        SPECIAL_FIELDS,
    )

    texts: list[str] = []
    for manifest in ALL_MANIFESTS:
        texts.append(manifest.title)
        for spec in manifest.fields:
            texts.append(spec.label or spec.leaf.replace("_", " "))
            if spec.tooltip:
                texts.append(spec.tooltip)
    for spec in (*INPUT_IMAGE_FIELDS, *SPECIAL_FIELDS, *DISPLAY_PANEL_FIELDS, *SIMULATION_FIELDS):
        texts.append(spec.label or spec.leaf.replace("_", " "))
        if spec.tooltip:
            texts.append(spec.tooltip)
    return texts


def _coverage(texts: list[str], tr) -> tuple[int, list[str]]:
    missing: list[str] = []
    seen: set[str] = set()
    for text in texts:
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        if tr(text) == text:
            missing.append(text)
    return len(seen), missing


def check_chinese_ui() -> None:
    from pathlib import Path

    os.environ["SPEKTRAFILM_CONFIG_DIR"] = tempfile.mkdtemp(prefix="spektrafilm-i18n-")
    os.environ["SPEKTRAFILM_LANG"] = "zh_CN"
    from spektrafilm_gui.i18n import (
        active_language,
        configure_napari_language,
        display_text,
        reset_language_cache,
        set_saved_language,
        tr,
    )
    from spektrafilm_gui.locales.zh_CN import ZH_CN
    from spektrafilm_gui.locales.zh_TW import ZH_TW

    reset_language_cache()
    if set(ZH_CN) != set(ZH_TW):
        raise RuntimeError("zh_CN and zh_TW catalogs do not cover the same strings")
    texts = _manifest_texts()
    total, missing = _coverage(texts, tr)
    print(f"smoke: zh_CN manifest strings translated {total - len(missing)}/{total}", flush=True)
    if missing:
        raise RuntimeError(f"{len(missing)} zh_CN manifest strings are still English: {', '.join(missing[:12])}")

    os.environ["SPEKTRAFILM_LANG"] = "zh_TW"
    total_tw, missing_tw = _coverage(texts, tr)
    print(f"smoke: zh_TW manifest strings translated {total_tw - len(missing_tw)}/{total_tw}", flush=True)
    if missing_tw:
        raise RuntimeError(f"{len(missing_tw)} zh_TW manifest strings are still English: {', '.join(missing_tw[:12])}")
    if tr("SAVE") != "儲存" or tr("Import RGB") != "匯入 RGB" or tr("Couplers") != "成色劑":
        raise RuntimeError("zh_TW wording did not use Traditional terminology")
    if tr("GUI parameters") == "界面参数":
        raise RuntimeError("zh_TW reused a Simplified string")

    os.environ["SPEKTRAFILM_LANG"] = "zh_CN"
    from spektrafilm_gui.widgets import create_widget_bundle
    from qtpy.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

    napari_language = configure_napari_language()
    print(
        "smoke: napari language pack",
        napari_language or "not installed; napari menus stay English",
        flush=True,
    )

    app = QApplication.instance() or QApplication([])
    bundle = create_widget_bundle()
    labels = [label.text() for label in bundle.load_raw.findChildren(QLabel)]
    if "白平衡" not in labels:
        raise RuntimeError(f"expected translated white-balance label, got {labels}")
    if bundle.load_raw.reprocess_button.text() != "重新处理 RAW":
        raise RuntimeError(f"unexpected reprocess button text {bundle.load_raw.reprocess_button.text()!r}")
    bundle.load_raw.white_balance.setCurrentText("tungsten")
    if bundle.load_raw.white_balance.value != "tungsten":
        raise RuntimeError("white-balance value was translated")
    if bundle.simulation.preview_button.text() != "预览":
        raise RuntimeError(f"unexpected preview button text {bundle.simulation.preview_button.text()!r}")

    os.environ.pop("SPEKTRAFILM_LANG", None)
    reset_language_cache()
    set_saved_language("zh_TW")
    from spektrafilm_gui.widget_sections import GuiConfigSection, LoadRawSection

    if active_language() != "zh_TW":
        raise RuntimeError("saved language did not override the system locale")
    traditional = LoadRawSection()
    if traditional.reprocess_button.text() != "重新處理 RAW":
        raise RuntimeError(f"saved zh_TW label was {traditional.reprocess_button.text()!r}")
    os.environ["SPEKTRAFILM_LANG"] = "zh_CN"
    if active_language() != "zh_CN":
        raise RuntimeError("SPEKTRAFILM_LANG did not override the saved language")
    os.environ.pop("SPEKTRAFILM_LANG", None)
    reset_language_cache()
    set_saved_language("en")
    settings = GuiConfigSection()
    if settings.save_current_as_default_button.text() != "save current as default":
        raise RuntimeError(settings.save_current_as_default_button.text())
    settings.language_combo.setCurrentIndex(settings.language_combo.findData("zh_TW"))
    if settings.save_current_as_default_button.text() != "將目前設為預設":
        raise RuntimeError(f"language switcher did not relabel: {settings.save_current_as_default_button.text()!r}")
    if settings.language_note.isHidden():
        raise RuntimeError("language switcher did not show the update note")
    if active_language() != "zh_TW":
        raise RuntimeError("switcher did not persist zh_TW")

    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(12, 12, 12, 12)
    for widget in (bundle.filepicker, bundle.load_raw, bundle.simulation, bundle.halation):
        layout.addWidget(widget)
    host.setStyleSheet("background: #1c1c1c; color: #f2f2f2;")
    host.setFixedWidth(520)
    host.adjustSize()
    host.show()
    app.processEvents()

    preview_dir = os.environ.get("SPEKTRAFILM_PREVIEW_DIR")
    if preview_dir:
        destination = Path(preview_dir)
        destination.mkdir(parents=True, exist_ok=True)
        pixmap = host.grab()
        if pixmap.isNull():
            print("smoke: offscreen grab returned a null pixmap", flush=True)
        else:
            image_path = destination / "zh_ui.png"
            pixmap.save(str(image_path))
            print(f"smoke: wrote {image_path} {pixmap.width()}x{pixmap.height()}", flush=True)
        icon = Path(__import__("spektrafilm_gui").__file__).resolve().parent / "assets" / "app_icon.png"
        if icon.is_file():
            target = destination / "app_icon.png"
            target.write_bytes(icon.read_bytes())
            print(f"smoke: wrote {target}", flush=True)

    os.environ["SPEKTRAFILM_LANG"] = "en"
    if display_text("Couplers") != "couplers":
        raise RuntimeError("English labels no longer match the upstream lowercase UI")
    if display_text("PREVIEW", preserve_case=True) != "PREVIEW":
        raise RuntimeError("English preserve-case buttons changed")
    if tr("Couplers") != "Couplers":
        raise RuntimeError("English tr() translated a string")


def main() -> None:
    print(
        f"smoke: python {sys.version.split()[0]} machine={platform.machine()} "
        f"pointer={struct.calcsize('P') * 8}",
        flush=True,
    )
    step("native modules and numba JIT", check_native_modules)
    step("package data", check_package_data)
    step("napari builtin plugins", check_napari_plugins)
    step("pipeline, Qt, and napari imports", check_pipeline_and_gui)
    step("Simplified Chinese labels", check_chinese_ui)
    step("window close exits the process", check_window_close_exits)
    print("SMOKE_OK", flush=True)


if __name__ == "__main__":
    main()
