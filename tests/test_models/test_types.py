"""模型层 types.py 单元测试"""

import pytest
from nimotion.models.types import (
    DataType,
    FunctionCode,
    ModbusRequest,
    ModbusResponse,
    MotorState,
    MotorStatus,
    RegisterDef,
    RegisterType,
    RunMode,
)


class TestFunctionCode:
    def test_values(self):
        assert FunctionCode.READ_HOLDING == 0x03
        assert FunctionCode.READ_INPUT == 0x04
        assert FunctionCode.WRITE_SINGLE == 0x06
        assert FunctionCode.WRITE_MULTIPLE == 0x10

    def test_is_int(self):
        assert isinstance(FunctionCode.READ_HOLDING, int)
        assert FunctionCode.READ_HOLDING + 1 == 4


class TestMotorState:
    def test_values(self):
        assert MotorState.UNKNOWN == -1
        assert MotorState.NOT_READY == 0
        assert MotorState.SWITCH_ON_DISABLED == 1
        assert MotorState.FAULT == 7

    def test_all_states_defined(self):
        assert len(MotorState) == 9


class TestRunMode:
    def test_values(self):
        assert RunMode.POSITION == 1
        assert RunMode.SPEED == 2
        assert RunMode.HOMING == 3
        assert RunMode.PULSE_INPUT == 4

    def test_from_int(self):
        assert RunMode(1) == RunMode.POSITION
        assert RunMode(4) == RunMode.PULSE_INPUT

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            RunMode(99)


class TestRegisterType:
    def test_values(self):
        assert RegisterType.HOLDING == 0
        assert RegisterType.INPUT == 1


class TestDataType:
    def test_values(self):
        assert DataType.UINT16 == 0
        assert DataType.INT16 == 1
        assert DataType.UINT32 == 2
        assert DataType.INT32 == 3


class TestRegisterDef:
    def test_creation(self):
        reg = RegisterDef(
            address=0x0000,
            name="从站地址",
            reg_type=RegisterType.HOLDING,
            data_type=DataType.UINT16,
            count=1,
            min_val=1,
            max_val=247,
            default_val=1,
        )
        assert reg.address == 0
        assert reg.name == "从站地址"
        assert reg.count == 1
        assert reg.writable is True
        assert reg.restart_required is False

    def test_defaults(self):
        reg = RegisterDef(0x10, "test", RegisterType.HOLDING, DataType.UINT16, 1)
        assert reg.unit == ""
        assert reg.min_val is None
        assert reg.max_val is None
        assert reg.default_val is None
        assert reg.description == ""


class TestModbusRequest:
    def test_read_request(self):
        req = ModbusRequest(
            slave_id=1,
            function_code=FunctionCode.READ_HOLDING,
            address=0x0017,
            count=10,
        )
        assert req.slave_id == 1
        assert req.function_code == FunctionCode.READ_HOLDING
        assert req.values == []

    def test_write_request(self):
        req = ModbusRequest(
            slave_id=1,
            function_code=FunctionCode.WRITE_SINGLE,
            address=0x0051,
            values=[0x0006],
        )
        assert req.values == [0x0006]


class TestModbusResponse:
    def test_success_response(self):
        resp = ModbusResponse(
            slave_id=1,
            function_code=0x03,
            data=b"\x00\x01",
            values=[1],
        )
        assert not resp.is_error
        assert resp.error_code == 0

    def test_error_response(self):
        resp = ModbusResponse(
            slave_id=1,
            function_code=0x83,
            data=b"\x02",
            is_error=True,
            error_code=2,
        )
        assert resp.is_error
        assert resp.error_code == 2

    def test_defaults(self):
        resp = ModbusResponse(slave_id=1, function_code=3, data=b"")
        assert resp.raw_tx == b""
        assert resp.raw_rx == b""
        assert resp.timestamp == 0.0


class TestMotorStatus:
    def test_defaults(self):
        status = MotorStatus()
        assert status.status_word == 0
        assert status.state == MotorState.UNKNOWN
        assert status.position == 0
        assert status.speed == 0
        assert status.voltage == 0
        assert status.current_mode is None
        assert status.direction == 0
        assert status.alarm_code == 0
        assert status.alarm_text == ""
        assert status.is_running is False

    def test_custom_values(self):
        status = MotorStatus(
            status_word=0x0037,
            state=MotorState.OPERATION_ENABLED,
            position=1000,
            speed=500,
            voltage=24,
            current_mode=RunMode.SPEED,
            direction=1,
            is_running=True,
        )
        assert status.state == MotorState.OPERATION_ENABLED
        assert status.is_running is True
        assert status.current_mode == RunMode.SPEED
