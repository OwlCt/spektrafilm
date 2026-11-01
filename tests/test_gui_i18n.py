"""Language selection does not need Qt."""

from spektrafilm_gui.i18n import active_language, display_text, tr


def test_english_override_is_identity(monkeypatch) -> None:
    monkeypatch.setenv("SPEKTRAFILM_LANG", "en")
    assert active_language() == "en"
    assert tr("Couplers") == "Couplers"
    assert display_text("Couplers") == "couplers"
    assert display_text("PREVIEW", preserve_case=True) == "PREVIEW"


def test_chinese_override_translates_display_text(monkeypatch) -> None:
    monkeypatch.setenv("SPEKTRAFILM_LANG", "zh_CN")
    assert active_language() == "zh_CN"
    assert tr("Couplers") == "成色剂"
    assert tr("couplers") == "成色剂"
    assert tr("White balance") == "白平衡"
    assert tr("as_shot") == "相机设定"
    assert tr("kodak_portra_400") == "kodak_portra_400"
    assert display_text("PREVIEW", preserve_case=True) == "预览"


def test_chinese_system_locale_is_the_default(monkeypatch) -> None:
    monkeypatch.delenv("SPEKTRAFILM_LANG", raising=False)
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    monkeypatch.setenv("LC_ALL", "zh_CN.UTF-8")
    assert active_language() == "zh_CN"


def test_traditional_locales_and_saved_choice(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SPEKTRAFILM_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("SPEKTRAFILM_LANG", raising=False)
    monkeypatch.setenv("LANG", "zh_HK.UTF-8")
    monkeypatch.setenv("LC_ALL", "zh_HK.UTF-8")
    from spektrafilm_gui.i18n import reset_language_cache, set_saved_language
    from spektrafilm_gui.locales.zh_CN import ZH_CN
    from spektrafilm_gui.locales.zh_TW import ZH_TW

    reset_language_cache()
    assert set(ZH_CN) == set(ZH_TW)
    assert active_language() == "zh_TW"
    assert tr("SAVE") == "儲存"
    assert tr("Import RGB") == "匯入 RGB"
    monkeypatch.setenv("LANG", "zh_Hans")
    monkeypatch.setenv("LC_ALL", "zh_Hans")
    assert active_language() == "zh_CN"
    assert tr("SAVE") == "保存"
    set_saved_language("zh_TW")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    assert active_language() == "zh_TW"
    monkeypatch.setenv("SPEKTRAFILM_LANG", "en")
    assert active_language() == "en"
    assert tr("Couplers") == "Couplers"


def test_unknown_locale_stays_english(monkeypatch) -> None:
    monkeypatch.delenv("SPEKTRAFILM_LANG", raising=False)
    monkeypatch.setenv("LANG", "C")
    monkeypatch.setenv("LC_ALL", "C")
    assert active_language() == "en"
