import os
import threading
import time
import wave
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog

from demucs_gui import pipeline
from demucs_gui.ui import MainWindow


def wait_until(app, condition):
    deadline = time.monotonic() + 5
    while not condition():
        app.processEvents()
        if time.monotonic() > deadline:
            pytest.fail("Timed out waiting for the worker")
        time.sleep(0.005)


@pytest.fixture
def live_batch(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "en")
    window = MainWindow(settings)
    files = [tmp_path / (name + ".wav") for name in ("one", "two", "three", "four")]
    for path in files:
        with wave.open(str(path), "wb") as data:
            data.setparams((2, 2, 44100, 0, "NONE", ""))
            data.writeframes(bytes(4410 * 4))

    calls = []

    def controlled_job(path, options, progress, cancelled):
        resume = threading.Event()
        calls.append((path, options, resume))
        progress(0.25, "Quarter complete")
        while not resume.wait(0.005):
            if cancelled():
                raise InterruptedError
        if cancelled():
            raise InterruptedError
        return {}

    monkeypatch.setattr(pipeline, "process_file", controlled_job)
    yield app, window, files, calls
    if window.active:
        window.cancel_work(True)
        wait_until(app, lambda: not window.active)
    window.close()
    window.probe_pool.waitForDone()
    app.processEvents()


def drop(window, file):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(file))])
    args = (Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    enter = QDragEnterEvent(QPoint(4, 4), *args)
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    event = QDropEvent(QPointF(4, 4), *args)
    window.dropEvent(event)
    assert event.isAccepted()


def test_edit_settings_append_remove_and_retry_during_batch(live_batch, monkeypatch, tmp_path):
    app, window, (one, two, three, four), calls = live_batch
    window.add_files([one, two])
    window.start.click()
    wait_until(app, lambda: len(calls) == 1)
    panel = window.options_panel
    assert window.add.isEnabled() and panel.isEnabled() and window.cancel.isEnabled()
    assert not window.start.isEnabled() and not window.clear.isEnabled()
    assert not window.remove.isEnabled()  # The selected first row is running.
    assert window.drop_hint.text() == "Settings changes apply to the next file."

    panel.format.buttons["mp3"].click()
    panel.quality.buttons["128"].click()
    panel.folder.setText(str(tmp_path / "next"))
    panel.separation_strength.setValue(72)
    panel.bleed_reduction_db.setValue(18)
    assert calls[0][1].format == "wav" and calls[0][1].output_dir == ""
    assert (calls[0][1].separation_strength, calls[0][1].bleed_reduction_db) == (100, 6)

    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args, **kwargs: ([str(three)], ""))
    window.add.click()
    drop(window, four)
    window.add_files([three])  # Repeated drag of an existing path adds no duplicate.
    assert [entry.path for entry in window.entries] == [one, two, three, four]
    assert window.stage.text().startswith("1/4")
    window.queue.selectRow(3)
    window.remove.click()
    assert [entry.path for entry in window.entries] == [one, two, three]
    assert window.stage.text().startswith("1/3")

    calls[0][2].set()
    wait_until(app, lambda: len(calls) == 2)
    assert calls[1][0] == two
    assert (calls[1][1].format, calls[1][1].quality) == ("mp3", "128")
    assert (calls[1][1].separation_strength, calls[1][1].bleed_reduction_db) == (72, 18)
    assert Path(calls[1][1].output_dir) == tmp_path / "next"
    panel.format.buttons["flac"].click()
    assert calls[1][1].format == "mp3"
    window.queue.selectRow(0)
    window.retry.click()
    calls[1][2].set()
    wait_until(app, lambda: len(calls) == 3)
    assert (calls[2][0], calls[2][1].format) == (three, "flac")
    calls[2][2].set()
    wait_until(app, lambda: len(calls) == 4)
    assert calls[3][0] == one
    calls[3][2].set()
    wait_until(app, lambda: not window.active)
    assert window.finished_counts["완료"] == 4
    assert not window.finished_counts["대기"]
    assert all(entry.status == "완료" for entry in window.entries)


def test_cancel_file_continues_and_cancel_batch_leaves_queue(live_batch):
    app, window, (one, two, three, four), calls = live_batch
    window.add_files([one, two])
    window.start.click()
    wait_until(app, lambda: len(calls) == 1)
    drop(window, three)
    window.cancel_work(False)
    wait_until(app, lambda: len(calls) == 2)
    assert calls[1][0] == two and window.entries[0].status == "취소"
    window.cancel_work(True)
    window.add_files([four])
    wait_until(app, lambda: not window.active)
    assert window.finished_counts == {"완료": 0, "실패": 0, "취소": 2, "대기": 2}
    assert [row.status for row in window.entries] == ["취소", "취소", "대기", "대기"]
    window.start.click()
    wait_until(app, lambda: len(calls) == 3)
    assert calls[2][0] == three
    calls[2][2].set()
    wait_until(app, lambda: len(calls) == 4)
    assert calls[3][0] == four
    calls[3][2].set()
    wait_until(app, lambda: not window.active)
    assert window.finished_counts["완료"] == 2
