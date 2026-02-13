"""
Modbus-RTU 帧构建与解析。
不涉及串口 IO，纯数据处理。
"""

from __future__ import annotations

from . import crc16
from ..models.types import FunctionCode, ModbusRequest, ModbusResponse


class ModbusRTU:
    """Modbus-RTU 协议处理器"""

    @staticmethod
    def build_frame(request: ModbusRequest) -> bytes:
        """
        根据 ModbusRequest 构建完整帧（含 CRC）。

        返回: 完整 RTU 帧 bytes
        """
        fc = request.function_code
        if fc in (FunctionCode.READ_HOLDING, FunctionCode.READ_INPUT):
            # 0x03/0x04: [从站][功能码][地址H][地址L][数量H][数量L]
            pdu = bytes([
                request.slave_id,
                fc,
                (request.address >> 8) & 0xFF,
                request.address & 0xFF,
                (request.count >> 8) & 0xFF,
                request.count & 0xFF,
            ])
        elif fc == FunctionCode.WRITE_SINGLE:
            # 0x06: [从站][功能码][地址H][地址L][值H][值L]
            value = request.values[0] if request.values else 0
            pdu = bytes([
                request.slave_id,
                fc,
                (request.address >> 8) & 0xFF,
                request.address & 0xFF,
                (value >> 8) & 0xFF,
                value & 0xFF,
            ])
        elif fc == FunctionCode.WRITE_MULTIPLE:
            # 0x10: [从站][功能码][地址H][地址L][数量H][数量L][字节数][数据...]
            count = len(request.values)
            byte_count = count * 2
            data_bytes = b""
            for v in request.values:
                data_bytes += bytes([(v >> 8) & 0xFF, v & 0xFF])
            pdu = bytes([
                request.slave_id,
                fc,
                (request.address >> 8) & 0xFF,
                request.address & 0xFF,
                (count >> 8) & 0xFF,
                count & 0xFF,
                byte_count,
            ]) + data_bytes
        else:
            raise ValueError(f"不支持的功能码: 0x{fc:02X}")

        return crc16.append(pdu)

    @staticmethod
    def parse_response(raw: bytes, request: ModbusRequest) -> ModbusResponse:
        """
        解析响应帧。

        参数:
            raw: 完整接收帧（含 CRC）
            request: 对应的请求（用于上下文判断）

        返回: ModbusResponse
        """
        # 最短合法帧: 从站(1) + 功能码(1) + 数据(≥1) + CRC(2) = 5
        if len(raw) < 5:
            return ModbusResponse(
                slave_id=raw[0] if raw else 0,
                function_code=0,
                data=b"",
                raw_rx=raw,
                is_error=True,
                error_code=-3,  # 帧长度不足
            )

        resp = ModbusResponse(
            slave_id=raw[0],
            function_code=raw[1],
            data=b"",
            raw_rx=raw,
        )

        # CRC 校验
        if not crc16.verify(raw):
            resp.is_error = True
            resp.error_code = -1  # CRC 错误特殊码
            return resp

        # 异常响应
        if raw[1] & 0x80:
            resp.is_error = True
            resp.function_code = raw[1] & 0x7F
            resp.error_code = raw[2]
            resp.data = raw[2:3]
            return resp

        fc = raw[1]
        if fc in (FunctionCode.READ_HOLDING, FunctionCode.READ_INPUT):
            # 响应: [从站][功能码][字节数][数据...]
            byte_count = raw[2]
            resp.data = raw[3:3 + byte_count]
            # 校验实际数据长度是否匹配
            if len(resp.data) < byte_count:
                resp.is_error = True
                resp.error_code = -3
                return resp
            # 将字节数据解析为 16 位寄存器值列表
            for i in range(0, byte_count - 1, 2):
                resp.values.append((resp.data[i] << 8) | resp.data[i + 1])
        elif fc == FunctionCode.WRITE_SINGLE:
            # 响应: [从站][功能码][地址H][地址L][值H][值L]
            if len(raw) < 8:
                resp.is_error = True
                resp.error_code = -3
                return resp
            resp.data = raw[2:6]
            resp.values = [(raw[4] << 8) | raw[5]]
        elif fc == FunctionCode.WRITE_MULTIPLE:
            # 响应: [从站][功能码][地址H][地址L][数量H][数量L]
            if len(raw) < 8:
                resp.is_error = True
                resp.error_code = -3
                return resp
            resp.data = raw[2:6]
            resp.values = [(raw[4] << 8) | raw[5]]

        return resp

    @staticmethod
    def expected_response_length(request: ModbusRequest) -> int:
        """计算期望的响应帧长度（用于读取判断）"""
        fc = request.function_code
        if fc in (FunctionCode.READ_HOLDING, FunctionCode.READ_INPUT):
            # 从站(1) + 功能码(1) + 字节数(1) + 数据(count*2) + CRC(2)
            return 5 + request.count * 2
        elif fc in (FunctionCode.WRITE_SINGLE, FunctionCode.WRITE_MULTIPLE):
            return 8
        return 8

    @staticmethod
    def combine_32bit(high: int, low: int, signed: bool = False) -> int:
        """将两个 16 位寄存器值合并为 32 位值"""
        val = (high << 16) | low
        if signed and val >= 0x80000000:
            val -= 0x100000000
        return val

    @staticmethod
    def split_32bit(value: int) -> tuple[int, int]:
        """将 32 位值拆分为 (高16位, 低16位)"""
        if value < 0:
            value += 0x100000000
        return (value >> 16) & 0xFFFF, value & 0xFFFF
