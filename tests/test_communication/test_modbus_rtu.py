"""通讯层 modbus_rtu.py 单元测试"""

import pytest
from nimotion.communication import crc16
from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.models.types import FunctionCode, ModbusRequest


class TestBuildFrame:
    def test_read_holding(self):
        """构建 0x03 读保持寄存器帧"""
        req = ModbusRequest(
            slave_id=1,
            function_code=FunctionCode.READ_HOLDING,
            address=0x0000,
            count=1,
        )
        frame = ModbusRTU.build_frame(req)
        assert len(frame) == 8  # 6 + 2 CRC
        assert frame[0] == 0x01  # 从站地址
        assert frame[1] == 0x03  # 功能码
        assert frame[2:4] == b"\x00\x00"  # 地址
        assert frame[4:6] == b"\x00\x01"  # 数量
        assert crc16.verify(frame)

    def test_read_input(self):
        """构建 0x04 读输入寄存器帧"""
        req = ModbusRequest(
            slave_id=1,
            function_code=FunctionCode.READ_INPUT,
            address=0x0017,
            count=16,
        )
        frame = ModbusRTU.build_frame(req)
        assert frame[1] == 0x04
        assert frame[2:4] == b"\x00\x17"
        assert frame[4:6] == b"\x00\x10"
        assert crc16.verify(frame)

    def test_write_single(self):
        """构建 0x06 写单个寄存器帧"""
        req = ModbusRequest(
            slave_id=1,
            function_code=FunctionCode.WRITE_SINGLE,
            address=0x0051,
            values=[0x0006],
        )
        frame = ModbusRTU.build_frame(req)
        assert len(frame) == 8
        assert frame[1] == 0x06
        assert frame[2:4] == b"\x00\x51"
        assert frame[4:6] == b"\x00\x06"
        assert crc16.verify(frame)

    def test_write_single_no_values(self):
        """写单个寄存器但 values 为空时，默认写 0"""
        req = ModbusRequest(
            slave_id=1,
            function_code=FunctionCode.WRITE_SINGLE,
            address=0x0051,
        )
        frame = ModbusRTU.build_frame(req)
        assert frame[4:6] == b"\x00\x00"

    def test_write_multiple(self):
        """构建 0x10 写多个寄存器帧"""
        req = ModbusRequest(
            slave_id=1,
            function_code=FunctionCode.WRITE_MULTIPLE,
            address=0x0053,
            count=2,
            values=[0x0000, 0x03E8],  # 高 + 低 = 1000
        )
        frame = ModbusRTU.build_frame(req)
        assert frame[1] == 0x10
        assert frame[2:4] == b"\x00\x53"  # 地址
        assert frame[4:6] == b"\x00\x02"  # 数量
        assert frame[6] == 0x04  # 字节数
        assert frame[7:9] == b"\x00\x00"  # 值高
        assert frame[9:11] == b"\x03\xE8"  # 值低
        assert crc16.verify(frame)

    def test_unsupported_function_code(self):
        """不支持的功能码应抛异常"""
        req = ModbusRequest(
            slave_id=1,
            function_code=0x01,  # type: ignore[arg-type]
            address=0,
        )
        with pytest.raises(ValueError, match="不支持"):
            ModbusRTU.build_frame(req)

    def test_save_params_frame(self):
        """保存参数命令: 写 0x7376 到 0x0008"""
        req = ModbusRequest(
            slave_id=1,
            function_code=FunctionCode.WRITE_SINGLE,
            address=0x0008,
            values=[0x7376],
        )
        frame = ModbusRTU.build_frame(req)
        assert frame[0] == 0x01
        assert frame[1] == 0x06
        assert frame[2:4] == b"\x00\x08"
        assert frame[4:6] == b"\x73\x76"


class TestParseResponse:
    def _make_response(self, pdu: bytes) -> bytes:
        """构造带 CRC 的完整帧"""
        return crc16.append(pdu)

    def test_read_holding_response(self):
        """解析 0x03 读响应"""
        # 响应: 从站1, 功能码03, 字节数2, 数据00 01
        raw = self._make_response(bytes([0x01, 0x03, 0x02, 0x00, 0x01]))
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0x0000, 1)
        resp = ModbusRTU.parse_response(raw, req)

        assert not resp.is_error
        assert resp.slave_id == 1
        assert resp.function_code == 0x03
        assert resp.values == [1]

    def test_read_multiple_registers(self):
        """解析读取多个寄存器的响应"""
        # 读 2 个寄存器, 返回 4 字节
        raw = self._make_response(
            bytes([0x01, 0x03, 0x04, 0x00, 0x0A, 0x00, 0x14])
        )
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0x0000, 2)
        resp = ModbusRTU.parse_response(raw, req)

        assert resp.values == [10, 20]

    def test_write_single_response(self):
        """解析 0x06 写响应（回显）"""
        raw = self._make_response(
            bytes([0x01, 0x06, 0x00, 0x51, 0x00, 0x06])
        )
        req = ModbusRequest(1, FunctionCode.WRITE_SINGLE, 0x0051, values=[0x0006])
        resp = ModbusRTU.parse_response(raw, req)

        assert not resp.is_error
        assert resp.values == [0x0006]

    def test_write_multiple_response(self):
        """解析 0x10 写多个寄存器响应"""
        raw = self._make_response(
            bytes([0x01, 0x10, 0x00, 0x53, 0x00, 0x02])
        )
        req = ModbusRequest(1, FunctionCode.WRITE_MULTIPLE, 0x0053, 2, [0, 0x03E8])
        resp = ModbusRTU.parse_response(raw, req)

        assert not resp.is_error
        assert resp.values == [2]  # 写入数量

    def test_exception_response(self):
        """解析 Modbus 异常响应"""
        # 功能码 0x83 = 0x03 | 0x80, 异常码 0x02 (非法地址)
        raw = self._make_response(bytes([0x01, 0x83, 0x02]))
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0xFFFF, 1)
        resp = ModbusRTU.parse_response(raw, req)

        assert resp.is_error
        assert resp.function_code == 0x03
        assert resp.error_code == 0x02

    def test_crc_error(self):
        """CRC 校验失败"""
        raw = bytes([0x01, 0x03, 0x02, 0x00, 0x01, 0xFF, 0xFF])  # 错误 CRC
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0x0000, 1)
        resp = ModbusRTU.parse_response(raw, req)

        assert resp.is_error
        assert resp.error_code == -1

    def test_raw_rx_preserved(self):
        """原始接收帧应保留在响应中"""
        raw = self._make_response(bytes([0x01, 0x03, 0x02, 0x00, 0x01]))
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0x0000, 1)
        resp = ModbusRTU.parse_response(raw, req)
        assert resp.raw_rx == raw


class TestExpectedResponseLength:
    def test_read_holding_1(self):
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0, 1)
        assert ModbusRTU.expected_response_length(req) == 7  # 5 + 1*2

    def test_read_holding_16(self):
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0x0017, 16)
        assert ModbusRTU.expected_response_length(req) == 37  # 5 + 16*2

    def test_read_input(self):
        req = ModbusRequest(1, FunctionCode.READ_INPUT, 0x0017, 10)
        assert ModbusRTU.expected_response_length(req) == 25  # 5 + 10*2

    def test_write_single(self):
        req = ModbusRequest(1, FunctionCode.WRITE_SINGLE, 0x0051, values=[6])
        assert ModbusRTU.expected_response_length(req) == 8

    def test_write_multiple(self):
        req = ModbusRequest(1, FunctionCode.WRITE_MULTIPLE, 0x0053, 2, [0, 1000])
        assert ModbusRTU.expected_response_length(req) == 8


class TestCombine32bit:
    def test_unsigned(self):
        assert ModbusRTU.combine_32bit(0x0000, 0x03E8) == 1000

    def test_large_unsigned(self):
        assert ModbusRTU.combine_32bit(0xFFFF, 0xFFFF) == 0xFFFFFFFF

    def test_signed_positive(self):
        assert ModbusRTU.combine_32bit(0x0000, 0x03E8, signed=True) == 1000

    def test_signed_negative(self):
        # -1000 = 0xFFFFFC18
        assert ModbusRTU.combine_32bit(0xFFFF, 0xFC18, signed=True) == -1000

    def test_signed_minus_one(self):
        assert ModbusRTU.combine_32bit(0xFFFF, 0xFFFF, signed=True) == -1

    def test_zero(self):
        assert ModbusRTU.combine_32bit(0, 0) == 0


class TestSplit32bit:
    def test_positive(self):
        assert ModbusRTU.split_32bit(1000) == (0x0000, 0x03E8)

    def test_large(self):
        assert ModbusRTU.split_32bit(0x00010000) == (0x0001, 0x0000)

    def test_negative(self):
        high, low = ModbusRTU.split_32bit(-1000)
        assert high == 0xFFFF
        assert low == 0xFC18

    def test_zero(self):
        assert ModbusRTU.split_32bit(0) == (0, 0)

    def test_roundtrip(self):
        """split → combine 往返测试"""
        for val in [0, 1, 1000, 65536, -1, -1000, -65536]:
            high, low = ModbusRTU.split_32bit(val)
            signed = val < 0
            assert ModbusRTU.combine_32bit(high, low, signed=signed) == val
