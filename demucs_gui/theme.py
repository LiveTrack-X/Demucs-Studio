from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def glyph(name: str, ink: str = "#495872", size: int = 22) -> QIcon:
    """Small vector icons drawn at double resolution for high-DPI screens."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24, size / 24)
    painter.setPen(QPen(QColor(ink), 1.65, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

    def line(x1, y1, x2, y2):
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    if name == "brand":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#808bff"))
        painter.drawRoundedRect(QRectF(0, 0, 24, 24), 6, 6)
        painter.setPen(QPen(QColor("#141830"), 2.0, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
    if name in {"brand", "wave"}:
        for x, h in [(5, 2), (8.5, 5), (12, 7.5), (15.5, 3.5), (19, 1.5)]:
            line(x, 12 - h, x, 12 + h)
    elif name == "plus":
        line(12, 5, 12, 19)
        line(5, 12, 19, 12)
    elif name == "video":
        painter.drawRoundedRect(QRectF(2, 5, 15, 14), 2, 2)
        path = QPainterPath(QPointF(17, 10))
        path.lineTo(22, 7)
        path.lineTo(22, 17)
        path.lineTo(17, 14)
        painter.drawPath(path)
    elif name == "folder":
        path = QPainterPath(QPointF(3, 6))
        for x, y in [(9, 6), (11, 8), (21, 8), (21, 18), (3, 18)]:
            path.lineTo(x, y)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "upload":
        line(12, 16, 12, 4)
        line(7.5, 8.5, 12, 4)
        line(12, 4, 16.5, 8.5)
        path = QPainterPath(QPointF(3.5, 14))
        path.lineTo(3.5, 20)
        path.lineTo(20.5, 20)
        path.lineTo(20.5, 14)
        painter.drawPath(path)
    elif name == "headphones":
        path = QPainterPath(QPointF(4, 15))
        path.lineTo(4, 12)
        path.cubicTo(4, 1, 20, 1, 20, 12)
        path.lineTo(20, 15)
        painter.drawPath(path)
        for x in (3.8, 16.3):
            painter.drawRoundedRect(QRectF(x, 12, 3.8, 7), 1.5, 1.5)
    elif name == "play":
        path = QPainterPath(QPointF(8, 5))
        path.lineTo(19, 12)
        path.lineTo(8, 19)
        path.closeSubpath()
        painter.fillPath(path, QColor(ink))
    elif name == "pause":
        for x in (8, 14):
            painter.fillRect(QRectF(x, 5, 3, 14), QColor(ink))
    painter.end()
    return QIcon(pixmap)


STYLE = """
* { font-family: 'Segoe UI', 'Malgun Gothic', sans-serif; font-size: 12px; color: #243149; }
QWidget#canvas, QScrollArea#settingsScroll { background: #f3f5f9; }
QFrame#topbar { background: #172137; }
QLabel#brandTitle { color: #f5f7fd; font-size: 21px; font-weight: 650; }
QLabel#brandSub { color: #c6d0e4; font-size: 12px; }
QLabel#local { color: #d4deef; font-size: 12px; }
QFrame#brandDivider { background: #49566f; }
QFrame#localDot { background: #83d8b1; border-radius: 3px; }
QFrame#panel, QFrame#footer { background: #ffffff; border: 1px solid #dfe4ed; border-radius: 10px; }
QWidget#settingsBody { background: #ffffff; }
QLabel#sectionTitle { font-size: 18px; font-weight: 700; color: #19253b; }
QLabel#groupTitle, QToolButton#disclosure { font-size: 13px; font-weight: 650; color: #26334a; }
QLabel#subtle, QLabel#timing { color: #68758a; }
QLabel#count { color: #514bb3; background: #edecfc; border-radius: 9px; padding: 1px 7px; font-weight: 650; }
QFrame#drop { background: #f4f5ff; border: 1px dashed #a3a8d9; border-radius: 8px; }
QFrame#drop[over="true"] { background: #e4e6ff; border: 2px solid #645bd4; }
QLabel#dropTitle { color: #35375b; font-size: 15px; font-weight: 650; }
QLabel#dropHint { color: #69728f; }
QPushButton, QToolButton#cancel {
    background: #ffffff; border: 1px solid #ccd3df; border-radius: 5px;
    padding: 5px 10px; min-height: 19px; font-weight: 550;
}
QPushButton:hover, QToolButton#cancel:hover { background: #f3f4fb; border-color: #a3acc1; }
QPushButton:pressed, QToolButton#cancel:pressed { background: #e7eaf5; }
QPushButton:disabled, QToolButton#cancel:disabled { color: #8993a5; background: #f4f6f9; border-color: #e2e6ed; }
QPushButton#primary { color: white; background: #5650c9; border-color: #5650c9; padding: 6px 19px; }
QPushButton#primary:hover { background: #4842b8; }
QPushButton#primary:disabled { color: #ecebfc; background: #9a96d4; border-color: #9a96d4; }
QPushButton#seg { background: #f5f6fa; color: #57637a; min-height: 26px; }
QPushButton#seg:checked { background: #eeedff; color: #443ca9; border: 1px solid #938ce3; font-weight: 700; }
QPushButton#textAction { border: none; padding: 3px 5px; color: #59667c; background: transparent; }
QPushButton#textAction:hover { background: #edf0f6; }
QPushButton#textAction:disabled { color: #a3aab7; }
QPushButton:focus, QToolButton:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QLineEdit:focus { border: 1px solid #817adc; }
QToolButton#disclosure { border: none; padding: 3px 0; background: transparent; }
QToolButton#disclosure:hover { color: #504ab8; }
QFrame#line { background: #e4e8ee; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { padding: 4px 7px; min-height: 20px;
    background: white; border: 1px solid #cdd4e0; border-radius: 4px; }
QComboBox::drop-down { width: 22px; border: none; background: transparent; }
QComboBox::down-arrow { width: 0; height: 0; }
QComboBox:disabled { color: #8a94a5; background: #f5f6fa; }
QPushButton#choiceCard {
    background: #ffffff; border: 1px solid #d5dce1; border-radius: 10px;
    padding: 0; min-height: 54px; text-align: left;
}
QPushButton#choiceCard[compact="true"] { min-height: 32px; }
QPushButton#choiceCard:hover { background: #f2f9f8; border-color: #88b8b0; }
QPushButton#choiceCard:checked { background: #eaf9f5; border: 1px solid #16867a; }
QPushButton#choiceCard:focus { border: 2px solid #187f76; }
QLabel#cardTitle { color: #1c2d34; font-size: 13px; font-weight: 700; }
QLabel#cardDetail { color: #536670; font-size: 11px; }
QToolButton#presetManage {
    border: 1px solid #ccd3df; border-radius: 5px; background: #ffffff;
    font-weight: 700; padding: 1px 7px; min-height: 25px;
}
QToolButton#presetManage::menu-indicator { width: 0px; }
QToolButton#presetManage:disabled { color: #9da5b6; background: #f5f6f9; }
QAbstractItemView { selection-color: #262759; selection-background-color: #e9e8fa; }
QTableWidget { background: #ffffff; border: none; gridline-color: #edf0f5; outline: 0; }
QTableWidget::item { padding: 4px; border-bottom: 1px solid #eef0f5; }
QHeaderView::section { border: none; border-bottom: 1px solid #dfe4ee;
    background: #f6f7fa; padding: 7px 5px; color: #657087; font-weight: 600; }
QProgressBar { border: none; border-radius: 3px; background: #e5e8f3; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #6a62d6; border-radius: 3px; }
QPlainTextEdit { background: #f4f6fa; color: #39465c; border: 1px solid #dfe4ee; border-radius: 4px; padding: 5px; }
QSlider::groove:horizontal { height: 4px; background: #dce0ed; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #7a73d5; border-radius: 2px; }
QSlider::handle:horizontal { width: 10px; margin: -3px 0; background: #655dcc; border-radius: 5px; }
QScrollBar:vertical { background: #f5f6fa; width: 9px; }
QScrollBar::handle:vertical { background: #c8cddd; min-height: 22px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenu { background: white; border: 1px solid #d2d8e4; padding: 4px; }
QMenu::item { padding: 6px 14px; }
QMenu::item:selected { background: #edecfc; }
"""
