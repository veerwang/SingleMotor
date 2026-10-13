"""集成测试 Tab — 回零 + 转盘孔位循环自动化测试 + 连续回零(重复性/成功率)"""

from __future__ import annotations

import random
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QComboBox,
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

    另含「连续回零测试」（2026-10-13 压测 A/B 区协议固化）：回零 → 移开
    固定偏移 → 再回零循环，统计成功率、边沿距离极差（=重复性，固定起点下
    HomeSearch.last_edge_distance 的离散度）与平均耗时。失败不中断，
    记录后继续下一轮。与循环测试互斥。

    测试项目预设:
    - A 短距重复性(偏移+800): 起点在感应窗口正侧前方, sweep 短距即触发,
      考察重复定位精度
    - B 整圈扫描漏窗(偏移-100~-400 每轮随机): 起点在窗口负侧, sweep 必须
      扫完整圈才再次进窗——专项考察 SWEEP_SPEED=150 下穿窗仅≈1 个轮询
      周期的漏检率(漏检表现为"行程内未找到感应点"失败, 计入成功率统计)。
      起点随机化消除相位锁定: 固定起点下穿窗时刻相对 20ms 轮询节拍每轮
      近似相同, 只检验单一相位; 300 脉冲随机跨度≈125ms, 扫遍 6 个轮询
      周期的相位空间(每 1 脉冲≈0.4ms 相移, ≥48 脉冲才覆盖一个周期)
    - C 窗口内起点(偏移+10~+40 每轮随机): 起点落在感应窗口内部(窗口为
      回零后 0~+50), 一上来 DI 即触发——考验 armed(先见释放帧才认触发)
      兜底逻辑: 不得把起点假触发当作感应点, 必须绕整圈从正侧重新进窗。
      随机深度覆盖窗口不同位置, 两端各留 ~10 脉冲防边沿抖动
    - D 测距模式(+800 固定起点, 带返回): 循环跑 HomeSearch.start() 测距
      而非回零——覆盖回零不经过的返回点动与 0x005B 临时限速路径。先回零
      +移至 +800 建立固定起点(不计数), 此后每轮测距并自动返回原地, 测距
      值与 800 的偏差即重复性; 测距失败时重建基准(回零+偏移)后继续

    重复性统计用"边沿偏差"= 实测边沿距离 − 期望值(短距类期望=偏移;
    整圈类期望=一圈脉冲+偏移, B/C 均属整圈类), 随机起点下同口径可比。
    自定义模式按符号推断: 正偏移=短距, 负偏移=整圈。
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
        # / rh_homing / rh_moving (连续回零测试)
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
        self._rh_move_target = 0  # 偏移移动的目标位置(回零后为0起点, 即=本轮偏移)
        self._rh_random_span = 0  # 偏移随机跨度(B=300/C=30, 扰动轮询相位)
        self._rh_exp_mode = "auto"  # 期望口径: short/full/auto(按符号推断)
        self._rh_op = "home"      # 每轮操作: home=回零 / measure=测距带返回(D)
        self._rh_need_setup = False  # D: 是否需先回零+偏移建立固定起点
        self._rh_prev_expected: int | None = None  # 本轮起点对应的期望边沿距离
        self._rh_one_rev = 0      # 一圈脉冲数(整圈类期望边沿距离=一圈+偏移)
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
        self._homer.finished.connect(self._on_rh_measure_done)

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
        rh_row.addWidget(QLabel("项目:"))
        self._rh_mode_combo = QComboBox()
        # 预设数据: (基准偏移, 随机跨度, 期望口径 short=偏移 / full=一圈+偏移,
        #            操作 home=回零 / measure=测距带返回)
        self._rh_mode_combo.addItem("A 短距重复性(+800)", (800, 0, "short", "home"))
        self._rh_mode_combo.addItem(
            "B 整圈扫描漏窗(-100~-400随机)", (-100, 300, "full", "home")
        )
        self._rh_mode_combo.addItem(
            "C 窗口内起点(+10~+40随机)", (10, 30, "full", "home")
        )
        self._rh_mode_combo.addItem(
            "D 测距模式(+800, 带返回)", (800, 0, "short", "measure")
        )
        self._rh_mode_combo.addItem("自定义", None)
        self._rh_mode_combo.currentIndexChanged.connect(self._on_rh_mode_changed)
        rh_row.addWidget(self._rh_mode_combo)
        rh_row.addWidget(QLabel("次数:"))
        self._rh_count_edit = QLineEdit("30")
        self._rh_count_edit.setValidator(QIntValidator(1, 9999, self))
        self._rh_count_edit.setFixedWidth(80)
        rh_row.addWidget(self._rh_count_edit)
        rh_row.addWidget(QLabel("偏移:"))
        self._rh_offset_edit = QLineEdit("800")
        self._rh_offset_edit.setValidator(QIntValidator(-20000, 20000, self))
        self._rh_offset_edit.setFixedWidth(80)
        self._rh_offset_edit.setEnabled(False)  # 预设项目锁定, 选"自定义"可编辑
        rh_row.addWidget(self._rh_offset_edit)
        rh_row.addWidget(QLabel("脉冲（正=窗口正侧短距，负=负侧整圈，0=原地连发）"))
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

    def _on_rh_mode_changed(self) -> None:
        preset = self._rh_mode_combo.currentData()
        if preset is None:
            self._rh_offset_edit.setEnabled(True)
        else:
            self._rh_offset_edit.setText(str(preset[0]))
            self._rh_offset_edit.setEnabled(False)

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

        preset = self._rh_mode_combo.currentData()
        self._rh_random_span = preset[1] if preset is not None else 0
        self._rh_exp_mode = preset[2] if preset is not None else "auto"
        self._rh_op = preset[3] if preset is not None else "home"
        self._rh_need_setup = self._rh_op == "measure"
        self._rh_one_rev = 4 * calculate_pulses_per_position(
            self._microstep, load_gear_ratio()
        )
        self._rh_target = count
        self._rh_offset = offset
        self._rh_done = 0
        self._rh_ok = 0
        self._rh_prev_ok = False
        self._rh_prev_expected = None
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
        pps = HomeSearch.SEARCH_SPEED * self._microstep
        max_travel = self._rh_one_rev + 1200
        if self._rh_op == "measure" and self._rh_need_setup:
            # D: 先回零+移至偏移点建立固定起点(不计入次数)
            self._phase = "rh_setup_homing"
            self._rh_progress_label.setText("进度: 建立基准(回零+偏移)...")
            self._rh_timer.start(self._HOME_TIMEOUT_MS)
            self._homer.start_homing(pulses_per_sec=pps, max_travel=max_travel)
            return
        self._rh_cycle_t0 = time.monotonic()
        self._rh_timer.start(self._HOME_TIMEOUT_MS)
        if self._rh_op == "measure":
            self._phase = "rh_measuring"
            self._rh_progress_label.setText(
                f"进度: 第 {self._rh_done + 1} / {self._rh_target} 次 测距中..."
            )
            self._homer.start(
                pulses_per_sec=pps, return_to_start=True, max_travel=max_travel
            )
        else:
            self._phase = "rh_homing"
            self._rh_progress_label.setText(
                f"进度: 第 {self._rh_done + 1} / {self._rh_target} 次 回零中..."
            )
            self._homer.start_homing(pulses_per_sec=pps, max_travel=max_travel)

    def _rh_cycle_finished(self, ok: bool, reason: str = "") -> None:
        """一次回零结束(成功/失败/超时均到此), 记账并推进。"""
        self._rh_timer.stop()
        self._rh_done += 1
        duration = time.monotonic() - self._rh_cycle_t0
        if ok:
            self._rh_ok += 1
            self._rh_durs.append(duration)
            # 仅"从已知偏移点出发"的轮次计入重复性样本(回零类还须上轮成功;
            # 测距类自动返回原地, 起点持续有效)。记录"边沿偏差"=实测-期望
            # (期望值在发起偏移移动时按口径算好), 起点随机化后依然同口径可比
            if self._rh_prev_expected is not None and (
                self._rh_prev_ok or self._rh_op == "measure"
            ):
                self._rh_dists.append(
                    self._homer.last_edge_distance - self._rh_prev_expected
                )
        else:
            self._rh_fail_reasons.append(reason)
        self._rh_prev_ok = ok
        self._rh_update_stats()

        if self._rh_done >= self._rh_target:
            self._rh_finish("测试完成")
            return
        if self._rh_op == "measure":
            # D: 成功时已自动返回起点, 直接下一轮; 失败则重建基准
            if not ok:
                self._rh_need_setup = True
                self._rh_prev_expected = None
            self._phase = "rh_homing_wait"
            QTimer.singleShot(500, self._rh_begin_cycle)
            return
        if ok and self._rh_offset != 0:
            self._rh_launch_offset_move()
        else:
            # 失败后(或无偏移)稍候原地发起下一轮, 起点不明不计重复性样本
            self._rh_prev_expected = None
            self._phase = "rh_homing_wait"
            QTimer.singleShot(500, self._rh_begin_cycle)

    def _rh_launch_offset_move(self) -> None:
        """移到偏移点作为下一轮起点(A/D=窗口正侧, B=负侧整圈, C=窗口内)。

        B/C 加随机扰动打散穿窗时刻相对轮询节拍的相位(防相位锁定)。
        完成判定用位置读数而非"起动→停止"跳变: 短偏移(如-100, ~40ms)
        在 500ms 轮询间隙内即走完, 等跳变必然漏过(2026-10-13 真机实锤)。
        """
        jitter = random.randint(0, self._rh_random_span)
        offset_used = (
            self._rh_offset - jitter
            if self._rh_offset < 0
            else self._rh_offset + jitter
        )
        mode = self._rh_exp_mode
        if mode == "auto":
            mode = "short" if offset_used > 0 else "full"
        self._rh_prev_expected = (
            offset_used if mode == "short"
            else self._rh_one_rev + offset_used
        )
        self._phase = "rh_moving"
        self._rh_move_target = offset_used  # 回零后位置=0, 目标即偏移值
        self._rh_timer.start(self._MOVE_TIMEOUT_MS)
        self._motor.move_relative(offset_used)

    def _rh_update_stats(self) -> None:
        parts = [f"成功 {self._rh_ok}/{self._rh_done}"]
        if len(self._rh_dists) >= 2:
            spread = max(self._rh_dists) - min(self._rh_dists)
            parts.append(
                f"边沿偏差 {min(self._rh_dists)}~{max(self._rh_dists)}"
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
        if self._phase in ("rh_homing", "rh_setup_homing", "rh_measuring"):
            self._homer.cancel()
            tag = "测距超时" if self._phase == "rh_measuring" else "回零超时"
            if self._phase == "rh_setup_homing":
                tag = "建立基准超时"
            self._rh_cycle_finished(False, tag)
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
            if self._phase == "rh_moving":
                if not status.is_running and status.position == self._rh_move_target:
                    self._rh_timer.stop()
                    self._rh_need_setup = False  # D: 基准(回零+偏移)已就绪
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
        if self._rh_running and self._phase == "rh_setup_homing":
            # D: 基准回零成功, 移到偏移点(不计数)
            self._rh_timer.stop()
            self._rh_launch_offset_move()
            return
        if not self._running or self._phase != "homing":
            return
        self._advance_step()

    def _on_rh_measure_done(self, distance: int) -> None:
        if self._rh_running and self._phase == "rh_measuring":
            self._rh_cycle_finished(True)

    def _on_homing_failed(self, reason: str) -> None:
        if self._rh_running and self._phase in (
            "rh_homing", "rh_measuring"
        ):
            self._rh_cycle_finished(False, reason)
            return
        if self._rh_running and self._phase == "rh_setup_homing":
            # D: 基准建立失败计一次失败, 稍后重试建基准
            self._rh_cycle_finished(False, f"建立基准失败: {reason}")
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
