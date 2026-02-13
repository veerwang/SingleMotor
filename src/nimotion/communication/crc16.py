"""Modbus CRC16 计算（多项式 0xA001，初始值 0xFFFF）"""

from __future__ import annotations


def calculate(data: bytes) -> int:
    """计算 CRC16，返回 16 位整数"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def append(data: bytes) -> bytes:
    """在数据末尾追加 CRC16（低字节在前）"""
    crc = calculate(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def verify(frame: bytes) -> bool:
    """校验完整帧的 CRC16（帧包含末尾 2 字节 CRC）"""
    if len(frame) < 4:
        return False
    return calculate(frame[:-2]) == (frame[-2] | (frame[-1] << 8))
