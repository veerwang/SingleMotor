"""HomeSearch 软件搜索测距状态机单元测试(用模拟电机, 无硬件/无事件循环)。"""

import pytest
from PyQt5.QtCore import QObject, pyqtSignal

from nimotion.models.types import MotorStatus
from nimotion.services.home_search import HomeSearch


class FakeMotor(QObject):
    """模拟电机：move_relative 更新位置，到达感应点(<=sensor_pos)时 DI1=1。

    配了负限位(DI1=neg_limit)后，负向移动不会越过 sensor_pos(硬件安全网)。
    """

    status_updated = pyqtSignal(object)

    def __init__(self, sensor_pos: int) -> None:
        super().__init__()
        self.pos = 0
        self.di = 0
        self.sensor_pos = sensor_pos
        self.neg_limit = False
        self.jogs: list[int] = []
        self.disabled = 0

    def disable(self) -> None:
        self.disabled += 1

    def set_zero(self) -> None:
        self.pos = 0
        self._update_di()

    def write_param_32bit(self, addr: int, value: int, signed: bool = False) -> None:
        if addr == 0x002C:
            self.neg_limit = value == 0x00000001

    def move_relative(self, step: int) -> None:
        self.jogs.append(step)
        new = self.pos + step
        if self.neg_limit and step < 0 and new <= self.sensor_pos:
            new = self.sensor_pos  # 撞到限位停住
        self.pos = new
        self._update_di()

    def _update_di(self) -> None:
        self.di = 1 if self.pos <= self.sensor_pos else 0

    def refresh_status(self) -> None:
        s = MotorStatus()
        s.position = self.pos
        s.di_status = self.di
        s.is_running = False
        self.status_updated.emit(s)


def _drive(hs: HomeSearch, results: list, max_steps: int = 5000) -> None:
    """无事件循环下手动推进：反复触发整定完成，直到出结果。"""
    for _ in range(max_steps):
        if results:
            return
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
    _drive(hs, results)

    assert results == [("ok", 1333)]
    assert fake.pos == 0          # 已返回起点
    assert fake.neg_limit is False  # DI1 已还原为无
    assert fake.disabled >= 1       # 结束已脱机
    assert hs.running is False


def test_search_no_return_stays_at_sensor(app):
    fake = FakeMotor(sensor_pos=-800)
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(d))
    hs.start(pulses_per_sec=960, return_to_start=False)
    _drive(hs, results)
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
    _drive(hs, results)
    assert results == [500]        # 清零后测得 500，而非受 7935 影响


def test_fail_when_sensor_unreachable(app):
    fake = FakeMotor(sensor_pos=-20000)  # 超出 MAX_TRAVEL
    hs = HomeSearch(fake)
    results = []
    hs.finished.connect(lambda d: results.append(("ok", d)))
    hs.failed.connect(lambda r: results.append(("fail", r)))
    hs.start(pulses_per_sec=960)
    _drive(hs, results)
    assert results and results[0][0] == "fail"
    assert fake.neg_limit is False   # 失败也还原了配置
