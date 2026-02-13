"""电机状态监控面板"""

from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models.types import MotorState, MotorStatus, RunMode
from ..services.motor_service import MotorService
from .widgets.led_indicator import LEDIndicator

STATE_DISPLAY: dict[MotorState, tuple[str, str]] = {
    MotorState.UNKNOWN: ("未知", "color: gray;"),
    MotorState.NOT_READY: ("未就绪", "color: gray;"),
    MotorState.SWITCH_ON_DISABLED: ("脱机", "color: gray;"),
    MotorState.READY_TO_SWITCH_ON: ("启动", "color: #2196F3;"),
    MotorState.SWITCHED_ON: ("使能", "color: #4CAF50;"),
    MotorState.OPERATION_ENABLED: ("运行", "color: #4CAF50; font-weight: bold;"),
    MotorState.QUICK_STOP: ("急停", "color: #FF9800;"),
    MotorState.FAULT_ACTIVE: ("故障激活", "color: #F44336;"),
    MotorState.FAULT: ("故障", "color: #F44336; font-weight: bold;"),
}

MODE_DISPLAY: dict[int, str] = {
    1: "位置模式",
    2: "速度模式",
    3: "原点回归",
    4: "脉冲输入",
}


class MotorStatusPanel(QWidget):
    """电机状态监控面板（左侧固定宽度）"""

    def __init__(self, motor_service: MotorService, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_poll)
        self._motor.status_updated.connect(self._update_display)
        self.setFixedWidth(220)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 指示灯
        led_row = QHBoxLayout()
        led_row.addWidget(QLabel("RUN"))
        self._led_run = LEDIndicator(16)
        led_row.addWidget(self._led_run)
        led_row.addWidget(QLabel("COM"))
        self._led_com = LEDIndicator(16)
        led_row.addWidget(self._led_com)
        led_row.addStretch()
        layout.addLayout(led_row)

        # 状态信息
        group = QGroupBox("电机状态")
        form = QFormLayout()

        self._lbl_state = QLabel("未知")
        form.addRow("状态:", self._lbl_state)

        self._lbl_position = QLabel("0 pulse")
        form.addRow("位置:", self._lbl_position)

        self._lbl_speed = QLabel("0 Step/s")
        form.addRow("速度:", self._lbl_speed)

        self._lbl_voltage = QLabel("0 V")
        form.addRow("电压:", self._lbl_voltage)

        self._lbl_mode = QLabel("--")
        form.addRow("模式:", self._lbl_mode)

        self._lbl_direction = QLabel("--")
        form.addRow("方向:", self._lbl_direction)

        self._lbl_alarm = QLabel("无")
        form.addRow("报警:", self._lbl_alarm)

        self._lbl_status_word = QLabel("0x0000")
        self._lbl_status_word.setStyleSheet("color: #888; font-size: 10px;")
        form.addRow("状态字:", self._lbl_status_word)

        group.setLayout(form)
        layout.addWidget(group)

        # 刷新控制
        refresh_row = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._motor.refresh_status)
        refresh_row.addWidget(refresh_btn)

        self._auto_cb = QCheckBox("自动")
        self._auto_cb.toggled.connect(self._on_auto_toggled)
        refresh_row.addWidget(self._auto_cb)

        self._interval_combo = QComboBox()
        for label, ms in [("200ms", 200), ("500ms", 500), ("1s", 1000), ("2s", 2000)]:
            self._interval_combo.addItem(label, ms)
        self._interval_combo.setCurrentIndex(1)  # 默认 500ms
        self._interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        refresh_row.addWidget(self._interval_combo)

        layout.addLayout(refresh_row)
        layout.addStretch()

    def _on_auto_toggled(self, checked: bool) -> None:
        if checked:
            interval = self._interval_combo.currentData()
            self._timer.start(interval)
        else:
            self._timer.stop()

    def _on_interval_changed(self, index: int) -> None:
        if self._timer.isActive():
            self._timer.start(self._interval_combo.currentData())

    def _on_poll(self) -> None:
        self._motor.refresh_status()

    def _update_display(self, status: MotorStatus) -> None:
        # 状态
        text, style = STATE_DISPLAY.get(status.state, ("未知", "color: gray;"))
        self._lbl_state.setText(text)
        self._lbl_state.setStyleSheet(style)

        # 位置
        self._lbl_position.setText(f"{status.position} pulse")

        # 速度
        rpm = status.speed * 0.3
        self._lbl_speed.setText(f"{status.speed} Step/s ({rpm:.0f} RPM)")

        # 电压
        self._lbl_voltage.setText(f"{status.voltage} V")

        # 模式
        if status.current_mode is not None:
            self._lbl_mode.setText(MODE_DISPLAY.get(status.current_mode, "未知"))
        else:
            self._lbl_mode.setText("--")

        # 方向
        self._lbl_direction.setText("正转" if status.direction == 1 else "反转")

        # 报警
        if status.alarm_code:
            self._lbl_alarm.setText(f"0x{status.alarm_code:04X} {status.alarm_text}")
            self._lbl_alarm.setStyleSheet("color: red;")
        else:
            self._lbl_alarm.setText("无")
            self._lbl_alarm.setStyleSheet("")

        # 状态字
        self._lbl_status_word.setText(f"0x{status.status_word:04X}")

        # LED
        if status.state == MotorState.FAULT:
            self._led_run.set_state("ERROR")
        elif status.is_running:
            self._led_run.set_state("ON")
        elif status.state in (MotorState.SWITCHED_ON, MotorState.OPERATION_ENABLED):
            self._led_run.set_state("BLINK")
        else:
            self._led_run.set_state("OFF")

        self._led_com.set_state("ON")  # 收到数据说明通讯正常
