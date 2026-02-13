"""串口资源管理，封装 pyserial"""

from __future__ import annotations

from dataclasses import dataclass

import serial
import serial.tools.list_ports


@dataclass
class SerialConfig:
    """串口配置"""

    port: str = ""
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"  # "N" / "E" / "O"
    stopbits: float = 1  # 1 / 2
    timeout: float = 0.5  # 读超时（秒）


class SerialPort:
    """
    串口管理器。
    非线程安全 - 仅应在通讯线程中调用。
    """

    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self._config = SerialConfig()

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def config(self) -> SerialConfig:
        return self._config

    @staticmethod
    def list_ports() -> list[str]:
        """枚举可用串口"""
        return [p.device for p in serial.tools.list_ports.comports()]

    def open(self, config: SerialConfig) -> None:
        """打开串口"""
        self.close()
        self._config = config
        self._serial = serial.Serial(
            port=config.port,
            baudrate=config.baudrate,
            bytesize=config.bytesize,
            parity=config.parity,
            stopbits=config.stopbits,
            timeout=config.timeout,
        )

    def close(self) -> None:
        """关闭串口"""
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def write(self, data: bytes) -> int:
        """发送数据，返回发送字节数"""
        if not self.is_open:
            raise IOError("串口未打开")
        return self._serial.write(data)  # type: ignore[union-attr]

    def read(self, size: int) -> bytes:
        """读取指定字节数（可能因超时返回不足）"""
        if not self.is_open:
            raise IOError("串口未打开")
        return self._serial.read(size)  # type: ignore[union-attr]

    def read_all(self) -> bytes:
        """读取缓冲区所有数据"""
        if not self.is_open:
            raise IOError("串口未打开")
        return self._serial.read_all()  # type: ignore[union-attr]

    def flush_input(self) -> None:
        """清空输入缓冲区"""
        if self.is_open:
            self._serial.reset_input_buffer()  # type: ignore[union-attr]
