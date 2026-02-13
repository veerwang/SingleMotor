"""物镜转盘可视化控件 — 工业风格 QPainter 自绘"""

from __future__ import annotations

import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QRadialGradient, QFont
from PyQt5.QtWidgets import QWidget

from ...models.turret import TurretPosition


class TurretWidget(QWidget):
    """4 孔物镜转盘可视化控件。

    圆形转盘体 + 4 个物镜孔 (12/3/6/9 点钟方向)。
    当前位置孔发黄色光晕，其余暗灰。
    未归零时显示橙色 "未归零" 提示。
    """

    # 孔位角度: 12点(270°), 3点(0°), 6点(90°), 9点(180°)
    # QPainter 以3点钟为0°，顺时针为正
    HOLE_ANGLES = {
        TurretPosition.POS_1: 270,  # 12点 (Home)
        TurretPosition.POS_2: 0,    # 3点
        TurretPosition.POS_3: 90,   # 6点
        TurretPosition.POS_4: 180,  # 9点
    }

    HOLE_LABELS = {
        TurretPosition.POS_1: "1",
        TurretPosition.POS_2: "2",
        TurretPosition.POS_3: "3",
        TurretPosition.POS_4: "4",
    }

    # 配色
    COLOR_BODY = QColor(55, 55, 60)
    COLOR_BODY_EDGE = QColor(75, 75, 80)
    COLOR_HOLE_INACTIVE = QColor(40, 40, 45)
    COLOR_HOLE_EDGE = QColor(65, 65, 70)
    COLOR_ACTIVE = QColor(255, 214, 0)        # 黄色 (活动孔)
    COLOR_ACTIVE_GLOW = QColor(255, 214, 0, 80)
    COLOR_NOT_HOMED = QColor(255, 152, 0)     # 橙色 (未归零提示)
    COLOR_LABEL = QColor(180, 180, 180)
    COLOR_LABEL_ACTIVE = QColor(40, 40, 40)

    def __init__(self, size: int = 200, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._position = TurretPosition.UNKNOWN
        self.setFixedSize(size + 20, size + 20)  # 留出光晕空间

    @property
    def position(self) -> TurretPosition:
        return self._position

    def set_position(self, pos: TurretPosition) -> None:
        """更新当前转盘位置并刷新显示。"""
        if self._position != pos:
            self._position = pos
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2
        cy = self.height() / 2
        radius = self._size / 2

        self._draw_body(painter, cx, cy, radius)
        self._draw_holes(painter, cx, cy, radius)

        if self._position == TurretPosition.UNKNOWN:
            self._draw_not_homed(painter, cx, cy)

        painter.end()

    def _draw_body(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """绘制转盘本体。"""
        # 外圈金属边框
        p.setPen(QPen(self.COLOR_BODY_EDGE, 2))
        p.setBrush(self.COLOR_BODY)
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        # 中心轴
        shaft_r = r * 0.12
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(70, 70, 75))
        p.drawEllipse(int(cx - shaft_r), int(cy - shaft_r),
                       int(shaft_r * 2), int(shaft_r * 2))

    def _draw_holes(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """绘制 4 个物镜孔。"""
        hole_r = r * 0.18
        hole_dist = r * 0.6  # 孔中心到转盘中心的距离

        font = QFont()
        font.setPixelSize(int(hole_r * 0.9))
        font.setBold(True)
        p.setFont(font)

        for pos, angle_deg in self.HOLE_ANGLES.items():
            angle_rad = math.radians(angle_deg)
            hx = cx + hole_dist * math.cos(angle_rad)
            hy = cy + hole_dist * math.sin(angle_rad)

            is_active = (pos == self._position)

            if is_active:
                # 活动孔光晕
                glow = QRadialGradient(hx, hy, hole_r + 8)
                glow.setColorAt(0.4, self.COLOR_ACTIVE_GLOW)
                glow.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow)
                p.drawEllipse(int(hx - hole_r - 8), int(hy - hole_r - 8),
                               int((hole_r + 8) * 2), int((hole_r + 8) * 2))

            # 孔体
            if is_active:
                grad = QRadialGradient(hx - hole_r * 0.2, hy - hole_r * 0.2,
                                        hole_r * 1.2)
                grad.setColorAt(0.0, self.COLOR_ACTIVE.lighter(130))
                grad.setColorAt(0.6, self.COLOR_ACTIVE)
                grad.setColorAt(1.0, self.COLOR_ACTIVE.darker(150))
                p.setBrush(grad)
                p.setPen(QPen(self.COLOR_ACTIVE.darker(120), 1))
            else:
                p.setBrush(self.COLOR_HOLE_INACTIVE)
                p.setPen(QPen(self.COLOR_HOLE_EDGE, 1))

            p.drawEllipse(int(hx - hole_r), int(hy - hole_r),
                           int(hole_r * 2), int(hole_r * 2))

            # 标号
            label = self.HOLE_LABELS[pos]
            p.setPen(self.COLOR_LABEL_ACTIVE if is_active else self.COLOR_LABEL)
            text_rect = p.fontMetrics().boundingRect(label)
            p.drawText(int(hx - text_rect.width() / 2),
                        int(hy + text_rect.height() / 3),
                        label)

    def _draw_not_homed(self, p: QPainter, cx: float, cy: float) -> None:
        """未归零时在中央绘制提示文字。"""
        font = QFont()
        font.setPixelSize(13)
        font.setBold(True)
        p.setFont(font)
        p.setPen(self.COLOR_NOT_HOMED)
        text = "未归零"
        text_rect = p.fontMetrics().boundingRect(text)
        p.drawText(int(cx - text_rect.width() / 2),
                    int(cy + text_rect.height() / 3),
                    text)
