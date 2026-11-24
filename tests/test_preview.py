import os
import time
import wave

import pytest
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtWidgets import QApplication

from demucs_gui import pipeline
from demucs_gui.ui import MainWindow, select


@pytest.fixture
def window(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "preview.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "en")
    view = MainWindow(settings)
    view.preview.audio.setMuted(True)
    yield view
    view.close()
    app.processEvents()


def wav(tmp_path, name):
    path = tmp_path / name
    with wave.open(str(path), "wb") as writer:
        writer.setparams((2, 2, 44100, 0, "NONE", ""))
        writer.writeframes(bytes(44100 * 4 * 5))
    return path


def wait_until(condition):
    app = QApplication.instance()
    end = time.monotonic() + 8
    while not condition() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    assert condition()


def local_url(path):
    return QUrl.fromLocalFile(str(path))


def test_completed_rows_prefer_vocals_or_first_stem_and_remember_manual_choices(window, tmp_path):
    first, second = [wav(tmp_path, name) for name in ("one.wav", "two.wav")]
    bass, vocals, drums = [wav(tmp_path, name) for name in ("one_bass.wav", "one_vocals.wav", "two_drums.wav")]
    window.add_files([first, second])
    one, two = window.entries
    one.outputs = {"bass": bass, "vocals": vocals}
    two.outputs = {"drums": drums}
    one.status = two.status = "완료"
    preview = window.preview
    window.selection_changed()
    assert preview.player.source() == local_url(vocals)
    window.queue.selectRow(1)
    assert preview.player.source() == local_url(drums)
    window.queue.selectRow(0)
    assert preview.player.source() == local_url(vocals)
    select(preview.tracks, str(first))
    window.selection_changed()
    assert preview.player.source() == local_url(first)
    window.queue.selectRow(1)
    window.queue.selectRow(0)
    assert preview.player.source() == local_url(first)
    select(preview.tracks, str(bass))
    window.queue.selectRow(1)
    window.queue.selectRow(0)
    assert preview.player.source() == local_url(bass)


def test_completion_switches_playing_original_at_current_position_and_failed_retry_clears_results(
    window, tmp_path, monkeypatch
):
    original = wav(tmp_path, "original.wav")
    vocal = wav(tmp_path, "actual_result.wav")
    monkeypatch.setattr(pipeline, "process_file", lambda *args: {"vocals": vocal})
    window.add_files([original])
    preview = window.preview
    wait_until(lambda: preview.player.duration() >= 5000)
    preview.play.click()
    wait_until(preview.player.isPlaying)
    preview.player.setPosition(1500)
    wait_until(lambda: preview.player.position() >= 1500)
    window.start.click()
    wait_until(lambda: not window.active and preview.pending is None and preview.player.isPlaying())
    assert preview.player.source() == local_url(vocal)
    assert preview.tracks.currentText() == "Vocals"
    assert preview.player.position() >= 1450
    preview.player.pause()

    def failed(*args):
        raise ValueError("test failure")

    monkeypatch.setattr(pipeline, "process_file", failed)
    window.retry.click()
    window.start.click()
    wait_until(lambda: not window.active)
    assert window.entries[0].status == "실패"
    assert not window.entries[0].outputs
    assert preview.tracks.count() == 1
    assert preview.player.source() == local_url(original)
    assert not preview.open_dir.isEnabled()
    assert vocal.exists()
