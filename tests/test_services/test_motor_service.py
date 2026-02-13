"""服务层 motor_service.py 单元测试"""

import pytest
from unittest.mock import MagicMock, patch, call

from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.communication import crc16
from nimotion.models.types import (
    FunctionCode,
    ModbusRequest,
    ModbusResponse,
    MotorState,
    MotorStatus,
    RunMode,
)
from nimotion.services.motor_service import MotorService


@pytest.fixture
def mock_worker(qtbot):
    """创建模拟的 CommWorker"""
    from nimotion.communication.worker import CommWorker

    worker = CommWorker()
    return worker


@pytest.fixture
def service(mock_worker):
    """创建 MotorService 实例"""
    return MotorService(mock_worker, slave_id=1)


class TestSlaveId:
    def test_default(self, service):
        assert service.slave_id == 1

    def test_set(self, service):
        service.slave_id = 5
        assert service.slave_id == 5


class TestStatusQuery:
    def test_refresh_status(self, service, mock_worker):
        """refresh_status 应发送读输入寄存器请求"""
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.refresh_status()
            mock_send.assert_called_once()
            req = mock_send.call_args[0][0]
            assert req.function_code == FunctionCode.READ_INPUT
            assert req.address == 0x0017
            assert req.count == 16


class TestStateControl:
    def _assert_control_word(self, service, mock_worker, method_name, expected_value):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            getattr(service, method_name)()
            mock_send.assert_called_once()
            req = mock_send.call_args[0][0]
            assert req.function_code == FunctionCode.WRITE_SINGLE
            assert req.address == 0x0051
            assert req.values == [expected_value]

    def test_startup(self, service, mock_worker):
        self._assert_control_word(service, mock_worker, "startup", 0x0006)

    def test_enable(self, service, mock_worker):
        self._assert_control_word(service, mock_worker, "enable", 0x0007)

    def test_run(self, service, mock_worker):
        self._assert_control_word(service, mock_worker, "run", 0x000F)

    def test_stop(self, service, mock_worker):
        self._assert_control_word(service, mock_worker, "stop", 0x0007)

    def test_quick_stop(self, service, mock_worker):
        self._assert_control_word(service, mock_worker, "quick_stop", 0x0002)

    def test_disable(self, service, mock_worker):
        self._assert_control_word(service, mock_worker, "disable", 0x0000)

    def test_clear_fault(self, service, mock_worker):
        self._assert_control_word(service, mock_worker, "clear_fault", 0x0080)


class TestMotionControl:
    def test_move_relative(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.move_relative(1000)
            assert mock_send.call_count == 3
            # 第一次: 写目标位置 (32位)
            req1 = mock_send.call_args_list[0][0][0]
            assert req1.function_code == FunctionCode.WRITE_MULTIPLE
            assert req1.address == 0x0053
            # 第二次: 控制字 0x004F
            req2 = mock_send.call_args_list[1][0][0]
            assert req2.values == [0x004F]
            # 第三次: 控制字 0x005F
            req3 = mock_send.call_args_list[2][0][0]
            assert req3.values == [0x005F]

    def test_move_absolute(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.move_absolute(5000)
            assert mock_send.call_count == 3

    def test_set_speed(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.set_speed(500, 1)
            assert mock_send.call_count == 3
            # 方向
            req1 = mock_send.call_args_list[0][0][0]
            assert req1.address == 0x0052
            assert req1.values == [1]
            # 速度 (32位)
            req2 = mock_send.call_args_list[1][0][0]
            assert req2.address == 0x0055
            # 控制字
            req3 = mock_send.call_args_list[2][0][0]
            assert req3.values == [0x000F]

    def test_start_homing(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.start_homing()
            assert mock_send.call_count == 2


class TestParamOperations:
    def test_read_param(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.read_param(0x001A, 1)
            req = mock_send.call_args[0][0]
            assert req.function_code == FunctionCode.READ_HOLDING
            assert req.address == 0x001A

    def test_write_param(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.write_param(0x001A, 5)
            req = mock_send.call_args[0][0]
            assert req.function_code == FunctionCode.WRITE_SINGLE
            assert req.address == 0x001A
            assert req.values == [5]

    def test_write_param_32bit(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.write_param_32bit(0x0055, 1000)
            req = mock_send.call_args[0][0]
            assert req.function_code == FunctionCode.WRITE_MULTIPLE
            assert req.address == 0x0055
            assert req.count == 2

    def test_save_params(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.save_params()
            req = mock_send.call_args[0][0]
            assert req.address == 0x0008
            assert req.values == [0x7376]

    def test_restore_defaults(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.restore_defaults()
            req = mock_send.call_args[0][0]
            assert req.address == 0x000B
            assert req.values == [0x6C64]

    def test_set_run_mode(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.set_run_mode(RunMode.SPEED)
            req = mock_send.call_args[0][0]
            assert req.address == 0x0039
            assert req.values == [2]

    def test_set_origin(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.set_origin()
            req = mock_send.call_args[0][0]
            assert req.address == 0x0048
            assert req.values == [0x5348]

    def test_set_zero(self, service, mock_worker):
        with patch.object(mock_worker, "send_modbus") as mock_send:
            service.set_zero()
            req = mock_send.call_args[0][0]
            assert req.address == 0x0047
            assert req.values == [0x535A]


class TestDecodeState:
    @pytest.mark.parametrize(
        "word,expected",
        [
            (0x0050, MotorState.SWITCH_ON_DISABLED),
            (0x0031, MotorState.READY_TO_SWITCH_ON),
            (0x0033, MotorState.SWITCHED_ON),
            (0x0037, MotorState.OPERATION_ENABLED),
            (0x0017, MotorState.QUICK_STOP),
            (0x0008, MotorState.FAULT),
            (0x0018, MotorState.FAULT),  # bit3 set
            (0x0000, MotorState.UNKNOWN),
            (0x1234, MotorState.UNKNOWN),
        ],
    )
    def test_decode(self, word, expected):
        assert MotorService._decode_state(word) == expected


class TestFormatError:
    def test_crc_error(self):
        resp = ModbusResponse(1, 3, b"", is_error=True, error_code=-1)
        assert "CRC" in MotorService._format_error(resp)

    def test_timeout(self):
        resp = ModbusResponse(1, 3, b"", is_error=True, error_code=-2)
        assert "超时" in MotorService._format_error(resp)

    def test_modbus_exception(self):
        resp = ModbusResponse(1, 3, b"", is_error=True, error_code=0x02)
        result = MotorService._format_error(resp)
        assert "Modbus" in result
        assert "非法数据地址" in result


class TestOnResponse:
    def test_error_response(self, service, qtbot):
        """错误响应应发出 operation_done(False, msg)"""
        resp = ModbusResponse(1, 3, b"", is_error=True, error_code=-2)
        with qtbot.waitSignal(service.operation_done, timeout=1000) as blocker:
            service._on_response(resp)
        assert blocker.args[0] is False
        assert "超时" in blocker.args[1]

    def test_write_response(self, service, qtbot):
        """写操作成功应发出 operation_done(True, msg)"""
        resp = ModbusResponse(
            slave_id=1,
            function_code=FunctionCode.WRITE_SINGLE,
            data=b"\x00\x51\x00\x06",
            values=[6],
        )
        with qtbot.waitSignal(service.operation_done, timeout=1000) as blocker:
            service._on_response(resp)
        assert blocker.args[0] is True

    def test_read_holding_response(self, service, qtbot):
        """读保持寄存器应发出 param_read 信号"""
        resp = ModbusResponse(
            slave_id=1,
            function_code=FunctionCode.READ_HOLDING,
            data=b"\x00\x07",
            values=[7],
            raw_tx=bytes([0x01, 0x03, 0x00, 0x1A, 0x00, 0x01, 0x00, 0x00]),
        )
        with qtbot.waitSignal(service.param_read, timeout=1000) as blocker:
            service._on_response(resp)
        assert blocker.args == [0x001A, 7]

    def test_status_response(self, service, qtbot):
        """读输入寄存器应解析并发出 status_updated 信号"""
        # 构造 16 个寄存器的值
        vals = [
            24,    # 0x17 电压
            0, 0,  # 0x18~0x19 DI
            0, 0, 0, 0,  # 0x1A~0x1D 预留
            2,     # 0x1E 当前模式=速度
            0x0037,  # 0x1F 状态字=运行
            1,     # 0x20 方向=正转
            0, 1000,  # 0x21~0x22 位置 (高, 低)
            0, 5000,  # 0x23~0x24 速度 (高, 低) 实际=500
            0,     # 0x25 错误寄存器
            0,     # 0x26 报警码
        ]
        resp = ModbusResponse(
            slave_id=1,
            function_code=FunctionCode.READ_INPUT,
            data=b"",
            values=vals,
        )
        with qtbot.waitSignal(service.status_updated, timeout=1000) as blocker:
            service._on_response(resp)
        status = blocker.args[0]
        assert isinstance(status, MotorStatus)
        assert status.voltage == 24
        assert status.current_mode == RunMode.SPEED
        assert status.state == MotorState.OPERATION_ENABLED
        assert status.direction == 1
        assert status.position == 1000
        assert status.speed == 500
        assert status.is_running is False  # bit12 未置位
        assert status.alarm_code == 0

    def test_status_with_fault(self, service, qtbot):
        """故障状态的解析"""
        vals = [24, 0, 0, 0, 0, 0, 0, 1, 0x0008, 0, 0, 0, 0, 0, 0, 0x2200]
        resp = ModbusResponse(
            slave_id=1,
            function_code=FunctionCode.READ_INPUT,
            data=b"",
            values=vals,
        )
        with qtbot.waitSignal(service.status_updated, timeout=1000) as blocker:
            service._on_response(resp)
        status = blocker.args[0]
        assert status.state == MotorState.FAULT
        assert status.alarm_code == 0x2200
        assert "过流" in status.alarm_text

    def test_status_too_few_values(self, service, qtbot):
        """值不足 16 个不应崩溃也不应发信号"""
        resp = ModbusResponse(
            slave_id=1,
            function_code=FunctionCode.READ_INPUT,
            data=b"",
            values=[1, 2, 3],
        )
        # 不应发出信号
        with qtbot.assertNotEmitted(service.status_updated, wait=100):
            service._on_response(resp)
