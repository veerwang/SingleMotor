"""公共串口连接栏"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from ..communication.serial_port import SerialConfig, SerialPort


class ConnectionBar(QWidget):
    """串口连接栏 - 统一管理串口配置和连接/断开操作"""

    connect_requested = pyqtSignal(object)  # SerialConfig
    disconnect_requested = pyqtSignal()
    slave_id_changed = pyqtSignal(int)

    BAUDRATES = [9600, 19200, 38400, 57600, 115200, 256000, 500000, 1000000]
    PARITIES = [("无 (N)", "N"), ("偶 (E)", "E"), ("奇 (O)", "O")]
    STOPBITS = [("1", 1), ("2", 2)]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._connected = False
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)

        # 串口选择
        layout.addWidget(QLabel("端口:"))
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(120)
        layout.addWidget(self._port_combo)

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.clicked.connect(self._refresh_ports)
        layout.addWidget(self._refresh_btn)

        # 波特率
        layout.addWidget(QLabel("波特率:"))
        self._baud_combo = QComboBox()
        for baud in self.BAUDRATES:
            self._baud_combo.addItem(str(baud), baud)
        self._baud_combo.setCurrentText("115200")
        layout.addWidget(self._baud_combo)

        # 校验
        layout.addWidget(QLabel("校验:"))
        self._parity_combo = QComboBox()
        for label, value in self.PARITIES:
            self._parity_combo.addItem(label, value)
        layout.addWidget(self._parity_combo)

        # 停止位
        layout.addWidget(QLabel("停止位:"))
        self._stop_combo = QComboBox()
        for label, value in self.STOPBITS:
            self._stop_combo.addItem(label, value)
        layout.addWidget(self._stop_combo)

        # 从站地址
        layout.addWidget(QLabel("从站:"))
        self._slave_spin = QSpinBox()
        self._slave_spin.setRange(1, 247)
        self._slave_spin.setValue(1)
        self._slave_spin.valueChanged.connect(self.slave_id_changed.emit)
        layout.addWidget(self._slave_spin)

        # 连接按钮
        self._connect_btn = QPushButton("连接")
        self._connect_btn.setFixedWidth(100)
        self._connect_btn.setProperty("cssClass", "primary")
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self._connect_btn)

        layout.addStretch()

        # 初始化端口列表
        self._refresh_ports()

    def _refresh_ports(self) -> None:
        """刷新可用串口列表"""
        current = self._port_combo.currentText()
        self._port_combo.clear()
        ports = SerialPort.list_ports()
        self._port_combo.addItems(ports)
        # 恢复之前选择
        idx = self._port_combo.findText(current)
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)
        elif not current:
            # 首次加载时优先选择 ttyUSB0
            usb_idx = self._port_combo.findText("/dev/ttyUSB0")
            if usb_idx >= 0:
                self._port_combo.setCurrentIndex(usb_idx)

    def _on_connect_clicked(self) -> None:
        if self._connected:
            self.disconnect_requested.emit()
        else:
            config = SerialConfig(
                port=self._port_combo.currentText(),
                baudrate=self._baud_combo.currentData(),
                parity=self._parity_combo.currentData(),
                stopbits=self._stop_combo.currentData(),
            )
            self.connect_requested.emit(config)

    @property
    def slave_id(self) -> int:
        return self._slave_spin.value()

    def on_connected(self) -> None:
        """连接成功回调"""
        self._connected = True
        self._connect_btn.setText("断开")
        self._set_controls_enabled(False)

    def on_disconnected(self) -> None:
        """断开连接回调"""
        self._connected = False
        self._connect_btn.setText("连接")
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self._port_combo.setEnabled(enabled)
        self._refresh_btn.setEnabled(enabled)
        self._baud_combo.setEnabled(enabled)
        self._parity_combo.setEnabled(enabled)
        self._stop_combo.setEnabled(enabled)
