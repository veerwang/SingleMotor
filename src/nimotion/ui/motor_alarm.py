"""报警信息面板"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models.error_codes import get_error_text
from ..models.types import FunctionCode, ModbusRequest, MotorStatus
from ..services.motor_service import MotorService


class MotorAlarmPanel(QWidget):
    """报警信息子面板"""

    def __init__(self, motor_service: MotorService, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor_service
        self._motor.status_updated.connect(self._on_status_updated)
        self._motor.param_read.connect(self._on_param_read)
        self._alarm_count = 0
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 当前报警
        group_current = QGroupBox("当前报警")
        current_layout = QHBoxLayout()
        self._alarm_code_label = QLabel("0x0000")
        self._alarm_code_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        current_layout.addWidget(self._alarm_code_label)

        self._alarm_desc_label = QLabel("无报警")
        self._alarm_desc_label.setStyleSheet("font-size: 14px;")
        current_layout.addWidget(self._alarm_desc_label)
        current_layout.addStretch()
        group_current.setLayout(current_layout)
        layout.addWidget(group_current)

        # 历史报警表格
        group_history = QGroupBox("历史报警")
        history_layout = QVBoxLayout()
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["序号", "报警码", "描述"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setAlternatingRowColors(True)
        history_layout.addWidget(self._table)
        group_history.setLayout(history_layout)
        layout.addWidget(group_history, stretch=1)

        # 按钮行
        btn_row = QHBoxLayout()

        read_current_btn = QPushButton("读取当前报警")
        read_current_btn.clicked.connect(self._on_read_current)
        btn_row.addWidget(read_current_btn)

        read_history_btn = QPushButton("读取历史报警")
        read_history_btn.clicked.connect(self._on_read_history)
        btn_row.addWidget(read_history_btn)

        clear_history_btn = QPushButton("清除历史报警")
        clear_history_btn.clicked.connect(self._on_clear_history)
        btn_row.addWidget(clear_history_btn)

        clear_fault_btn = QPushButton("清除故障状态")
        clear_fault_btn.clicked.connect(self._motor.clear_fault)
        btn_row.addWidget(clear_fault_btn)

        layout.addLayout(btn_row)

    def _on_read_current(self) -> None:
        """读取当前报警值"""
        self._motor.read_param(0x0026, 1)

    def _on_read_history(self) -> None:
        """读取历史报警: 先读个数再逐个读"""
        self._motor.read_param(0x0027, 1)

    def _on_clear_history(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认",
            "确定要清除历史报警记录？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._motor.write_param(0x0073, 0x6C64)
            self._table.setRowCount(0)

    def _on_status_updated(self, status: MotorStatus) -> None:
        """从定时刷新的状态中更新报警显示"""
        self._update_alarm_display(status.alarm_code)

    def _on_param_read(self, address: int, value: int) -> None:
        """处理读取到的报警参数"""
        if address == 0x0026:
            self._update_alarm_display(value)
        elif address == 0x0027:
            # 报警个数
            self._alarm_count = value
            # 读取每个历史报警
            self._table.setRowCount(value)
            for i in range(value):
                self._motor.read_param(0x0028 + i, 1)
        elif 0x0028 <= address <= 0x002F:
            # 历史报警值
            row = address - 0x0028
            if row < self._table.rowCount():
                self._table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
                self._table.setItem(row, 1, QTableWidgetItem(f"0x{value:04X}"))
                self._table.setItem(row, 2, QTableWidgetItem(get_error_text(value)))

    def _update_alarm_display(self, code: int) -> None:
        self._alarm_code_label.setText(f"0x{code:04X}")
        if code:
            text = get_error_text(code)
            self._alarm_desc_label.setText(text)
            self._alarm_desc_label.setStyleSheet("font-size: 14px; color: red;")
            self._alarm_code_label.setStyleSheet(
                "font-weight: bold; font-size: 14px; color: red;"
            )
        else:
            self._alarm_desc_label.setText("无报警")
            self._alarm_desc_label.setStyleSheet("font-size: 14px; color: green;")
            self._alarm_code_label.setStyleSheet(
                "font-weight: bold; font-size: 14px; color: green;"
            )
