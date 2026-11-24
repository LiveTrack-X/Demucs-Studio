"""Version credit and in-app update controls."""

from __future__ import annotations

import sys
from threading import Event, Thread
from time import monotonic
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QMessageBox, QProgressDialog, QPushButton, QWidget,
)


class _UpdateSignals(QObject):
    checked = Signal(object, object)
    progress = Signal(float, str)
    downloaded = Signal(object, object)
    discarded = Signal(object, object)


class UpdateFooter(QWidget):
    installationStarted = Signal()
    busyChanged = Signal(bool)

    def __init__(self, is_busy: Callable[[], bool], parent=None, *, backend=None):
        super().__init__(parent)
        if backend is None:
            from . import updater as backend
        self._backend = backend
        self._is_busy = is_busy
        self._release = None
        self._checking = False
        self._notify_check = False
        self._close_after_cancel = False
        self._launched = False
        self._cancel = None
        self._dialog = None
        self._signals = _UpdateSignals()
        self._signals.checked.connect(self._checked)
        self._signals.progress.connect(self._progress)
        self._signals.downloaded.connect(self._downloaded)
        self._signals.discarded.connect(self._finish_download)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.update_button = QPushButton("Update")
        self.update_button.setObjectName("releaseUpdate")
        self.update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_button.clicked.connect(self._update)
        self.update_button.hide()
        self.credit = QPushButton(f"v{backend.VERSION} | Created by LiveTrack")
        self.credit.setObjectName("versionCredit")
        self.credit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.credit.setToolTip("GitHub 프로젝트 열기 · 오른쪽 클릭으로 업데이트 확인")
        self.credit.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(backend.REPO_URL)))
        self.credit.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.manual_check = QAction("업데이트 확인", self.credit)
        self.manual_check.triggered.connect(lambda: self.check_now(manual=True))
        self.credit.addAction(self.manual_check)
        row.addWidget(self.update_button)
        row.addWidget(self.credit)
        self.setStyleSheet("""
            QPushButton#versionCredit { background: transparent; border: 1px solid transparent;
                color: #657185; font-size: 11px; font-weight: 500; min-height: 16px; padding: 1px 2px; }
            QPushButton#versionCredit:hover { color: #3f4781; text-decoration: underline; }
            QPushButton#releaseUpdate { background: #ffad47; border: 1px solid #ee9d39;
                border-radius: 4px; color: #412800; font-size: 11px; font-weight: 700;
                min-height: 16px; padding: 1px 7px; }
            QPushButton#releaseUpdate:hover { background: #ffba63; }
            QPushButton#versionCredit:focus, QPushButton#releaseUpdate:focus { border-color: #6762b9; }
        """)
        self._startup = QTimer(self)
        self._startup.setSingleShot(True)
        self._startup.timeout.connect(self.check_now)
        self._periodic = QTimer(self)
        self._periodic.setInterval(6 * 60 * 60 * 1000)
        self._periodic.timeout.connect(self.check_now)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._periodic.isActive():
            self._startup.start(1200)
            self._periodic.start()

    @property
    def installing(self) -> bool:
        return self._cancel is not None or self._launched

    def check_now(self, manual=False):
        if self.installing:
            return
        self._startup.stop()
        self._notify_check |= manual
        if self._checking:
            return
        self._checking = True
        backend, signals = self._backend, self._signals

        def check():
            try:
                release = backend.check_update()
            except Exception as exc:
                signals.checked.emit(None, str(exc) or type(exc).__name__)
            else:
                signals.checked.emit(release, None)

        Thread(target=check, name="release-check", daemon=True).start()

    @Slot(object, object)
    def _checked(self, release, error):
        self._checking = False
        manual = self._notify_check
        self._notify_check = False
        if error:
            if manual:
                QMessageBox.warning(self, "업데이트 확인 실패", str(error))
            return
        self._release = release
        self.update_button.setVisible(release is not None)
        if release:
            self.update_button.setToolTip(f"v{release.version} 업데이트")
        if manual:
            message = (f"v{release.version}을 사용할 수 있습니다. Update 버튼을 눌러 주세요."
                       if release else "현재 사용할 수 있는 새 버전이 없습니다.")
            QMessageBox.information(self, "업데이트 확인", message)

    @Slot()
    def _update(self):
        release = self._release
        if not release or self.installing:
            return
        if self._is_busy():
            QMessageBox.information(self, "업데이트", "분리 작업을 마친 후 업데이트해 주세요.")
            return
        if not getattr(sys, "frozen", False):
            QDesktopServices.openUrl(QUrl(release.page_url))
            return
        size = release.size / 1024 ** 2
        answer = QMessageBox.question(
            self, "업데이트 설치", f"v{release.version} ({size:,.0f} MB)을 설치할까요?\n"
            "다운로드와 무결성 확인이 끝나면 앱을 닫고 설치 프로그램을 실행합니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if (answer != QMessageBox.StandardButton.Yes or self._release != release
                or self.installing or self._is_busy()):
            return
        cancel = Event()
        self._cancel = cancel
        self.busyChanged.emit(True)
        self.update_button.setEnabled(False)
        self.manual_check.setEnabled(False)
        dialog = QProgressDialog("업데이트 준비 중…", "취소", 0, 100, self.window())
        dialog.setWindowTitle(f"v{release.version} 업데이트")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setAutoReset(False)
        dialog.setAutoClose(False)
        dialog.setMinimumDuration(0)
        dialog.setMinimumWidth(360)
        dialog.canceled.connect(cancel.set)
        self._dialog = dialog
        dialog.setValue(0)
        dialog.show()
        backend, signals = self._backend, self._signals

        def download():
            last = 0.0

            def report(fraction, message):
                nonlocal last
                now = monotonic()
                if fraction >= 1 or now - last >= 0.1:
                    signals.progress.emit(fraction, message)
                    last = now

            try:
                path = backend.download_install(release, report, cancel.is_set)
            except Exception as exc:
                signals.downloaded.emit(None, str(exc) or type(exc).__name__)
            else:
                signals.downloaded.emit(path, None)

        Thread(target=download, name="release-download", daemon=True).start()

    @Slot(float, str)
    def _progress(self, fraction, message):
        if self._dialog and not self._cancel.is_set():
            percent = max(0, min(100, int(fraction * 100)))
            self._dialog.setLabelText(f"{message}  ·  {percent}%")
            self._dialog.setValue(percent)

    @Slot(object, object)
    def _downloaded(self, path, error):
        cancel = self._cancel
        if cancel is None:
            return
        self._dialog.hide()
        self._dialog.deleteLater()
        self._dialog = None
        if not cancel.is_set() and not error:
            if self._is_busy():
                error = "분리 작업이 진행 중입니다. 작업을 마친 후 다시 업데이트해 주세요."
            else:
                try:
                    self._backend.launch_installer(path)
                except Exception as exc:
                    error = str(exc) or type(exc).__name__
                else:
                    self._launched = True
        if self._launched:
            self._cancel = None
            self.installationStarted.emit()
            return
        if path is not None:
            # A cancelled download can finish verification just before the GUI
            # receives it. Release these large files before completing an exit.
            backend, signals = self._backend, self._signals

            def discard():
                try:
                    backend.discard_download(path)
                except Exception as exc:
                    signals.discarded.emit(error, str(exc) or type(exc).__name__)
                else:
                    signals.discarded.emit(error, None)

            Thread(target=discard, name="release-cleanup", daemon=True).start()
        else:
            self._finish_download(error, None)

    @Slot(object, object)
    def _finish_download(self, error, cleanup_error):
        cancelled = self._cancel.is_set()
        self._cancel = None
        self.update_button.setEnabled(True)
        self.manual_check.setEnabled(True)
        self.busyChanged.emit(False)
        if self._close_after_cancel:
            self._close_after_cancel = False
            QTimer.singleShot(0, self.window().close)
        elif cleanup_error:
            QMessageBox.warning(self, "업데이트 파일 정리 실패", str(cleanup_error))
        elif error and not cancelled:
            QMessageBox.warning(self, "업데이트 실패", str(error))

    def may_close(self) -> bool:
        """An explicit exit cancels outstanding downloads before closing the window."""
        if self._cancel is None:
            return True
        self._close_after_cancel = True
        self._cancel.set()
        if self._dialog:
            self._dialog.setLabelText("다운로드를 취소한 후 닫는 중…")
        return False
