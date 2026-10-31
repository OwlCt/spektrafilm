"""Display-language selection for the spektrafilm GUI.

``SPEKTRAFILM_LANG=en`` keeps every string exactly as the English UI builds it.
``SPEKTRAFILM_LANG=zh_CN`` (or a Chinese system locale) translates display text.
Stored values, film-stock names, and enum identifiers are not rewritten here;
combo boxes may paint a translated label while keeping the English item text.
"""

from __future__ import annotations

import locale
import os

from spektrafilm_gui.locales.zh_CN import ZH_CN

_ZH = {key.casefold(): value for key, value in ZH_CN.items()}


def active_language() -> str:
    """Return ``en`` or ``zh_CN``.

    ``SPEKTRAFILM_LANG`` wins. Otherwise a Chinese locale selects ``zh_CN``.
    Anything else stays English, which is the upstream UI.
    """
    override = os.environ.get("SPEKTRAFILM_LANG", "").strip().replace("-", "_")
    if override:
        token = override.split(".", 1)[0].lower()
        if token.startswith("zh"):
            return "zh_CN"
        return "en"

    env_locale = os.environ.get("LC_ALL", "").strip() or os.environ.get("LANG", "").strip()
    if env_locale:
        token = env_locale.split(".", 1)[0].replace("-", "_").lower()
        if token.startswith("zh"):
            return "zh_CN"
        return "en"

    try:
        system_locale = locale.getlocale()[0] or ""
    except (TypeError, ValueError):
        system_locale = ""
    if system_locale.replace("-", "_").lower().startswith("zh"):
        return "zh_CN"
    return "en"


def tr(text: str) -> str:
    """Translate one complete user-visible string. English is unchanged."""
    if not text or active_language() == "en":
        return text
    translated = _ZH.get(text.casefold())
    if translated is None:
        return text
    return translated


def configure_napari_language() -> str | None:
    """Point napari at an installed language pack.

    napari 0.6 reads ``NAPARI_LANGUAGE`` while it imports and only translates
    when a ``napari.languagepack`` plugin provides that locale. No official
    Simplified Chinese pack is published, so this usually does nothing and
    napari's own menus stay English.
    """
    if active_language() != "zh_CN":
        return None
    try:
        from importlib.metadata import entry_points

        discovered = entry_points()
        selected = discovered.select(group="napari.languagepack") if hasattr(discovered, "select") else discovered.get("napari.languagepack", ())
        available = {entry.name for entry in selected}
    except Exception:
        return None
    for candidate in ("zh_CN", "zh-CN", "zh"):
        if candidate in available:
            os.environ["NAPARI_LANGUAGE"] = candidate
            return candidate
    return None


def display_text(text: str, *, preserve_case: bool = False) -> str:
    """Text placed on a label or button.

    English labels are lowercased unless ``preserve_case`` is set, matching
    the previous GUI. Chinese text is not lowercased.
    """
    if active_language() == "en":
        return text if preserve_case else text.lower()
    return tr(text)
