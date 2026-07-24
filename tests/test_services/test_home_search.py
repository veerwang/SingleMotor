"""HomeSearch 混合式测距状态机单元测试(用模拟电机, 无硬件/无事件循环)。"""

import pytest
from PyQt5.QtCore import QObject, pyqtSignal

from nimotion.models.types import MotorStatus
from nimotion.services.home_search import HomeSearch


class FakeMotor(QObject):
    """模拟电机。

    感应窗口模型: sensor_pos 为窗口正侧边沿，active 当
    sensor_pos - window < pos <= sensor_pos。默认 window 很大(半直线，兼容
    基础用例)；防走样用例传实测值 window=50。

    速度模式(set_speed)后每次 tick() 前进 SWEEP_TICK 脉冲(模拟 50ms 轮询间隔
    内 400 pulses/s × 0.05s = 20 脉冲)并发一帧状态。
    DI1 常驻原点开关(设计要求: 严禁配限位)，搜索全程不应写 DI 配置。
    """

    SWEEP_TICK = 20

    status_updated = pyqtSignal(object)
    param_read = pyqtSignal(int, int)

    def __init__(self, sensor_pos: int, window: int = 10**9) -> None:
        super().__init__()
        self.pos = 0
        self.di = 0
        self.sensor_pos = sensor_pos
        self.window = window
        self.alarm_code = 0
        self.clamped = False
        self.zero_calls = 0
        self.di_config_writes: list[int] = []
        self.jogs: list[int] = []
        self.disabled = 0
        self.stops = 0
        self.sweeping = False
        self.sweep_dir = -1
        self.max_speed = 600
        self.speed_writes: list[int] = []
        self.respond_to_read = True

    def disable(self) -> None:
        self.disabled += 1
        self.sweeping = False
        self.clamped = False

    def hold_position_clamp(self) -> None:
        self.clamped = True

    def stop(self) -> None:
        self.stops += 1
        self.sweeping = False

    def set_zero(self) -> None:
        self.zero_calls += 1
        self.pos = 0
        self._update_di()

    def set_speed(self, speed: int, direction: int) -> None:
        self.sweeping = True
        self.sweep_dir = 1 if direction == 1 else -1

    def read_param(self, addr: int, count: int = 1) -> None:
        if addr == 0x005B and self.respond_to_read:
            self.param_read.emit(addr, self.max_speed)

    def write_param_32bit(self, addr: int, value: int, signed: bool = False) -> None:
        if addr == 0x002C:
            self.di_config_writes.append(value)
        elif addr == 0x005B:
            self.max_speed = value
            self.speed_writes.append(value)

    def move_relative(self, step: int) -> None:
        self.jogs.append(step)
        self.pos += step
        self._update_di()

    def _update_di(self) -> None:
        in_window = (self.sensor_pos - self.window) < self.pos <= self.sensor_pos
        self.di = 1 if in_window else 0

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
            self.pos += self.sweep_dir * self.SWEEP_TICK
            self._update_di()
        self.refresh_status()


def _drive(hs: HomeSearch, fake: FakeMotor, results: list, max_steps: int = 5000) -> None:
    """无事件循环下手动推进: sweep 阶段模拟轮询 tick，其余阶段触发整定完成。"""
    for _ in range(max_steps):
        if results:
            return
        if hs._phase == "sweep":
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

    # sweep 停在 -1340(20 步进网格)，回退后细搜(步长5)首个 ≤ -1333 的采样点
    # 是 -1335，量化误差 < FINE_STEP
    assert results == [("ok", 1335)]
    assert fake.pos == 0          # 已返回起点
    assert fake.di_config_writes == []  # 搜索全程不改 DI 配置(严禁配限位)
    assert fake.stops >= 1          # sweep 触发后发过减速停机
    assert fake.disabled >= 1       # 结束已脱机
    assert hs.running is False


def test_search_no_return_stays_at_sensor(app):
    fake = FakeMotor(sensor_pos=-800)
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    assert results == [800]
    assert fake.pos == -800        # 停在感应点，未返回


def test_zeroing_before_measure(app):
    """起点非 0 时，测距前应先清零，距离仍为到感应点的真实位移。"""
    fake = FakeMotor(sensor_pos=-500)
    fake.pos = 7935               # 模拟遗留的非零计数
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    assert results == [500]        # 清零后测得 500，而非受 7935 影响


def test_narrow_window_not_skipped(app):
    """防走样: 实测 50 脉冲窄窗口在 sweep 的 20 脉冲/轮询步进下不会被跨过。"""
    fake = FakeMotor(sensor_pos=-1333, window=50)  # 窗口 [-1382, -1333]
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(("ok", d)))
    hs.failed.connect(lambda r: results.append(("fail", r)))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    assert results == [("ok", 1335)]


def test_start_inside_window_skips_sweep(app):
    """起点已在感应窗口内: 不启动连续扫描，直接回退+细搜。"""
    fake = FakeMotor(sensor_pos=10, window=50)  # 窗口 [-39, +10] 含起点 0
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    assert results == [-10]        # 边沿在正侧 10 处，测量值为负
    assert fake.stops == 0         # 未进入连续扫描
    assert all(j > 0 or abs(j) == hs.FINE_STEP for j in fake.jogs)


def test_speed_lowered_during_search_and_restored(app):
    """搜索前临时把最大速度降为 SEARCH_SPEED，结束后恢复原值。"""
    fake = FakeMotor(sensor_pos=-500)
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, fake, results)
    assert results == [500]
    assert fake.speed_writes[0] == HomeSearch.SEARCH_SPEED  # 搜索前降速
    assert fake.speed_writes[-1] == 600                     # 结束后恢复
    assert fake.max_speed == 600


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
    assert results == [("fail", "读取最大速度超时")]
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


def test_software_homing_zeroes_at_edge_and_clamps(app):
    """软件回零: 与测距同协议(sweep→回退→细搜)，边沿设零并夹持，不脱机结束。"""
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
