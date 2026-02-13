"""物镜转盘控制面板"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models.turret import (
    POSITION_PULSES,
    TurretPosition,
    pulse_to_turret_position,
)
from ..models.types import MotorStatus, RunMode
from ..services.motor_service import MotorService
from .widgets.turret_widget import TurretWidget


class TurretPanel(QWidget):
    """物镜转盘控制面板。

    左侧: TurretWidget 可视化 + 当前位置标签
    右侧: 归零按钮 + 4 个物镜切换按钮
    """

    _POS_LABELS = {
        TurretPosition.POS_1: "位置 1 (Home)",
        TurretPosition.POS_2: "位置 2",
        TurretPosition.POS_3: "位置 3",
        TurretPosition.POS_4: "位置 4",
    }

    def __init__(self, motor_service: MotorService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._homed = False
        self._is_moving = False
        self._init_ui()
        self._motor.status_updated.connect(self._on_status_updated)
        self._motor.operation_done.connect(self._on_operation_done)

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)

        # -- 左侧: 可视化 + 位置标签 --
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._turret = TurretWidget(size=200)
        left.addWidget(self._turret, alignment=Qt.AlignmentFlag.AlignCenter)

        self._pos_label = QLabel("当前位置: 未知")
        self._pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pos_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #AAA;")
        left.addWidget(self._pos_label)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("color: #666;")
        left.addWidget(self._status_label)

        left.addStretch()
        layout.addLayout(left)

        # -- 右侧: 控制按钮 --
        right = QVBoxLayout()

        # 归零按钮组
        home_group = QGroupBox("归零")
        home_layout = QVBoxLayout()
        self._home_btn = QPushButton("原点回归")
        self._home_btn.clicked.connect(self._on_home)
        home_layout.addWidget(self._home_btn)
        home_group.setLayout(home_layout)
        right.addWidget(home_group)

        # 物镜切换按钮组
        switch_group = QGroupBox("物镜切换")
        switch_layout = QVBoxLayout()
        self._switch_btns: dict[TurretPosition, QPushButton] = {}
        for pos in (TurretPosition.POS_1, TurretPosition.POS_2,
                     TurretPosition.POS_3, TurretPosition.POS_4):
            label = self._POS_LABELS[pos]
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, p=pos: self._on_switch(p))
            btn.setEnabled(False)  # 未归零时禁用
            switch_layout.addWidget(btn)
            self._switch_btns[pos] = btn

        switch_group.setLayout(switch_layout)
        right.addWidget(switch_group)

        right.addStretch()
        layout.addLayout(right)

    # -- 操作回调 --

    def _on_home(self) -> None:
        """执行归零流程。"""
        self._set_moving(True)
        self._status_label.setText("正在归零...")
        self._status_label.setStyleSheet("color: #FFA726;")
        self._motor.set_run_mode(RunMode.HOMING)
        self._motor.start_homing()

    def _on_switch(self, pos: TurretPosition) -> None:
        """切换到指定物镜位置。"""
        target = POSITION_PULSES[pos]
        self._set_moving(True)
        self._status_label.setText(f"正在切换到{self._POS_LABELS[pos]}...")
        self._status_label.setStyleSheet("color: #FFA726;")
        self._motor.set_run_mode(RunMode.POSITION)
        self._motor.move_absolute(target)

    # -- 信号处理 --

    def _on_status_updated(self, status: MotorStatus) -> None:
        """根据电机实时状态更新 UI。"""
        pos = pulse_to_turret_position(status.position)
        self._turret.set_position(pos)

        if pos != TurretPosition.UNKNOWN:
            self._pos_label.setText(f"当前位置: {self._POS_LABELS[pos]}")
            self._pos_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #FFD600;"
            )
            if not self._homed:
                self._homed = True
                self._update_switch_buttons()
        else:
            self._pos_label.setText("当前位置: 未知")
            self._pos_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #AAA;"
            )

        # 运动结束检测
        if self._is_moving and not status.is_running:
            self._set_moving(False)
            self._status_label.setText("")

    def _on_operation_done(self, success: bool, message: str) -> None:
        """操作完成回调。"""
        if not success:
            self._status_label.setText(message)
            self._status_label.setStyleSheet("color: #F44336;")
            self._set_moving(False)

    # -- 辅助方法 --

    def _set_moving(self, moving: bool) -> None:
        """设置运动状态，更新按钮可用性。"""
        self._is_moving = moving
        self._home_btn.setEnabled(not moving)
        self._update_switch_buttons()

    def _update_switch_buttons(self) -> None:
        """根据归零状态和运动状态更新切换按钮。"""
        enabled = self._homed and not self._is_moving
        for btn in self._switch_btns.values():
            btn.setEnabled(enabled)
