import os
import time
import wave

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

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
        select(panel.presets, "builtin/" + name)
        panel.apply_button.click()
        options = panel.options()
        assert (options.stem_mode, options.selected_stem, options.format) == (mode, stem, "mkv")
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
    select(panel.device, "cpu")
    panel.folder.setText(str(tmp_path))
    expected = panel.options()
    name = "공연 / 기타"
    monkeypatch.setattr(panel, "ask_preset_name", lambda: name)
    panel.save_button.click()
    assert panel.presets.currentData() == "user/" + name
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
