"""物镜转盘控制面板"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..models.turret import (
    MICROSTEP_REG_ADDR,
    TurretPosition,
    effective_position_pulses,
    load_calibration,
    microstep_from_register,
    pulse_to_turret_position,
    save_calibration,
)
from ..models.types import HomingConfig, MotorStatus
from ..services.motor_service import MotorService
from .widgets.turret_widget import TurretWidget

_SLOTS = (
    TurretPosition.POS_1,
    TurretPosition.POS_2,
    TurretPosition.POS_3,
    TurretPosition.POS_4,
)


class TurretPanel(QWidget):
    """物镜转盘控制面板。

    左侧: TurretWidget 可视化 + 当前位置标签
    右侧: 归零 + 点动对位 + 4 个孔位切换/标定

    标定工作流：回零 → 点动把转盘转到某孔位对准 → 点该孔位「标定」记录当前
    电机绝对位置 → 之后「切换」直接按标定的绝对脉冲值移动。标定值持久化到
    turret_calibration.json，未标定的孔位回退到理论计算值。
    """

    _POS_LABELS = {
        TurretPosition.POS_1: "位置 1",
        TurretPosition.POS_2: "位置 2",
        TurretPosition.POS_3: "位置 3",
        TurretPosition.POS_4: "位置 4",
    }

    _PARAM_READ_TIMEOUT_MS = 3000  # 参数读取超时（毫秒）
    _MOVING_TIMEOUT_MS = 30000  # 普通移动(点动/切换)超时（毫秒）
    _HOME_TIMEOUT_MS = 60000  # 回零超时（回零较慢，尤其降速后，独立于普通移动超时）
    _DEFAULT_JOG_STEP = 50  # 默认点动步进（脉冲）

    def __init__(self, motor_service: MotorService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._homed = False
        self._is_moving = False
        self._homing = False  # 回零进行中（用回零完成信号判定结束，而非状态位）
        self._microstep: int | None = None
        self._last_position = 0  # 最近一次实时电机位置，用于标定捕获

        # 参数读取超时定时器
        self._param_timer = QTimer(self)
        self._param_timer.setSingleShot(True)
        self._param_timer.timeout.connect(self._on_param_timeout)

        # 运动超时定时器
        self._moving_timer = QTimer(self)
        self._moving_timer.setSingleShot(True)
        self._moving_timer.timeout.connect(self._on_moving_timeout)

        self._calibration = load_calibration()
        self._init_ui()
        self._motor.status_updated.connect(self._on_status_updated)
        self._motor.operation_done.connect(self._on_operation_done)
        self._motor.param_read.connect(self._on_param_read)
        self._motor.homing_done.connect(self._on_homing_done)
        self._motor._worker.disconnected.connect(self._on_disconnected)
        # 启动时读取细分参数
        self._motor.read_param(MICROSTEP_REG_ADDR)
        self._param_timer.start(self._PARAM_READ_TIMEOUT_MS)

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

        self._live_label = QLabel("当前脉冲: --")
        self._live_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._live_label.setStyleSheet("color: #888; font-family: monospace;")
        left.addWidget(self._live_label)

        self._status_label = QLabel("读取参数中...")
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
        self._home_btn.setEnabled(False)  # 读取细分参数前禁用
        self._home_btn.clicked.connect(self._on_home)
        home_layout.addWidget(self._home_btn)
        home_group.setLayout(home_layout)
        right.addWidget(home_group)

        # 点动对位组
        jog_group = QGroupBox("点动对位")
        jog_layout = QHBoxLayout()
        jog_layout.addWidget(QLabel("步进:"))
        self._jog_step_spin = QSpinBox()
        self._jog_step_spin.setRange(1, 2200)
        self._jog_step_spin.setValue(self._DEFAULT_JOG_STEP)
        self._jog_step_spin.setSuffix(" pulse")
        self._jog_step_spin.setFixedWidth(110)
        jog_layout.addWidget(self._jog_step_spin)
        self._jog_neg_btn = QPushButton("转盘 −")
        self._jog_neg_btn.setEnabled(False)
        self._jog_neg_btn.clicked.connect(lambda: self._on_jog(-1))
        jog_layout.addWidget(self._jog_neg_btn)
        self._jog_pos_btn = QPushButton("转盘 +")
        self._jog_pos_btn.setEnabled(False)
        self._jog_pos_btn.clicked.connect(lambda: self._on_jog(+1))
        jog_layout.addWidget(self._jog_pos_btn)
        jog_group.setLayout(jog_layout)
        right.addWidget(jog_group)

        # 物镜切换 + 标定组
        switch_group = QGroupBox("物镜切换 / 标定")
        switch_layout = QVBoxLayout()
        self._switch_btns: dict[TurretPosition, QPushButton] = {}
        self._teach_btns: dict[TurretPosition, QPushButton] = {}
        self._pos_spins: dict[TurretPosition, QSpinBox] = {}
        for pos in _SLOTS:
            row = QHBoxLayout()
            btn = QPushButton(self._POS_LABELS[pos])
            btn.clicked.connect(lambda checked, p=pos: self._on_switch(p))
            btn.setEnabled(False)  # 未归零时禁用
            row.addWidget(btn)
            self._switch_btns[pos] = btn

            teach_btn = QPushButton("标定")
            teach_btn.setFixedWidth(56)
            teach_btn.setToolTip("将当前电机位置记录为该孔位目标")
            teach_btn.clicked.connect(lambda checked, p=pos: self._on_teach(p))
            teach_btn.setEnabled(False)
            row.addWidget(teach_btn)
            self._teach_btns[pos] = teach_btn

            pos_spin = QSpinBox()
            pos_spin.setRange(-99999, 99999)
            pos_spin.setValue(0)
            pos_spin.setSuffix(" pulse")
            pos_spin.setFixedWidth(120)
            pos_spin.setToolTip("回零点→该孔位的标定绝对脉冲值")
            pos_spin.valueChanged.connect(self._save_calibration)
            row.addWidget(pos_spin)
            self._pos_spins[pos] = pos_spin

            switch_layout.addLayout(row)

        switch_group.setLayout(switch_layout)
        right.addWidget(switch_group)

        right.addStretch()
        layout.addLayout(right)

    # -- 操作回调 --

    def _on_home(self) -> None:
        """执行归零流程（含 DI1 临时切换）。"""
        self._homing = True
        self._set_moving(True)
        self._status_label.setText("正在归零...")
        self._status_label.setStyleSheet("color: #FFA726;")
        self._motor.configure_and_start_homing(HomingConfig())
        self._moving_timer.start(self._HOME_TIMEOUT_MS)

    def _on_jog(self, direction: int) -> None:
        """点动：相对移动一个步进，用于对位标定。"""
        if self._is_moving:
            return
        step = self._jog_step_spin.value() * direction
        self._set_moving(True)
        self._status_label.setText(f"点动 {step:+d} pulse...")
        self._status_label.setStyleSheet("color: #FFA726;")
        self._motor.move_relative(step)
        self._moving_timer.start(self._MOVING_TIMEOUT_MS)

    def _on_teach(self, pos: TurretPosition) -> None:
        """标定：把当前电机位置记录为该孔位目标。"""
        self._pos_spins[pos].setValue(self._last_position)  # 触发保存
        self._status_label.setText(
            f"已标定{self._POS_LABELS[pos]} = {self._last_position} pulse"
        )
        self._status_label.setStyleSheet("color: #66BB6A;")

    def _on_switch(self, pos: TurretPosition) -> None:
        """切换到指定物镜位置（使用标定的绝对脉冲值）。"""
        target = self._pos_spins[pos].value()
        self._set_moving(True)
        self._status_label.setText(f"正在切换到{self._POS_LABELS[pos]}...")
        self._status_label.setStyleSheet("color: #FFA726;")
        self._motor.move_absolute(target)
        self._moving_timer.start(self._MOVING_TIMEOUT_MS)

    # -- 信号处理 --

    def _on_param_read(self, address: int, value: int) -> None:
        """接收参数读取结果，处理细分寄存器。"""
        if address != MICROSTEP_REG_ADDR:
            return
        self._param_timer.stop()
        try:
            microstep = microstep_from_register(value)
        except ValueError:
            self._status_label.setText(f"细分参数异常: {value}")
            self._status_label.setStyleSheet("color: #F44336;")
            return
        self._microstep = microstep
        # 用标定值（缺失回退理论值）初始化各孔位目标 spinbox
        effective = effective_position_pulses(microstep, self._calibration)
        for pos in _SLOTS:
            spin = self._pos_spins[pos]
            spin.blockSignals(True)
            spin.setValue(effective[pos])
            spin.blockSignals(False)
        self._status_label.setText("")
        self._home_btn.setEnabled(True)
        self._update_controls()

    def _on_homing_done(self) -> None:
        """回零完成（DI1 已恢复）：进入已归零状态，可开始对位标定。"""
        if not self._homing:
            return
        self._homing = False
        self._homed = True
        self._moving_timer.stop()
        self._set_moving(False)
        self._status_label.setText("归零完成，可点动对位并标定")
        self._status_label.setStyleSheet("color: #66BB6A;")

    def _on_status_updated(self, status: MotorStatus) -> None:
        """根据电机实时状态更新 UI。"""
        self._last_position = status.position
        self._live_label.setText(f"当前脉冲: {status.position}")

        effective = self._effective_positions()
        if effective is not None:
            pos = pulse_to_turret_position(status.position, effective)
            self._turret.set_position(pos)
            if pos != TurretPosition.UNKNOWN:
                self._pos_label.setText(f"当前位置: {self._POS_LABELS[pos]}")
                self._pos_label.setStyleSheet(
                    "font-size: 14px; font-weight: bold; color: #FFD600;"
                )
            else:
                self._pos_label.setText("当前位置: 未知")
                self._pos_label.setStyleSheet(
                    "font-size: 14px; font-weight: bold; color: #AAA;"
                )

        # 运动结束检测（回零结束由 homing_done 判定，此处跳过）
        if self._is_moving and not self._homing and not status.is_running:
            self._moving_timer.stop()
            # 移动完成后去使能（写 0x0000 脱机），空闲时不保持力矩，靠机械定位保持孔位。
            # 下次孔位切换/点动的命令序列会自动重新使能。
            self._motor.disable()
            self._set_moving(False)
            if self._status_label.styleSheet().find("F44336") < 0:
                self._status_label.setText("")

    def _on_operation_done(self, success: bool, message: str) -> None:
        """操作完成回调。"""
        if not success:
            self._status_label.setText(message)
            self._status_label.setStyleSheet("color: #F44336;")
            self._homing = False
            self._set_moving(False)

    def _on_param_timeout(self) -> None:
        """参数读取超时处理。"""
        if self._microstep is not None:
            return  # 已经成功读取
        self._status_label.setText("读取参数超时，请检查连接")
        self._status_label.setStyleSheet("color: #F44336;")

    def _on_moving_timeout(self) -> None:
        """运动超时处理。"""
        if not self._is_moving:
            return
        self._homing = False
        self._set_moving(False)
        self._status_label.setText("运动超时")
        self._status_label.setStyleSheet("color: #F44336;")

    def _on_disconnected(self) -> None:
        """设备断连处理。"""
        self._param_timer.stop()
        self._moving_timer.stop()
        self._homing = False
        if self._is_moving:
            self._set_moving(False)
        self._status_label.setText("设备已断开")
        self._status_label.setStyleSheet("color: #F44336;")

    # -- 辅助方法 --

    def _effective_positions(self) -> dict[TurretPosition, int] | None:
        """当前各孔位采用的绝对脉冲（即 spinbox 值），细分未就绪时返回 None。"""
        if self._microstep is None:
            return None
        return {pos: spin.value() for pos, spin in self._pos_spins.items()}

    def _set_moving(self, moving: bool) -> None:
        """设置运动状态，更新按钮可用性。"""
        self._is_moving = moving
        self._home_btn.setEnabled(not moving and self._microstep is not None)
        self._update_controls()

    def _update_controls(self) -> None:
        """根据归零状态和运动状态更新点动/切换/标定控件。"""
        ready = self._microstep is not None and not self._is_moving
        # 点动只需参数就绪（对位需在回零后进行，但也允许连接后手动点动）
        self._jog_neg_btn.setEnabled(ready and self._homed)
        self._jog_pos_btn.setEnabled(ready and self._homed)
        for pos in _SLOTS:
            self._switch_btns[pos].setEnabled(ready and self._homed)
            self._teach_btns[pos].setEnabled(ready and self._homed)

    def _save_calibration(self) -> None:
        """将各孔位 spinbox 的绝对脉冲值保存到 JSON。"""
        self._calibration = {pos: spin.value() for pos, spin in self._pos_spins.items()}
        save_calibration(self._calibration)
