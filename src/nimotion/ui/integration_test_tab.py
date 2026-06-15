"""集成测试 Tab — 回零 + 转盘孔位循环自动化测试"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models.turret import (
    MICROSTEP_REG_ADDR,
    TurretPosition,
    calculate_position_pulses,
    microstep_from_register,
)
from ..models.types import HomingConfig, MotorStatus
from ..services.motor_service import MotorService

# 一圈循环的步骤序列。"HOME" 为回零，其余为目标孔位。
_HOME = "HOME"
_SEQUENCE: list[object] = [
    _HOME,
    TurretPosition.POS_2,
    TurretPosition.POS_3,
    TurretPosition.POS_4,
    TurretPosition.POS_3,
    TurretPosition.POS_2,
    TurretPosition.POS_1,
    TurretPosition.POS_2,
]

_STEP_LABELS = {
    TurretPosition.POS_1: "位置 1",
    TurretPosition.POS_2: "位置 2",
    TurretPosition.POS_3: "位置 3",
    TurretPosition.POS_4: "位置 4",
}


class IntegrationTestTab(QWidget):
    """集成测试标签页。

    点击「开始」后按 回零 → 位置2 → 位置3 → 位置4 → 位置3 → 位置2 →
    位置1 → 位置2 的顺序循环执行。循环次数为 0 时无限循环，直到点击「停止」。

    运动命令异步非阻塞，本面板用状态机驱动：
    - 移动步：发出 move_absolute 后，先等 is_running 变 True（开始运动），
      再等变 False（运动结束），然后进入下一步。
    - 回零步：发出 configure_and_start_homing 后，等 motor.homing_done 信号
      （回零完成且 DI1 已恢复）后进入下一步。
    """

    _POLL_INTERVAL_MS = 500  # 状态轮询周期
    _MOVE_TIMEOUT_MS = 30000  # 单次移动超时
    _HOME_TIMEOUT_MS = 60000  # 单次回零超时

    _OFFSETS_FILE = Path(__file__).resolve().parents[3] / "turret_offsets.json"

    def __init__(self, motor_service: MotorService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._position_pulses: dict[TurretPosition, int] | None = None

        # 测试运行状态
        self._running = False
        self._target_loops = 0  # 0 = 无限
        self._loop_done = 0
        self._step_idx = 0
        self._phase = "idle"  # idle / homing / wait_start / wait_stop

        # 状态轮询定时器（不依赖状态面板的「自动」勾选）
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._motor.refresh_status)

        # 单步看门狗（防止某一步卡死）
        self._step_timer = QTimer(self)
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._on_step_timeout)

        self._init_ui()

        self._motor.status_updated.connect(self._on_status_updated)
        self._motor.homing_done.connect(self._on_homing_done)
        self._motor.operation_done.connect(self._on_operation_done)
        self._motor._worker.disconnected.connect(self._on_disconnected)

        # 启动时读取细分参数以计算各孔位脉冲
        self._motor.param_read.connect(self._on_param_read)
        self._motor.read_param(MICROSTEP_REG_ADDR)

    # -- UI --

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        group = QGroupBox("自动循环测试")
        gl = QVBoxLayout()

        # 序列说明
        seq_label = QLabel(
            "循环序列：回零 → 位置2 → 位置3 → 位置4 → 位置3 → 位置2 → 位置1 → 位置2"
        )
        seq_label.setStyleSheet("color: #888;")
        gl.addWidget(seq_label)

        # 循环次数输入
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("循环次数:"))
        self._count_edit = QLineEdit("0")
        self._count_edit.setValidator(QIntValidator(0, 999999, self))
        self._count_edit.setFixedWidth(100)
        count_row.addWidget(self._count_edit)
        count_row.addWidget(QLabel("（0 = 无限循环，直到点击停止）"))
        count_row.addStretch()
        gl.addLayout(count_row)

        # 开始 / 停止 按钮
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("开始")
        self._start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        gl.addLayout(btn_row)

        group.setLayout(gl)
        layout.addWidget(group)

        # 进度显示
        self._loop_label = QLabel("循环: --")
        self._loop_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._loop_label)

        self._step_label = QLabel("步骤: --")
        layout.addWidget(self._step_label)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    # -- 参数读取 --

    def _on_param_read(self, address: int, value: int) -> None:
        if address != MICROSTEP_REG_ADDR:
            return
        try:
            microstep = microstep_from_register(value)
        except ValueError:
            return
        self._position_pulses = calculate_position_pulses(microstep)

    def _load_offsets(self) -> dict[TurretPosition, int]:
        """从 turret_offsets.json 读取各孔位机械偏移（只读，与转盘页一致）。"""
        offsets = {pos: 0 for pos in TurretPosition if pos != TurretPosition.UNKNOWN}
        if not self._OFFSETS_FILE.exists():
            return offsets
        try:
            data = json.loads(self._OFFSETS_FILE.read_text(encoding="utf-8"))
            for pos in offsets:
                offsets[pos] = int(data.get(str(int(pos)), 0))
        except (json.JSONDecodeError, ValueError):
            pass
        return offsets

    # -- 开始 / 停止 --

    def _on_start(self) -> None:
        if self._running:
            return
        if self._position_pulses is None:
            self._set_status("参数未就绪，请先连接设备", error=True)
            return
        text = self._count_edit.text().strip()
        try:
            count = int(text) if text else 0
        except ValueError:
            self._set_status("循环次数无效", error=True)
            return
        if count < 0:
            self._set_status("循环次数不能为负", error=True)
            return

        self._offsets = self._load_offsets()
        self._target_loops = count
        self._loop_done = 0
        self._step_idx = 0
        self._running = True

        self._start_btn.setEnabled(False)
        self._count_edit.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._set_status("")

        self._poll_timer.start()
        self._begin_step()

    def _on_stop(self) -> None:
        if not self._running:
            return
        self._motor.stop()
        self._finish("已停止")

    def _finish(self, message: str, error: bool = False) -> None:
        self._running = False
        self._phase = "idle"
        self._poll_timer.stop()
        self._step_timer.stop()
        self._start_btn.setEnabled(True)
        self._count_edit.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._step_label.setText("步骤: --")
        self._set_status(message, error=error)

    # -- 状态机 --

    def _begin_step(self) -> None:
        """启动当前步骤。"""
        self._update_loop_label()
        step = _SEQUENCE[self._step_idx]
        if step == _HOME:
            self._phase = "homing"
            self._step_label.setText("步骤: 回零中...")
            self._step_timer.start(self._HOME_TIMEOUT_MS)
            self._motor.configure_and_start_homing(HomingConfig())
        else:
            assert self._position_pulses is not None
            target = self._position_pulses[step] + self._offsets.get(step, 0)
            self._phase = "wait_start"
            self._step_label.setText(f"步骤: 切换到{_STEP_LABELS[step]}...")
            self._step_timer.start(self._MOVE_TIMEOUT_MS)
            self._motor.move_absolute(target)

    def _advance_step(self) -> None:
        """当前步完成，前进到下一步；满一圈则计数。"""
        self._step_timer.stop()
        self._step_idx += 1
        if self._step_idx >= len(_SEQUENCE):
            self._step_idx = 0
            self._loop_done += 1
            if self._target_loops != 0 and self._loop_done >= self._target_loops:
                self._finish(f"测试完成，共 {self._loop_done} 圈")
                return
        self._begin_step()

    def _on_status_updated(self, status: MotorStatus) -> None:
        if not self._running:
            return
        if self._phase == "wait_start":
            if status.is_running:
                self._phase = "wait_stop"
        elif self._phase == "wait_stop":
            if not status.is_running:
                self._advance_step()

    def _on_homing_done(self) -> None:
        if not self._running or self._phase != "homing":
            return
        self._advance_step()

    def _on_operation_done(self, success: bool, message: str) -> None:
        if not self._running or success:
            return
        self._motor.stop()
        self._finish(f"出错停止: {message}", error=True)

    def _on_step_timeout(self) -> None:
        if not self._running:
            return
        self._motor.stop()
        self._finish("步骤超时，测试中止", error=True)

    def _on_disconnected(self) -> None:
        if self._running:
            self._finish("设备已断开，测试中止", error=True)

    # -- 辅助 --

    def _update_loop_label(self) -> None:
        if self._target_loops == 0:
            self._loop_label.setText(f"循环: 第 {self._loop_done + 1} 圈（无限）")
        else:
            self._loop_label.setText(
                f"循环: 第 {self._loop_done + 1} / {self._target_loops} 圈"
            )

    def _set_status(self, message: str, error: bool = False) -> None:
        self._status_label.setText(message)
        self._status_label.setStyleSheet("color: #F44336;" if error else "color: #888;")
