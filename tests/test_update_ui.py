import io
import json
import os
import sys
from pathlib import Path
from threading import Event, get_ident
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from demucs_gui.update_ui import UpdateFooter


class FakeUpdater:
    VERSION = "1.0.0"
    REPO_URL = "https://github.com/LiveTrack-X/Demucs-Studio"

    def __init__(self):
        self.release = SimpleNamespace(version="1.1.0", size=12345,
                                       page_url=self.REPO_URL + "/releases/tag/v1.1.0")
        self.checks = []
        self.launched = []
        self.discarded = []

    def check_update(self):
        self.checks.append(get_ident())
        return self.release

    def download_install(self, release, progress, cancelled):
        assert release is self.release
        assert not cancelled()
        progress(0.5, "다운로드")
        return Path("test-installer.exe")

    def launch_installer(self, path):
        self.launched.append(path)

    def discard_download(self, path):
        self.discarded.append(path)


@pytest.fixture(scope="module")
def application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def wait_for(app, predicate):
    end = monotonic() + 5
    while not predicate() and monotonic() < end:
        app.processEvents()
        sleep(0.005)
    assert predicate()


def discover(footer, app):
    footer.check_now()
    wait_for(app, lambda: not footer._checking)


def test_version_credit_periodic_detection_and_source_release_page(application, monkeypatch):
    api = FakeUpdater()
    newer = api.release
    api.release = None
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    monkeypatch.delattr(sys, "frozen", raising=False)
    footer = UpdateFooter(lambda: False, backend=api)
    assert footer.credit.text() == "v1.0.0 | Created by LiveTrack"
    assert footer.update_button.isHidden()
    footer.show()
    footer._startup.start(0)
    wait_for(application, lambda: len(api.checks) == 1 and not footer._checking)
    assert footer.update_button.isHidden()
    api.release = newer
    footer._periodic.setInterval(30)
    wait_for(application, lambda: not footer.update_button.isHidden())
    footer._periodic.stop()
    assert all(worker != get_ident() for worker in api.checks)
    footer.credit.click()
    footer.update_button.click()
    assert opened == [api.REPO_URL, newer.page_url]
    assert api.launched == []
    footer.close()


def test_update_button_requires_newer_compatible_github_release(application, monkeypatch, tmp_path):
    from demucs_gui import updater

    monkeypatch.setattr(updater, "_cache_root", lambda: tmp_path)
    replies = []
    monkeypatch.setattr(updater, "_request", lambda *_: io.BytesIO(json.dumps(replies.pop()).encode()))
    footer = UpdateFooter(lambda: False)
    major, minor, patch = map(int, updater.VERSION.split("."))
    next_tag = f"v{major}.{minor}.{patch + 1}"
    for tag, prerelease, name, expected in [
        (f"v{updater.VERSION}", False, "DemucsStudio-Setup-x64.exe", False),
        (next_tag, True, "DemucsStudio-Setup-x64.exe", False),
        (next_tag, False, "Linux.tar.gz", False),
        (next_tag, False, "DemucsStudio-Setup-x64.exe", True),
    ]:
        replies.append({"tag_name": tag, "prerelease": prerelease, "assets": [{
            "name": name, "size": 32, "state": "uploaded", "digest": "sha256:" + "5" * 64,
            "browser_download_url": f"{updater.REPO_URL}/releases/download/{tag}/{name}",
        }]})
        discover(footer, application)
        assert (not footer.update_button.isHidden()) == expected
    footer.close()


def test_switching_footer_language_preserves_release_and_credit(application, monkeypatch):
    from demucs_gui.i18n import language, set_language

    before = language()
    try:
        set_language("ko")
        footer = UpdateFooter(lambda: True, backend=FakeUpdater())
        discover(footer, application)
        assert footer.manual_check.text() == "업데이트 확인"
        set_language("en")
        footer.retranslate()
        assert footer.credit.text() == "v1.0.0 | Created by LiveTrack"
        assert footer.manual_check.text() == "Check for updates"
        assert footer.update_button.toolTip() == "Update to v1.1.0"
        messages = []
        monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[1:3]))
        footer.update_button.click()
        assert messages == [("Update", "Finish the current separation before updating.")]
        footer.close()
    finally:
        set_language(before)


def test_packaged_install_requires_approval_and_idle_queue(application, monkeypatch):
    api = FakeUpdater()
    busy = [True]
    footer = UpdateFooter(lambda: busy[0], backend=api)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    discover(footer, application)
    footer.update_button.click()
    assert messages and not footer.installing
    busy[0] = False
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    footer.update_button.click()
    assert not footer.installing and not api.launched
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    changes = []
    started = []
    footer.busyChanged.connect(changes.append)
    footer.installationStarted.connect(lambda: started.append(True))
    footer.update_button.click()
    wait_for(application, lambda: bool(started))
    assert api.launched == [Path("test-installer.exe")] and changes == [True]
    assert api.discarded == []
    assert footer.may_close()
    footer.close()


def test_cancel_exit_does_not_launch_even_after_download_finishes(application, monkeypatch):
    api = FakeUpdater()
    began, finish = Event(), Event()
    def download(release, report, cancelled):
        began.set()
        assert finish.wait(5)
        assert cancelled()
        return Path("verified-but-cancelled.exe")

    api.download_install = download
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    parent = QWidget()
    footer = UpdateFooter(lambda: False, parent, backend=api)
    parent.show()
    discover(footer, application)
    state = []
    footer.busyChanged.connect(state.append)
    footer.update_button.click()
    wait_for(application, began.is_set)
    assert footer.installing and not footer.may_close()
    finish.set()
    wait_for(application, lambda: not footer.installing and not parent.isVisible())
    assert state == [True, False] and not api.launched
    assert api.discarded == [Path("verified-but-cancelled.exe")]


def test_installer_error_recovers_and_manual_check_explains_offline(application, monkeypatch):
    api = FakeUpdater()
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[2]))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    def failed_launch(path):
        raise OSError("installer busy")

    def failed_check():
        raise OSError("offline")

    api.launch_installer = failed_launch
    footer = UpdateFooter(lambda: False, backend=api)
    discover(footer, application)
    footer.update_button.click()
    wait_for(application, lambda: errors == ["installer busy"])
    assert not footer.installing and footer.update_button.isEnabled()
    assert api.discarded == [Path("test-installer.exe")]
    api.check_update = failed_check
    discover(footer, application)
    assert errors == ["installer busy"]
    footer.manual_check.trigger()
    wait_for(application, lambda: errors == ["installer busy", "offline"])
    footer.close()
