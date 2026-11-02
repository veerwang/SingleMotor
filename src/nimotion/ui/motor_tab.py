"""电机控制 Tab（容器）"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QTabWidget, QWidget

from ..services.motor_service import MotorService
from .motor_alarm import MotorAlarmPanel
from .motor_control import MotorControlPanel
from .motor_params import MotorParamsPanel
from .motor_status import MotorStatusPanel
from .turret_panel import TurretPanel


class MotorTab(QWidget):
    """电机控制 Tab 页 - 左侧状态面板 + 右侧子 Tab"""

    def __init__(self, motor_service: MotorService, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)

        # 左侧: 状态面板
        self._status_panel = MotorStatusPanel(self._motor)
        layout.addWidget(self._status_panel)

        # 右侧: 子 Tab
        self._sub_tabs = QTabWidget()
        self._turret_panel = TurretPanel(self._motor)
        self._sub_tabs.addTab(self._turret_panel, "物镜转换")
        self._sub_tabs.addTab(
            MotorControlPanel(self._motor), "运动控制"
        )
        self._params_panel = MotorParamsPanel(self._motor)
        self._sub_tabs.addTab(self._params_panel, "参数设置")
        self._sub_tabs.addTab(
            MotorAlarmPanel(self._motor), "报警信息"
        )
        layout.addWidget(self._sub_tabs, stretch=1)

        # 齿轮变比修改后转盘页即时刷新(理论孔位/点动上限/间隙换算)，无需重启
        self._params_panel.gear_config_changed.connect(
            self._turret_panel.refresh_gear_ratio
        )
