"""软件测距/软件回零控制器(共用同一状态机与参数，经理要求协议一致)。

**测距模式**：每次测量前把当前位置计数**清 0**(设置零点 0x0047) →
**sweep**: 速度模式低速负向连续运动，上位机周期轮询 DI 电平，见触发立即
减速停机(停在窗口内或刚越过) → **backoff**: 回退释放开关 → **fine**:
细步逼近取精确触发点(窗口正侧边沿) → (可选)返回起点。清 0 后触发点为
负值，距离取其绝对值。

**回零模式**(start_homing)：与测距前 3 步完全相同(sweep → backoff →
fine，同参数)，fine 找到边沿后**就地设零**建立 home 基准，随后保持使能
夹持(hold_position_clamp)停在 home 点。不使用驱动器内置回零，回零与测距
的边沿检测工况因此完全一致。注: home 重复精度 = 细搜步长量化(±FINE_STEP)。

防走样约束: 感应窗口实测仅约 50 脉冲宽(home 边沿起 -10~-55, ≈2°转盘)。
sweep 速度必须满足 窗口穿越时间 ≥ 2×轮询周期，否则两次轮询之间会整个跨过
窗口。SWEEP_SPEED=60 Step/s(×16=960 pulses/s) → 穿越 52ms ≥ 2~3 个 20ms
轮询周期。若产品批次窗口更窄需相应降速(或缩短 POLL_MS)。另: 停车距离
(29脉冲)+检测滞后(20)最深 49 脉冲 < BACKOFF(60)，回退后必在边沿上方。

注: DI1 常驻"原点开关"配置，搜索只读取 DI 电平，不改 DI 功能。设计要求
homing 传感器严禁配成限位(转盘无限位，自研固件会报 FF0E 超负限位故障)。

搜索期间临时把最大速度(0x005B)降为 SEARCH_SPEED(先读原值，结束/失败恢复)，
作用于回退/细搜/返回的点动精度；sweep 用速度模式目标速度(0x0055)，独立设置。
细搜阶段另临时把加速度(0x005F)降为 FINE_ACCEL 软化微步逼近(2026-07-28 经理
定值)，转 returning 或结束时恢复原值；减速度(0x0061)不动。

异常快失败: 任一状态帧带报警码(如欠压 3120)立即停机报错，不傻等看门狗。
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from ..models.app_config import load_di_invert
from ..models.types import MotorStatus
from .motor_service import MotorService

_MAX_SPEED_ADDR = 0x005B        # 最大速度(UINT32, Step/s)
_ACCEL_ADDR = 0x005F            # 加速度(UINT32, Step/s²)


class HomeSearch(QObject):
    """软件搜索感应点并测量当前位置→感应点距离。"""

    progress = pyqtSignal(int)   # 搜索中当前位置(脉冲)
    finished = pyqtSignal(int)   # 测距完成: 测得距离(脉冲, 正值)
    homed = pyqtSignal()         # 软件回零完成: 已在边沿设零并夹持
    failed = pyqtSignal(str)     # 失败原因(两种模式共用)

    SWEEP_SPEED = 60             # sweep 连续扫描速度(Step/s)，见模块注释防走样约束
                                 # (2026-07-28 经理定值 50→60)
    POLL_MS = 20                 # sweep 期间状态轮询周期(2026-07-28 经理定值 25→20)
    FINE_STEP = 2                # 细搜步长(脉冲)，决定最终精度
    BACKOFF = 60                 # 触发后回退步长(释放开关)。停点最深在边沿下方
                                 # ~40脉冲(轮询量化20+停车距离20)，60一次可出窗，
                                 # 循环兜底；取小减少细搜空走步数(2026-07-28 经理定值 90→60)
    MAX_TRAVEL = 10000           # 搜索行程上限(>转盘一圈 8800)
    FINE_TRAVEL_LIMIT = 200      # 细搜行程上限(回退60+窗口50+裕量)，防误触发后无限细搜
    SETTLE_MARGIN_MS = 300       # 单步整定裕量
    STOP_SETTLE_MS = 400         # sweep 触发停机后的整定时间
    OVERALL_TIMEOUT_MS = 120000  # 总看门狗
    SEARCH_SPEED = 60            # 点动阶段临时最大速度(Step/s)
    FINE_ACCEL = 50              # 细搜阶段临时加速度(Step/s², 2026-07-28 经理定值 990→50)
    PREPARE_TIMEOUT_MS = 3000    # 读取原最大速度/加速度超时

    def __init__(
        self, motor: MotorService, di_bit: int = 0, invert_di: bool = False, parent=None
    ) -> None:
        super().__init__(parent)
        self._motor = motor
        self._di_bit = di_bit
        # 原点开关(DI1)极性取反：默认 False=旧逻辑(高电平触发)。
        # 新物镜转换器感应逻辑可能相反，由 GUI 设置项读写本机配置传入。
        self._invert_di = invert_di
        # idle/prepare/sweep/stopping/backoff/fine/returning
        self._phase = "idle"
        self._settling = False
        self._awaiting = False   # 点动阶段: 本整定周期是否还需处理一次状态
        self._sweeping = False   # sweep 阶段: 连续运动是否已启动
        self._fine_travel = 0
        self._measured = 0
        self._return_to_start = True
        self._mode = "measure"   # measure=测距 / home=软件回零
        self._pps = 480
        self._orig_speed: int | None = None  # 搜索前的最大速度，结束后恢复
        self._orig_accel: int | None = None  # 搜索前的加速度，细搜降 200 后恢复
        self._accel_lowered = False          # 细搜临时加速度是否已写入
        self._prepare_reads: dict[int, int] = {}

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._on_settle_done)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self.POLL_MS)
        self._poll_timer.timeout.connect(self._motor.refresh_status)
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(lambda: self._fail("搜索超时"))
        self._motor.status_updated.connect(self._on_status)
        self._motor.param_read.connect(self._on_param_read)

    @property
    def running(self) -> bool:
        return self._phase != "idle"

    def cancel(self) -> None:
        """中止搜索(如设备断连)，还原状态，不发 finished/failed。"""
        if self._phase != "idle":
            self._teardown()

    def start(self, pulses_per_sec: int = 480, return_to_start: bool = True) -> None:
        """开始测量：清 0 → sweep → 回退 → 细搜 → (可选)返回起点。

        pulses_per_sec 用于按步长动态估算点动整定时长(建议传 最大速度×细分数)。
        """
        self._invert_di = load_di_invert()  # 每次启动读取最新本机配置
        self._begin(pulses_per_sec, return_to_start, "measure")

    def start_homing(self, pulses_per_sec: int = 480) -> None:
        """软件回零：sweep → 回退 → 细搜到边沿 → 就地设零 → 夹持。

        与测距前 3 步协议/参数完全一致(经理要求)，完成发 homed 信号。
        """
        self._invert_di = load_di_invert()  # 每次启动读取最新本机配置
        self._begin(pulses_per_sec, False, "home")

    def _begin(self, pulses_per_sec: int, return_to_start: bool, mode: str) -> None:
        if self._phase != "idle":
            return
        self._mode = mode
        self._pps = max(int(pulses_per_sec), 1)
        self._return_to_start = return_to_start
        self._measured = 0
        self._fine_travel = 0
        self._sweeping = False
        self._orig_speed = None
        self._orig_accel = None
        self._accel_lowered = False
        self._prepare_reads = {}
        # 先停机(写参数需停机)；DI 配置不动(DI1 常驻原点开关，只读电平)
        self._motor.disable()
        # 当前位置计数清 0
        self._motor.set_zero()
        # 读当前最大速度/加速度(结束后恢复)，读齐后临时降速再进入 sweep
        self._phase = "prepare"
        self._settling = False
        self._awaiting = False
        self._watchdog.start(self.OVERALL_TIMEOUT_MS)
        self._settle_timer.start(self.PREPARE_TIMEOUT_MS)  # 读取超时兜底
        self._motor.read_param(_MAX_SPEED_ADDR, 2)
        self._motor.read_param(_ACCEL_ADDR, 2)

    # -- 内部 --

    def _on_param_read(self, addr: int, value: int) -> None:
        if self._phase != "prepare" or addr not in (_MAX_SPEED_ADDR, _ACCEL_ADDR):
            return
        self._prepare_reads[addr] = value
        if len(self._prepare_reads) < 2:
            return
        self._settle_timer.stop()
        self._orig_speed = self._prepare_reads[_MAX_SPEED_ADDR]
        self._orig_accel = self._prepare_reads[_ACCEL_ADDR]
        if self._orig_speed != self.SEARCH_SPEED:
            self._motor.write_param_32bit(_MAX_SPEED_ADDR, self.SEARCH_SPEED)
        # 进入 sweep，先取首帧状态(覆盖起点已在窗口内的情况)
        self._phase = "sweep"
        self._awaiting = True
        self._motor.refresh_status()

    def _settle_for(self, step: int) -> int:
        """按步长/速度动态估算整定时长(ms)，×1.3 裕量 + 固定裕量。"""
        return int(abs(step) / self._pps * 1000 * 1.3) + self.SETTLE_MARGIN_MS

    def _jog(self, step: int) -> None:
        self._settling = True
        self._awaiting = False
        self._motor.move_relative(step)
        self._settle_timer.start(self._settle_for(step))

    def _lower_accel_for_fine(self) -> None:
        """细搜前临时降加速度(0x005F)软化微步逼近，转 returning/结束时恢复。"""
        if self._orig_accel is not None and self._orig_accel != self.FINE_ACCEL:
            self._motor.write_param_32bit(_ACCEL_ADDR, self.FINE_ACCEL)
            self._accel_lowered = True

    def _restore_accel(self) -> None:
        if self._accel_lowered and self._orig_accel is not None:
            self._motor.write_param_32bit(_ACCEL_ADDR, self._orig_accel)
        self._accel_lowered = False

    def _on_settle_done(self) -> None:
        if self._phase == "prepare":
            self._fail("读取最大速度/加速度超时")
            return
        if self._phase == "stopping":
            # sweep 停机整定完毕，开始回退
            self._phase = "backoff"
            self._jog(+self.BACKOFF)
            return
        self._settling = False
        self._awaiting = True
        self._motor.refresh_status()  # 主动取一帧最新状态来推进

    def _on_status(self, status: MotorStatus) -> None:
        if self._phase in ("idle", "prepare", "stopping") or self._settling:
            return
        # 报警快失败(欠压/过流等会中断运动，等看门狗无意义)
        if status.alarm_code != 0:
            self._fail(f"驱动器报警 0x{status.alarm_code:04X}，测距中止")
            return

        triggered = bool(status.di_status & (1 << self._di_bit))
        if self._invert_di:
            triggered = not triggered
        pos = status.position

        if self._phase == "sweep":
            self.progress.emit(pos)
            if not self._sweeping:
                # 首帧: 起点已在窗口内则直接回退，否则启动连续扫描
                if triggered:
                    self._phase = "backoff"
                    self._jog(+self.BACKOFF)
                else:
                    self._sweeping = True
                    self._motor.set_speed(self.SWEEP_SPEED, 0)  # 0=反转(负向)
                    self._poll_timer.start()
                return
            if triggered:
                self._poll_timer.stop()
                self._motor.stop()  # 减速停机(0x0007)
                self._phase = "stopping"
                self._settle_timer.start(self.STOP_SETTLE_MS)
            elif abs(pos) > self.MAX_TRAVEL:
                self._poll_timer.stop()
                self._motor.stop()
                self._fail("行程内未找到感应点(方向/接线?)")
            return

        # 点动阶段: 每个整定周期只处理一次，防其它来源的状态刷新重复发步
        if not self._awaiting:
            return
        self._awaiting = False
        self.progress.emit(pos)

        if self._phase == "backoff":
            if triggered:
                self._jog(+self.BACKOFF)   # 继续退回直到开关释放
            else:
                self._phase = "fine"
                self._fine_travel = 0
                self._lower_accel_for_fine()
                self._jog(-self.FINE_STEP)
        elif self._phase == "fine":
            if triggered:
                if self._mode == "home":
                    # 就地设零建立 home 基准，保持使能夹持停在 home 点
                    self._motor.set_zero()
                    self._finish_home()
                    return
                self._measured = -pos       # 清 0 后触发点为负，距离取正
                if self._return_to_start:
                    self._phase = "returning"
                    self._restore_accel()   # 返回长行程不必用细搜低加速度
                    self._jog(+self._measured)
                else:
                    self._finish()
            else:
                self._fine_travel += self.FINE_STEP
                if self._fine_travel > self.FINE_TRAVEL_LIMIT:
                    self._fail("细搜未找到感应点(触发信号异常?)")
                else:
                    self._jog(-self.FINE_STEP)
        elif self._phase == "returning":
            self._finish()

    def _finish(self) -> None:
        self._teardown()
        self.finished.emit(self._measured)

    def _finish_home(self) -> None:
        """回零成功收尾：还原速度参数后保持使能夹持(不脱机)。"""
        self._teardown()
        self._motor.hold_position_clamp()
        self.homed.emit()

    def _fail(self, reason: str) -> None:
        self._teardown()
        self.failed.emit(reason)

    def _teardown(self) -> None:
        self._settle_timer.stop()
        self._poll_timer.stop()
        self._watchdog.stop()
        self._motor.disable()                                   # 脱机(写参数需停机)
        if self._orig_speed is not None and self._orig_speed != self.SEARCH_SPEED:
            self._motor.write_param_32bit(_MAX_SPEED_ADDR, self._orig_speed)
        self._restore_accel()
        self._orig_speed = None
        self._orig_accel = None
        self._phase = "idle"
        self._settling = False
        self._awaiting = False
        self._sweeping = False
