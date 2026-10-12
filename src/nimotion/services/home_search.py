"""软件测距/软件回零控制器(共用同一状态机与参数，经理要求协议一致)。

**测距模式**：每次测量前把当前位置计数**清 0**(设置零点 0x0047) →
**sweep**: 速度模式高速负向连续扫描，上位机周期轮询 DI 电平，见触发立即
减速停机(150 速度下停点必已越过整个感应窗口) → **creep**: 低速正向反查，
见触发立即停机，停点即感应窗口负侧边沿 → (可选)返回起点。清 0 后边沿为
负值，距离取其绝对值。

**回零模式**(start_homing)：与测距前 2 步完全相同(sweep → creep，同参数)，
creep 停点**就地设零**建立 home 基准，随后保持使能夹持(hold_position_clamp)
停在 home 点。不使用驱动器内置回零，回零与测距的边沿检测工况因此完全一致。

2026-10-12 经理改版: 取消 backoff 回退与 FINE_STEP 细步逼近，改为 creep
低速连续反查；sweep 60→150。home 基准从窗口正侧边沿移到**负侧边沿**(两者
相距约一个窗口宽≈50脉冲)，**部署本版后必须重新标定孔位**。
精度: creep 10 Step/s(×16=160 pulses/s)，轮询量化 20ms≈3.2脉冲+低速停车
距离≈1脉冲 → 重复精度约 ±4 脉冲(旧细搜为 ±2)。

防走样风险(待真机复验): 感应窗口实测仅约 50 脉冲宽(≈2°转盘)。SWEEP_SPEED=
150(×16=2400 pulses/s) → 穿越窗口仅 21ms ≈ 1.05 个 20ms 轮询周期，低于
"穿越时间≥2×轮询周期"的安全下限，存在两次轮询之间整窗跨过的漏检可能——
漏检表现为扫满行程报"行程内未找到感应点"，重试一次通常可过(相位随机)。
creep 阶段 160 pulses/s 穿窗 312ms，无此问题。

sweep 停点验算: 检测滞后(≤48脉冲)+停车距离(∝v², 按60时29折算≈181)最深约
230 脉冲，必已越过整个窗口(50)，故 creep 反查起点处 DI 应为释放态；若起点
仍在感应区内(异常)则快失败请重试。sweep 采用"先见释放帧才认触发"(armed)
判定——起点恰在窗口内时会多扫一圈从窗口正侧重新进入，保证停点几何一致。

注: DI1 常驻"原点开关"配置，搜索只读取 DI 电平，不改 DI 功能。设计要求
homing 传感器严禁配成限位(转盘无限位，自研固件会报 FF0E 超负限位故障)。

点动仅剩测距的返回起点一步: 返回前临时把最大速度(0x005B)降为 SEARCH_SPEED
(prepare 先读原值，结束/失败恢复)。0x005B 对速度模式同样钳速，故 sweep/creep
期间不降速(SWEEP_SPEED 150 > SEARCH_SPEED 60 会被钳)。

creep 前另临时把加速度(0x005F)降为 CREEP_ACCEL=100(2026-10-12 经理定值,
sweep 阶段保持全局值 1000 不受影响)，转 returning(长行程不必低加速度)或
结束时恢复原值；减速度(0x0061)不动，creep 触发停机仍按全局减速度急停。

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

    SWEEP_SPEED = 150            # sweep 连续扫描速度(Step/s)，见模块注释防走样风险
                                 # (2026-10-12 经理定值 80→150, 穿窗21ms≈1.05轮询
                                 # 周期低于2×下限, 漏检重试兜底, 待真机复验)
    CREEP_SPEED = 10             # creep 反查速度(Step/s)，决定边沿定位精度(≈±4脉冲)
                                 # (2026-10-12 经理定值, 取代原细搜 FINE_STEP 逐步逼近)
    CREEP_ACCEL = 100            # creep 阶段临时加速度(Step/s², 2026-10-12 经理定值,
                                 # 起步斜坡 0.1s/8脉冲; 停机走减速度 0x0061 不受影响)
    POLL_MS = 20                 # sweep/creep 期间状态轮询周期(2026-07-28 经理定值 25→20)
    MAX_TRAVEL = 10000           # 默认搜索行程上限(>默认齿轮比下转盘一圈 8800)；
                                 # 齿轮比可配置后调用方按实际一圈脉冲经 start()/
                                 # start_homing() 的 max_travel 参数传入覆盖
    CREEP_TRAVEL_LIMIT = 600     # creep 反查行程上限(停点最深~230+窗口50+裕量)，
                                 # 防触发信号异常后无限爬行
    SETTLE_MARGIN_MS = 300       # 单步整定裕量(返回起点用)
    STOP_SETTLE_MS = 400         # sweep/creep 触发停机后的整定时间
    OVERALL_TIMEOUT_MS = 120000  # 总看门狗
    SEARCH_SPEED = 60            # 返回起点时临时最大速度(Step/s)
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
        # idle/prepare/sweep/stopping/creep/creep_stopping/returning
        self._phase = "idle"
        self._settling = False
        self._awaiting = False   # returning 点动: 本整定周期是否还需处理一次状态
        self._sweeping = False   # sweep 阶段: 连续运动是否已启动
        self._armed = False      # sweep: 已见过释放帧，触发判定生效(起点在窗口内兜底)
        self._creeping = False   # creep 阶段: 反查运动是否已启动
        self._creep_start = 0    # creep 起点位置(行程保护基准)
        self._measured = 0
        self._return_to_start = True
        self._mode = "measure"   # measure=测距 / home=软件回零
        self._pps = 480
        self._max_travel = self.MAX_TRAVEL  # 实际行程上限，_begin 时可被覆盖
        self._orig_speed: int | None = None  # 搜索前的最大速度，结束后恢复
        self._speed_lowered = False          # 0x005B 是否已降为 SEARCH_SPEED
        self._orig_accel: int | None = None  # 搜索前的加速度，creep 降 100 后恢复
        self._accel_lowered = False          # creep 临时加速度是否已写入
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

    def start(
        self,
        pulses_per_sec: int = 480,
        return_to_start: bool = True,
        max_travel: int | None = None,
    ) -> None:
        """开始测量：清 0 → sweep → creep 反查 → (可选)返回起点。

        pulses_per_sec 用于按步长动态估算返回起点的整定时长(建议传 最大速度×细分数)。
        max_travel 覆盖搜索行程上限(建议传 转盘一圈脉冲+裕量)，None 用默认。
        """
        self._invert_di = load_di_invert()  # 每次启动读取最新本机配置
        self._begin(pulses_per_sec, return_to_start, "measure", max_travel)

    def start_homing(
        self, pulses_per_sec: int = 480, max_travel: int | None = None
    ) -> None:
        """软件回零：sweep → creep 反查到边沿 → 就地设零 → 夹持。

        与测距前 2 步协议/参数完全一致(经理要求)，完成发 homed 信号。
        """
        self._invert_di = load_di_invert()  # 每次启动读取最新本机配置
        self._begin(pulses_per_sec, False, "home", max_travel)

    def _begin(
        self,
        pulses_per_sec: int,
        return_to_start: bool,
        mode: str,
        max_travel: int | None = None,
    ) -> None:
        if self._phase != "idle":
            return
        self._mode = mode
        self._max_travel = (
            int(max_travel) if max_travel and max_travel > 0 else self.MAX_TRAVEL
        )
        self._pps = max(int(pulses_per_sec), 1)
        self._return_to_start = return_to_start
        self._measured = 0
        self._sweeping = False
        self._armed = False
        self._creeping = False
        self._creep_start = 0
        self._orig_speed = None
        self._speed_lowered = False
        self._orig_accel = None
        self._accel_lowered = False
        self._prepare_reads = {}
        # 先停机(写参数需停机)；DI 配置不动(DI1 常驻原点开关，只读电平)
        self._motor.disable()
        # 当前位置计数清 0
        self._motor.set_zero()
        # 读当前最大速度/加速度(临时改用、结束后恢复)，读齐后进入 sweep
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
        # 此处不降 0x005B——它对速度模式同样钳速(会把 sweep/creep 钳到
        # SEARCH_SPEED)，降速推迟到返回起点前(_lower_speed_for_return)
        # 进入 sweep，先取首帧状态(决定触发判定是否需要先见释放帧)
        self._phase = "sweep"
        self._motor.refresh_status()

    def _settle_for(self, step: int) -> int:
        """按步长/速度动态估算整定时长(ms)，×1.3 裕量 + 固定裕量。"""
        return int(abs(step) / self._pps * 1000 * 1.3) + self.SETTLE_MARGIN_MS

    def _jog(self, step: int) -> None:
        self._settling = True
        self._awaiting = False
        self._motor.move_relative(step)
        self._settle_timer.start(self._settle_for(step))

    def _lower_speed_for_return(self) -> None:
        """返回起点前临时降最大速度(此刻电机已停，sweep/creep 期间不可降)。"""
        if self._orig_speed is not None and self._orig_speed != self.SEARCH_SPEED:
            self._motor.write_param_32bit(_MAX_SPEED_ADDR, self.SEARCH_SPEED)
            self._speed_lowered = True

    def _lower_accel_for_creep(self) -> None:
        """creep 前临时降加速度(0x005F)软化起步，转 returning/结束时恢复。"""
        if self._orig_accel is not None and self._orig_accel != self.CREEP_ACCEL:
            self._motor.write_param_32bit(_ACCEL_ADDR, self.CREEP_ACCEL)
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
            # sweep 停机整定完毕，降加速度后进入低速反查(先取首帧确认已出感应区)
            self._lower_accel_for_creep()
            self._phase = "creep"
            self._motor.refresh_status()
            return
        if self._phase == "creep_stopping":
            # creep 触发停机整定完毕: 停点即感应窗口负侧边沿
            if self._mode == "home":
                # 就地设零建立 home 基准，保持使能夹持停在 home 点
                self._motor.set_zero()
                self._finish_home()
            elif self._return_to_start:
                self._phase = "returning"
                self._restore_accel()   # 返回长行程不必用 creep 低加速度
                self._lower_speed_for_return()
                self._jog(+self._measured)
            else:
                self._finish()
            return
        # returning 点动整定结束
        self._settling = False
        self._awaiting = True
        self._motor.refresh_status()  # 主动取一帧最新状态来推进

    def _on_status(self, status: MotorStatus) -> None:
        if (
            self._phase in ("idle", "prepare", "stopping", "creep_stopping")
            or self._settling
        ):
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
                # 首帧: 起点已在窗口内则先见释放帧才认触发(多扫一圈兜底)，
                # 保证停点总是从窗口正侧越入、几何一致
                self._sweeping = True
                self._armed = not triggered
                self._motor.set_speed(self.SWEEP_SPEED, 0)  # 0=反转(负向)
                self._poll_timer.start()
                return
            if not triggered:
                self._armed = True
            elif self._armed:
                self._poll_timer.stop()
                self._motor.stop()  # 减速停机(0x0007)，停点已越过整个窗口
                self._phase = "stopping"
                self._settle_timer.start(self.STOP_SETTLE_MS)
                return
            if abs(pos) > self._max_travel:
                self._poll_timer.stop()
                self._motor.stop()
                self._fail("行程内未找到感应点(方向/接线?)")
            return

        if self._phase == "creep":
            self.progress.emit(pos)
            if not self._creeping:
                # 首帧: 正常情况 sweep 停点已越过窗口，DI 应为释放态
                if triggered:
                    self._fail("sweep 停点仍在感应区内(停车距离异常)，请重试")
                    return
                self._creeping = True
                self._creep_start = pos
                self._motor.set_speed(self.CREEP_SPEED, 1)  # 1=正转(反向回查)
                self._poll_timer.start()
                return
            if triggered:
                # 迎到负侧边沿，立即停机(低速停车距离≈1脉冲)
                self._poll_timer.stop()
                self._motor.stop()
                self._measured = -pos       # 清 0 后边沿为负，距离取正
                self._phase = "creep_stopping"
                self._settle_timer.start(self.STOP_SETTLE_MS)
            elif abs(pos - self._creep_start) > self.CREEP_TRAVEL_LIMIT:
                self._poll_timer.stop()
                self._motor.stop()
                self._fail("反查未找到感应点(触发信号异常?)")
            return

        # returning 点动: 每个整定周期只处理一次，防其它来源的状态刷新重复推进
        if not self._awaiting:
            return
        self._awaiting = False
        self.progress.emit(pos)
        if self._phase == "returning":
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
        if self._speed_lowered and self._orig_speed is not None:
            self._motor.write_param_32bit(_MAX_SPEED_ADDR, self._orig_speed)
        self._restore_accel()
        self._speed_lowered = False
        self._orig_speed = None
        self._orig_accel = None
        self._phase = "idle"
        self._settling = False
        self._awaiting = False
        self._sweeping = False
        self._creeping = False
