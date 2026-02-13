"""Modbus 调试 Tab"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..communication.worker import CommWorker
from ..models.registers import get_register
from ..models.types import FunctionCode, ModbusRequest, ModbusResponse, RegisterType
from .widgets.hex_input import HexInput
from .widgets.log_viewer import LogViewer


class ModbusTab(QWidget):
    """Modbus 调试 Tab 页"""

    FC_OPTIONS = [
        ("0x03 读保持寄存器", FunctionCode.READ_HOLDING),
        ("0x04 读输入寄存器", FunctionCode.READ_INPUT),
        ("0x06 写单个寄存器", FunctionCode.WRITE_SINGLE),
        ("0x10 写多个寄存器", FunctionCode.WRITE_MULTIPLE),
    ]

    def __init__(self, worker: CommWorker, parent=None) -> None:
        super().__init__(parent)
        self._worker = worker
        self._slave_id = 1
        self._init_ui()
        self._connect_signals()
        self._on_fc_changed(0)

    def set_slave_id(self, slave_id: int) -> None:
        self._slave_id = slave_id

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 操作区
        group_op = QGroupBox("操作")
        op_layout = QVBoxLayout()

        # 第一行: 功能码 + 地址 + 数量
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("功能码:"))
        self._fc_combo = QComboBox()
        for label, fc in self.FC_OPTIONS:
            self._fc_combo.addItem(label, fc)
        self._fc_combo.currentIndexChanged.connect(self._on_fc_changed)
        row1.addWidget(self._fc_combo)

        row1.addWidget(QLabel("起始地址:"))
        self._addr_input = HexInput()
        self._addr_input.setFixedWidth(100)
        self._addr_input.setPlaceholderText("0000")
        self._addr_input.editingFinished.connect(self._on_address_changed)
        row1.addWidget(self._addr_input)

        row1.addWidget(QLabel("数量:"))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 125)
        self._count_spin.setValue(1)
        row1.addWidget(self._count_spin)

        row1.addStretch()
        op_layout.addLayout(row1)

        # 第二行: 写入值
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("写入值:"))
        self._value_input = HexInput()
        self._value_input.setPlaceholderText("高字节 低字节 (如: 00 06)")
        row2.addWidget(self._value_input, stretch=1)
        op_layout.addLayout(row2)

        # 寄存器提示
        self._reg_hint = QLabel("")
        self._reg_hint.setStyleSheet("color: #666; font-style: italic;")
        op_layout.addWidget(self._reg_hint)

        # 按钮行
        btn_row = QHBoxLayout()
        self._read_btn = QPushButton("读取")
        self._read_btn.setFixedWidth(100)
        self._read_btn.clicked.connect(self._on_read)
        btn_row.addWidget(self._read_btn)

        self._write_btn = QPushButton("写入")
        self._write_btn.setFixedWidth(100)
        self._write_btn.clicked.connect(self._on_write)
        btn_row.addWidget(self._write_btn)
        btn_row.addStretch()
        op_layout.addLayout(btn_row)

        group_op.setLayout(op_layout)
        layout.addWidget(group_op)

        # 结果表格
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["地址", "HEX 值", "十进制", "有符号", "说明"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, stretch=1)

        # 通讯日志
        group_log = QGroupBox("通讯日志")
        log_layout = QVBoxLayout()
        self._log = LogViewer()
        self._log.setMaximumHeight(150)
        log_layout.addWidget(self._log)
        group_log.setLayout(log_layout)
        layout.addWidget(group_log)

    def _connect_signals(self) -> None:
        self._worker.response_received.connect(self._on_response)
        self._worker.raw_data_sent.connect(self._log.append_tx)

    def _on_fc_changed(self, index: int) -> None:
        """功能码切换联动"""
        fc = self._fc_combo.currentData()
        is_read = fc in (FunctionCode.READ_HOLDING, FunctionCode.READ_INPUT)
        is_write_single = fc == FunctionCode.WRITE_SINGLE

        self._read_btn.setEnabled(is_read)
        self._write_btn.setEnabled(not is_read)
        self._count_spin.setEnabled(not is_write_single)
        self._value_input.setEnabled(not is_read)

        if is_write_single:
            self._count_spin.setValue(1)

    def _on_address_changed(self) -> None:
        """地址输入变化 - 显示寄存器提示"""
        data = self._addr_input.get_bytes()
        if len(data) < 2:
            addr_val = int.from_bytes(data, "big") if data else 0
        else:
            addr_val = int.from_bytes(data[:2], "big")

        fc = self._fc_combo.currentData()
        reg_type = (
            RegisterType.INPUT
            if fc == FunctionCode.READ_INPUT
            else RegisterType.HOLDING
        )
        reg = get_register(addr_val, reg_type)
        if reg:
            hint_parts = [f"0x{reg.address:04X} - {reg.name}"]
            if reg.min_val is not None and reg.max_val is not None:
                hint_parts.append(f"范围: {reg.min_val}~{reg.max_val}")
            if reg.unit:
                hint_parts.append(f"单位: {reg.unit}")
            if reg.default_val is not None:
                hint_parts.append(f"默认: {reg.default_val}")
            if reg.description:
                hint_parts.append(reg.description)
            self._reg_hint.setText(" | ".join(hint_parts))
        else:
            self._reg_hint.setText("未知寄存器")

    def _get_address(self) -> int:
        data = self._addr_input.get_bytes()
        if not data:
            return 0
        return int.from_bytes(data[:2], "big") if len(data) >= 2 else data[0]

    def _on_read(self) -> None:
        """读取按钮"""
        fc = self._fc_combo.currentData()
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=fc,
            address=self._get_address(),
            count=self._count_spin.value(),
        )
        self._worker.send_modbus(req)

    def _on_write(self) -> None:
        """写入按钮"""
        fc = self._fc_combo.currentData()
        value_bytes = self._value_input.get_bytes()

        if fc == FunctionCode.WRITE_SINGLE:
            if len(value_bytes) < 2:
                value_bytes = value_bytes.rjust(2, b"\x00")
            value = int.from_bytes(value_bytes[:2], "big")
            req = ModbusRequest(
                slave_id=self._slave_id,
                function_code=fc,
                address=self._get_address(),
                values=[value],
            )
        else:  # WRITE_MULTIPLE
            values = []
            for i in range(0, len(value_bytes), 2):
                chunk = value_bytes[i : i + 2]
                if len(chunk) < 2:
                    chunk = chunk + b"\x00"
                values.append(int.from_bytes(chunk, "big"))
            req = ModbusRequest(
                slave_id=self._slave_id,
                function_code=fc,
                address=self._get_address(),
                count=len(values),
                values=values,
            )
        self._worker.send_modbus(req)

    def _on_response(self, resp: ModbusResponse) -> None:
        """处理响应"""
        # 记录原始帧
        if resp.raw_rx:
            self._log.append_rx(resp.raw_rx)

        if resp.is_error:
            self._log.append_info(f"错误: code={resp.error_code}")
            return

        # 读取响应 - 填充表格
        if resp.function_code in (FunctionCode.READ_HOLDING, FunctionCode.READ_INPUT):
            self._fill_table(resp)
        else:
            self._log.append_info("写入成功")

    def _fill_table(self, resp: ModbusResponse) -> None:
        """填充结果表格"""
        if resp.raw_tx and len(resp.raw_tx) >= 4:
            start_addr = (resp.raw_tx[2] << 8) | resp.raw_tx[3]
            fc = resp.raw_tx[1]
        else:
            start_addr = 0
            fc = 0x03
        reg_type = (
            RegisterType.INPUT
            if fc == FunctionCode.READ_INPUT
            else RegisterType.HOLDING
        )

        self._table.setRowCount(len(resp.values))
        for i, val in enumerate(resp.values):
            addr = start_addr + i
            # 地址
            self._table.setItem(i, 0, QTableWidgetItem(f"0x{addr:04X}"))
            # HEX 值
            self._table.setItem(i, 1, QTableWidgetItem(f"0x{val:04X}"))
            # 十进制
            self._table.setItem(i, 2, QTableWidgetItem(str(val)))
            # 有符号
            signed_val = val - 65536 if val > 32767 else val
            self._table.setItem(i, 3, QTableWidgetItem(str(signed_val)))
            # 说明
            reg = get_register(addr, reg_type)
            desc = reg.name if reg else ""
            self._table.setItem(i, 4, QTableWidgetItem(desc))
