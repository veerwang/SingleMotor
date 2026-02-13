"""串口调试 Tab"""

from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..communication import crc16
from ..communication.worker import CommWorker
from .widgets.hex_input import HexInput
from .widgets.log_viewer import LogViewer

# 预定义快捷指令: (名称, 帧数据不含CRC, 首字节替换为从站地址)
QUICK_COMMANDS: list[tuple[str, list[int]]] = [
    ("读状态字", [0x01, 0x04, 0x00, 0x1F, 0x00, 0x01]),
    ("读电压", [0x01, 0x04, 0x00, 0x17, 0x00, 0x01]),
    ("读位置", [0x01, 0x04, 0x00, 0x21, 0x00, 0x02]),
    ("读速度", [0x01, 0x04, 0x00, 0x23, 0x00, 0x02]),
    ("读报警", [0x01, 0x04, 0x00, 0x26, 0x00, 0x01]),
    ("启动", [0x01, 0x06, 0x00, 0x51, 0x00, 0x06]),
    ("使能", [0x01, 0x06, 0x00, 0x51, 0x00, 0x07]),
    ("运行", [0x01, 0x06, 0x00, 0x51, 0x00, 0x0F]),
    ("停止", [0x01, 0x06, 0x00, 0x51, 0x00, 0x07]),
    ("清除故障", [0x01, 0x06, 0x00, 0x51, 0x00, 0x80]),
]


class SerialTab(QWidget):
    """串口调试 Tab 页"""

    def __init__(self, worker: CommWorker, parent=None) -> None:
        super().__init__(parent)
        self._worker = worker
        self._slave_id = 1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_send)
        self._init_ui()
        self._connect_signals()

    def set_slave_id(self, slave_id: int) -> None:
        self._slave_id = slave_id

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 快捷指令区
        group_quick = QGroupBox("快捷指令")
        grid = QGridLayout()
        self._quick_buttons: list[QPushButton] = []
        for i, (name, _) in enumerate(QUICK_COMMANDS):
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda checked, idx=i: self._on_quick_command(idx))
            grid.addWidget(btn, i // 5, i % 5)
            self._quick_buttons.append(btn)
        group_quick.setLayout(grid)
        layout.addWidget(group_quick)

        # 接收区
        self._log = LogViewer()
        layout.addWidget(self._log, stretch=1)

        # 接收区控制栏
        rx_bar = QHBoxLayout()
        self._hex_display_cb = QCheckBox("HEX 显示")
        self._hex_display_cb.setChecked(True)
        self._hex_display_cb.toggled.connect(self._log.set_hex_mode)
        rx_bar.addWidget(self._hex_display_cb)

        self._timestamp_cb = QCheckBox("时间戳")
        self._timestamp_cb.setChecked(True)
        self._timestamp_cb.toggled.connect(self._log.set_timestamp)
        rx_bar.addWidget(self._timestamp_cb)

        clear_btn = QPushButton("清空")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self._log.clear)
        rx_bar.addWidget(clear_btn)
        rx_bar.addStretch()
        layout.addLayout(rx_bar)

        # 发送区
        group_send = QGroupBox("发送")
        send_layout = QVBoxLayout()

        # 历史记录 + 输入
        input_row = QHBoxLayout()
        self._history_combo = QComboBox()
        self._history_combo.setEditable(False)
        self._history_combo.setMinimumWidth(200)
        self._history_combo.activated.connect(self._on_history_selected)
        input_row.addWidget(self._history_combo)

        self._hex_input = HexInput()
        input_row.addWidget(self._hex_input, stretch=1)
        send_layout.addLayout(input_row)

        # 发送控制栏
        ctrl_row = QHBoxLayout()
        self._append_crc_cb = QCheckBox("追加 CRC")
        self._append_crc_cb.setChecked(True)
        ctrl_row.addWidget(self._append_crc_cb)

        send_btn = QPushButton("发送")
        send_btn.setFixedWidth(80)
        send_btn.clicked.connect(self._on_send)
        ctrl_row.addWidget(send_btn)

        self._timer_cb = QCheckBox("定时发送")
        self._timer_cb.toggled.connect(self._on_timer_toggled)
        ctrl_row.addWidget(self._timer_cb)

        ctrl_row.addWidget(QLabel("间隔 ms:"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(50, 60000)
        self._interval_spin.setValue(1000)
        ctrl_row.addWidget(self._interval_spin)

        ctrl_row.addStretch()
        send_layout.addLayout(ctrl_row)
        group_send.setLayout(send_layout)
        layout.addWidget(group_send)

    def _connect_signals(self) -> None:
        self._worker.raw_data_received.connect(self._on_data_received)
        self._worker.raw_data_sent.connect(self._on_data_sent)

    def _on_quick_command(self, idx: int) -> None:
        """快捷指令点击"""
        _, frame_data = QUICK_COMMANDS[idx]
        data = list(frame_data)
        data[0] = self._slave_id  # 替换从站地址
        frame = crc16.append(bytes(data))
        self._hex_input.set_bytes(frame)
        self._send_data(frame)

    def _on_send(self) -> None:
        """发送按钮点击"""
        data = self._hex_input.get_bytes()
        if not data:
            return
        if self._append_crc_cb.isChecked():
            data = crc16.append(data)
            self._hex_input.set_bytes(data)  # 更新显示
        self._send_data(data)

    def _send_data(self, data: bytes) -> None:
        """执行发送并记录历史"""
        self._worker.send_raw(data)
        # 添加到历史记录
        hex_str = " ".join(f"{b:02X}" for b in data)
        if self._history_combo.findText(hex_str) < 0:
            self._history_combo.insertItem(0, hex_str)
            if self._history_combo.count() > 20:
                self._history_combo.removeItem(20)

    def _on_history_selected(self, index: int) -> None:
        text = self._history_combo.itemText(index)
        self._hex_input.setText(text)

    def _on_timer_toggled(self, checked: bool) -> None:
        if checked:
            self._timer.start(self._interval_spin.value())
        else:
            self._timer.stop()

    def _on_timer_send(self) -> None:
        self._on_send()

    def _on_data_received(self, data: bytes) -> None:
        self._log.append_rx(data)

    def _on_data_sent(self, data: bytes) -> None:
        self._log.append_tx(data)
