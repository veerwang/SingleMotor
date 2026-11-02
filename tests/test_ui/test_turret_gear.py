"""TurretPanel 齿轮比联动测试。

回归: 齿轮变比(本机配置)修改后，转盘页须即时按新比值刷新——未标定孔位
理论值、点动步进上限、同步提示跟随变化，已标定孔位保持不变，无需重启。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nimotion.communication.worker import CommWorker
from nimotion.models.turret import TurretPosition
from nimotion.services.motor_service import MotorService
from nimotion.ui import turret_panel as tp_mod
from nimotion.ui.turret_panel import TurretPanel

MICROSTEP_REG = 0x001A
MICROSTEP_16_REG_VALUE = 4  # 2**4 = 16 细分

_SLOTS = (
    TurretPosition.POS_1,
    TurretPosition.POS_2,
    TurretPosition.POS_3,
    TurretPosition.POS_4,
)


@pytest.fixture
def app():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def gear(monkeypatch):
    """可变齿轮比：默认 2.75(每孔2200)，测试中改值模拟本机配置变更。"""
    holder = {"ratio": 2.75}
    monkeypatch.setattr(tp_mod, "load_gear_ratio", lambda: holder["ratio"])
    return holder


def _make_panel(monkeypatch, calibration):
    """构造 TurretPanel：隔离标定文件读写，并模拟细分参数读取完成。"""
    monkeypatch.setattr(tp_mod, "load_calibration", lambda: dict(calibration))
    monkeypatch.setattr(tp_mod, "save_calibration", lambda _c: None)
    panel = TurretPanel(MotorService(CommWorker()))
    panel._on_param_read(MICROSTEP_REG, MICROSTEP_16_REG_VALUE)
    return panel


@pytest.fixture
def panel(app, gear, monkeypatch):
    return _make_panel(monkeypatch, {})


def _spin_values(panel):
    return [panel._pos_spins[pos].value() for pos in _SLOTS]


def test_initial_theoretical_values(panel):
    """默认齿轮比 2.75 下每孔 2200：理论孔位/点动上限/同步提示一致。"""
    assert _spin_values(panel) == [0, 2200, 4400, 6600]
    assert panel._jog_step_spin.maximum() == 2200
    assert "2200" in panel._sync_btn.toolTip()


def test_refresh_follows_gear_ratio(panel, gear):
    """齿轮比变更后 refresh_gear_ratio 须按新比值刷新全部派生项。"""
    gear["ratio"] = 3.0  # 每孔 = 200*16*3.0/4 = 2400
    panel.refresh_gear_ratio()
    assert _spin_values(panel) == [0, 2400, 4800, 7200]
    assert panel._jog_step_spin.maximum() == 2400
    assert "2400" in panel._sync_btn.toolTip()


def test_refresh_keeps_calibrated_holes(app, gear, monkeypatch):
    """已标定孔位不随齿轮比刷新(物理位置须重新标定/同步)，未标定孔位跟随。"""
    panel = _make_panel(monkeypatch, {TurretPosition.POS_2: 2210})
    gear["ratio"] = 3.0
    panel.refresh_gear_ratio()
    assert panel._pos_spins[TurretPosition.POS_2].value() == 2210
    assert panel._pos_spins[TurretPosition.POS_3].value() == 4800


def test_sync_uses_current_gear_ratio(panel, gear):
    """「同步」按点击时的齿轮比计算每孔脉冲，而非固定 2200。"""
    gear["ratio"] = 3.0
    panel._pos_spins[TurretPosition.POS_1].setValue(100)
    panel._on_sync()
    assert _spin_values(panel) == [100, 2500, 4900, 7300]


def test_params_panel_emits_gear_config_changed(app, monkeypatch):
    """参数页齿数修改须发出 gear_config_changed(转盘页即时刷新依赖此信号)。"""
    from nimotion.ui import motor_params as mp_mod

    monkeypatch.setattr(mp_mod, "save_gear_teeth", lambda _t, _m: None)
    params = mp_mod.MotorParamsPanel(MotorService(CommWorker()))
    fired: list[int] = []
    params.gear_config_changed.connect(lambda: fired.append(1))
    params._gear_turret_spin.setValue(params._gear_turret_spin.value() + 12)
    assert fired
