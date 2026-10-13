"""集成测试 Tab — 回零 + 转盘孔位循环自动化测试 + 连续回零(重复性/成功率)"""

from __future__ import annotations

import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QDoubleSpinBox,
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
    calculate_pulses_per_position,
    effective_position_pulses,
    load_calibration,
    microstep_from_register,
)
from ..models.app_config import load_di_invert, load_gear_ratio
from ..models.types import MotorStatus
from ..services.home_search import HomeSearch
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
    - 回零步：软件回零（HomeSearch.start_homing，与测距前2步同协议同参数，
      边沿设零+夹持），等 homed 信号后进入下一步。

    另含「连续回零测试」（2026-10-13 压测 A 区协议固化）：回零 → 移开固定
    偏移 → 再回零循环，统计成功率、边沿距离极差（=重复性，固定起点下
    HomeSearch.last_edge_distance 的离散度）与平均耗时。失败不中断，
    记录后继续下一轮。与循环测试互斥。
    """

    _POLL_INTERVAL_MS = 500  # 状态轮询周期
    _MOVE_TIMEOUT_MS = 5000  # 单次移动超时；90°切孔正常约1s
    _HOME_TIMEOUT_MS = 60000  # 单次回零超时
    _PAUSE_DEFAULT_S = 1.0  # 每步完成后的间歇默认值：怠机电流(0.15A)介入散热，降低占空比

    def __init__(self, motor_service: MotorService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._microstep: int | None = None
        self._position_pulses: dict[TurretPosition, int] | None = None

        # 测试运行状态
        self._running = False
        self._target_loops = 0  # 0 = 无限
        self._loop_done = 0
        self._step_idx = 0
        # idle / homing / wait_start / wait_stop / pausing
        # / rh_homing / rh_wait_start / rh_wait_stop (连续回零测试)
        self._phase = "idle"

        # 连续回零测试状态
        self._rh_running = False
        self._rh_target = 0
        self._rh_done = 0
        self._rh_ok = 0
        self._rh_offset = 800
        self._rh_prev_ok = False     # 上一轮是否成功(成功才从偏移点出发, 计入重复性)
        self._rh_dists: list[int] = []
        self._rh_durs: list[float] = []
        self._rh_fail_reasons: list[str] = []
        self._rh_cycle_t0 = 0.0
        self._rh_timer = QTimer(self)
        self._rh_timer.setSingleShot(True)
        self._rh_timer.timeout.connect(self._on_rh_timeout)

        # 状态轮询定时器（不依赖状态面板的「自动」勾选）
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._motor.refresh_status)

        # 单步看门狗（防止某一步卡死）
        self._step_timer = QTimer(self)
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._on_step_timeout)

        # 步间间歇定时器
        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.timeout.connect(self._on_pause_done)

        # 软件回零控制器(与转盘页/测距同协议同参数；原点开关极性取反按本机配置)
        self._homer = HomeSearch(
            self._motor, di_bit=0, invert_di=load_di_invert(), parent=self
        )
        self._homer.homed.connect(self._on_homing_done)
        self._homer.failed.connect(self._on_homing_failed)

        self._init_ui()

        self._motor.status_updated.connect(self._on_status_updated)
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

        # 步间间歇时间
        pause_row = QHBoxLayout()
        pause_row.addWidget(QLabel("步间间歇:"))
        self._pause_spin = QDoubleSpinBox()
        self._pause_spin.setRange(0.0, 10.0)
        self._pause_spin.setSingleStep(0.5)
        self._pause_spin.setDecimals(1)
        self._pause_spin.setValue(self._PAUSE_DEFAULT_S)
        self._pause_spin.setSuffix(" 秒")
        self._pause_spin.setFixedWidth(100)
        pause_row.addWidget(self._pause_spin)
        pause_row.addWidget(QLabel("（每步完成后停留散热，0 = 不间歇）"))
        pause_row.addStretch()
        gl.addLayout(pause_row)

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

        # -- 连续回零测试(重复性/成功率) --
        rh_group = QGroupBox("连续回零测试（重复性 / 成功率）")
        rl = QVBoxLayout()

        rh_desc = QLabel(
            "协议：回零 → 移开偏移脉冲 → 再回零循环；统计成功率、"
            "边沿距离极差（重复性）与耗时，失败记录后继续"
        )
        rh_desc.setStyleSheet("color: #888;")
        rl.addWidget(rh_desc)

        rh_row = QHBoxLayout()
        rh_row.addWidget(QLabel("次数:"))
        self._rh_count_edit = QLineEdit("30")
        self._rh_count_edit.setValidator(QIntValidator(1, 9999, self))
        self._rh_count_edit.setFixedWidth(80)
        rh_row.addWidget(self._rh_count_edit)
        rh_row.addWidget(QLabel("偏移:"))
        self._rh_offset_edit = QLineEdit("800")
        self._rh_offset_edit.setValidator(QIntValidator(0, 20000, self))
        self._rh_offset_edit.setFixedWidth(80)
        rh_row.addWidget(self._rh_offset_edit)
        rh_row.addWidget(QLabel("脉冲（0 = 原地连发）"))
        rh_row.addStretch()
        rl.addLayout(rh_row)

        rh_btn_row = QHBoxLayout()
        self._rh_start_btn = QPushButton("开始连续回零")
        self._rh_start_btn.clicked.connect(self._on_rh_start)
        rh_btn_row.addWidget(self._rh_start_btn)
        self._rh_stop_btn = QPushButton("停止")
        self._rh_stop_btn.setEnabled(False)
        self._rh_stop_btn.clicked.connect(self._on_rh_stop)
        rh_btn_row.addWidget(self._rh_stop_btn)
        rh_btn_row.addStretch()
        rl.addLayout(rh_btn_row)

        self._rh_progress_label = QLabel("进度: --")
        self._rh_progress_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        rl.addWidget(self._rh_progress_label)
        self._rh_stats_label = QLabel("统计: --")
        rl.addWidget(self._rh_stats_label)

        rh_group.setLayout(rl)
        layout.addWidget(rh_group)

    # -- 参数读取 --

    def _on_param_read(self, address: int, value: int) -> None:
        if address != MICROSTEP_REG_ADDR:
            return
        try:
            self._microstep = microstep_from_register(value)
        except ValueError:
            return
        # 采用与转盘页一致的标定绝对脉冲（未标定回退理论值）
        self._position_pulses = effective_position_pulses(
            self._microstep, load_calibration(), load_gear_ratio()
        )

    # -- 开始 / 停止 --

    def _on_start(self) -> None:
        if self._running or self._rh_running:
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

        # 重新按最新标定值刷新孔位目标（用户可能刚在转盘页标定过）
        if self._microstep is not None:
            self._position_pulses = effective_position_pulses(
                self._microstep, load_calibration(), load_gear_ratio()
            )
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

    # -- 连续回零测试 --

    def _on_rh_start(self) -> None:
        if self._running or self._rh_running:
            return
        if self._microstep is None:
            self._rh_stats_label.setText("统计: 参数未就绪，请先连接设备")
            return
        try:
            count = int(self._rh_count_edit.text().strip() or "0")
            offset = int(self._rh_offset_edit.text().strip() or "0")
        except ValueError:
            self._rh_stats_label.setText("统计: 次数/偏移无效")
            return
        if count < 1:
            self._rh_stats_label.setText("统计: 次数须 ≥1")
            return

        self._rh_target = count
        self._rh_offset = offset
        self._rh_done = 0
        self._rh_ok = 0
        self._rh_prev_ok = False
        self._rh_dists = []
        self._rh_durs = []
        self._rh_fail_reasons = []
        self._rh_running = True
        self._rh_start_btn.setEnabled(False)
        self._start_btn.setEnabled(False)
        self._rh_count_edit.setEnabled(False)
        self._rh_offset_edit.setEnabled(False)
        self._rh_stop_btn.setEnabled(True)
        self._rh_stats_label.setText("统计: --")
        self._poll_timer.start()
        self._rh_begin_cycle()

    def _on_rh_stop(self) -> None:
        if not self._rh_running:
            return
        self._motor.stop()
        self._rh_finish("已停止")

    def _rh_begin_cycle(self) -> None:
        if not self._rh_running:
            return
        assert self._microstep is not None
        self._phase = "rh_homing"
        self._rh_cycle_t0 = time.monotonic()
        self._rh_progress_label.setText(
            f"进度: 第 {self._rh_done + 1} / {self._rh_target} 次 回零中..."
        )
        self._rh_timer.start(self._HOME_TIMEOUT_MS)
        one_rev = 4 * calculate_pulses_per_position(
            self._microstep, load_gear_ratio()
        )
        self._homer.start_homing(
            pulses_per_sec=HomeSearch.SEARCH_SPEED * self._microstep,
            max_travel=one_rev + 1200,
        )

    def _rh_cycle_finished(self, ok: bool, reason: str = "") -> None:
        """一次回零结束(成功/失败/超时均到此), 记账并推进。"""
        self._rh_timer.stop()
        self._rh_done += 1
        duration = time.monotonic() - self._rh_cycle_t0
        if ok:
            self._rh_ok += 1
            self._rh_durs.append(duration)
            # 仅"上一轮成功且从偏移点出发"的轮次计入重复性样本
            if self._rh_prev_ok and self._rh_offset > 0 and self._rh_done > 1:
                self._rh_dists.append(self._homer.last_edge_distance)
        else:
            self._rh_fail_reasons.append(reason)
        self._rh_prev_ok = ok
        self._rh_update_stats()

        if self._rh_done >= self._rh_target:
            self._rh_finish("测试完成")
            return
        if ok and self._rh_offset > 0:
            # 移到偏移点作为下一轮固定起点
            self._phase = "rh_wait_start"
            self._rh_timer.start(self._MOVE_TIMEOUT_MS)
            self._motor.move_relative(self._rh_offset)
        else:
            # 失败后(或无偏移)稍候原地发起下一轮
            self._phase = "rh_homing_wait"
            QTimer.singleShot(500, self._rh_begin_cycle)

    def _rh_update_stats(self) -> None:
        parts = [f"成功 {self._rh_ok}/{self._rh_done}"]
        if len(self._rh_dists) >= 2:
            spread = max(self._rh_dists) - min(self._rh_dists)
            parts.append(
                f"边沿 {min(self._rh_dists)}~{max(self._rh_dists)}"
                f"（极差 {spread} 脉冲 ≈±{spread / 2:.1f}）"
            )
        if self._rh_durs:
            parts.append(
                f"耗时均值 {sum(self._rh_durs) / len(self._rh_durs):.1f}s"
            )
        if self._rh_fail_reasons:
            parts.append(f"最近失败: {self._rh_fail_reasons[-1]}")
        self._rh_stats_label.setText("统计: " + "  |  ".join(parts))

    def _rh_finish(self, message: str, error: bool = False, disable: bool = True) -> None:
        self._rh_running = False
        self._phase = "idle"
        self._rh_timer.stop()
        if not self._running:
            self._poll_timer.stop()
        if self._homer.running and disable:
            self._homer.cancel()
        if disable:
            self._motor.disable()
        self._rh_start_btn.setEnabled(True)
        self._start_btn.setEnabled(True)
        self._rh_count_edit.setEnabled(True)
        self._rh_offset_edit.setEnabled(True)
        self._rh_stop_btn.setEnabled(False)
        self._rh_progress_label.setText(
            f"进度: {message}（共 {self._rh_done} 次, 成功 {self._rh_ok}）"
        )
        self._rh_update_stats()

    def _on_rh_timeout(self) -> None:
        if not self._rh_running:
            return
        if self._phase == "rh_homing":
            self._homer.cancel()
            self._rh_cycle_finished(False, "回零超时")
        else:
            # 偏移移动超时属硬件异常, 终止测试
            self._motor.stop()
            self._rh_finish("偏移移动超时，测试中止", error=True)

    def _on_stop(self) -> None:
        if not self._running:
            return
        self._motor.stop()
        self._finish("已停止")

    def _finish(self, message: str, error: bool = False, disable: bool = True) -> None:
        """结束测试并复位 UI。disable=True 时去使能电机(电流归零)；
        设备已断开时传 False(端口失效，不再发指令)。"""
        self._running = False
        self._phase = "idle"
        self._poll_timer.stop()
        self._step_timer.stop()
        self._pause_timer.stop()
        if self._homer.running and disable:
            self._homer.cancel()  # 软件回零中止(teardown 恢复速度+脱机)
        if disable:
            self._motor.disable()
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
            assert self._microstep is not None
            self._phase = "homing"
            self._step_label.setText("步骤: 回零中(软件回零)...")
            self._step_timer.start(self._HOME_TIMEOUT_MS)
            one_rev = 4 * calculate_pulses_per_position(
                self._microstep, load_gear_ratio()
            )
            self._homer.start_homing(
                pulses_per_sec=HomeSearch.SEARCH_SPEED * self._microstep,
                max_travel=one_rev + 1200,
            )
        else:
            assert self._position_pulses is not None
            target = self._position_pulses[step]
            self._phase = "wait_start"
            self._step_label.setText(f"步骤: 切换到{_STEP_LABELS[step]}...")
            self._step_timer.start(self._MOVE_TIMEOUT_MS)
            self._motor.move_absolute(target)

    def _advance_step(self) -> None:
        """当前步完成，间歇 1s 后前进到下一步；满一圈则计数。"""
        self._step_timer.stop()
        self._step_idx += 1
        if self._step_idx >= len(_SEQUENCE):
            self._step_idx = 0
            self._loop_done += 1
            if self._target_loops != 0 and self._loop_done >= self._target_loops:
                self._finish(f"测试完成，共 {self._loop_done} 圈")
                return
        pause_ms = int(self._pause_spin.value() * 1000)
        if pause_ms <= 0:
            self._begin_step()
            return
        self._phase = "pausing"
        self._step_label.setText(f"步骤: 间歇散热中({self._pause_spin.value():.1f}s)...")
        self._pause_timer.start(pause_ms)

    def _on_pause_done(self) -> None:
        if not self._running or self._phase != "pausing":
            return
        self._begin_step()

    def _on_status_updated(self, status: MotorStatus) -> None:
        if self._rh_running:
            if self._phase == "rh_wait_start":
                if status.is_running:
                    self._phase = "rh_wait_stop"
            elif self._phase == "rh_wait_stop":
                if not status.is_running:
                    self._rh_timer.stop()
                    self._rh_begin_cycle()
            return
        if not self._running:
            return
        if self._phase == "wait_start":
            if status.is_running:
                self._phase = "wait_stop"
        elif self._phase == "wait_stop":
            if not status.is_running:
                self._advance_step()

    def _on_homing_done(self) -> None:
        if self._rh_running and self._phase == "rh_homing":
            self._rh_cycle_finished(True)
            return
        if not self._running or self._phase != "homing":
            return
        self._advance_step()

    def _on_homing_failed(self, reason: str) -> None:
        if self._rh_running and self._phase == "rh_homing":
            self._rh_cycle_finished(False, reason)
            return
        if not self._running or self._phase != "homing":
            return
        self._finish(f"回零失败: {reason}", error=True)

    def _on_operation_done(self, success: bool, message: str) -> None:
        if success:
            return
        if self._rh_running:
            self._motor.stop()
            self._rh_finish(f"出错停止: {message}", error=True)
            return
        if not self._running:
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
            self._finish("设备已断开，测试中止", error=True, disable=False)
        if self._rh_running:
            self._rh_finish("设备已断开，测试中止", error=True, disable=False)

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
