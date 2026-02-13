"""电机参数设置面板"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..models.registers import HOLDING_REGISTERS, get_register
from ..models.types import DataType, RegisterType
from ..services.motor_service import MotorService

# 参数分组: (组名, [(地址, 控件类型)])
PARAM_GROUPS: list[tuple[str, list[int]]] = [
    ("通讯参数", [0x0000, 0x0001, 0x0002]),
    ("电流参数", [0x0016, 0x0018, 0x0017, 0x0015, 0x0019]),
    ("运动参数", [0x001A, 0x005B, 0x005D, 0x005F, 0x0061]),
    ("停机设置", [0x003A, 0x003B, 0x003C]),
]


class ParamWidget(QWidget):
    """单个参数控件"""

    def __init__(self, address: int, parent=None) -> None:
        super().__init__(parent)
        self.address = address
        reg = get_register(address, RegisterType.HOLDING)
        self._reg = reg
        self._read_value: int | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if reg and reg.data_type in (DataType.UINT32, DataType.INT32):
            self._spin = QSpinBox()
            self._spin.setRange(
                reg.min_val if reg.min_val is not None else -2147483648,
                reg.max_val if reg.max_val is not None else 2147483647,
            )
        else:
            self._spin = QSpinBox()
            self._spin.setRange(
                reg.min_val if reg and reg.min_val is not None else 0,
                reg.max_val if reg and reg.max_val is not None else 65535,
            )

        if reg and reg.default_val is not None:
            self._spin.setValue(reg.default_val)

        self._spin.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._spin)

        if reg and reg.unit:
            layout.addWidget(QLabel(reg.unit))

    @property
    def value(self) -> int:
        return self._spin.value()

    @value.setter
    def value(self, v: int) -> None:
        self._spin.setValue(v)

    def set_read_value(self, v: int) -> None:
        """设置从电机读回的值"""
        self._read_value = v
        self._spin.setValue(v)
        self._update_style()

    def _on_value_changed(self, v: int) -> None:
        self._update_style()

    def _update_style(self) -> None:
        if self._read_value is not None and self._spin.value() != self._read_value:
            self._spin.setStyleSheet("background-color: #FFFDE7;")
        else:
            self._spin.setStyleSheet("")


class MotorParamsPanel(QWidget):
    """参数设置子面板"""

    def __init__(self, motor_service: MotorService, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._param_widgets: dict[int, ParamWidget] = {}
        self._motor.param_read.connect(self._on_param_read)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        for group_name, addresses in PARAM_GROUPS:
            group = QGroupBox(group_name)
            form = QFormLayout()
            for addr in addresses:
                reg = get_register(addr, RegisterType.HOLDING)
                if reg is None:
                    continue
                widget = ParamWidget(addr)
                self._param_widgets[addr] = widget
                label = f"{reg.name}"
                if reg.restart_required:
                    label += " *"
                form.addRow(label + ":", widget)
                if reg.description:
                    hint = QLabel(reg.description)
                    hint.setStyleSheet("color: #888; font-size: 10px;")
                    form.addRow("", hint)
            group.setLayout(form)
            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        # 提示
        hint = QLabel("* 标记的参数修改后需要重启电机")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(hint)

        # 按钮行
        btn_row = QHBoxLayout()
        read_btn = QPushButton("读取参数")
        read_btn.clicked.connect(self._on_read_all)
        btn_row.addWidget(read_btn)

        write_btn = QPushButton("设置参数")
        write_btn.clicked.connect(self._on_write_all)
        btn_row.addWidget(write_btn)

        save_btn = QPushButton("保存到 EEPROM")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        restore_btn = QPushButton("恢复出厂")
        restore_btn.clicked.connect(self._on_restore)
        btn_row.addWidget(restore_btn)

        layout.addLayout(btn_row)

    def _on_read_all(self) -> None:
        """读取所有参数"""
        for addr in self._param_widgets:
            reg = get_register(addr, RegisterType.HOLDING)
            count = reg.count if reg else 1
            self._motor.read_param(addr, count)

    def _on_write_all(self) -> None:
        """写入所有已修改的参数"""
        for addr, widget in self._param_widgets.items():
            reg = get_register(addr, RegisterType.HOLDING)
            if reg and reg.data_type in (DataType.UINT32, DataType.INT32):
                signed = reg.data_type == DataType.INT32
                self._motor.write_param_32bit(addr, widget.value, signed)
            else:
                self._motor.write_param(addr, widget.value)

    def _on_save(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认",
            "确定要将当前参数保存到 EEPROM？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._motor.save_params()

    def _on_restore(self) -> None:
        reply = QMessageBox.warning(
            self,
            "警告",
            "确定要恢复出厂默认参数？\n此操作需要重启电机才能生效。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._motor.restore_defaults()

    def _on_param_read(self, address: int, value: int) -> None:
        """接收读取到的参数值"""
        if address in self._param_widgets:
            self._param_widgets[address].set_read_value(value)
