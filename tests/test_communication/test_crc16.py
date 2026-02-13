"""通讯层 crc16.py 单元测试"""

import pytest
from nimotion.communication.crc16 import append, calculate, verify


class TestCalculate:
    def test_standard_vector_1(self):
        """标准测试向量: 读从站1保持寄存器0x0000, 数量1"""
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        crc = calculate(data)
        # 标准 Modbus CRC16 结果
        assert crc == 0x0A84

    def test_standard_vector_2(self):
        """写从站1单个寄存器0x0051, 值0x0006"""
        data = bytes([0x01, 0x06, 0x00, 0x51, 0x00, 0x06])
        crc = calculate(data)
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF

    def test_empty_data(self):
        """空数据的 CRC 应为 0xFFFF（初始值）"""
        assert calculate(b"") == 0xFFFF

    def test_single_byte(self):
        crc = calculate(b"\x00")
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF

    def test_deterministic(self):
        """相同数据应产生相同 CRC"""
        data = bytes([0x01, 0x03, 0x00, 0x17, 0x00, 0x10])
        assert calculate(data) == calculate(data)

    def test_different_data_different_crc(self):
        """不同数据应产生不同 CRC"""
        data1 = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        data2 = bytes([0x02, 0x03, 0x00, 0x00, 0x00, 0x01])
        assert calculate(data1) != calculate(data2)


class TestAppend:
    def test_length_increase(self):
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        result = append(data)
        assert len(result) == len(data) + 2

    def test_original_preserved(self):
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        result = append(data)
        assert result[:len(data)] == data

    def test_crc_low_byte_first(self):
        """CRC 追加顺序: 低字节在前"""
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        crc = calculate(data)
        result = append(data)
        assert result[-2] == crc & 0xFF  # 低字节
        assert result[-1] == (crc >> 8) & 0xFF  # 高字节

    def test_known_frame(self):
        """验证完整帧: 01 03 00 00 00 01 84 0A"""
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        result = append(data)
        assert result == bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01, 0x84, 0x0A])


class TestVerify:
    def test_valid_frame(self):
        """有效帧验证通过"""
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        frame = append(data)
        assert verify(frame) is True

    def test_corrupted_frame(self):
        """篡改数据后验证失败"""
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        frame = append(data)
        corrupted = bytearray(frame)
        corrupted[2] = 0xFF  # 修改一个字节
        assert verify(bytes(corrupted)) is False

    def test_wrong_crc(self):
        """错误 CRC 验证失败"""
        frame = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00])
        assert verify(frame) is False

    def test_too_short(self):
        """帧长度 < 4 返回 False"""
        assert verify(b"\x01\x03") is False
        assert verify(b"\x01") is False
        assert verify(b"") is False

    def test_roundtrip(self):
        """append → verify 往返测试"""
        for test_data in [
            bytes([0x01, 0x06, 0x00, 0x51, 0x00, 0x06]),
            bytes([0x01, 0x04, 0x00, 0x17, 0x00, 0x10]),
            bytes([0x01, 0x10, 0x00, 0x53, 0x00, 0x02, 0x04, 0x00, 0x00, 0x03, 0xE8]),
        ]:
            assert verify(append(test_data)) is True
