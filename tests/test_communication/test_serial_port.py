"""通讯层 serial_port.py 单元测试"""

import pytest
from unittest.mock import patch, MagicMock
from nimotion.communication.serial_port import SerialConfig, SerialPort


class TestSerialConfig:
    def test_defaults(self):
        config = SerialConfig()
        assert config.port == ""
        assert config.baudrate == 115200
        assert config.bytesize == 8
        assert config.parity == "N"
        assert config.stopbits == 1
        assert config.timeout == 0.5

    def test_custom(self):
        config = SerialConfig(
            port="/dev/ttyUSB0",
            baudrate=9600,
            parity="E",
            stopbits=2,
        )
        assert config.port == "/dev/ttyUSB0"
        assert config.baudrate == 9600
        assert config.parity == "E"
        assert config.stopbits == 2


class TestSerialPort:
    def test_initial_state(self):
        sp = SerialPort()
        assert sp.is_open is False
        assert sp.config.port == ""

    def test_write_when_closed(self):
        sp = SerialPort()
        with pytest.raises(IOError, match="串口未打开"):
            sp.write(b"\x01\x02")

    def test_read_when_closed(self):
        sp = SerialPort()
        with pytest.raises(IOError, match="串口未打开"):
            sp.read(10)

    def test_read_all_when_closed(self):
        sp = SerialPort()
        with pytest.raises(IOError, match="串口未打开"):
            sp.read_all()

    def test_flush_when_closed(self):
        """关闭状态下 flush 不应抛异常"""
        sp = SerialPort()
        sp.flush_input()  # 不应报错

    def test_close_when_not_open(self):
        """未打开状态下 close 不应抛异常"""
        sp = SerialPort()
        sp.close()  # 不应报错

    @patch("nimotion.communication.serial_port.serial.Serial")
    def test_open_and_close(self, mock_serial_cls):
        """使用 mock 测试打开和关闭"""
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_serial_cls.return_value = mock_instance

        sp = SerialPort()
        config = SerialConfig(port="/dev/ttyUSB0", baudrate=115200)
        sp.open(config)

        mock_serial_cls.assert_called_once_with(
            port="/dev/ttyUSB0",
            baudrate=115200,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.5,
        )
        assert sp.is_open is True
        assert sp.config.port == "/dev/ttyUSB0"

        sp.close()
        mock_instance.close.assert_called_once()

    @patch("nimotion.communication.serial_port.serial.Serial")
    def test_write(self, mock_serial_cls):
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_instance.write.return_value = 8
        mock_serial_cls.return_value = mock_instance

        sp = SerialPort()
        sp.open(SerialConfig(port="/dev/ttyUSB0"))
        result = sp.write(b"\x01\x03\x00\x00\x00\x01\x84\x0A")

        assert result == 8
        mock_instance.write.assert_called_once()

    @patch("nimotion.communication.serial_port.serial.Serial")
    def test_read(self, mock_serial_cls):
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_instance.read.return_value = b"\x01\x03\x02\x00\x01"
        mock_serial_cls.return_value = mock_instance

        sp = SerialPort()
        sp.open(SerialConfig(port="/dev/ttyUSB0"))
        data = sp.read(5)

        assert data == b"\x01\x03\x02\x00\x01"

    @patch("nimotion.communication.serial_port.serial.tools.list_ports.comports")
    def test_list_ports(self, mock_comports):
        mock_port1 = MagicMock()
        mock_port1.device = "/dev/ttyUSB0"
        mock_port2 = MagicMock()
        mock_port2.device = "/dev/ttyUSB1"
        mock_comports.return_value = [mock_port1, mock_port2]

        ports = SerialPort.list_ports()
        assert ports == ["/dev/ttyUSB0", "/dev/ttyUSB1"]
