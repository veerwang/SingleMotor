"""HomeSearch 测距/回零状态机单元测试(用模拟电机, 无硬件/无事件循环)。

2026-10-12 经理改版后的流程: sweep 高速负向扫描(150) → 越窗停车 →
creep 低速(10)正向反查 → 触发即停(= 窗口负侧边沿) → 设零/返回。
"""

import pytest
from PyQt5.QtCore import QObject, pyqtSignal

from nimotion.models.types import MotorStatus
from nimotion.services.home_search import HomeSearch


class FakeMotor(QObject):
    """模拟电机。

    感应窗口模型: sensor_pos 为窗口正侧边沿，窗口宽 window —— 触发条件
    0 <= (sensor_pos - pos) % circumference < window(circumference=None 时
    不取模, 线性)。

    运动模型: set_speed 后每次 tick() 前进一格并发一帧状态; 高速(≥50)档
    步进 SWEEP_TICK=20、停机惯性 brake(默认120, 模拟 150 速度下停点越过
    整个窗口); 低速档步进 CREEP_TICK=4(真机 2 Step/s 下≈0.6 脉冲/轮询,
    此处取 4 保证网格确定性)、停机无惯性。
    注: 真机 150 速度下每轮询前进 48 脉冲, 贴近 50 窗口宽(防走样风险在
    真机复验, 本处用 20 保证逻辑测试确定性)。

    DI1 常驻原点开关(设计要求: 严禁配限位)，搜索全程不应写 DI 配置。
    """

    SWEEP_TICK = 20
    CREEP_TICK = 4

    status_updated = pyqtSignal(object)
    param_read = pyqtSignal(int, int)

    def __init__(
        self,
        sensor_pos: int,
        window: int = 50,
        brake: int = 120,
        circumference: int | None = None,
    ) -> None:
        super().__init__()
        self.pos = 0
        self.di = 0
        self.sensor_pos = sensor_pos
        self.window = window
        self.brake = brake
        self.circumference = circumference
        self.alarm_code = 0
        self.clamped = False
        self.zero_calls = 0
        self.di_config_writes: list[int] = []
        self.jogs: list[int] = []
        self.disabled = 0
        self.stops = 0
        self.sweeping = False
        self.sweep_dir = -1
        self.tick_step = self.SWEEP_TICK
        self.cur_brake = 0
        self.max_speed = 600
        self.speed_writes: list[int] = []
        self.accel = 1000
        self.accel_writes: list[int] = []
        self.min_speed = 16
        self.min_speed_writes: list[int] = []
        self.respond_to_read = True

    def disable(self) -> None:
        self.disabled += 1
        self.sweeping = False
        self.clamped = False

    def hold_position_clamp(self) -> None:
        self.clamped = True

    def stop(self) -> None:
        self.stops += 1
        if self.sweeping:
            # 模拟减速停车惯性: 高速档停点越过触发点 brake 脉冲
            self.pos += self.sweep_dir * self.cur_brake
            self._update_di()
        self.sweeping = False

    def set_zero(self) -> None:
        self.zero_calls += 1
        self.pos = 0
        self._update_di()

    def set_speed(self, speed: int, direction: int) -> None:
        self.sweeping = True
        self.sweep_dir = 1 if direction == 1 else -1
        if speed >= 50:
            self.tick_step = self.SWEEP_TICK
            self.cur_brake = self.brake
        else:
            self.tick_step = self.CREEP_TICK
            self.cur_brake = 0

    def read_param(self, addr: int, count: int = 1) -> None:
        if not self.respond_to_read:
            return
        if addr == 0x005B:
            self.param_read.emit(addr, self.max_speed)
        elif addr == 0x005F:
            self.param_read.emit(addr, self.accel)
        elif addr == 0x005D:
            self.param_read.emit(addr, self.min_speed)

    def write_param_32bit(self, addr: int, value: int, signed: bool = False) -> None:
        if addr == 0x002C:
            self.di_config_writes.append(value)
        elif addr == 0x005B:
            self.max_speed = value
            self.speed_writes.append(value)
        elif addr == 0x005F:
            self.accel = value
            self.accel_writes.append(value)
        elif addr == 0x005D:
            self.min_speed = value
            self.min_speed_writes.append(value)

    def move_relative(self, step: int) -> None:
        self.jogs.append(step)
        self.pos += step
        self._update_di()

    def _update_di(self) -> None:
        delta = self.sensor_pos - self.pos
        if self.circumference:
            delta %= self.circumference
        self.di = 1 if 0 <= delta < self.window else 0

    def refresh_status(self) -> None:
        s = MotorStatus()
        s.position = self.pos
        s.di_status = self.di
        s.is_running = self.sweeping
        s.alarm_code = self.alarm_code
        self.status_updated.emit(s)

    def tick(self) -> None:
        """模拟一个轮询周期: 连续运动前进一格并上报状态。"""
        if self.sweeping:
            self.pos += self.sweep_dir * self.tick_step
            self._update_di()
        self.refresh_status()


def _drive(hs: HomeSearch, fake: FakeMotor, results: list, max_steps: int = 5000) -> None:
    """无事件循环下手动推进: sweep/creep 阶段模拟轮询 tick，其余触发整定完成。"""
    for _ in range(max_steps):
        if results:
            return
        if hs._phase in ("sweep", "creep") and fake.sweeping:
            fake.tick()
        else:
            hs._on_settle_done()


@pytest.fixture
def app():
    from PyQt5.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    return a


def test_search_measures_distance_and_returns(app):
    fake = FakeMotor(sensor_pos=-1333)
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(("ok", d)))
    hs.failed.connect(lambda r: results.append(("fail", r)))

    hs.start(pulses_per_sec=960, return_to_start=True)
    _drive(hs, fake, results)

    # sweep 在 -1340 触发、惯性停至 -1460(已越窗) → creep +4 步进网格上
    # 首个回到窗口 [-1382,-1333] 内的采样点是 -1380(负侧边沿 F=-1382,
    # 量化误差 < CREEP_TICK)
    assert results == [("ok", 1380)]
    assert fake.pos == 0          # 已返回起点
    assert fake.di_config_writes == []  # 搜索全程不改 DI 配置(严禁配限位)
    assert fake.stops >= 2          # sweep 触发停机 + creep 触发停机
    assert fake.disabled >= 1       # 结束已脱机
    assert hs.running is False


def test_search_no_return_stays_at_sensor(app):
    fake = FakeMotor(sensor_pos=-800)
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    # sweep 在 -800 触发、停至 -920 → creep 首个入窗采样点 -848
    assert results == [848]
    assert fake.pos == -848        # 停在感应窗口负侧边沿，未返回


def test_zeroing_before_measure(app):
    """起点非 0 时，测距前应先清零，距离仍为到感应点的真实位移。"""
    fake = FakeMotor(sensor_pos=-500)
    fake.pos = 7935               # 模拟遗留的非零计数
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    assert results == [548]        # 清零后测得 548，而非受 7935 影响


def test_narrow_window_not_skipped(app):
    """实测 50 脉冲窄窗口在 sweep 模拟步进(20/轮询)下可靠捕获并反查到边沿。"""
    fake = FakeMotor(sensor_pos=-1333, window=50)
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(("ok", d)))
    hs.failed.connect(lambda r: results.append(("fail", r)))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    assert results == [("ok", 1380)]


def test_start_inside_window_sweeps_full_circle(app):
    """起点已在感应窗口内: 先见释放帧才认触发(armed)，多扫一圈从正侧重新
    进窗，保证停点几何与常规路径一致。"""
    fake = FakeMotor(sensor_pos=10, window=50, circumference=8800)  # 起点 0 在窗口内
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.failed.connect(lambda r: results.append(("fail", r)))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    assert results == [8836]       # 绕一圈后在窗口负侧边沿停下
    assert fake.stops >= 2         # 经过了完整 sweep+creep


def test_speed_lowered_only_for_return_and_restored(app):
    """仅返回起点前把最大速度降为 SEARCH_SPEED，结束后恢复原值；
    sweep/creep 期间不得降速(否则 150 会被 0x005B 钳住)。"""
    fake = FakeMotor(sensor_pos=-500)
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.start(pulses_per_sec=960, return_to_start=True)
    _drive(hs, fake, results)
    assert results == [548]
    assert fake.speed_writes == [HomeSearch.SEARCH_SPEED, 600]  # 返回前降、结束恢复
    assert fake.max_speed == 600

    # 不返回起点则全程不触碰 0x005B
    fake2 = FakeMotor(sensor_pos=-500)
    hs2 = HomeSearch(fake2)
    results2 = []
    hs2.finished.connect(lambda d: results2.append(d))
    hs2.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs2, fake2, results2)
    assert results2 == [548]
    assert fake2.speed_writes == []


def test_creep_params_lowered_and_restored(app):
    """creep 前临时把加速度降为 CREEP_ACCEL、最小速度(起停速度, 对目标速度
    托底)降为 CREEP_SPEED，转 returning/结束后恢复原值；sweep 阶段两者均
    保持全局值不受影响。"""
    fake = FakeMotor(sensor_pos=-500)
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.start(pulses_per_sec=960, return_to_start=True)
    _drive(hs, fake, results)
    assert results == [548]
    assert fake.accel_writes == [HomeSearch.CREEP_ACCEL, 1000]  # creep 降、返回前恢复
    assert fake.accel == 1000
    assert fake.min_speed_writes == [HomeSearch.CREEP_SPEED, 16]
    assert fake.min_speed == 16

    # 回零模式同样降/恢复(teardown 兜底恢复)
    fake2 = FakeMotor(sensor_pos=-500)
    hs2 = HomeSearch(fake2)
    homed = []
    hs2.homed.connect(lambda: homed.append(True))
    hs2.start_homing(pulses_per_sec=960)
    _drive(hs2, fake2, homed)
    assert homed == [True]
    assert fake2.accel_writes == [HomeSearch.CREEP_ACCEL, 1000]
    assert fake2.accel == 1000
    assert fake2.min_speed_writes == [HomeSearch.CREEP_SPEED, 16]
    assert fake2.min_speed == 16


def test_fail_when_speed_read_times_out(app):
    """读不到最大速度时失败并还原配置，不带病搜索。"""
    fake = FakeMotor(sensor_pos=-500)
    fake.respond_to_read = False
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(("ok", d)))
    hs.failed.connect(lambda r: results.append(("fail", r)))
    hs.start(pulses_per_sec=960)
    hs._on_settle_done()  # 模拟读取超时到期
    assert results == [("fail", "读取最大速度/加速度超时")]
    assert fake.di_config_writes == []
    assert hs.running is False


def test_fail_fast_on_alarm(app):
    """sweep 途中驱动器报警(如欠压 3120)应立即失败，不等看门狗。"""
    fake = FakeMotor(sensor_pos=-5000)
    hs = HomeSearch(fake)
    results = []
    hs.failed.connect(lambda r: results.append(r))
    hs.start(pulses_per_sec=960)
    # 推进几个轮询后注入报警
    for _ in range(5):
        fake.tick()
    fake.alarm_code = 0x3120
    fake.tick()
    assert results and "0x3120" in results[0]
    assert hs.running is False
    assert fake.disabled >= 1


def test_fail_fast_if_stop_inside_window(app):
    """异常防护: sweep 停点仍在感应区内(停车距离异常短)时快失败请重试，
    不得在窗口内部随意设零。"""
    fake = FakeMotor(sensor_pos=-800, window=200, brake=0)  # 无惯性→停在窗口内
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(("ok", d)))
    hs.failed.connect(lambda r: results.append(("fail", r)))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    assert results and results[0][0] == "fail"
    assert "感应区" in results[0][1]
    assert fake.zero_calls == 1    # 仅开始清零，未在窗口内设零


def test_creep_travel_limit(app):
    """creep 反查行程保护: 触发信号消失(传感器异常)时限程失败，不无限爬行。"""
    fake = FakeMotor(sensor_pos=-800)
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(("ok", d)))
    hs.failed.connect(lambda r: results.append(("fail", r)))
    hs.start(pulses_per_sec=960, return_to_start=False)
    # 推进到 sweep 触发停机，然后让传感器"消失"
    for _ in range(200):
        if fake.stops >= 1:
            break
        fake.tick()
    assert fake.stops >= 1
    fake.window = 0
    fake._update_di()
    _drive(hs, fake, results)
    assert results == [("fail", "反查未找到感应点(触发信号异常?)")]


def test_software_homing_zeroes_at_edge_and_clamps(app):
    """软件回零: 与测距同协议(sweep→creep)，负侧边沿设零并夹持，不脱机结束。"""
    fake = FakeMotor(sensor_pos=-1333, window=50)
    hs = HomeSearch(fake)
    homed = []
    hs.homed.connect(lambda: homed.append(True))
    hs.failed.connect(lambda r: homed.append(("fail", r)))
    hs.start_homing(pulses_per_sec=960)
    _drive(hs, fake, homed)
    assert homed == [True]
    assert fake.zero_calls == 2      # 开始清零一次 + 边沿设零一次
    assert fake.pos == 0             # 边沿即新的 home 基准
    assert fake.clamped is True      # 结束保持使能夹持(而非脱机)
    assert fake.di_config_writes == []
    assert fake.speed_writes == []   # 回零无返回步，不触碰 0x005B
    assert hs.running is False


def test_software_homing_fail_fast_on_alarm(app):
    """软件回零途中报警同样快失败，且不夹持。"""
    fake = FakeMotor(sensor_pos=-5000)
    hs = HomeSearch(fake)
    results = []
    hs.failed.connect(lambda r: results.append(r))
    hs.start_homing(pulses_per_sec=960)
    for _ in range(3):
        fake.tick()
    fake.alarm_code = 0x3120
    fake.tick()
    assert results and "0x3120" in results[0]
    assert fake.clamped is False
    assert hs.running is False


def test_fail_when_sensor_unreachable(app):
    fake = FakeMotor(sensor_pos=-20000)  # 超出 MAX_TRAVEL
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(("ok", d)))
    hs.failed.connect(lambda r: results.append(("fail", r)))
    hs.start(pulses_per_sec=960)
    _drive(hs, fake, results)
    assert results and results[0][0] == "fail"
    assert fake.di_config_writes == []  # 失败路径同样不触碰 DI 配置
    assert fake.stops >= 1              # 越限已停机
