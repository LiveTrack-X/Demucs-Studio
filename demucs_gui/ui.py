"""Korean desktop workspace for local Demucs jobs."""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QObject, QPointF, QRunnable, QSettings, QSize, Qt, QThread, QThreadPool,
    QTimer, QUrl, Signal,
)
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QComboBox, QDoubleSpinBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from .config import Options, QUALITY_OPTIONS, STEMS as MODE_STEMS
from .theme import STYLE, glyph
from .update_ui import UpdateFooter


VIDEO = {"mp4", "mkv", "mov", "webm", "avi", "m4v", "ts", "mts", "m2ts"}
AUDIO = {"mp3", "wav", "flac", "m4a", "aac", "ogg", "opus", "aif", "aiff", "wma"}
FORMAT_LABELS = {
    "audio": [("wav", "WAV"), ("mp3", "MP3"), ("aac", "AAC (.aac)"),
              ("m4a", "M4A (AAC)"), ("flac", "FLAC")],
    "video": [("mp4", "MP4"), ("mkv", "MKV")],
}
STEMS = {
    "all": "전체 스템 (각각 저장)", "vocals": "보컬", "accompaniment": "반주",
    "drums": "드럼", "bass": "베이스", "other": "그 외 악기", "guitar": "기타",
    "piano": "피아노",
}


def label(text, name=""):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    return widget


def button(text, name="", icon=None):
    widget = QPushButton(text)
    widget.setObjectName(name)
    if icon:
        widget.setIcon(glyph(icon))
        widget.setIconSize(QSize(16, 16))
    return widget


def heading(text):
    return label(text, "sectionTitle")


def divider():
    widget = QFrame()
    widget.setObjectName("line")
    widget.setFixedHeight(1)
    return widget


class ComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        paint = QPainter(self)
        paint.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint.setPen(QPen(QColor("#657187" if self.isEnabled() else "#a2a9b8"), 1.4))
        x, y = self.width() - 13, self.height() / 2
        paint.drawPolyline([QPointF(x - 3, y - 1), QPointF(x, y + 2), QPointF(x + 3, y - 1)])
        paint.end()


def combo(entries=()):
    box = ComboBox()
    box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    box.setMinimumContentsLength(4)
    box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    for value, title in entries:
        box.addItem(title, value)
    return box


def select(box, value):
    index = box.findData(value)
    if index >= 0:
        box.setCurrentIndex(index)


def time_text(seconds):
    s = max(0, int(seconds))
    h, remainder = divmod(s, 3600)
    m, s = divmod(remainder, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def disclosure(title, content):
    switch = QToolButton()
    switch.setObjectName("disclosure")
    switch.setText(title)
    switch.setCheckable(True)
    switch.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    switch.setArrowType(Qt.ArrowType.RightArrow)
    content.hide()

    def show_content(on):
        switch.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        content.setVisible(on)

    switch.toggled.connect(show_content)
    return switch


class ChoiceCards(QWidget):
    changed = Signal(str)

    def __init__(self, minimum_card_width, compact=False):
        super().__init__()
        self.minimum_card_width = minimum_card_width
        self.compact = compact
        self.group = QButtonGroup(self)
        self.buttons = {}
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        self.columns = 0

    def populate(self, choices, selected):
        if list(self.buttons) != [key for key, _, _ in choices]:
            for card in self.buttons.values():
                self.group.removeButton(card)
                self.grid.removeWidget(card)
                card.hide()
                card.deleteLater()
            self.buttons = {}
            for key, title, detail in choices:
                card = QPushButton()
                card.setObjectName("choiceCard")
                card.setProperty("compact", self.compact)
                card.setCheckable(True)
                card.setAccessibleName(title)
                card.setAccessibleDescription(detail)
                card.setToolTip(f"{title} · {detail}" if detail else title)
                card.setMinimumHeight(30 if self.compact else 51)
                card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
                info = QVBoxLayout(card)
                info.setContentsMargins(8, 3, 8, 3)
                info.setSpacing(0)
                for text, name in ((title, "cardTitle"), (detail, "cardDetail")):
                    if text:
                        item = label(text, name)
                        item.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                        if self.compact:
                            item.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        info.addWidget(item)
                self.group.addButton(card)
                card.clicked.connect(lambda _checked, value=key: self.changed.emit(value))
                self.buttons[key] = card
            self.columns = 0
            self.reflow()
        self.choose(selected)

    def choose(self, value):
        self.buttons[value].setChecked(True)

    def value(self):
        return next((key for key, card in self.buttons.items() if card.isChecked()), None)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        count = len(self.buttons)
        if not count:
            return
        columns = min(count, max(1, (self.width() + 6) // (self.minimum_card_width + 6)))
        if columns == 3 and count == 4:
            columns = 2
        if columns == self.columns:
            return
        for col in range(self.grid.columnCount()):
            self.grid.setColumnStretch(col, 0)
        for i, card in enumerate(self.buttons.values()):
            self.grid.removeWidget(card)
            self.grid.addWidget(card, i // columns, i % columns)
        for col in range(columns):
            self.grid.setColumnStretch(col, 1)
        self.columns = columns
        rows = (count + columns - 1) // columns
        row_height = 34 if self.compact else 56
        self.setFixedHeight(rows * row_height + (rows - 1) * self.grid.spacing())


MODEL_CARDS = [
    ("htdemucs", "표준", "빠른 분리"),
    ("htdemucs_ft", "최고 품질", "정밀한 분리"),
    ("htdemucs_6s", "6스템 모델", "기타·피아노 추가"),
    ("mdx_extra", "MDX Extra", "MDX 계열 모델"),
]
MODE_CARDS = [
    ("2", "2스템", "보컬 · 반주"),
    ("4", "4스템", "보컬 · 드럼 · 베이스 등"),
    ("6", "6스템", "기타 · 피아노 포함"),
]
FORMAT_DESCRIPTIONS = {
    "wav": "무손실 PCM", "mp3": "손실 압축", "aac": "ADTS 스트림",
    "m4a": "AAC 컨테이너", "flac": "무손실 압축",
    "mp4": "MP4 컨테이너", "mkv": "Matroska 컨테이너",
}
BUILTIN_PRESETS = {
    "vocal": ("보컬만 추출", "2", "vocals", 1),
    "backing": ("반주만 추출", "2", "accompaniment", 1),
    "instruments": ("악기별 분리", "4", "all", 5),
}


class SettingsPanel(QFrame):
    def __init__(self, settings):
        super().__init__()
        self.setObjectName("panel")
        self.settings = settings
        self.loading = True
        self.qualities = {}
        self.formats = {"audio": "wav", "video": "mp4"}
        self.kind = "audio"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        title = heading("분리 · 내보내기 설정")
        title.setContentsMargins(16, 13, 16, 10)
        outer.addWidget(title)
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("settingsBody")
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 2, 16, 14)
        layout.setSpacing(7)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(5)
        self.presets = combo()
        self.presets.setAccessibleName("프리셋 선택")
        self.apply_button = button("적용")
        self.save_button = button("새로 저장")
        self.manage_button = QToolButton()
        self.manage_button.setText("⋯")
        self.manage_button.setObjectName("presetManage")
        self.manage_button.setAccessibleName("사용자 프리셋 관리")
        self.manage_button.setToolTip("사용자 프리셋 이름 변경 또는 삭제")
        self.manage_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.manage_button)
        menu.addAction("이름 변경", self.rename_preset_dialog)
        menu.addAction("삭제", self.delete_preset_dialog)
        self.manage_button.setMenu(menu)
        preset_row.addWidget(label("프리셋", "groupTitle"))
        preset_row.addWidget(self.presets, 1)
        preset_row.addWidget(self.apply_button)
        preset_row.addWidget(self.save_button)
        preset_row.addWidget(self.manage_button)
        layout.addLayout(preset_row)
        self.presets.currentIndexChanged.connect(self.preset_controls)
        self.apply_button.clicked.connect(self.apply_selected_preset)
        self.save_button.clicked.connect(self.save_preset_dialog)
        self.refresh_presets()
        layout.addWidget(divider())

        layout.addWidget(label("모델", "groupTitle"))
        self.model = ChoiceCards(96)
        self.model.populate(MODEL_CARDS, "htdemucs_ft")
        self.model.changed.connect(self.model_chosen)
        layout.addWidget(self.model)

        layout.addWidget(label("분리할 스템", "groupTitle"))
        self.mode = ChoiceCards(118)
        self.mode.populate(MODE_CARDS, "2")
        self.mode.buttons["6"].setToolTip("6스템을 선택하면 6스템 모델로 전환합니다.")
        self.mode.changed.connect(self.mode_chosen)
        layout.addWidget(self.mode)
        stems = QHBoxLayout()
        stems.addWidget(label("저장할 스템"))
        self.stem = combo()
        self.stem.setAccessibleName("저장할 스템")
        stems.addWidget(self.stem, 1)
        layout.addLayout(stems)
        layout.addWidget(divider())

        kind_row = QHBoxLayout()
        kind_row.addWidget(label("출력 형식", "groupTitle"))
        kind_row.addStretch()
        self.group = QButtonGroup(self)
        self.kind_buttons = {}
        for key, title, icon in [("audio", "음원", "wave"), ("video", "영상", "video")]:
            toggle = button(title, "seg", icon)
            toggle.setCheckable(True)
            toggle.clicked.connect(lambda checked, selected=key: self.set_kind(selected))
            self.group.addButton(toggle)
            self.kind_buttons[key] = toggle
            kind_row.addWidget(toggle)
        layout.addLayout(kind_row)
        self.format = ChoiceCards(79)
        self.format.changed.connect(self.update_format)
        layout.addWidget(self.format)
        self.video_note = label("원본 화면에 선택한 스템을 넣어 저장합니다.", "subtle")
        self.video_note.setWordWrap(True)
        layout.addWidget(self.video_note)
        self.quality_label = label("", "groupTitle")
        layout.addWidget(self.quality_label)
        self.quality = ChoiceCards(75, compact=True)
        self.quality.changed.connect(self.quality_changed)
        layout.addWidget(self.quality)
        layout.addWidget(divider())

        folder_row = QHBoxLayout()
        folder_row.addWidget(label("저장 위치", "groupTitle"))
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("원본 옆 separated 폴더")
        self.folder.setClearButtonEnabled(True)
        self.folder.setAccessibleName("출력 폴더")
        browse = button("", icon="folder")
        browse.setAccessibleName("출력 폴더 선택")
        browse.setToolTip("출력 폴더 선택")
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)
        advanced = QWidget()
        self.advanced_toggle = disclosure("고급 설정", advanced)
        layout.addWidget(self.advanced_toggle)
        details = QGridLayout(advanced)
        details.setContentsMargins(0, 0, 0, 3)
        details.setVerticalSpacing(6)
        self.model_name = label("")
        self.device = combo([("auto", "자동 (CUDA 우선)"), ("cuda", "GPU (CUDA)"), ("cpu", "CPU")])
        self.shifts = QSpinBox()
        self.shifts.setRange(0, 10)
        self.shifts.setToolTip("입력 위치를 바꿔 반복 계산합니다. 값이 크면 시간이 더 걸립니다.")
        self.overlap = QDoubleSpinBox()
        self.overlap.setRange(0, 0.99)
        self.overlap.setDecimals(2)
        self.overlap.setSingleStep(0.05)
        self.overlap.setToolTip("분리할 오디오 구간이 서로 겹치는 비율")
        for i, (title, widget) in enumerate([("모델 이름", self.model_name), ("장치", self.device),
                                             ("Shifts", self.shifts), ("Overlap", self.overlap)]):
            details.addWidget(label(title), i, 0)
            details.addWidget(widget, i, 1)
        details.setColumnStretch(1, 1)
        layout.addWidget(advanced)
        layout.addStretch()
        browse.clicked.connect(self.browse_output)
        for signal in (self.stem.currentIndexChanged, self.device.currentIndexChanged,
                       self.shifts.valueChanged, self.overlap.valueChanged, self.folder.textChanged):
            signal.connect(self.save)
        self.restore()
        self.loading = False

    def set_kind(self, kind):
        self.kind = kind
        self.kind_buttons[kind].setChecked(True)
        choices = [(key, title, FORMAT_DESCRIPTIONS[key]) for key, title in FORMAT_LABELS[kind]]
        self.format.populate(choices, self.formats[kind])
        self.video_note.setVisible(kind == "video")
        self.update_format(self.format.value())

    def update_format(self, fmt):
        self.formats[self.kind] = fmt
        lossless = fmt in ("wav", "flac")
        self.quality_label.setText("비트 깊이" if lossless else "오디오 비트레이트")
        entries = QUALITY_OPTIONS[fmt]
        quality = self.qualities.get(fmt, "24" if lossless else "320")
        if quality not in dict(entries):
            quality = entries[0][0]
        self.quality.populate([(key, title, "") for key, title in entries], quality)
        self.quality_changed(quality)

    def quality_changed(self, quality):
        self.qualities[self.format.value()] = quality
        self.save()

    def model_chosen(self, model):
        if model == "htdemucs_6s":
            self.mode.choose("6")
        elif self.mode.value() == "6":
            self.mode.choose("4")
        self.update_stems()

    def mode_chosen(self, mode):
        if mode == "6":
            self.model.choose("htdemucs_6s")
        self.update_stems()

    def update_stems(self):
        previous = self.stem.currentData()
        self.stem.blockSignals(True)
        self.stem.clear()
        for key in ["all", *MODE_STEMS[self.mode.value()]]:
            self.stem.addItem(STEMS[key], key)
        select(self.stem, previous)
        self.stem.blockSignals(False)
        self.model_name.setText(self.model.value())
        self.save()

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "출력 폴더 선택", self.folder.text())
        if path:
            self.folder.setText(path)

    def options(self):
        return Options(
            model=self.model.value(), stem_mode=self.mode.value(),
            selected_stem=self.stem.currentData(), vocals_only=self.stem.currentData() == "vocals",
            shifts=self.shifts.value(), overlap=self.overlap.value(), device=self.device.currentData(),
            output_kind=self.kind, audio_format=self.formats["audio"], video_format=self.formats["video"],
            quality=self.quality.value(), output_dir=self.folder.text().strip(),
        )

    def apply_settings(self, config, qualities):
        config.validate()
        self.loading = True
        try:
            self.qualities = dict(qualities)
            self.formats.update(audio=config.audio_format, video=config.video_format)
            self.qualities[config.format] = config.quality
            self.set_kind(config.output_kind)
            self.model.choose(config.model)
            self.mode.choose(config.stem_mode)
            self.update_stems()
            select(self.stem, "vocals" if config.vocals_only else config.selected_stem)
            self.shifts.setValue(config.shifts)
            self.overlap.setValue(config.overlap)
            select(self.device, config.device)
            self.folder.setText(config.output_dir)
        finally:
            self.loading = False
        self.save()

    def save(self, *_):
        if not self.loading:
            self.settings.setValue("options", json.dumps(asdict(self.options()), ensure_ascii=False))
            self.settings.setValue("qualities", json.dumps(self.qualities))

    def restore(self):
        try:
            opts = Options(**json.loads(self.settings.value("options", "{}")))
            self.apply_settings(opts, json.loads(self.settings.value("qualities", "{}")))
        except (TypeError, ValueError, KeyError):
            self.apply_settings(Options(), {})

    def custom_presets(self):
        self.settings.sync()
        try:
            presets = json.loads(self.settings.value("userPresets", "{}"))
            return presets if isinstance(presets, dict) else {}
        except (TypeError, ValueError):
            return {}

    def refresh_presets(self, selected=None):
        self.presets.blockSignals(True)
        self.presets.clear()
        self.presets.addItem("프리셋 선택", "")
        for key, (title, *_) in BUILTIN_PRESETS.items():
            self.presets.addItem(title, "builtin/" + key)
        for name in sorted(self.custom_presets(), key=str.casefold):
            self.presets.addItem("내 프리셋 · " + name, "user/" + name)
        select(self.presets, selected)
        self.presets.blockSignals(False)
        self.preset_controls()

    def preset_controls(self, *_):
        key = self.presets.currentData() or ""
        self.apply_button.setEnabled(bool(key))
        self.manage_button.setEnabled(key.startswith("user/"))

    def apply_selected_preset(self):
        source, _, name = (self.presets.currentData() or "").partition("/")
        if source == "builtin":
            _, mode, stem, shifts = BUILTIN_PRESETS[name]
            options = self.options()
            options.model = "htdemucs_ft"
            options.stem_mode = mode
            options.selected_stem = stem
            options.vocals_only = stem == "vocals"
            options.shifts = shifts
            options.overlap = 0.25
            self.apply_settings(options, self.qualities)
        elif source == "user":
            try:
                data = self.custom_presets()[name]
                self.apply_settings(Options(**data["options"]), data["qualities"])
            except (TypeError, ValueError, KeyError):
                QMessageBox.warning(self, "프리셋", "저장된 프리셋을 불러올 수 없습니다.")
                self.refresh_presets()

    def write_presets(self, presets, name=None):
        self.settings.setValue("userPresets", json.dumps(presets, ensure_ascii=False))
        self.settings.sync()
        self.refresh_presets("user/" + name if name else None)

    def confirm(self, title, message, action):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(message)
        proceed = dialog.addButton(action, QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.exec()
        return dialog.clickedButton() == proceed

    def ask_preset_name(self, initial=""):
        dialog = QInputDialog(self)
        dialog.setWindowTitle("사용자 프리셋")
        dialog.setLabelText("프리셋 이름")
        dialog.setTextValue(initial)
        dialog.setOkButtonText("저장")
        dialog.setCancelButtonText("취소")
        return dialog.textValue().strip() if dialog.exec() else ""

    def save_preset_dialog(self):
        name = self.ask_preset_name()
        if not name:
            return
        presets = self.custom_presets()
        if name in presets and not self.confirm("프리셋 덮어쓰기", f"‘{name}’ 프리셋을 현재 설정으로 바꿀까요?", "덮어쓰기"):
            return
        presets[name] = {"options": asdict(self.options()), "qualities": self.qualities.copy()}
        self.write_presets(presets, name)

    def rename_preset_dialog(self):
        old = (self.presets.currentData() or "").removeprefix("user/")
        presets = self.custom_presets()
        if old not in presets:
            return
        name = self.ask_preset_name(old)
        if not name or name == old:
            return
        if name in presets and not self.confirm("프리셋 덮어쓰기", f"기존 ‘{name}’ 프리셋을 바꿀까요?", "덮어쓰기"):
            return
        presets[name] = presets.pop(old)
        self.write_presets(presets, name)

    def delete_preset_dialog(self):
        name = (self.presets.currentData() or "").removeprefix("user/")
        presets = self.custom_presets()
        if name in presets and self.confirm("프리셋 삭제", f"‘{name}’ 프리셋을 삭제할까요?", "삭제"):
            del presets[name]
            self.write_presets(presets)


class PreviewPane(QWidget):
    message = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        strip = QHBoxLayout()
        headphones = label("")
        headphones.setPixmap(glyph("headphones").pixmap(18, 18))
        strip.addWidget(headphones)
        strip.addWidget(label("미리듣기", "groupTitle"))
        self.tracks = combo()
        self.tracks.setMinimumWidth(116)
        self.tracks.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        strip.addWidget(self.tracks)
        strip.addStretch()
        self.open_dir = button("결과 폴더", "textAction", "folder")
        strip.addWidget(self.open_dir)
        layout.addLayout(strip)
        controls = QHBoxLayout()
        self.play = button("", icon="play")
        self.play.setAccessibleName("재생")
        self.play.setToolTip("재생")
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setAccessibleName("재생 위치")
        self.time = label("00:00 / 00:00", "timing")
        controls.addWidget(self.play)
        controls.addWidget(self.seek, 1)
        controls.addWidget(self.time)
        layout.addLayout(controls)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.source = None
        self.pending = None
        self.output_folder = None
        self.play.clicked.connect(self.toggle)
        self.tracks.currentIndexChanged.connect(self.switch)
        self.open_dir.clicked.connect(self.open_results)
        self.player.durationChanged.connect(self.update_clock)
        self.player.positionChanged.connect(self.update_clock)
        self.player.playbackStateChanged.connect(self.sync_play)
        self.player.mediaStatusChanged.connect(self.loaded)
        self.player.errorOccurred.connect(self.player_error)
        self.seek.sliderReleased.connect(lambda: self.player.setPosition(self.seek.value()))
        self.set_entry(None)

    def open_results(self):
        if self.output_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_folder)))

    def toggle(self):
        if self.player.isPlaying():
            self.player.pause()
        else:
            self.player.play()

    def update_clock(self, *_):
        duration = max(0, self.player.duration())
        self.seek.setRange(0, min(duration, 2**31 - 1))
        if not self.seek.isSliderDown():
            self.seek.setValue(min(self.player.position(), 2**31 - 1))
        self.time.setText(f"{time_text(self.player.position()/1000)} / {time_text(duration/1000)}")

    def sync_play(self, *_):
        active = self.player.isPlaying()
        title = "일시 정지" if active else "재생"
        self.play.setIcon(glyph("pause" if active else "play"))
        self.play.setAccessibleName(title)
        self.play.setToolTip(title)

    def player_error(self, error, text):
        if error != QMediaPlayer.Error.NoError:
            self.message.emit(f"미리듣기 오류 · {text}")

    def loaded(self, status):
        if self.pending and status in (QMediaPlayer.MediaStatus.LoadedMedia,
                                       QMediaPlayer.MediaStatus.BufferedMedia):
            source, position, resume = self.pending
            if self.player.source() != source:
                return
            self.pending = None
            self.player.setPosition(position)
            if resume:
                self.player.play()

    def switch(self, *_):
        path = self.tracks.currentData()
        if path:
            url = QUrl.fromLocalFile(str(path))
            if self.player.source() != url:
                self.pending = (url, self.player.position(), self.player.isPlaying())
                self.player.setSource(url)

    def set_entry(self, entry, prefer_result=False):
        previous = self.tracks.currentData()
        same = entry is not None and self.source == entry.path
        if not same:
            self.pending = None
            self.player.stop()
            self.player.setSource(QUrl())
        self.source = entry.path if entry else None
        self.tracks.blockSignals(True)
        self.tracks.clear()
        self.output_folder = None
        if entry:
            self.tracks.addItem("원본", str(entry.path))
            for stem, path in entry.outputs.items():
                self.tracks.addItem(STEMS.get(stem, stem), str(path))
                self.output_folder = path.parent
            if prefer_result and entry.outputs:
                self.tracks.setCurrentIndex(1)
            elif same:
                select(self.tracks, previous)
        else:
            self.tracks.addItem("파일 선택", None)
        self.tracks.blockSignals(False)
        self.play.setEnabled(bool(entry))
        self.tracks.setEnabled(bool(entry))
        self.seek.setEnabled(bool(entry))
        self.open_dir.setEnabled(bool(self.output_folder))
        self.switch()


@dataclass
class Entry:
    path: Path
    status: str = "대기"
    duration: float | None = None
    error: str = ""
    outputs: dict[str, Path] = field(default_factory=dict)


class ProbeSignals(QObject):
    ready = Signal(object, object)


class ProbeTask(QRunnable):
    def __init__(self, path, signals):
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self):
        try:
            from .media import probe
            duration = probe(self.path).duration
        except Exception:
            duration = None
        self.signals.ready.emit(self.path, duration)


class FileWorker(QThread):
    progress = Signal(float, str)

    def __init__(self, path, options, parent):
        super().__init__(parent)
        self.path = path
        self.options = options
        self.stop = threading.Event()
        self.outputs = {}
        self.status = "실패"
        self.error = ""

    def run(self):
        latest = 0.0

        def report(fraction, detail):
            nonlocal latest
            now = time.monotonic()
            if now - latest >= 0.12 or fraction >= 1:
                self.progress.emit(max(0, min(1, fraction)), detail)
                latest = now

        try:
            from .pipeline import process_file
            self.outputs = process_file(self.path, self.options, report, self.stop.is_set)
            self.status = "완료"
        except InterruptedError:
            self.status = "취소"
        except Exception as error:
            self.error = str(error).strip() or type(error).__name__


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or QSettings("Demucs Studio", "Demucs Studio")
        self.entries = []
        self.worker = None
        self.batch = []
        self.batch_options = None
        self.batch_index = 0
        self.active = False
        self.stop_batch = False
        self.close_after_stop = False
        self.fraction = 0.0
        self.last_stage = ""
        self.probe_pool = QThreadPool(self)
        self.probe_pool.setMaxThreadCount(2)
        self.probes = ProbeSignals(self)
        self.probes.ready.connect(self.probed)
        self.setWindowTitle("Demucs Studio · 음원 분리")
        self.setWindowIcon(glyph("brand", size=48))
        self.setAcceptDrops(True)
        self.setMinimumSize(780, 548)
        self.setStyleSheet(STYLE)
        canvas = QWidget()
        canvas.setObjectName("canvas")
        self.setCentralWidget(canvas)
        outer = QVBoxLayout(canvas)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.make_header())
        workspace = QVBoxLayout()
        workspace.setContentsMargins(15, 14, 15, 13)
        workspace.setSpacing(10)
        outer.addLayout(workspace, 1)
        middle = QHBoxLayout()
        middle.setSpacing(12)
        workspace.addLayout(middle, 1)
        middle.addWidget(self.make_queue(), 5)
        self.options_panel = SettingsPanel(self.settings)
        self.options_panel.setMinimumWidth(332)
        middle.addWidget(self.options_panel, 6)
        workspace.addWidget(self.make_footer())
        self.update_footer = UpdateFooter(lambda: self.active, self)
        self.update_footer.installationStarted.connect(self.close)
        self.update_footer.busyChanged.connect(lambda _: self.update_actions())
        workspace.addWidget(self.update_footer, 0, Qt.AlignmentFlag.AlignRight)
        self.clock = QTimer(self)
        self.clock.setInterval(500)
        self.clock.timeout.connect(self.update_total)
        self.preview.message.connect(self.log_message)
        self.queue.itemSelectionChanged.connect(self.selection_changed)
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.browse_files)
        self.queue.addAction(self.remove_action)
        self.update_actions()
        screen = self.screen().availableGeometry()
        self.resize(min(1200, screen.width() - 24), min(800, screen.height() - 55))

    def make_header(self):
        header = QFrame()
        header.setObjectName("topbar")
        bar = QHBoxLayout(header)
        bar.setContentsMargins(21, 10, 22, 10)
        bar.setSpacing(10)
        logo = label("")
        logo.setPixmap(glyph("brand", size=33).pixmap(33, 33))
        bar.addWidget(logo)
        bar.addWidget(label("Demucs Studio", "brandTitle"))
        split = QFrame()
        split.setFixedSize(1, 16)
        split.setObjectName("brandDivider")
        bar.addWidget(split)
        bar.addWidget(label("음원 분리 작업실", "brandSub"))
        bar.addStretch()
        local = QFrame()
        local.setFixedSize(6, 6)
        local.setObjectName("localDot")
        bar.addWidget(local)
        bar.addWidget(label("로컬 처리", "local"))
        return header

    def make_queue(self):
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 13, 15, 12)
        layout.setSpacing(9)
        title = QHBoxLayout()
        title.setSpacing(6)
        title.addWidget(heading("작업 대기열"))
        self.count = label("0", "count")
        title.addWidget(self.count)
        title.addStretch()
        self.retry = button("다시 대기", "textAction")
        self.remove = button("제거", "textAction")
        self.clear = button("비우기", "textAction")
        for btn in [self.retry, self.remove, self.clear]:
            title.addWidget(btn)
        layout.addLayout(title)
        self.drop_area = QFrame()
        self.drop_area.setObjectName("drop")
        drop_row = QHBoxLayout(self.drop_area)
        drop_row.setContentsMargins(14, 13, 14, 13)
        drop_row.setSpacing(11)
        upload = label("")
        upload.setPixmap(glyph("upload", "#5d57b8", 26).pixmap(26, 26))
        drop_row.addWidget(upload)
        drop_copy = QVBoxLayout()
        drop_copy.setSpacing(3)
        drop_text = label("영상·음원 파일을 여기에 놓으세요", "dropTitle")
        drop_text.setWordWrap(True)
        drop_copy.addWidget(drop_text)
        drop_copy.addWidget(label("MP4 · MKV · WAV · FLAC · MP3 외", "dropHint"))
        drop_row.addLayout(drop_copy, 1)
        self.add = button("파일 추가", icon="plus")
        self.add.setToolTip("파일 추가 (Ctrl+O)")
        drop_row.addWidget(self.add)
        layout.addWidget(self.drop_area)
        self.queue = QTableWidget(0, 4)
        self.queue.setHorizontalHeaderLabels(["파일 이름", "길이", "상태", "진행률"])
        self.queue.verticalHeader().setVisible(False)
        self.queue.verticalHeader().setDefaultSectionSize(36)
        header = self.queue.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setMinimumSectionSize(40)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in [(1, 63), (2, 77), (3, 77)]:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.queue.setColumnWidth(col, width)
        self.queue.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue.setShowGrid(False)
        self.queue.setFrameShape(QFrame.Shape.NoFrame)
        self.queue.setMinimumWidth(0)
        self.queue.setMinimumHeight(70)
        self.queue.setWordWrap(False)
        self.queue.setAccessibleName("배치 작업 대기열")
        self.queue.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue.customContextMenuRequested.connect(self.queue_menu)
        self.remove_action = QAction("대기열에서 제거", self.queue)
        self.remove_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self.remove_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.remove_action.triggered.connect(self.remove_selected)
        layout.addWidget(self.queue, 1)
        layout.addWidget(divider())
        self.preview = PreviewPane()
        layout.addWidget(self.preview)
        self.add.clicked.connect(self.browse_files)
        self.retry.clicked.connect(self.retry_selected)
        self.remove.clicked.connect(self.remove_selected)
        self.clear.clicked.connect(self.clear_queue)
        return panel

    def make_footer(self):
        footer = QFrame()
        footer.setObjectName("footer")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(15, 9, 15, 10)
        layout.setSpacing(5)
        row = QHBoxLayout()
        detail = QVBoxLayout()
        detail.setSpacing(1)
        self.stage = label("작업 대기 중", "groupTitle")
        self.stage.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        detail.addWidget(self.stage)
        self.timing = label("경과 00:00   ·   남은 시간 —", "timing")
        detail.addWidget(self.timing)
        row.addLayout(detail, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1200)
        self.log.setFixedHeight(83)
        self.log_toggle = disclosure("작업 기록", self.log)
        row.addWidget(self.log_toggle)
        self.cancel = QToolButton()
        self.cancel.setObjectName("cancel")
        self.cancel.setText("취소")
        self.cancel.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.cancel)
        menu.addAction("현재 파일 취소 · 다음 파일 계속", lambda: self.cancel_work(False))
        menu.addAction("현재 파일 취소 · 전체 중지", lambda: self.cancel_work(True))
        self.cancel.setMenu(menu)
        self.cancel.setToolTip("현재 파일 또는 전체 작업 취소")
        row.addWidget(self.cancel)
        self.start = button("분리 시작", "primary")
        self.start.setIcon(glyph("play", "white", 15))
        self.start.clicked.connect(self.start_batch)
        row.addWidget(self.start)
        layout.addLayout(row)
        self.total = QProgressBar()
        self.total.setRange(0, 1000)
        self.total.setValue(0)
        self.total.setTextVisible(False)
        self.total.setAccessibleName("전체 작업 진행률")
        layout.addWidget(self.total)
        layout.addWidget(self.log)
        return footer

    def browse_files(self):
        if self.active:
            return
        extensions = " ".join(f"*.{ext}" for ext in sorted(AUDIO | VIDEO))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "영상·음원 파일 추가", self.settings.value("lastInput", ""),
            f"영상·음원 ({extensions});;모든 파일 (*)")
        if paths:
            self.settings.setValue("lastInput", str(Path(paths[0]).parent))
            self.add_files(paths)

    def set_drag(self, over):
        if self.drop_area.property("over") != over:
            self.drop_area.setProperty("over", over)
            self.drop_area.style().unpolish(self.drop_area)
            self.drop_area.style().polish(self.drop_area)

    def dragEnterEvent(self, event):
        if not self.active and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            self.set_drag(True)

    def dragLeaveEvent(self, event):
        self.set_drag(False)
        event.accept()

    def dropEvent(self, event):
        self.set_drag(False)
        if not self.active:
            self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()

    def add_files(self, paths):
        if self.active:
            return
        first = len(self.entries)
        known = {entry.path for entry in self.entries}
        rejected = []
        for raw in paths:
            path = Path(raw).resolve()
            if path in known:
                continue
            if not path.is_file() or path.suffix.lower()[1:] not in AUDIO | VIDEO:
                rejected.append(path.name)
                continue
            known.add(path)
            row = len(self.entries)
            entry = Entry(path)
            self.entries.append(entry)
            self.queue.insertRow(row)
            name = QTableWidgetItem(glyph("video" if path.suffix.lower()[1:] in VIDEO else "wave"), path.name)
            name.setToolTip(str(path))
            self.queue.setItem(row, 0, name)
            self.queue.setItem(row, 1, QTableWidgetItem("…"))
            self.queue.setItem(row, 2, QTableWidgetItem(entry.status))
            cell = QWidget()
            bar_layout = QHBoxLayout(cell)
            bar_layout.setContentsMargins(5, 0, 7, 0)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setAccessibleName(f"{path.name} 진행률")
            bar_layout.addWidget(bar)
            self.queue.setCellWidget(row, 3, cell)
            self.probe_pool.start(ProbeTask(path, self.probes))
        if first == 0 and self.entries:
            self.queue.selectRow(0)
        if rejected:
            self.log_message("지원하지 않는 파일 · " + ", ".join(rejected))
            self.log_toggle.setChecked(True)
        self.update_actions()

    def probed(self, path, duration):
        for row, entry in enumerate(self.entries):
            if entry.path == path:
                entry.duration = duration
                self.queue.item(row, 1).setText("—" if duration is None else time_text(duration))
                return

    def selected_rows(self):
        return sorted(index.row() for index in self.queue.selectionModel().selectedRows())

    def selection_changed(self):
        rows = self.selected_rows()
        row = self.queue.currentRow()
        if row not in rows:
            row = rows[0] if rows else -1
        self.preview.set_entry(self.entries[row] if 0 <= row < len(self.entries) else None)
        self.update_actions()

    def queue_menu(self, point):
        if self.active or not self.queue.indexAt(point).isValid():
            return
        menu = QMenu(self)
        again = menu.addAction("선택 파일 다시 대기", self.retry_selected)
        again.setEnabled(self.retry.isEnabled())
        menu.addAction(self.remove_action)
        menu.exec(self.queue.viewport().mapToGlobal(point))

    def remove_selected(self):
        if self.active:
            return
        self.queue.blockSignals(True)
        for row in reversed(self.selected_rows()):
            self.entries.pop(row)
            self.queue.removeRow(row)
        self.queue.blockSignals(False)
        self.selection_changed()
        self.reset_footer()

    def clear_queue(self):
        if self.active:
            return
        self.entries.clear()
        self.queue.setRowCount(0)
        self.selection_changed()
        self.reset_footer()

    def retry_selected(self):
        if self.active:
            return
        for row in self.selected_rows():
            entry = self.entries[row]
            entry.status = "대기"
            entry.error = ""
            self.set_row(entry, 0)
        self.reset_footer()
        self.update_actions()

    def reset_footer(self):
        self.total.setValue(0)
        self.stage.setText("작업 대기 중")
        self.timing.setText("경과 00:00   ·   남은 시간 —")

    def update_actions(self):
        rows = self.selected_rows()
        self.add.setEnabled(not self.active)
        self.clear.setEnabled(bool(self.entries) and not self.active)
        self.remove.setEnabled(bool(rows) and not self.active)
        self.remove_action.setEnabled(self.remove.isEnabled())
        self.retry.setEnabled(not self.active and any(self.entries[i].status != "대기" for i in rows))
        self.options_panel.setEnabled(not self.active)
        self.cancel.setEnabled(self.active and not self.stop_batch)
        self.start.setEnabled(not self.active and not self.update_footer.installing
                              and any(e.status == "대기" for e in self.entries))
        self.count.setText(str(len(self.entries)))

    def start_batch(self):
        if self.active or self.update_footer.installing:
            return
        self.batch = [e for e in self.entries if e.status == "대기"]
        if not self.batch:
            return
        self.batch_options = self.options_panel.options()
        self.active = True
        self.batch_index = 0
        self.stop_batch = False
        self.began = time.monotonic()
        self.fraction = 0.0
        self.log_message(f"분리 시작 · {len(self.batch)}개 · {self.batch_options.model} · "
                         f"{self.batch_options.format.upper()} · {self.batch_options.quality}")
        self.clock.start()
        self.update_actions()
        self.next_file()

    def next_file(self):
        if self.stop_batch or self.batch_index >= len(self.batch):
            self.finish_batch()
            return
        entry = self.batch[self.batch_index]
        entry.status = "처리 중"
        self.last_stage = ""
        self.fraction = 0.0
        self.set_row(entry, 0)
        self.log_message(f"{entry.path.name} · 처리 시작")
        self.on_progress(0, "시작 중")
        self.worker = FileWorker(entry.path, self.batch_options, self)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.file_finished)
        self.worker.start()

    def set_row(self, entry, value=None):
        row = self.entries.index(entry)
        cell = self.queue.item(row, 2)
        status = f"{entry.status} · {entry.error}" if entry.error else entry.status
        cell.setText(status)
        cell.setToolTip(status)
        if value is not None:
            bar = self.queue.cellWidget(row, 3).findChild(QProgressBar)
            bar.setValue(int(value * 100))
            bar.setToolTip(f"{int(value * 100)}%")

    def on_progress(self, fraction, detail):
        if not self.active or self.batch_index >= len(self.batch):
            return
        entry = self.batch[self.batch_index]
        self.fraction = fraction
        self.stage.setText(f"{self.batch_index + 1}/{len(self.batch)}  {entry.path.name}  ·  {detail}")
        self.stage.setToolTip(self.stage.text())
        self.set_row(entry, fraction)
        if detail and detail != self.last_stage:
            self.last_stage = detail
            self.log_message(detail)
        self.update_total()

    def update_total(self):
        if not self.active:
            return
        progress = min(1.0, (self.batch_index + self.fraction) / len(self.batch))
        elapsed = time.monotonic() - self.began
        remaining = time_text(elapsed * (1 - progress) / progress) if progress > 0.005 else "계산 중"
        self.total.setValue(int(progress * 1000))
        self.timing.setText(f"전체 {progress:.0%}   ·   경과 {time_text(elapsed)}   ·   예상 남은 시간 {remaining}")

    def cancel_work(self, all_files):
        if self.worker:
            self.stop_batch = self.stop_batch or all_files
            self.worker.stop.set()
            self.stage.setText("취소 중…")
            self.log_message("전체 작업 중지 요청" if all_files else "현재 파일 취소 요청")
            self.update_actions()

    def file_finished(self):
        worker = self.worker
        entry = self.batch[self.batch_index]
        entry.status = worker.status
        entry.error = worker.error
        if worker.status == "완료":
            entry.outputs = worker.outputs
        self.set_row(entry, 1 if entry.status == "완료" else None)
        self.log_message(f"{entry.path.name} · {entry.status}" + (f" · {entry.error}" if entry.error else ""))
        if entry.error:
            self.log_toggle.setChecked(True)
        if entry.path == self.preview.source:
            self.preview.set_entry(entry, prefer_result=entry.status == "완료" and not self.preview.player.isPlaying())
        self.batch_index += 1
        self.fraction = 0.0
        self.worker = None
        worker.deleteLater()
        self.next_file()

    def finish_batch(self):
        self.update_total()
        self.active = False
        self.clock.stop()
        summary = "   ·   ".join(f"{status} {sum(e.status == status for e in self.batch)}개"
                                for status in ["완료", "실패", "취소", "대기"] if any(e.status == status for e in self.batch))
        self.stage.setText(summary)
        self.stage.setToolTip(summary)
        self.timing.setText(f"경과 {time_text(time.monotonic() - self.began)}")
        self.log_message(summary)
        self.update_actions()
        if self.close_after_stop:
            self.close()

    def log_message(self, message):
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    def closeEvent(self, event):
        if not self.update_footer.may_close():
            event.ignore()
            return
        if self.active:
            event.ignore()
            if self.close_after_stop:
                return
            confirm = QMessageBox(self)
            confirm.setWindowTitle("작업 종료")
            confirm.setText("처리 중인 파일을 취소하고 앱을 닫을까요?")
            quit_button = confirm.addButton("취소 후 종료", QMessageBox.ButtonRole.DestructiveRole)
            keep = confirm.addButton("계속 처리", QMessageBox.ButtonRole.RejectRole)
            confirm.setDefaultButton(keep)
            confirm.exec()
            if confirm.clickedButton() == quit_button and self.active:
                self.close_after_stop = True
                self.cancel_work(True)
            elif confirm.clickedButton() == quit_button:
                self.close()
            return
        self.probe_pool.clear()
        self.options_panel.save()
        self.settings.sync()
        self.preview.player.stop()
        self.preview.player.setSource(QUrl())
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Demucs Studio")
    app.setOrganizationName("Demucs Studio")
    app.setStyle("Fusion")
    window = MainWindow()
    inputs = [arg for arg in app.arguments()[1:] if Path(arg).is_file()]
    if inputs:
        window.add_files(inputs)
    window.show()
    return app.exec()
