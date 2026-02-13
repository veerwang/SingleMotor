"""主窗口"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..communication.serial_port import SerialConfig
from ..communication.worker import CommWorker
from ..services.motor_service import MotorService
from .connection_bar import ConnectionBar
from .modbus_tab import ModbusTab
from .motor_tab import MotorTab
from .serial_tab import SerialTab


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # 核心组件
        self._worker = CommWorker(self)
        self._motor_service = MotorService(self._worker)

        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 连接栏
        self._conn_bar = ConnectionBar()
        layout.addWidget(self._conn_bar)

        # Tab 页
        self._tabs = QTabWidget()

        self._serial_tab = SerialTab(self._worker)
        self._tabs.addTab(self._serial_tab, "串口调试")

        self._modbus_tab = ModbusTab(self._worker)
        self._tabs.addTab(self._modbus_tab, "Modbus 调试")

        self._motor_tab = MotorTab(self._motor_service)
        self._tabs.addTab(self._motor_tab, "电机控制")

        layout.addWidget(self._tabs)
        self.setCentralWidget(central)

        # 状态栏
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._conn_status = QLabel("未连接")
        self._status_bar.addWidget(self._conn_status)
        self._bytes_label = QLabel("TX: 0  RX: 0")
        self._status_bar.addPermanentWidget(self._bytes_label)

    def _connect_signals(self) -> None:
        # 连接栏
        self._conn_bar.connect_requested.connect(self._on_connect)
        self._conn_bar.disconnect_requested.connect(self._on_disconnect)
        self._conn_bar.slave_id_changed.connect(self._on_slave_id_changed)

        # Worker
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.connection_error.connect(self._on_connection_error)
        self._worker.bytes_count_updated.connect(self._on_bytes_updated)

    def _on_connect(self, config: SerialConfig) -> None:
        self._worker.connect_port(config)

    def _on_disconnect(self) -> None:
        self._worker.disconnect_port()

    def _on_connected(self) -> None:
        self._conn_bar.on_connected()
        config = self._worker._serial.config
        self._conn_status.setText(f"已连接 {config.port} {config.baudrate}")
        self._conn_status.setStyleSheet("color: green;")

    def _on_disconnected(self) -> None:
        self._conn_bar.on_disconnected()
        self._conn_status.setText("未连接")
        self._conn_status.setStyleSheet("color: gray;")

    def _on_connection_error(self, error: str) -> None:
        QMessageBox.critical(self, "连接失败", error)

    def _on_slave_id_changed(self, slave_id: int) -> None:
        self._motor_service.slave_id = slave_id
        self._serial_tab.set_slave_id(slave_id)
        self._modbus_tab.set_slave_id(slave_id)

    def _on_bytes_updated(self, tx: int, rx: int) -> None:
        self._bytes_label.setText(f"TX: {tx}  RX: {rx}")

    def closeEvent(self, event) -> None:
        """关闭窗口时断开串口"""
        if self._worker.is_connected:
            self._worker.disconnect_port()
        super().closeEvent(event)
