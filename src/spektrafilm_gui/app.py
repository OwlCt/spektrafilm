from dataclasses import dataclass
from importlib import import_module
import os
import sys
import threading
from typing import Any, Callable, cast

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui.controller import GuiController
from spektrafilm_gui.napari_layout import (
    build_controls_panel,
    build_main_window,
    configure_napari_chrome,
    show_viewer_window,
)
from spektrafilm_gui.persistence import load_default_gui_state
from spektrafilm_gui.state_bridge import GUI_STATE_SECTION_NAMES, apply_gui_state
from spektrafilm_gui.theme_palette import GRAY_0, GRAY_1, GRAY_2, GRAY_3, TEXT_DIM, TEXT_MAIN, TEXT_SELECTION_BG
from spektrafilm_gui.widgets import WidgetBundle, create_widget_bundle
from spektrafilm.utils.numba_warmup import warmup

QThreadPool = getattr(QtCore, 'QThreadPool')
QRunnable = getattr(QtCore, 'QRunnable')
QTimer = getattr(QtCore, 'QTimer')

_background_warmup_started = False
_background_warmup_scheduled = False
_background_warmup_pool: Any | None = None
_shutdown_requested = False
_cancel_warmup = threading.Event()
WARMUP_IMAGE_SHAPE = (16, 16, 3)

@dataclass(slots=True)
class GuiApp:
    viewer: Any
    widgets: WidgetBundle
    controller: GuiController
    main_window: QtWidgets.QMainWindow


def _warmup_launch_input_path(gui_state: object | None = None) -> None:
    state = load_default_gui_state() if gui_state is None else gui_state
    try:
        colour_module = import_module('colour')
        controller_runtime = import_module('spektrafilm_gui.controller_runtime')
        import_module('spektrafilm.utils.io')
        import_module('spektrafilm.utils.preview')
    except (AttributeError, ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        return

    warmup_image = np.full(WARMUP_IMAGE_SHAPE, 0.18, dtype=np.float64)
    try:
        controller_runtime.prepare_input_color_preview_image(
            warmup_image,
            input_color_space=state.input_image.io.input_color_space,
            apply_cctf_decoding=state.input_image.io.input_cctf_decoding,
            colour_module=colour_module,
        )
    except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
        return


def _warmup_full_gui() -> None:
    if _cancel_warmup.is_set():
        return
    gui_state = load_default_gui_state()
    warmup()
    if _cancel_warmup.is_set():
        return

    colour_module = import_module('colour')
    pil_image_module = import_module('PIL.Image')
    imagecms_module = import_module('PIL.ImageCms')
    controller_runtime = import_module('spektrafilm_gui.controller_runtime')
    params_mapper = import_module('spektrafilm_gui.params_mapper')
    runtime_api = import_module('spektrafilm.runtime.api')
    import_module('spektrafilm.utils.io')
    import_module('spektrafilm.utils.preview')
    import_module('spektrafilm.utils.raw_file_processor')

    if _cancel_warmup.is_set():
        return
    warmup_image = np.full(WARMUP_IMAGE_SHAPE, 0.18, dtype=np.float64)
    controller_runtime.prepare_input_color_preview_image(
        warmup_image,
        input_color_space=gui_state.input_image.io.input_color_space,
        apply_cctf_decoding=gui_state.input_image.io.input_cctf_decoding,
        colour_module=colour_module,
    )

    if _cancel_warmup.is_set():
        return
    params = params_mapper.build_params_from_state(gui_state)
    simulator = runtime_api.Simulator(runtime_api.digest_params(params))
    scan = np.asarray(simulator.process(warmup_image), dtype=np.float32)
    if _cancel_warmup.is_set():
        return

    # Force the display path once as part of startup so the first preview avoids lazy import/setup cost.
    controller_runtime.prepare_output_display_image(
        scan,
        output_color_space=gui_state.simulation.io.output_color_space,
        use_display_transform=True,
        imagecms_module=imagecms_module,
        colour_module=colour_module,
        pil_image_module=pil_image_module,
    )


class _WarmupTask(QRunnable):
    def __init__(self, *, warmup_fn: Callable[[], None] | None = None) -> None:
        super().__init__()
        self._warmup_fn = _warmup_full_gui if warmup_fn is None else warmup_fn

    def run(self) -> None:
        try:
            self._warmup_fn()
        except (AttributeError, ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError):
            return


def _build_app_palette() -> QtGui.QPalette:
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(GRAY_0))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(TEXT_MAIN))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(GRAY_1))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(GRAY_2))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(GRAY_1))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(TEXT_MAIN))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(TEXT_MAIN))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(GRAY_1))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(TEXT_MAIN))
    palette.setColor(QtGui.QPalette.BrightText, QtGui.QColor(TEXT_MAIN))
    palette.setColor(QtGui.QPalette.Mid, QtGui.QColor(GRAY_3))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(TEXT_SELECTION_BG))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(TEXT_MAIN))
    placeholder_role = getattr(QtGui.QPalette, 'PlaceholderText', None)
    if placeholder_role is not None:
        palette.setColor(placeholder_role, QtGui.QColor(TEXT_DIM))

    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(TEXT_DIM))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(TEXT_DIM))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(TEXT_DIM))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.HighlightedText, QtGui.QColor(TEXT_DIM))
    return palette


def _apply_app_palette() -> None:
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    app.setPalette(_build_app_palette())


def _create_viewer() -> Any:
    napari = import_module('napari')
    get_settings = import_module('napari.settings').get_settings
    viewer_cls = cast(Any, getattr(napari, 'Viewer'))
    viewer = viewer_cls(show=False)
    settings = get_settings()
    appearance = getattr(settings, 'appearance', None)
    if appearance is not None:
        setattr(cast(Any, appearance), 'theme', 'dark')
    return viewer


def _create_widgets() -> WidgetBundle:
    return create_widget_bundle()


def _start_background_warmup(
    *,
    thread_pool: Any | None = None,
    thread_pool_factory: Callable[[], Any] | None = None,
    task_factory: Callable[[], QRunnable] = _WarmupTask,
) -> None:
    global _background_warmup_started, _background_warmup_scheduled, _background_warmup_pool
    if _background_warmup_started:
        return
    _background_warmup_started = True
    _background_warmup_scheduled = False
    if thread_pool is None:
        if _background_warmup_pool is None:
            pool_factory = QThreadPool if thread_pool_factory is None else thread_pool_factory
            _background_warmup_pool = pool_factory()
            set_max_thread_count = getattr(_background_warmup_pool, 'setMaxThreadCount', None)
            if callable(set_max_thread_count):
                set_max_thread_count(1)
        pool = _background_warmup_pool
    else:
        pool = thread_pool
    pool.start(task_factory())


def stop_background_warmup() -> None:
    """Drop queued warmup work and stop waiting on the pool."""
    _cancel_warmup.set()
    pool = _background_warmup_pool
    if pool is None:
        return
    clear = getattr(pool, 'clear', None)
    if callable(clear):
        clear()
    wait = getattr(pool, 'waitForDone', None)
    if not callable(wait):
        return
    try:
        wait(200)
    except TypeError:
        return


def non_daemon_threads() -> list[str]:
    names: list[str] = []
    for thread in threading.enumerate():
        if thread is threading.main_thread() or not thread.is_alive() or thread.daemon:
            continue
        names.append(thread.name)
    return names


def request_shutdown() -> None:
    """Stop background work and leave the Qt event loop.

    Closing the Spektrafilm window has to end the process. napari's own
    top-level shell and a running warmup used to keep the loop, or a
    non-daemon thread, alive after the window was gone.
    """
    global _shutdown_requested
    if _shutdown_requested:
        return
    _shutdown_requested = True
    stop_background_warmup()
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    set_quit = getattr(app, 'setQuitOnLastWindowClosed', None)
    if callable(set_quit):
        set_quit(True)
    for widget in list(app.topLevelWidgets()):
        set_attribute = getattr(widget, 'setAttribute', None)
        if callable(set_attribute):
            set_attribute(QtCore.Qt.WA_QuitOnClose, False)
        hide = getattr(widget, 'hide', None)
        if callable(hide):
            hide()
    quit_app = getattr(app, 'quit', None)
    if callable(quit_app):
        quit_app()


def _schedule_background_warmup(
    *,
    single_shot_fn: Callable[[int, Callable[[], None]], None] | None = None,
) -> None:
    global _background_warmup_scheduled
    if os.environ.get('SPEKTRAFILM_SKIP_WARMUP') == '1':
        return
    if _background_warmup_started or _background_warmup_scheduled:
        return
    _background_warmup_scheduled = True
    scheduler = QTimer.singleShot if single_shot_fn is None else single_shot_fn
    scheduler(0, _start_background_warmup)


def _connect_auto_preview_signal(widget: Any, callback: Callable[..., None]) -> None:
    editors = getattr(widget, '_editors', None)
    if editors is not None:
        for editor in editors:
            _connect_auto_preview_signal(editor, callback)
        return

    for signal_name in ('toggled', 'currentTextChanged', 'valueChanged'):
        signal = getattr(widget, signal_name, None)
        if signal is not None and hasattr(signal, 'connect'):
            signal.connect(callback)
            return


def connect_auto_preview_signals(controller: GuiController, widgets: WidgetBundle) -> None:
    for section_name in GUI_STATE_SECTION_NAMES:
        section = getattr(widgets, section_name, None)
        if section is None or not getattr(section, '_is_params_group', False):
            continue

        skip_leaves = set(getattr(section, '_skip_auto_preview_leaves', ()))
        for leaf, editor in getattr(section, '_editors', {}).items():
            if leaf in skip_leaves:
                continue
            _connect_auto_preview_signal(editor, controller.request_auto_preview)

    widgets.simulation.bottom_auto_preview.toggled.connect(controller.request_auto_preview)
    widgets.simulation.bottom_scan_film.toggled.connect(controller.request_auto_preview)
    widgets.simulation.bottom_scan_for_print.toggled.connect(controller.request_auto_preview)


def connect_controller_signals(controller: GuiController, widgets: WidgetBundle) -> None:
    widgets.filepicker.load_requested.connect(controller.load_input_image)
    widgets.load_raw.load_requested.connect(controller.load_raw_image)
    widgets.simulation.film_stock.textActivated.connect(controller.apply_profile_defaults)
    widgets.simulation.print_paper.textActivated.connect(controller.apply_profile_defaults)
    widgets.gui_config.save_current_as_default_requested.connect(controller.save_current_as_default)
    widgets.gui_config.save_current_to_file_requested.connect(controller.save_current_state_to_file)
    widgets.gui_config.load_from_file_requested.connect(controller.load_state_from_file)
    widgets.gui_config.restore_factory_default_requested.connect(controller.restore_factory_default)
    widgets.simulation.preview_requested.connect(controller.run_preview)
    widgets.simulation.scan_requested.connect(controller.run_scan)
    widgets.simulation.save_requested.connect(controller.save_output_layer)
    widgets.display.use_display_transform.toggled.connect(controller.report_display_transform_status)
    widgets.display.gray_18_canvas.toggled.connect(controller.set_gray_18_canvas_enabled)
    widgets.display.output_interpolation.currentTextChanged.connect(controller.set_output_interpolation_mode)
    widgets.display.update_preview_requested.connect(controller.refresh_preview_cache)
    widgets.display.update_preview_requested.connect(controller.request_auto_preview)
    connect_auto_preview_signals(controller, widgets)


def gray_18_canvas_enabled(widgets: WidgetBundle) -> bool:
    toggle = getattr(widgets.display, 'gray_18_canvas', None)
    is_checked = getattr(toggle, 'isChecked', None)
    return bool(is_checked()) if callable(is_checked) else False


def initialize_controller(
    *,
    viewer: Any,
    widgets: WidgetBundle,
    controller_cls: type[GuiController] = GuiController,
    connect_signals_fn: Callable[[GuiController, WidgetBundle], None] = connect_controller_signals,
) -> GuiController:
    controller = controller_cls(viewer=viewer, widgets=widgets)
    controller.sync_display_transform_availability(report_status=False)
    show_startup_placeholder = getattr(controller, 'show_startup_placeholder', None)
    if callable(show_startup_placeholder):
        show_startup_placeholder()
    connect_signals_fn(controller, widgets)
    return controller


def build_main_window_for_app(
    *,
    viewer: Any,
    widgets: WidgetBundle,
    controller: GuiController | None = None,
    configure_napari_chrome_fn: Callable[..., None] = configure_napari_chrome,
    build_controls_panel_fn: Callable[[Any, WidgetBundle], Any] = build_controls_panel,
    build_main_window_fn: Callable[[Any, Any], Any] = build_main_window,
) -> Any:
    configure_napari_chrome_fn(viewer, gray_18_canvas=gray_18_canvas_enabled(widgets))
    controls_panel = build_controls_panel_fn(viewer, widgets)
    if controller is None:
        return build_main_window_fn(viewer, controls_panel)
    return build_main_window_fn(
        viewer,
        controls_panel,
        on_rotate_ccw=controller.rotate_input_image_counterclockwise,
        on_rotate_cw=controller.rotate_input_image_clockwise,
    )


def create_app() -> GuiApp:
    viewer = _create_viewer()
    _apply_app_palette()
    widgets = _create_widgets()
    gui_state = load_default_gui_state()
    apply_gui_state(gui_state, widgets=widgets)
    _warmup_launch_input_path(gui_state)
    controller = initialize_controller(viewer=viewer, widgets=widgets)
    main_window = build_main_window_for_app(viewer=viewer, widgets=widgets, controller=controller)
    _schedule_background_warmup()
    return GuiApp(
        viewer=viewer,
        widgets=widgets,
        controller=controller,
        main_window=main_window,
    )

def _finish_process() -> None:
    stop_background_warmup()
    lingering = non_daemon_threads()
    if lingering:
        print('spektrafilm: stopping lingering threads: ' + ', '.join(lingering), flush=True)
        os._exit(0)


def quit_check() -> None:
    """Show the real window, fire its quit shortcut, and require a clean exit."""
    # macOS offscreen has no OpenGL and segfaults inside napari's canvas.
    # Callers on that platform pass QT_QPA_PLATFORM=cocoa.
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('QT_API', 'pyside6')
    os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
    os.environ.setdefault('QT_OPENGL', 'software')
    os.environ.setdefault('NUMBA_NUM_THREADS', '1')
    os.environ.setdefault('PYTHONNOUSERSITE', '1')
    os.environ.setdefault('SPEKTRAFILM_SKIP_WARMUP', '1')
    from spektrafilm_gui.i18n import configure_napari_language

    configure_napari_language()
    napari = import_module('napari')
    gui = create_app()
    show_viewer_window(gui.viewer)
    from qtpy.QtCore import QTimer

    def fire_quit() -> None:
        from qtpy.QtCore import Qt
        from qtpy.QtGui import QKeySequence
        from qtpy.QtTest import QTest
        from qtpy.QtWidgets import QApplication

        window = gui.main_window
        action = getattr(window, '_quit_action', None)
        if action is None:
            for candidate in window.actions():
                if candidate.text() == 'Quit':
                    action = candidate
                    break
        shortcuts = []
        if action is not None:
            shortcuts = list(action.shortcuts()) if hasattr(action, 'shortcuts') else [action.shortcut()]
            shortcuts = [sequence for sequence in shortcuts if sequence is not None and not sequence.isEmpty()]
        if action is None or not shortcuts:
            described = [(candidate.text(), candidate.shortcut().toString()) for candidate in window.actions()]
            print(f'QUIT_SHORTCUT_MISSING actions={described}', flush=True)
            os._exit(6)
        portable = QKeySequence('Meta+Q' if sys.platform == 'darwin' else 'Ctrl+Q')
        sequence = next((item for item in shortcuts if item.matches(portable) or item == portable), shortcuts[0])
        window.show()
        window.activateWindow()
        window.raise_()
        focus_reason = getattr(Qt, 'OtherFocusReason', None)
        if focus_reason is None:
            focus_reason = Qt.FocusReason.OtherFocusReason
        window.setFocus(focus_reason)
        qt_app = QApplication.instance()
        if qt_app is not None:
            set_active = getattr(qt_app, 'setActiveWindow', None)
            if callable(set_active):
                set_active(window)
            qt_app.processEvents()
        combo = sequence[0]
        key = combo.key()
        modifiers = combo.keyboardModifiers()
        print(f'QUIT_KEY key={key} modifiers={modifiers}', flush=True)
        QTest.keyClick(window, key, modifiers)

    QTimer.singleShot(500, fire_quit)
    QTimer.singleShot(15000, lambda: os._exit(4))
    napari.run()
    lingering = non_daemon_threads()
    if lingering:
        print('LINGERING_THREADS ' + ','.join(lingering), flush=True)
        os._exit(5)
    print('QUIT_OK', flush=True)
    os._exit(0)


def main():
    from spektrafilm_gui.i18n import configure_napari_language

    configure_napari_language()
    napari = import_module('napari')
    app = create_app()
    qt_app = QtWidgets.QApplication.instance()
    if qt_app is not None and hasattr(qt_app, 'setQuitOnLastWindowClosed'):
        qt_app.setQuitOnLastWindowClosed(True)
    show_viewer_window(app.viewer)
    napari.run()
    _finish_process()


if __name__ == "__main__":
    main()
