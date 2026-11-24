import json
import os
import time
import wave

import pytest
from PySide6.QtCore import QLocale, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSlider

from demucs_gui.ui import Entry, MainWindow, select


@pytest.fixture(scope="module")
def application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_audio_format_labels_and_bitrates(application, tmp_path):
    window = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    panel = window.options_panel
    assert [card.accessibleName() for card in panel.format.buttons.values()] == [
        "WAV", "MP3", "AAC (.aac)", "M4A (AAC)", "FLAC",
    ]
    rates = ["128", "192", "256", "320"]
    for fmt in ("mp3", "aac"):
        panel.format.buttons[fmt].click()
        assert [card.accessibleName() for card in panel.quality.buttons.values()] == [
            f"{rate} kbps" for rate in rates
        ]
        for rate in rates:
            panel.quality.buttons[rate].click()
            options = panel.options()
            assert (options.format, options.quality) == (fmt, rate)
            options.validate()
    window.close()


def test_audio_and_video_quality_survive_restart(application, tmp_path):
    path = str(tmp_path / "settings.ini")
    first = MainWindow(QSettings(path, QSettings.Format.IniFormat))
    panel = first.options_panel
    panel.format.buttons["mp3"].click()
    panel.quality.buttons["128"].click()
    panel.kind_buttons["video"].click()
    panel.format.buttons["mkv"].click()
    panel.quality.buttons["192"].click()
    select(panel.stem, "vocals")
    first.close()

    restored = MainWindow(QSettings(path, QSettings.Format.IniFormat))
    panel = restored.options_panel
    assert (panel.options().format, panel.options().quality, panel.options().selected_stem) == (
        "mkv", "192", "vocals",
    )
    panel.kind_buttons["audio"].click()
    assert (panel.options().format, panel.options().quality) == ("mp3", "128")
    restored.close()


def test_stem_model_cards_and_builtin_presets(application, tmp_path):
    window = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    panel = window.options_panel
    panel.mode.buttons["6"].click()
    assert panel.model.buttons["htdemucs_6s"].isChecked()
    select(panel.stem, "piano")
    assert panel.options().selected_stem == "piano"
    panel.model.buttons["mdx_extra"].click()
    assert panel.mode.buttons["4"].isChecked()
    assert panel.options().selected_stem == "all"
    assert panel.stem.findData("piano") < 0
    panel.options().validate()
    panel.kind_buttons["video"].click()
    panel.format.buttons["mkv"].click()
    for name, mode, stem in [("backing", "2", "accompaniment"), ("vocal", "2", "vocals"),
                              ("instruments", "4", "all")]:
        panel.separation_strength.setValue(73)
        panel.bleed_reduction_db.setValue(20)
        select(panel.presets, "builtin/" + name)
        panel.apply_button.click()
        options = panel.options()
        assert (options.stem_mode, options.selected_stem, options.format) == (mode, stem, "mkv")
        assert (options.separation_strength, options.bleed_reduction_db) == (100, 6)
        options.validate()
    window.close()


def test_named_preset_lifecycle(application, tmp_path, monkeypatch):
    path = str(tmp_path / "settings.ini")
    first = MainWindow(QSettings(path, QSettings.Format.IniFormat))
    panel = first.options_panel
    panel.model.buttons["htdemucs_6s"].click()
    select(panel.stem, "guitar")
    panel.format.buttons["aac"].click()
    panel.quality.buttons["256"].click()
    panel.kind_buttons["video"].click()
    panel.format.buttons["mkv"].click()
    panel.quality.buttons["192"].click()
    panel.shifts.setValue(7)
    panel.overlap.setValue(0.65)
    panel.separation_strength.setValue(81)
    panel.bleed_reduction_db.setValue(17)
    select(panel.device, "cpu")
    panel.folder.setText(str(tmp_path))
    expected = panel.options()
    name = "공연 / 기타"
    monkeypatch.setattr(panel, "ask_preset_name", lambda: name)
    panel.save_button.click()
    assert panel.presets.currentData() == "user/" + name
    panel.separation_strength.setValue(0)
    panel.bleed_reduction_db.setValue(1)
    panel.format.buttons["mp4"].click()
    confirmations = []
    def reject(*args):
        confirmations.append(args)
        return False
    monkeypatch.setattr(panel, "confirm", reject)
    panel.save_button.click()
    assert confirmations
    first.close()

    reopened = MainWindow(QSettings(path, QSettings.Format.IniFormat))
    panel = reopened.options_panel
    assert panel.options().format == "mp4"
    assert panel.separation_strength.value() == 0 and not panel.bleed_reduction_db.isEnabled()
    select(panel.presets, "user/" + name)
    panel.apply_button.click()
    assert panel.options() == expected
    panel.kind_buttons["audio"].click()
    assert (panel.options().format, panel.options().quality) == ("aac", "256")
    monkeypatch.setattr(panel, "ask_preset_name", lambda old: "기타 연습")
    panel.rename_preset_dialog()
    assert panel.presets.currentData() == "user/기타 연습"
    assert name not in panel.custom_presets()
    monkeypatch.setattr(panel, "confirm", lambda *args: False)
    panel.delete_preset_dialog()
    assert "기타 연습" in panel.custom_presets()
    monkeypatch.setattr(panel, "confirm", lambda *args: True)
    panel.delete_preset_dialog()
    assert not panel.custom_presets()
    reopened.close()


def test_separation_controls_and_legacy_presets(application, tmp_path):
    settings = QSettings(str(tmp_path / "levels.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "ko")
    legacy = {"shifts": 4, "quality": "16"}
    settings.setValue("options", json.dumps(legacy))
    settings.setValue("userPresets", json.dumps({"legacy": {"options": legacy, "qualities": {}}}))
    window = MainWindow(settings)
    panel = window.options_panel
    panel.advanced_toggle.click()
    strength, bleed = panel.separation_strength, panel.bleed_reduction_db
    assert (panel.shifts.value(), panel.options().quality) == (4, "16")
    assert (strength.minimum(), strength.maximum(), strength.text()) == (0, 100, "100%")
    assert (bleed.minimum(), bleed.maximum(), bleed.text()) == (0, 24, "6 dB")
    assert (strength.accessibleName(), bleed.accessibleName()) == ("분리 강도", "잔여음 억제")
    sliders = {item.accessibleName(): item for item in panel.findChildren(QSlider)}
    sliders["잔여음 억제 슬라이더"].setValue(18)
    sliders["분리 강도 슬라이더"].setValue(0)
    assert strength.value() == 0 and bleed.value() == 18
    assert not bleed.isEnabled() and not sliders["잔여음 억제 슬라이더"].isEnabled()

    select(window.language_box, "en")
    assert (strength.accessibleName(), bleed.accessibleName()) == ("Separation strength", "Bleed reduction")
    assert sliders["분리 강도 슬라이더"].accessibleName() == "Separation strength slider"
    assert "original mix" in strength.toolTip() and "24 dB" in bleed.toolTip()
    strength.selectAll()
    QTest.keyClicks(strength, "37")
    QTest.keyClick(strength, Qt.Key_Return)
    assert bleed.isEnabled() and (strength.value(), bleed.value()) == (37, 18)
    assert (sliders["분리 강도 슬라이더"].value(), sliders["잔여음 억제 슬라이더"].value()) == (37, 18)
    select(panel.presets, "user/legacy")
    panel.apply_button.click()
    assert (panel.shifts.value(), strength.value(), bleed.value()) == (4, 100, 6)
    window.close()


def test_closing_window_releases_preview_media(application, tmp_path):
    media = tmp_path / "preview.wav"
    with wave.open(str(media), "wb") as writer:
        writer.setparams((2, 2, 44100, 0, "NONE", ""))
        writer.writeframes(bytes(44100 * 4))
    window = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    window.preview.set_entry(Entry(media))
    deadline = time.monotonic() + 5
    while not window.preview.player.duration() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    assert window.preview.player.duration() == 1000
    window.close()
    assert window.preview.player.source().isEmpty()
    media.unlink()


def test_switch_language_preserves_media_queue_settings_and_history(application, tmp_path, monkeypatch):
    ini = str(tmp_path / "language-settings.ini")
    settings = QSettings(ini, QSettings.Format.IniFormat)
    settings.setValue("language", "ko")
    window = MainWindow(settings)
    panel = window.options_panel
    name = "보컬 {name}"
    media = tmp_path / (name + ".wav")
    output = tmp_path / "보컬 결과.wav"
    for path in (media, output):
        with wave.open(str(path), "wb") as writer:
            writer.setparams((2, 2, 44100, 0, "NONE", ""))
            writer.writeframes(bytes(44100 * 4))
    panel.format.buttons["flac"].click()
    monkeypatch.setattr(panel, "ask_preset_name", lambda: name)
    panel.save_button.click()
    window.add_files([media])
    entry = window.entries[0]
    entry.outputs = {"vocals": output}
    entry.status = "완료"
    window.set_row(entry, 1)
    window.preview.set_entry(entry, prefer_result=True)
    raw_source = window.preview.player.source()
    window.log_message("{name} · {status} · {detail}", name=media.name, status="완료", detail="저장 완료")
    options = panel.options()

    select(window.language_box, "en")
    assert window.windowTitle() == "Demucs Studio · Audio separation"
    assert window.language_box.accessibleName() == "Display language"
    assert window.queue.item(0, 0).text() == media.name
    assert window.queue.item(0, 2).text() == "Completed"
    assert window.queue.horizontalHeaderItem(1).text() == "Length"
    assert window.preview.player.source() == raw_source
    assert window.preview.tracks.currentText() == "Vocals"
    assert window.log.toPlainText().endswith(media.name + " · Completed · Export complete")
    assert window.update_footer.manual_check.text() == "Check for updates"
    assert panel.model.buttons["htdemucs_ft"].accessibleName() == "Best quality"
    assert panel.quality.buttons["24"].accessibleName() == "24-bit lossless"
    assert panel.quality_label.text() == "Bit depth"
    assert panel.presets.currentText() == "My preset · " + name
    assert panel.options() == options
    window.close()

    restored = MainWindow(QSettings(ini, QSettings.Format.IniFormat))
    assert restored.start.text() == "Start separation"
    assert restored.language_box.currentData() == "en"
    select(restored.language_box, "ko")
    assert restored.start.text() == "분리 시작"
    assert restored.options_panel.presets.findText("내 프리셋 · " + name) >= 0
    restored.close()


def test_device_status_tracks_selection_in_both_languages(application, tmp_path):
    settings = QSettings(str(tmp_path / "device.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "ko")
    window = MainWindow(settings)
    devices = window.options_panel.device
    window.device_status.detected("NVIDIA Test GPU", "")
    assert window.device_status.text() == "분리 장치 · GPU (CUDA) · NVIDIA Test GPU"
    select(devices, "cpu")
    assert window.device_status.text() == "분리 장치 · CPU"
    select(window.language_box, "en")
    assert window.device_status.text() == "Device · CPU"
    assert devices.accessibleName() == "Select processing device"
    select(devices, "cuda")
    assert window.device_status.text() == "Device · GPU (CUDA) · NVIDIA Test GPU"
    window.device_status.detected("", "")
    assert window.device_status.text() == "Device · CUDA GPU unavailable"
    select(devices, "auto")
    assert window.device_status.text() == "Device · CPU (auto)"
    select(window.language_box, "ko")
    assert window.device_status.text() == "분리 장치 · CPU (자동)"
    window.close()


@pytest.mark.parametrize("system_locale,initial,chosen", [("en_US", "en", "ko"), ("ko_KR", "ko", "en")])
def test_saved_language_overrides_system_locale(application, tmp_path, monkeypatch, system_locale, initial, chosen):
    monkeypatch.setattr(QLocale, "system", staticmethod(lambda: QLocale(system_locale)))
    path = str(tmp_path / "locale.ini")
    first = MainWindow(QSettings(path, QSettings.Format.IniFormat))
    assert first.language_box.currentData() == initial
    select(first.language_box, chosen)
    first.close()
    reopened = MainWindow(QSettings(path, QSettings.Format.IniFormat))
    assert reopened.language_box.currentData() == chosen
    reopened.close()
