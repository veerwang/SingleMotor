"""公共数据类型：枚举、数据类定义"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class FunctionCode(IntEnum):
    """Modbus 功能码"""

    READ_HOLDING = 0x03
    READ_INPUT = 0x04
    WRITE_SINGLE = 0x06
    WRITE_MULTIPLE = 0x10


class MotorState(IntEnum):
    """电机状态机状态"""

    UNKNOWN = -1
    NOT_READY = 0  # 初始化
    SWITCH_ON_DISABLED = 1  # 电机无故障 (0x0050)
    READY_TO_SWITCH_ON = 2  # 启动 (0x0031)
    SWITCHED_ON = 3  # 使能 (0x0033)
    OPERATION_ENABLED = 4  # 运行 (0x0037)
    QUICK_STOP = 5  # 快速停机 (0x0017)
    FAULT_ACTIVE = 6  # 故障激活
    FAULT = 7  # 故障 (0x0008)


class RunMode(IntEnum):
    """运行模式"""

    POSITION = 1
    SPEED = 2
    HOMING = 3
    PULSE_INPUT = 4  # 仅 57H


class RegisterType(IntEnum):
    """寄存器类型"""

    HOLDING = 0  # 保持寄存器（可读写）
    INPUT = 1  # 输入寄存器（只读）


class DataType(IntEnum):
    """数据类型"""

    UINT16 = 0  # 1 个寄存器
    INT16 = 1  # 1 个寄存器，有符号
    UINT32 = 2  # 2 个寄存器
    INT32 = 3  # 2 个寄存器，有符号


@dataclass
class RegisterDef:
    """寄存器定义"""

    address: int
    name: str
    reg_type: RegisterType
    data_type: DataType
    count: int  # 寄存器数量: 1 或 2
    unit: str = ""
    min_val: int | None = None
    max_val: int | None = None
    default_val: int | None = None
    description: str = ""
    writable: bool = True
    restart_required: bool = False  # 修改后是否需要重启


@dataclass
class ModbusRequest:
    """Modbus 请求"""

    slave_id: int
    function_code: FunctionCode
    address: int
    count: int = 1  # 读取数量 / 写入数量
    values: list[int] = field(default_factory=list)  # 写入值


@dataclass
class ModbusResponse:
    """Modbus 响应"""

    slave_id: int
    function_code: int
    data: bytes  # 原始数据段
    values: list[int] = field(default_factory=list)  # 解析后的寄存器值
    is_error: bool = False
    error_code: int = 0
    raw_tx: bytes = b""  # 原始发送帧
    raw_rx: bytes = b""  # 原始接收帧
    timestamp: float = 0.0


@dataclass
class MotorStatus:
    """电机实时状态快照"""

    status_word: int = 0
    state: MotorState = MotorState.UNKNOWN
    position: int = 0  # pulse
    speed: int = 0  # Step/s (实际值，已除10)
    voltage: int = 0  # V
    current_mode: RunMode | None = None
    direction: int = 0  # 0=反转 1=正转
    alarm_code: int = 0
    alarm_text: str = ""
    is_running: bool = False  # 状态字 bit12
