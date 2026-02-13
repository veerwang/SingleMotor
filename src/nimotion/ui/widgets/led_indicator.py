"""LED 指示灯控件 — 工业风格发光效果"""

from __future__ import annotations

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QPainter, QRadialGradient
from PyQt5.QtWidgets import QWidget


class LEDIndicator(QWidget):
    """
    圆形 LED 指示灯控件 — 带发光光晕效果。
    支持状态: OFF(灰) / ON(绿) / WARN(黄) / ERROR(红) / BLINK(闪烁绿)
    """

    COLORS = {
        "OFF": (QColor(80, 80, 80), QColor(50, 50, 50)),
        "ON": (QColor(0, 230, 118), QColor(0, 100, 50)),
        "WARN": (QColor(255, 214, 0), QColor(139, 115, 0)),
        "ERROR": (QColor(255, 61, 0), QColor(140, 20, 0)),
    }

    GLOW_COLORS = {
        "OFF": QColor(80, 80, 80, 0),
        "ON": QColor(0, 230, 118, 100),
        "WARN": QColor(255, 214, 0, 100),
        "ERROR": QColor(255, 61, 0, 120),
    }

    def __init__(self, size: int = 18, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._state = "OFF"
        self._blink_visible = True
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self.setFixedSize(size + 6, size + 6)  # 留出光晕空间

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

        cx = self.width() / 2
        cy = self.height() / 2
        r = self._size / 2

        if self._state == "BLINK":
            state_key = "ON" if self._blink_visible else "OFF"
        else:
            state_key = self._state if self._state in self.COLORS else "OFF"

        core_color, dark_color = self.COLORS[state_key]
        glow_color = self.GLOW_COLORS[state_key]

        # 外部光晕
        if state_key != "OFF":
            glow = QRadialGradient(cx, cy, r + 3)
            glow.setColorAt(0.5, glow_color)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(cx - r - 3), int(cy - r - 3),
                                int((r + 3) * 2), int((r + 3) * 2))

        # 外圈（金属边框）
        painter.setBrush(QColor(60, 60, 60))
        painter.setPen(QColor(80, 80, 80))
        painter.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        # 内部 LED 渐变
        led_r = r - 2
        gradient = QRadialGradient(cx - led_r * 0.3, cy - led_r * 0.3, led_r * 1.2)
        gradient.setColorAt(0.0, core_color.lighter(140))
        gradient.setColorAt(0.5, core_color)
        gradient.setColorAt(1.0, dark_color)
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(cx - led_r), int(cy - led_r),
                            int(led_r * 2), int(led_r * 2))

        # 高光反射点
        highlight_r = led_r * 0.3
        highlight = QRadialGradient(cx - led_r * 0.25, cy - led_r * 0.25, highlight_r)
        highlight.setColorAt(0.0, QColor(255, 255, 255, 180))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(highlight)
        painter.drawEllipse(int(cx - led_r * 0.5), int(cy - led_r * 0.5),
                            int(highlight_r * 2), int(highlight_r * 2))

        painter.end()
