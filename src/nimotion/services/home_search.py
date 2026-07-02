"""软件回零/测距控制器。

不使用驱动器内置回零(method 17 会在原点清零计数器)，而是软件小步搜索到
homing 感应点(默认 DI1)，测量"当前位置 → 感应点"的脉冲距离。

流程：每次测量前把当前位置计数**清 0**(设置零点 0x0047) → 负向粗搜(大步)撞到
感应点 → 回退释放开关 → 细步逼近取精确触发点 → (可选)返回起点。清 0 后触发点
为负值，距离取其绝对值。

异步状态机，逐步驱动：发一步 move_relative → 等待整定(settle) → 读状态判断是否
触发 → 下一步。**整定时长按步长/速度动态估算并留裕量**，避免固定超时打断长行程
(尤其返回移动)；另设总看门狗兜底。搜索期间临时把 DI1 配为负限位作硬件安全网
(撞到自动停)，结束后还原。
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from ..models.types import MotorStatus
from .motor_service import MotorService

_DI_FUNC_ADDR = 0x002C          # DI 功能配置
_DI_NEG_LIMIT = 0x00000001      # DI1=负限位(搜索安全网)
_DI_NONE = 0x00000000           # DI1=无


class HomeSearch(QObject):
    """软件搜索感应点并测量当前位置→感应点距离。"""

    progress = pyqtSignal(int)   # 搜索中当前位置(脉冲)
    finished = pyqtSignal(int)   # 测得距离(脉冲, 正值)
    failed = pyqtSignal(str)     # 失败原因

    COARSE_STEP = 100            # 粗搜步长(脉冲)
    FINE_STEP = 5                # 细搜步长(脉冲)
    BACKOFF = 150                # 触发后回退步长(释放开关)
    MAX_TRAVEL = 10000           # 搜索行程上限(>转盘一圈 8800)
    SETTLE_MARGIN_MS = 300       # 单步整定裕量
    OVERALL_TIMEOUT_MS = 120000  # 总看门狗

    def __init__(self, motor: MotorService, di_bit: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor
        self._di_bit = di_bit
        self._phase = "idle"     # idle/coarse/backoff/fine/returning
        self._settling = False
        self._awaiting = False   # 本整定周期是否还需处理一次状态(防重复处理)
        self._measured = 0
        self._return_to_start = True
        self._pps = 480

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._on_settle_done)
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(lambda: self._fail("搜索超时"))
        self._motor.status_updated.connect(self._on_status)

    @property
    def running(self) -> bool:
        return self._phase != "idle"

    def cancel(self) -> None:
        """中止搜索(如设备断连)，还原状态，不发 finished/failed。"""
        if self._phase != "idle":
            self._teardown()

    def start(self, pulses_per_sec: int = 480, return_to_start: bool = True) -> None:
        """开始测量：清 0 → 粗搜 → 回退 → 细搜 → (可选)返回起点。

        pulses_per_sec 用于按步长动态估算整定时长(建议传 最大速度×细分数)。
        """
        if self._phase != "idle":
            return
        self._pps = max(int(pulses_per_sec), 1)
        self._return_to_start = return_to_start
        self._measured = 0
        # 先停机确保可写 DI；DI1=负限位作硬件安全网(撞到自动停)
        self._motor.disable()
        self._motor.write_param_32bit(_DI_FUNC_ADDR, _DI_NEG_LIMIT)
        # 当前位置计数清 0
        self._motor.set_zero()
        # 进入粗搜，等首帧状态
        self._phase = "coarse"
        self._settling = False
        self._awaiting = True
        self._watchdog.start(self.OVERALL_TIMEOUT_MS)
        self._motor.refresh_status()

    # -- 内部 --

    def _settle_for(self, step: int) -> int:
        """按步长/速度动态估算整定时长(ms)，×1.3 裕量 + 固定裕量。"""
        return int(abs(step) / self._pps * 1000 * 1.3) + self.SETTLE_MARGIN_MS

    def _jog(self, step: int) -> None:
        self._settling = True
        self._awaiting = False
        self._motor.move_relative(step)
        self._settle_timer.start(self._settle_for(step))

    def _on_settle_done(self) -> None:
        self._settling = False
        self._awaiting = True
        self._motor.refresh_status()  # 主动取一帧最新状态来推进

    def _on_status(self, status: MotorStatus) -> None:
        # 每个整定周期只处理一次，避免其它来源的状态刷新导致重复发步
        if self._phase == "idle" or self._settling or not self._awaiting:
            return
        self._awaiting = False
        triggered = bool(status.di_status & (1 << self._di_bit))
        pos = status.position
        self.progress.emit(pos)

        if self._phase == "coarse":
            if triggered:
                self._phase = "backoff"
                self._jog(+self.BACKOFF)
            elif abs(pos) > self.MAX_TRAVEL:
                self._fail("行程内未找到感应点(方向/接线?)")
            else:
                self._jog(-self.COARSE_STEP)
        elif self._phase == "backoff":
            if triggered:
                self._jog(+self.BACKOFF)   # 继续退回直到开关释放
            else:
                self._phase = "fine"
                self._jog(-self.FINE_STEP)
        elif self._phase == "fine":
            if triggered:
                self._measured = -pos       # 清 0 后触发点为负，距离取正
                if self._return_to_start:
                    self._phase = "returning"
                    self._jog(+self._measured)
                else:
                    self._finish()
            else:
                self._jog(-self.FINE_STEP)
        elif self._phase == "returning":
            self._finish()

    def _finish(self) -> None:
        self._teardown()
        self.finished.emit(self._measured)

    def _fail(self, reason: str) -> None:
        self._teardown()
        self.failed.emit(reason)

    def _teardown(self) -> None:
        self._settle_timer.stop()
        self._watchdog.stop()
        self._motor.disable()                                   # 脱机
        self._motor.write_param_32bit(_DI_FUNC_ADDR, _DI_NONE)  # 还原 DI1=无
        self._phase = "idle"
        self._settling = False
        self._awaiting = False
