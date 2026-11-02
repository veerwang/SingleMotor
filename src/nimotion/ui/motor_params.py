"""电机参数设置面板"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
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

from ..models.app_config import (
    DEFAULT_GEAR_TEETH,
    load_di_invert,
    load_gear_teeth,
    save_di_invert,
    save_direction_inverted,
    save_gear_teeth,
)
from ..models.registers import get_register
from ..models.types import DataType, RegisterType
from ..services.motor_service import MotorService

# 参数分组: (组名, 地址列表, 是否只读)
PARAM_GROUPS: list[tuple[str, list[int], bool]] = [
    ("通讯参数（只读）", [0x0000, 0x0001, 0x0002], True),
    # 0x0015 减速电流已屏蔽: SDM42 驱动器无减速电流(2026-07-27 经理指示)
    ("电流参数", [0x0016, 0x0018, 0x0017, 0x0019], False),
    ("运动参数", [0x001A, 0x005B, 0x005D, 0x005F, 0x0061], False),
    ("停机设置", [0x003A, 0x003B, 0x003C], False),
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

    @property
    def is_modified(self) -> bool:
        """值是否被用户修改过（相对于上次读取的值）"""
        return self._read_value is not None and self._spin.value() != self._read_value

    def set_readonly(self, readonly: bool) -> None:
        """设置只读模式"""
        self._spin.setReadOnly(readonly)
        if readonly:
            self._spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            self._spin.setStyleSheet("background-color: #F0F0F0;")

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

    gear_config_changed = pyqtSignal()  # 齿轮变比(本机配置)已修改并保存

    def __init__(self, motor_service: MotorService, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._param_widgets: dict[int, ParamWidget] = {}
        self._motor.param_read.connect(self._on_param_read)
        self._motor.operation_done.connect(self._on_operation_done)
        self._read_count = 0
        self._read_total = 0
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # 软件选项：本机配置，不写驱动器寄存器
        sw_group = QGroupBox("软件选项（本机）")
        sw_form = QFormLayout()
        self._invert_check = QCheckBox("电机方向反转")
        self._invert_check.setChecked(self._motor.direction_inverted)
        self._invert_check.toggled.connect(self._on_invert_toggled)
        sw_form.addRow(self._invert_check)
        self._di_invert_check = QCheckBox("原点开关极性取反")
        self._di_invert_check.setChecked(load_di_invert())
        self._di_invert_check.toggled.connect(self._on_di_invert_toggled)
        sw_form.addRow(self._di_invert_check)
        # 齿轮变比：输入齿数由软件换算比值，避免小数输错
        gear_row = QHBoxLayout()
        turret_teeth, motor_teeth = load_gear_teeth()
        self._gear_turret_spin = QSpinBox()
        self._gear_turret_spin.setRange(1, 999)
        self._gear_turret_spin.setValue(turret_teeth)
        self._gear_turret_spin.setToolTip("转盘大齿轮齿数（默认 132）")
        gear_row.addWidget(self._gear_turret_spin)
        gear_row.addWidget(QLabel("/"))
        self._gear_motor_spin = QSpinBox()
        self._gear_motor_spin.setRange(1, 999)
        self._gear_motor_spin.setValue(motor_teeth)
        self._gear_motor_spin.setToolTip("电机小齿轮齿数（默认 48）")
        gear_row.addWidget(self._gear_motor_spin)
        self._gear_ratio_label = QLabel()
        self._gear_ratio_label.setStyleSheet("color: #888;")
        gear_row.addWidget(self._gear_ratio_label)
        gear_row.addStretch()
        sw_form.addRow("齿轮变比（转盘齿数/电机齿数）:", gear_row)
        self._update_gear_ratio_label()
        self._gear_turret_spin.valueChanged.connect(self._on_gear_teeth_changed)
        self._gear_motor_spin.valueChanged.connect(self._on_gear_teeth_changed)
        sw_hint = QLabel(
            "电机方向反转: 适配相序相反的电机型号(所有运动指令与位置/方向读数软件侧"
            "统一取反)；原点开关极性取反: 适配感应逻辑相反的物镜转换器(回零/测距时"
            "DI1 触发判定取反)；齿轮变比: 转盘大齿轮/电机小齿轮齿数(默认 132/48"
            "=2.75)，决定理论孔位脉冲、同步与间隙补偿换算。均保存于本机"
            " motor_config.json；修改后请重新回零，需重新标定或同步孔位。"
        )
        sw_hint.setStyleSheet("color: #888; font-size: 10px;")
        sw_hint.setWordWrap(True)
        sw_form.addRow(sw_hint)
        sw_group.setLayout(sw_form)
        scroll_layout.addWidget(sw_group)

        for group_name, addresses, readonly in PARAM_GROUPS:
            group = QGroupBox(group_name)
            form = QFormLayout()
            for addr in addresses:
                reg = get_register(addr, RegisterType.HOLDING)
                if reg is None:
                    continue
                widget = ParamWidget(addr)
                if readonly:
                    widget.set_readonly(True)
                self._param_widgets[addr] = widget

                # 构建标签: 名称 + 标记
                label = reg.name
                tags = []
                if reg.disable_required:
                    tags.append("需脱机")
                if reg.restart_required:
                    tags.append("需重启")
                if tags:
                    label += f"  ({', '.join(tags)})"
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

        # 操作提示
        hint_layout = QVBoxLayout()
        hint_layout.setSpacing(2)
        hint1 = QLabel("操作流程: 读取参数 -> 修改数值 -> 设置参数 -> 保存到 EEPROM")
        hint1.setStyleSheet("color: #1976D2; font-size: 11px;")
        hint_layout.addWidget(hint1)
        hint2 = QLabel("黄色背景 = 已修改未写入 | 需脱机的参数写入时会自动先脱机")
        hint2.setStyleSheet("color: #888; font-size: 10px;")
        hint_layout.addWidget(hint2)
        layout.addLayout(hint_layout)

        # 状态提示
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #666; font-size: 12px;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

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

    def _on_invert_toggled(self, checked: bool) -> None:
        """方向反转切换：立即生效并持久化到本机配置文件"""
        self._motor.direction_inverted = checked
        save_direction_inverted(checked)
        self._set_status(
            f"电机方向反转已{'开启' if checked else '关闭'}（已保存到本机）。"
            "请重新回零；如孔位标定建立于切换前，需重新标定。",
            "#E65100",
        )

    def _update_gear_ratio_label(self) -> None:
        ratio = self._gear_turret_spin.value() / self._gear_motor_spin.value()
        default_mark = (
            "（默认）"
            if (self._gear_turret_spin.value(), self._gear_motor_spin.value())
            == DEFAULT_GEAR_TEETH
            else ""
        )
        self._gear_ratio_label.setText(f"= {ratio:.4g}{default_mark}")

    def _on_gear_teeth_changed(self) -> None:
        """齿轮齿数修改：立即生效并持久化到本机配置文件"""
        save_gear_teeth(
            self._gear_turret_spin.value(), self._gear_motor_spin.value()
        )
        self._update_gear_ratio_label()
        self.gear_config_changed.emit()
        self._set_status(
            f"齿轮变比已保存到本机: {self._gear_turret_spin.value()}"
            f"/{self._gear_motor_spin.value()}"
            f" = {self._gear_turret_spin.value() / self._gear_motor_spin.value():.4g}"
            "（默认 132/48=2.75）。理论孔位/同步/间隙换算已按新比值即时刷新"
            "（已标定孔位保持不变）；请重新回零并重新标定或同步孔位。",
            "#E65100",
        )

    def _on_di_invert_toggled(self, checked: bool) -> None:
        """原点开关极性取反切换：立即生效并持久化到本机配置文件"""
        self._motor.di_invert = checked
        save_di_invert(checked)
        self._set_status(
            f"原点开关极性取反已{'开启' if checked else '关闭'}（已保存到本机）。"
            "回零/测距将在下次启动时使用新极性。",
            "#E65100",
        )

    def _on_read_all(self) -> None:
        """读取所有参数"""
        self._read_count = 0
        self._read_total = len(self._param_widgets)
        self._set_status("正在读取参数...", "#1976D2")
        for addr in self._param_widgets:
            reg = get_register(addr, RegisterType.HOLDING)
            count = reg.count if reg else 1
            self._motor.read_param(addr, count)

    def _on_write_all(self) -> None:
        """只写入已修改的非只读参数"""
        # 收集只读地址
        readonly_addrs = set()
        for _name, addresses, readonly in PARAM_GROUPS:
            if readonly:
                readonly_addrs.update(addresses)

        # 分类: 需要脱机的参数 和 普通参数
        need_disable: list[tuple[int, ParamWidget, object]] = []
        normal: list[tuple[int, ParamWidget, object]] = []
        for addr, widget in self._param_widgets.items():
            if addr in readonly_addrs:
                continue
            if not widget.is_modified:
                continue
            reg = get_register(addr, RegisterType.HOLDING)
            if reg and reg.disable_required:
                need_disable.append((addr, widget, reg))
            else:
                normal.append((addr, widget, reg))

        if not need_disable and not normal:
            self._set_status("没有需要写入的参数（请先读取，再修改数值）", "#FF9800")
            return

        # 构建写入详情
        details = []

        # 有需要脱机的参数，先发脱机命令
        if need_disable:
            self._motor.disable()
            names = []
            for addr, widget, reg in need_disable:
                self._write_one(addr, widget, reg)
                names.append(f"{reg.name}: {widget.value}")
            details.append(f"[自动脱机] {', '.join(names)}")

        if normal:
            names = []
            for addr, widget, reg in normal:
                self._write_one(addr, widget, reg)
                names.append(f"{reg.name}: {widget.value}")
            details.append(', '.join(names))

        total = len(need_disable) + len(normal)
        msg = f"已发送 {total} 个参数: {' | '.join(details)}"
        self._set_status(msg, "#4CAF50")

    def _write_one(self, addr: int, widget: ParamWidget, reg) -> None:
        """写入单个参数"""
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
            self._set_status("已发送保存 EEPROM 命令", "#4CAF50")

    def _on_restore(self) -> None:
        reply = QMessageBox.warning(
            self,
            "警告",
            "确定要恢复出厂默认参数？\n此操作需要重启电机才能生效。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._motor.restore_defaults()
            self._set_status("已发送恢复出厂命令，请重启电机", "#FF9800")

    def _on_param_read(self, address: int, value: int) -> None:
        """接收读取到的参数值"""
        if address in self._param_widgets:
            self._param_widgets[address].set_read_value(value)
            self._read_count += 1
            if self._read_total > 0 and self._read_count >= self._read_total:
                self._set_status(
                    f"读取完成，共 {self._read_count} 个参数", "#4CAF50"
                )
                self._read_total = 0

    def _on_operation_done(self, success: bool, message: str) -> None:
        """接收写入操作结果"""
        if not success:
            self._set_status(f"操作失败: {message}", "#F44336")

    def _set_status(self, text: str, color: str) -> None:
        """设置状态标签"""
        self._status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._status_label.setText(text)
