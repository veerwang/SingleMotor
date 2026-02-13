"""模型层 registers.py 单元测试"""

import pytest
from nimotion.models.registers import (
    HOLDING_REGISTERS,
    INPUT_REGISTERS,
    get_register,
)
from nimotion.models.types import DataType, RegisterType


class TestHoldingRegisters:
    def test_not_empty(self):
        assert len(HOLDING_REGISTERS) > 0

    def test_all_holding_type(self):
        for reg in HOLDING_REGISTERS:
            assert reg.reg_type == RegisterType.HOLDING

    def test_slave_address_register(self):
        reg = HOLDING_REGISTERS[0]
        assert reg.address == 0x0000
        assert reg.name == "从站地址"
        assert reg.min_val == 1
        assert reg.max_val == 247
        assert reg.default_val == 1
        assert reg.restart_required is True

    def test_baudrate_register(self):
        reg = get_register(0x0001, RegisterType.HOLDING)
        assert reg is not None
        assert reg.name == "波特率"
        assert reg.default_val == 5

    def test_save_params_register(self):
        reg = get_register(0x0008, RegisterType.HOLDING)
        assert reg is not None
        assert reg.name == "保存所有参数"
        assert "0x7376" in reg.description

    def test_control_word_register(self):
        reg = get_register(0x0051, RegisterType.HOLDING)
        assert reg is not None
        assert reg.name == "运动控制字"

    def test_32bit_registers(self):
        """32 位寄存器的 count 应为 2"""
        for reg in HOLDING_REGISTERS:
            if reg.data_type in (DataType.UINT32, DataType.INT32):
                assert reg.count == 2, f"Register {reg.name} (0x{reg.address:04X}) should have count=2"

    def test_unique_addresses(self):
        """保持寄存器地址不应重复"""
        addresses = [r.address for r in HOLDING_REGISTERS]
        assert len(addresses) == len(set(addresses))


class TestInputRegisters:
    def test_not_empty(self):
        assert len(INPUT_REGISTERS) > 0

    def test_all_input_type(self):
        for reg in INPUT_REGISTERS:
            assert reg.reg_type == RegisterType.INPUT

    def test_all_readonly(self):
        for reg in INPUT_REGISTERS:
            assert reg.writable is False

    def test_voltage_register(self):
        reg = get_register(0x0017, RegisterType.INPUT)
        assert reg is not None
        assert reg.name == "输入电压"
        assert reg.unit == "V"

    def test_status_word_register(self):
        reg = get_register(0x001F, RegisterType.INPUT)
        assert reg is not None
        assert reg.name == "运动状态字"

    def test_position_register(self):
        reg = get_register(0x0021, RegisterType.INPUT)
        assert reg is not None
        assert reg.name == "当前显示位置"
        assert reg.data_type == DataType.INT32
        assert reg.count == 2

    def test_unique_addresses(self):
        addresses = [r.address for r in INPUT_REGISTERS]
        assert len(addresses) == len(set(addresses))


class TestGetRegister:
    def test_found_holding(self):
        reg = get_register(0x0000, RegisterType.HOLDING)
        assert reg is not None
        assert reg.name == "从站地址"

    def test_found_input(self):
        reg = get_register(0x001F, RegisterType.INPUT)
        assert reg is not None
        assert reg.name == "运动状态字"

    def test_not_found(self):
        reg = get_register(0xFFFF, RegisterType.HOLDING)
        assert reg is None

    def test_wrong_type(self):
        """保持寄存器的地址用输入类型查找应返回 None（除非地址恰好重合）"""
        reg = get_register(0x0039, RegisterType.INPUT)
        assert reg is None

    def test_overlapping_address_different_type(self):
        """0x0017 同时存在于保持寄存器和输入寄存器"""
        h = get_register(0x0017, RegisterType.HOLDING)
        i = get_register(0x0017, RegisterType.INPUT)
        assert h is not None
        assert i is not None
        assert h.name != i.name  # 不同寄存器
