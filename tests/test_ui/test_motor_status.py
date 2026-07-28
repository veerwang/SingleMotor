"""MotorStatusPanel 测试。

回归: 断连会取消"自动"轮询，重连后必须自动恢复——否则转盘/回零的
完成检测收不到状态帧，电机实际到位仍报"运动超时"(2026-07-28 定位)。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nimotion.communication.worker import CommWorker
from nimotion.services.motor_service import MotorService
from nimotion.ui.motor_status import MotorStatusPanel


@pytest.fixture
def app():
    from PyQt5.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    return a


@pytest.fixture
def panel(app):
    worker = CommWorker()
    service = MotorService(worker)
    return MotorStatusPanel(service)


def test_auto_poll_on_by_default(panel):
    assert panel._auto_cb.isChecked()
    assert panel._timer.isActive()


def test_auto_poll_stops_on_disconnect(panel, app):
    panel._motor._worker.disconnected.emit()
    app.processEvents()
    assert not panel._auto_cb.isChecked()
    assert not panel._timer.isActive()


def test_auto_poll_restored_on_reconnect(panel, app):
    """断连→重连后自动轮询必须恢复(完成检测依赖状态帧)。"""
    panel._motor._worker.disconnected.emit()
    app.processEvents()
    assert not panel._timer.isActive()

    panel._motor._worker.connected.emit()
    app.processEvents()
    assert panel._auto_cb.isChecked()
    assert panel._timer.isActive()
