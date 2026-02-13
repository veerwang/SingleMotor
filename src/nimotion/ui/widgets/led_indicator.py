"""LED 指示灯控件"""

from __future__ import annotations

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget


class LEDIndicator(QWidget):
    """
    圆形 LED 指示灯控件。
    支持状态: OFF(灰) / ON(绿) / WARN(黄) / ERROR(红) / BLINK(闪烁绿)
    """

    COLORS = {
        "OFF": QColor(128, 128, 128),
        "ON": QColor(0, 200, 0),
        "WARN": QColor(255, 200, 0),
        "ERROR": QColor(255, 50, 50),
    }

    def __init__(self, size: int = 16, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._state = "OFF"
        self._blink_visible = True
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self.setFixedSize(size, size)

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        """设置状态: OFF / ON / WARN / ERROR / BLINK"""
        self._state = state.upper()
        if self._state == "BLINK":
            if not self._blink_timer.isActive():
                self._blink_timer.start(500)
        else:
            self._blink_timer.stop()
            self._blink_visible = True
        self.update()

    def _toggle_blink(self) -> None:
        self._blink_visible = not self._blink_visible
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._state == "BLINK":
            color = self.COLORS["ON"] if self._blink_visible else self.COLORS["OFF"]
        else:
            color = self.COLORS.get(self._state, self.COLORS["OFF"])

        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        margin = 1
        painter.drawEllipse(margin, margin, self._size - 2 * margin, self._size - 2 * margin)
        painter.end()
