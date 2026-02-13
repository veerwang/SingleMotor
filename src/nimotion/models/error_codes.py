"""错误码定义表"""

from __future__ import annotations

ERROR_CODES: dict[int, str] = {
    0x2200: "过流保护",
    0x3110: "电源过压",
    0x3120: "电源欠压",
    0x4310: "过热报警",
    0x7121: "失速报警",
    0x8612: "限位报警",
    0xFF00: "过热关机",
    0xFF01: "错误的命令",
    0xFF02: "不能执行的命令",
    0xFF0E: "超负限位报警",
    0xFF0F: "超正限位报警",
    0xFF11: "SPI 通信失败报警",
}

MODBUS_EXCEPTIONS: dict[int, str] = {
    0x01: "非法功能码",
    0x02: "非法数据地址",
    0x03: "非法数据值",
    0x04: "从设备故障",
    0x05: "确认（处理中）",
    0x06: "从设备忙",
}


def get_error_text(code: int) -> str:
    """根据错误码获取中文描述"""
    return ERROR_CODES.get(code, f"未知错误 (0x{code:04X})")


def get_exception_text(code: int) -> str:
    """根据 Modbus 异常码获取中文描述"""
    return MODBUS_EXCEPTIONS.get(code, f"未知异常 (0x{code:02X})")
