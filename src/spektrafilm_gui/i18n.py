"""Display-language selection for the spektrafilm GUI.

Precedence is ``SPEKTRAFILM_LANG``, then the saved in-app choice, then the
system locale.

``en`` keeps every string exactly as the English UI builds it.
``zh_CN`` / ``zh_Hans`` select Simplified Chinese.
``zh_TW`` / ``zh_HK`` / ``zh_Hant`` select Traditional Chinese.
Stored values, film-stock names, and enum identifiers are not rewritten;
combo boxes may paint a translated label while keeping the English item text.
"""

from __future__ import annotations

import json
import locale
import os
import sys
from pathlib import Path

from spektrafilm_gui.locales.zh_CN import ZH_CN
from spektrafilm_gui.locales.zh_TW import ZH_TW

LANGUAGE_CHOICES = (
    ("en", "English"),
    ("zh_CN", "简体中文"),
    ("zh_TW", "繁體中文"),
)

_CATALOGS = {
    "zh_CN": {key.casefold(): value for key, value in ZH_CN.items()},
    "zh_TW": {key.casefold(): value for key, value in ZH_TW.items()},
}
_saved_cache_key: str | None = None
_saved_cache = ""


def language_locked_by_environment() -> bool:
    return bool(os.environ.get("SPEKTRAFILM_LANG", "").strip())


def config_path() -> Path:
    override = os.environ.get("SPEKTRAFILM_CONFIG_DIR", "").strip()
    if override:
        return Path(override) / "settings.json"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "spektrafilm" / "settings.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "spektrafilm" / "settings.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "spektrafilm" / "settings.json"


def _classify(token: str) -> str:
    """Map a locale token to ``en``, ``zh_CN``, or ``zh_TW``."""
    normalized = token.strip().replace("-", "_").split(".", 1)[0].lower()
    if not normalized or normalized in {"c", "posix"}:
        return "en"
    parts = [part for part in normalized.split("_") if part]
    if not parts or parts[0] != "zh":
        return "en"
    if any(part in {"hant", "tw", "hk", "mo"} for part in parts[1:]):
        return "zh_TW"
    return "zh_CN"


def _saved_language() -> str:
    global _saved_cache, _saved_cache_key
    path = config_path()
    key = str(path)
    if _saved_cache_key == key:
        return _saved_cache
    choice = ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        payload = None
    if isinstance(payload, dict):
        raw = payload.get("language", "")
        if isinstance(raw, str) and raw.strip():
            classified = _classify(raw)
            if classified != "en" or raw.lower().startswith("en"):
                choice = classified
    _saved_cache_key = key
    _saved_cache = choice
    return choice


def reset_language_cache() -> None:
    global _saved_cache, _saved_cache_key
    _saved_cache_key = None
    _saved_cache = ""


def set_saved_language(language: str) -> None:
    """Persist an in-app language choice. Ignored while ``SPEKTRAFILM_LANG`` is set."""
    global _saved_cache, _saved_cache_key
    choice = _classify(language)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"language": choice}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _saved_cache_key = str(path)
    _saved_cache = choice


def _windows_ui_language() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import ctypes

        lang_id = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
    except (AttributeError, OSError, ValueError):
        return ""
    primary = lang_id & 0x3FF
    sublanguage = (lang_id >> 10) & 0x3F
    if primary != 0x04:  # LANG_CHINESE
        return ""
    # Traditional: Taiwan, Hong Kong, Macau. Singapore is Simplified.
    if sublanguage in {0x01, 0x03, 0x05}:
        return "zh_TW"
    return "zh_CN"


def _system_language() -> str:
    windows = _windows_ui_language()
    if windows:
        return windows
    env_locale = os.environ.get("LC_ALL", "").strip() or os.environ.get("LANG", "").strip()
    if env_locale:
        return _classify(env_locale)
    try:
        system_locale = locale.getlocale()[0] or ""
    except (TypeError, ValueError):
        system_locale = ""
    if system_locale:
        return _classify(system_locale)
    return "en"


def active_language() -> str:
    """Return ``en``, ``zh_CN``, or ``zh_TW``."""
    override = os.environ.get("SPEKTRAFILM_LANG", "").strip()
    if override:
        return _classify(override)
    saved = _saved_language()
    if saved:
        return saved
    return _system_language()


def tr(text: str) -> str:
    """Translate one complete user-visible string. English is unchanged."""
    if not text or active_language() == "en":
        return text
    catalog = _CATALOGS.get(active_language())
    if catalog is None:
        return text
    translated = catalog.get(text.casefold())
    if translated is None:
        return text
    return translated


def display_text(text: str, *, preserve_case: bool = False) -> str:
    """Text placed on a label or button.

    English labels are lowercased unless ``preserve_case`` is set, matching
    the previous GUI. Chinese text is not lowercased.
    """
    if active_language() == "en":
        return text if preserve_case else text.lower()
    return tr(text)


def bind_text(widget, english: str, *, preserve_case: bool = False) -> None:
    """Remember the English source so a later language change can relabel the widget."""
    widget.setProperty("sf_msgid", english)
    widget.setProperty("sf_preserve_case", preserve_case)
    widget.setText(display_text(english, preserve_case=preserve_case))


def bind_tooltip(widget, english: str) -> None:
    if not english:
        return
    widget.setProperty("sf_tip", english)
    widget.setToolTip(tr(english))


def bind_placeholder(widget, english: str) -> None:
    widget.setProperty("sf_placeholder", english)
    widget.setPlaceholderText(display_text(english))


def bind_tab(tab_widget, index: int, english: str) -> None:
    tabs = getattr(tab_widget, "_sf_tabs", None)
    if not isinstance(tabs, dict):
        tabs = {}
        tab_widget._sf_tabs = tabs
    tabs[index] = english
    tab_widget.setTabText(index, tr(english))


def retranslate(root) -> None:
    """Update widgets that were bound to English source strings."""
    from qtpy.QtWidgets import QWidget

    widgets = [root, *root.findChildren(QWidget)]
    for widget in widgets:
        msgid = widget.property("sf_msgid")
        if isinstance(msgid, str) and msgid and hasattr(widget, "setText"):
            widget.setText(display_text(msgid, preserve_case=bool(widget.property("sf_preserve_case"))))
        tip = widget.property("sf_tip")
        if isinstance(tip, str) and tip and hasattr(widget, "setToolTip"):
            widget.setToolTip(tr(tip))
        placeholder = widget.property("sf_placeholder")
        if isinstance(placeholder, str) and placeholder and hasattr(widget, "setPlaceholderText"):
            widget.setPlaceholderText(display_text(placeholder))
        tabs = getattr(widget, "_sf_tabs", None)
        if isinstance(tabs, dict):
            for index, english in tabs.items():
                widget.setTabText(int(index), tr(english))
        update = getattr(widget, "update", None)
        if callable(update):
            update()


def configure_napari_language() -> str | None:
    """Point napari at an installed language pack.

    napari 0.6 reads ``NAPARI_LANGUAGE`` while it imports and only translates
    when a ``napari.languagepack`` plugin provides that locale. No official
    Simplified or Traditional Chinese pack is published, so this usually does
    nothing and napari's own menus stay English.
    """
    language = active_language()
    if language == "en":
        return None
    candidates = ("zh_TW", "zh-TW", "zh_Hant") if language == "zh_TW" else ("zh_CN", "zh-CN", "zh")
    try:
        from importlib.metadata import entry_points

        discovered = entry_points()
        selected = discovered.select(group="napari.languagepack") if hasattr(discovered, "select") else discovered.get("napari.languagepack", ())
        available = {entry.name for entry in selected}
    except Exception:
        return None
    for candidate in candidates:
        if candidate in available:
            os.environ["NAPARI_LANGUAGE"] = candidate
            return candidate
    return None
