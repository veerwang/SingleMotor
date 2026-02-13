"""
通讯工作线程。
独占串口资源，通过 Signal/Slot 与主线程交互。
"""

from __future__ import annotations

import logging
import time

from PyQt5.QtCore import QMutex, QThread, QWaitCondition, pyqtSignal

logger = logging.getLogger(__name__)

from ..models.types import ModbusRequest, ModbusResponse
from .modbus_rtu import ModbusRTU
from .serial_port import SerialConfig, SerialPort


class CommWorker(QThread):
    """通讯工作线程"""

    # -- Signals（通讯线程 -> 主线程）--
    connected = pyqtSignal()  # 串口已连接
    disconnected = pyqtSignal()  # 串口已断开
    connection_error = pyqtSignal(str)  # 连接失败
    response_received = pyqtSignal(object)  # ModbusResponse
    raw_data_received = pyqtSignal(bytes)  # 原始数据（串口调试模式）
    raw_data_sent = pyqtSignal(bytes)  # 原始数据已发送
    bytes_count_updated = pyqtSignal(int, int)  # (tx_total, rx_total)

    # -- 内部常量 --
    MIN_FRAME_GAP = 0.005  # 帧间最小间隔（秒）

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._serial = SerialPort()
        self._modbus = ModbusRTU()
        self._running = False
        self._tx_bytes = 0
        self._rx_bytes = 0

        # 请求队列 (用 mutex + condition 实现)
        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._pending_request: ModbusRequest | None = None
        self._pending_raw: bytes | None = None
        self._raw_mode = False  # True = 串口调试模式

    # -- 公共方法（主线程调用）--

    @property
    def is_connected(self) -> bool:
        return self._serial.is_open

    def connect_port(self, config: SerialConfig) -> None:
        """请求连接串口"""
        try:
            self._serial.open(config)
            self._running = True
            if not self.isRunning():
                self.start()
            self.connected.emit()
        except Exception as e:
            self.connection_error.emit(str(e))

    def disconnect_port(self) -> None:
        """请求断开串口"""
        self._running = False
        self._condition.wakeAll()
        self.wait(2000)
        self._serial.close()
        self.disconnected.emit()

    def send_modbus(self, request: ModbusRequest) -> None:
        """提交 Modbus 请求（主线程调用）"""
        self._mutex.lock()
        self._pending_request = request
        self._raw_mode = False
        self._condition.wakeOne()
        self._mutex.unlock()

    def send_raw(self, data: bytes) -> None:
        """发送原始数据（串口调试模式）"""
        self._mutex.lock()
        self._pending_raw = data
        self._raw_mode = True
        self._condition.wakeOne()
        self._mutex.unlock()

    def reset_counters(self) -> None:
        """重置收发计数器"""
        self._tx_bytes = 0
        self._rx_bytes = 0
        self.bytes_count_updated.emit(0, 0)

    # -- 线程主循环 --

    def run(self) -> None:
        while self._running:
            self._mutex.lock()
            # 等待请求或超时（超时用于检测串口调试模式的持续接收）
            if self._pending_request is None and self._pending_raw is None:
                self._condition.wait(self._mutex, 50)  # 50ms 轮询
            request = self._pending_request
            raw = self._pending_raw
            raw_mode = self._raw_mode
            self._pending_request = None
            self._pending_raw = None
            self._mutex.unlock()

            try:
                if raw_mode and raw is not None:
                    self._handle_raw_send(raw)
                elif request is not None:
                    self._handle_modbus(request)

                # 串口调试模式：持续接收
                if self._serial.is_open:
                    incoming = self._serial.read_all()
                    if incoming:
                        self._rx_bytes += len(incoming)
                        self.raw_data_received.emit(incoming)
                        self.bytes_count_updated.emit(self._tx_bytes, self._rx_bytes)
            except Exception as exc:
                logger.exception("通讯线程异常")
                if self._running:
                    self._serial.close()
                    self.connection_error.emit(f"通讯异常: {exc}")
                    self.disconnected.emit()
                    self._running = False

    def _handle_raw_send(self, data: bytes) -> None:
        """发送原始数据"""
        self._serial.write(data)
        self._tx_bytes += len(data)
        self.raw_data_sent.emit(data)
        self.bytes_count_updated.emit(self._tx_bytes, self._rx_bytes)

    def _handle_modbus(self, request: ModbusRequest) -> None:
        """发送 Modbus 请求并等待响应"""
        frame = self._modbus.build_frame(request)
        self._serial.flush_input()
        written = self._serial.write(frame)
        self._tx_bytes += written
        if written != len(frame):
            logger.warning("串口写入不完整: 期望 %d 字节, 实际 %d", len(frame), written)
        self.raw_data_sent.emit(frame)

        time.sleep(self.MIN_FRAME_GAP)

        expected_len = self._modbus.expected_response_length(request)
        raw_rx = self._serial.read(expected_len)
        self._rx_bytes += len(raw_rx)

        if len(raw_rx) == 0:
            resp = ModbusResponse(
                slave_id=request.slave_id,
                function_code=request.function_code,
                data=b"",
                is_error=True,
                error_code=-2,  # 超时特殊码
                raw_tx=frame,
                raw_rx=b"",
                timestamp=time.time(),
            )
        else:
            resp = self._modbus.parse_response(raw_rx, request)
            resp.raw_tx = frame
            resp.timestamp = time.time()

        self.response_received.emit(resp)
        self.bytes_count_updated.emit(self._tx_bytes, self._rx_bytes)
