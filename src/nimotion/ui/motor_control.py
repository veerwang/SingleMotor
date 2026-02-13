"""运动控制面板"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..models.types import RunMode
from ..services.motor_service import MotorService


class PositionPanel(QWidget):
    """位置模式控制面板"""

    def __init__(self, motor_service: MotorService, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._target_spin = QSpinBox()
        self._target_spin.setRange(-2147483648, 2147483647)
        self._target_spin.setValue(0)
        form.addRow("目标位置 (pulse):", self._target_spin)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        rel_btn = QPushButton("相对运动")
        rel_btn.clicked.connect(self._on_move_relative)
        btn_row.addWidget(rel_btn)

        abs_btn = QPushButton("绝对运动")
        abs_btn.clicked.connect(self._on_move_absolute)
        btn_row.addWidget(abs_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()

    def _on_move_relative(self) -> None:
        self._motor.move_relative(self._target_spin.value())

    def _on_move_absolute(self) -> None:
        self._motor.move_absolute(self._target_spin.value())


class SpeedPanel(QWidget):
    """速度模式控制面板"""

    def __init__(self, motor_service: MotorService, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._speed_spin = QSpinBox()
        self._speed_spin.setRange(0, 15610)
        self._speed_spin.setValue(100)
        form.addRow("目标速度 (Step/s):", self._speed_spin)

        self._dir_combo = QComboBox()
        self._dir_combo.addItem("反转 (0)", 0)
        self._dir_combo.addItem("正转 (1)", 1)
        self._dir_combo.setCurrentIndex(1)
        form.addRow("方向:", self._dir_combo)
        layout.addLayout(form)

        # 速度换算提示
        self._speed_hint = QLabel("= 30.0 RPM")
        self._speed_hint.setStyleSheet("color: #666;")
        self._speed_spin.valueChanged.connect(
            lambda v: self._speed_hint.setText(f"= {v * 0.3:.1f} RPM")
        )
        layout.addWidget(self._speed_hint)

        btn_row = QHBoxLayout()
        run_btn = QPushButton("运行")
        run_btn.clicked.connect(self._on_run)
        btn_row.addWidget(run_btn)

        stop_btn = QPushButton("停止")
        stop_btn.clicked.connect(self._motor.stop)
        btn_row.addWidget(stop_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()

    def _on_run(self) -> None:
        self._motor.set_speed(
            self._speed_spin.value(),
            self._dir_combo.currentData(),
        )


class HomingPanel(QWidget):
    """原点回归控制面板"""

    def __init__(self, motor_service: MotorService, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._method_spin = QSpinBox()
        self._method_spin.setRange(17, 31)
        self._method_spin.setValue(17)
        form.addRow("回归方式:", self._method_spin)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        start_btn = QPushButton("开始回归")
        start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(start_btn)

        set_origin_btn = QPushButton("设置原点")
        set_origin_btn.clicked.connect(self._motor.set_origin)
        btn_row.addWidget(set_origin_btn)

        set_zero_btn = QPushButton("设置零点")
        set_zero_btn.clicked.connect(self._motor.set_zero)
        btn_row.addWidget(set_zero_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()

    def _on_start(self) -> None:
        self._motor.start_homing()


class MotorControlPanel(QWidget):
    """运动控制子面板"""

    def __init__(self, motor_service: MotorService, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._motor.operation_done.connect(self._on_operation_done)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 状态切换按钮组
        group_state = QGroupBox("状态切换")
        state_layout = QHBoxLayout()

        btn_data = [
            ("一键使能", self._on_quick_enable),
            ("启动", self._motor.startup),
            ("使能", self._motor.enable),
            ("运行", self._motor.run),
            ("停止", self._motor.stop),
            ("急停", self._motor.quick_stop),
            ("脱机", self._motor.disable),
            ("清除故障", self._motor.clear_fault),
        ]
        self._state_buttons: list[QPushButton] = []
        for name, handler in btn_data:
            btn = QPushButton(name)
            btn.clicked.connect(handler)
            if name == "急停":
                btn.setStyleSheet("background-color: #FFCDD2;")
            state_layout.addWidget(btn)
            self._state_buttons.append(btn)

        group_state.setLayout(state_layout)
        layout.addWidget(group_state)

        # 模式选择
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("运行模式:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("位置模式", RunMode.POSITION)
        self._mode_combo.addItem("速度模式", RunMode.SPEED)
        self._mode_combo.addItem("原点回归", RunMode.HOMING)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self._mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # 模式面板栈
        self._stack = QStackedWidget()
        self._stack.addWidget(PositionPanel(self._motor))
        self._stack.addWidget(SpeedPanel(self._motor))
        self._stack.addWidget(HomingPanel(self._motor))
        layout.addWidget(self._stack, stretch=1)

        # 状态提示
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #666;")
        layout.addWidget(self._status_label)

    def _on_mode_changed(self, index: int) -> None:
        mode = self._mode_combo.currentData()
        self._motor.set_run_mode(mode)
        self._stack.setCurrentIndex(index)

    def _on_quick_enable(self) -> None:
        """一键使能：启动 + 使能"""
        self._motor.startup()
        self._motor.enable()

    def _on_operation_done(self, success: bool, message: str) -> None:
        if success:
            self._status_label.setStyleSheet("color: #4CAF50;")
        else:
            self._status_label.setStyleSheet("color: #F44336;")
        self._status_label.setText(message)
