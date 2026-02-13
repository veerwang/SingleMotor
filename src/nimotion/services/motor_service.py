"""
电机业务逻辑层。
将寄存器操作封装为语义化方法，供 UI 层调用。
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal

from ..communication.modbus_rtu import ModbusRTU
from ..communication.worker import CommWorker
from ..models.error_codes import get_error_text, get_exception_text
from ..models.types import (
    FunctionCode,
    ModbusRequest,
    ModbusResponse,
    MotorState,
    MotorStatus,
    RunMode,
)


class MotorService(QObject):
    """电机操作服务"""

    # 状态更新信号
    status_updated = pyqtSignal(object)  # MotorStatus
    param_read = pyqtSignal(int, int)  # (地址, 值)
    operation_done = pyqtSignal(bool, str)  # (成功, 消息)

    def __init__(self, worker: CommWorker, slave_id: int = 1) -> None:
        super().__init__()
        self._worker = worker
        self._slave_id = slave_id
        self._worker.response_received.connect(self._on_response)

    @property
    def slave_id(self) -> int:
        return self._slave_id

    @slave_id.setter
    def slave_id(self, value: int) -> None:
        self._slave_id = value

    # -- 状态查询 --

    def refresh_status(self) -> None:
        """
        读取电机实时状态。
        一次批量读取 0x17~0x26 范围的输入寄存器（16 个），
        减少通讯次数。
        """
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=FunctionCode.READ_INPUT,
            address=0x0017,
            count=16,  # 0x17 ~ 0x26
        )
        self._worker.send_modbus(req)

    # -- 状态机控制 --

    def startup(self) -> None:
        """无故障 -> 启动"""
        self._write_control_word(0x0006)

    def enable(self) -> None:
        """启动 -> 使能"""
        self._write_control_word(0x0007)

    def run(self) -> None:
        """使能 -> 运行"""
        self._write_control_word(0x000F)

    def stop(self) -> None:
        """运行 -> 使能（减速停机）"""
        self._write_control_word(0x0007)

    def quick_stop(self) -> None:
        """紧急停机"""
        self._write_control_word(0x0002)

    def disable(self) -> None:
        """回到无故障状态"""
        self._write_control_word(0x0000)

    def clear_fault(self) -> None:
        """清除故障"""
        self._write_control_word(0x0080)

    # -- 运动控制 --

    def move_relative(self, position: int) -> None:
        """相对位置运动"""
        self._write_32bit(0x0053, position, signed=True)
        self._write_control_word(0x004F)
        self._write_control_word(0x005F)

    def move_absolute(self, position: int) -> None:
        """绝对位置运动"""
        self._write_32bit(0x0053, position, signed=True)
        self._write_control_word(0x000F)
        self._write_control_word(0x001F)

    def set_speed(self, speed: int, direction: int) -> None:
        """速度模式运行"""
        self._write_single(0x0052, direction)
        self._write_32bit(0x0055, speed)
        self._write_control_word(0x000F)

    def start_homing(self) -> None:
        """开始原点回归"""
        self._write_control_word(0x000F)
        self._write_control_word(0x001F)

    # -- 参数操作 --

    def read_param(self, address: int, count: int = 1) -> None:
        """读取保持寄存器"""
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=FunctionCode.READ_HOLDING,
            address=address,
            count=count,
        )
        self._worker.send_modbus(req)

    def write_param(self, address: int, value: int) -> None:
        """写入单个保持寄存器"""
        self._write_single(address, value)

    def write_param_32bit(
        self, address: int, value: int, signed: bool = False
    ) -> None:
        """写入 32 位参数（2 个寄存器）"""
        self._write_32bit(address, value, signed)

    def save_params(self) -> None:
        """保存所有参数到 EEPROM"""
        self._write_single(0x0008, 0x7376)

    def restore_defaults(self) -> None:
        """恢复出厂默认参数"""
        self._write_single(0x000B, 0x6C64)

    def set_run_mode(self, mode: RunMode) -> None:
        """设置运行模式"""
        self._write_single(0x0039, int(mode))

    def set_origin(self) -> None:
        """设置原点"""
        self._write_single(0x0048, 0x5348)

    def set_zero(self) -> None:
        """设置零点"""
        self._write_single(0x0047, 0x535A)

    # -- 内部方法 --

    def _write_control_word(self, value: int) -> None:
        self._write_single(0x0051, value)

    def _write_single(self, address: int, value: int) -> None:
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=FunctionCode.WRITE_SINGLE,
            address=address,
            values=[value & 0xFFFF],
        )
        self._worker.send_modbus(req)

    def _write_32bit(
        self, address: int, value: int, signed: bool = False
    ) -> None:
        high, low = ModbusRTU.split_32bit(value)
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=FunctionCode.WRITE_MULTIPLE,
            address=address,
            count=2,
            values=[high, low],
        )
        self._worker.send_modbus(req)

    def _on_response(self, resp: ModbusResponse) -> None:
        """处理通讯线程返回的响应"""
        if resp.is_error:
            self.operation_done.emit(False, self._format_error(resp))
            return

        # 判断是状态查询响应还是参数响应
        if resp.function_code == FunctionCode.READ_INPUT:
            self._parse_status(resp)
        elif resp.function_code == FunctionCode.READ_HOLDING:
            # 逐个发出 param_read 信号
            start_addr = (resp.raw_tx[2] << 8) | resp.raw_tx[3]
            for i, val in enumerate(resp.values):
                self.param_read.emit(start_addr + i, val)
        else:
            self.operation_done.emit(True, "操作成功")

    def _parse_status(self, resp: ModbusResponse) -> None:
        """从批量读取结果中解析电机状态"""
        vals = resp.values
        if len(vals) < 16:
            return

        # 偏移量基于起始地址 0x17
        status = MotorStatus()
        status.voltage = vals[0]  # 0x17
        # vals[1], vals[2] = 0x18~0x19 (DI, 32位)
        # vals[3]~vals[6] = 0x1A~0x1D (预留)
        # vals[7] = 0x1E (当前模式)
        status.current_mode = RunMode(vals[7]) if vals[7] in (1, 2, 3, 4) else None
        # vals[8] = 0x1F (状态字)
        status.status_word = vals[8]
        status.state = self._decode_state(vals[8])
        status.is_running = bool(vals[8] & (1 << 12))
        # vals[9] = 0x20 (方向)
        status.direction = vals[9]
        # vals[10], vals[11] = 0x21~0x22 (位置, 32位)
        status.position = ModbusRTU.combine_32bit(vals[10], vals[11], signed=True)
        # vals[12], vals[13] = 0x23~0x24 (速度, 32位, 值=实际x10)
        raw_speed = ModbusRTU.combine_32bit(vals[12], vals[13])
        status.speed = raw_speed // 10
        # vals[14] = 0x25 (错误寄存器)
        # vals[15] = 0x26 (当前报警码)
        status.alarm_code = vals[15]
        status.alarm_text = get_error_text(vals[15]) if vals[15] else ""

        self.status_updated.emit(status)

    @staticmethod
    def _decode_state(word: int) -> MotorState:
        """从状态字解码电机状态"""
        if word & 0x0008:  # bit3 = 故障
            return MotorState.FAULT
        if word == 0x0050:
            return MotorState.SWITCH_ON_DISABLED
        if word == 0x0031:
            return MotorState.READY_TO_SWITCH_ON
        if word == 0x0033:
            return MotorState.SWITCHED_ON
        if word == 0x0037:
            return MotorState.OPERATION_ENABLED
        if word == 0x0017:
            return MotorState.QUICK_STOP
        return MotorState.UNKNOWN

    @staticmethod
    def _format_error(resp: ModbusResponse) -> str:
        if resp.error_code == -1:
            return "CRC 校验失败"
        if resp.error_code == -2:
            return "通讯超时"
        return f"Modbus 异常: {get_exception_text(resp.error_code)}"
