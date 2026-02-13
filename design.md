# 软件设计文档

**项目名称**: NiMotion 一体化步进电机调试工具
**版本**: v0.1
**日期**: 2026-02-13
**前置文档**: `requirements.md`

---

## 1. 设计概述

### 1.1 架构风格

采用 **分层架构 + 事件驱动** 设计：

```
┌────────────────────────────────────────────┐
│                 UI 层 (PyQt5)               │
│   MainWindow / SerialTab / ModbusTab / ...  │
├────────────────────────────────────────────┤
│                 服务层                       │
│   MotorService (业务逻辑封装)               │
├────────────────────────────────────────────┤
│                 通讯层                       │
│   ModbusRTU / SerialPort / CommWorker       │
├────────────────────────────────────────────┤
│                 模型层                       │
│   RegisterTable / ErrorCodeTable            │
└────────────────────────────────────────────┘
```

**各层职责**:

| 层 | 职责 | 依赖方向 |
|----|------|---------|
| UI 层 | 界面渲染、用户交互、信号绑定 | → 服务层 |
| 服务层 | 电机操作业务逻辑、状态机管理、参数校验 | → 通讯层、模型层 |
| 通讯层 | 串口管理、Modbus 帧构建/解析、CRC、线程 | → 模型层 |
| 模型层 | 寄存器定义、错误码、数据结构 | 无依赖 |

**核心原则**: UI 层不直接构造 Modbus 帧；通讯层不理解电机业务含义。

### 1.2 线程模型

```
┌─────────────────┐         Signal/Slot         ┌──────────────────┐
│   主线程 (GUI)    │ ◄──────────────────────►   │  通讯线程 (Worker) │
│                 │    request_signal            │                  │
│  PyQt5 事件循环   │ ──────────────────────►    │  串口读写执行      │
│  UI 更新         │    response_signal          │  超时管理         │
│  定时器触发       │ ◄──────────────────────    │  帧解析           │
└─────────────────┘                             └──────────────────┘
```

- **主线程**: PyQt5 事件循环、UI 渲染、QTimer 轮询调度
- **通讯线程**: CommWorker (QThread)，独占串口资源，处理所有读写操作
- **线程通讯**: 严格通过 Qt Signal/Slot 机制，不共享可变数据

---

## 2. 目录与模块结构

```
src/
└── nimotion/
    ├── __init__.py
    ├── main.py                  # 程序入口
    │
    ├── models/                  # 模型层：纯数据，无副作用
    │   ├── __init__.py
    │   ├── registers.py         # 寄存器定义表
    │   ├── error_codes.py       # 错误码定义表
    │   └── types.py             # 公共数据类型 / 枚举 / 数据类
    │
    ├── communication/           # 通讯层：串口和协议
    │   ├── __init__.py
    │   ├── serial_port.py       # 串口封装
    │   ├── modbus_rtu.py        # Modbus-RTU 协议
    │   ├── crc16.py             # CRC16 计算
    │   └── worker.py            # 通讯线程
    │
    ├── services/                # 服务层：业务逻辑
    │   ├── __init__.py
    │   └── motor_service.py     # 电机操作封装
    │
    └── ui/                      # UI 层：界面
        ├── __init__.py
        ├── main_window.py       # 主窗口
        ├── connection_bar.py    # 公共串口连接栏
        ├── serial_tab.py        # 串口调试 Tab
        ├── modbus_tab.py        # Modbus 调试 Tab
        ├── motor_tab.py         # 电机控制 Tab（容器）
        ├── motor_status.py      # 电机状态监控面板
        ├── motor_params.py      # 参数设置子 Tab
        ├── motor_control.py     # 运动控制子 Tab
        ├── motor_alarm.py       # 报警信息子 Tab
        └── widgets/             # 自定义控件
            ├── __init__.py
            ├── hex_input.py     # HEX 输入控件
            ├── led_indicator.py # LED 指示灯控件
            └── log_viewer.py    # 日志查看控件
```

---

## 3. 模型层设计

### 3.1 types.py — 公共数据类型

```python
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
    NOT_READY = 0       # 初始化
    SWITCH_ON_DISABLED = 1  # 电机无故障 (0x0050)
    READY_TO_SWITCH_ON = 2  # 启动 (0x0031)
    SWITCHED_ON = 3     # 使能 (0x0033)
    OPERATION_ENABLED = 4   # 运行 (0x0037)
    QUICK_STOP = 5      # 快速停机 (0x0017)
    FAULT_ACTIVE = 6    # 故障激活
    FAULT = 7           # 故障 (0x0008)


class RunMode(IntEnum):
    """运行模式"""
    POSITION = 1
    SPEED = 2
    HOMING = 3
    PULSE_INPUT = 4     # 仅 57H


class RegisterType(IntEnum):
    """寄存器类型"""
    HOLDING = 0   # 保持寄存器（可读写）
    INPUT = 1     # 输入寄存器（只读）


class DataType(IntEnum):
    """数据类型"""
    UINT16 = 0    # 1 个寄存器
    INT16 = 1     # 1 个寄存器，有符号
    UINT32 = 2    # 2 个寄存器
    INT32 = 3     # 2 个寄存器，有符号


@dataclass
class RegisterDef:
    """寄存器定义"""
    address: int
    name: str
    reg_type: RegisterType
    data_type: DataType
    count: int               # 寄存器数量: 1 或 2
    unit: str = ""
    min_val: int | None = None
    max_val: int | None = None
    default_val: int | None = None
    description: str = ""
    writable: bool = True
    restart_required: bool = False   # 修改后是否需要重启


@dataclass
class ModbusRequest:
    """Modbus 请求"""
    slave_id: int
    function_code: FunctionCode
    address: int
    count: int = 1           # 读取数量 / 写入数量
    values: list[int] = field(default_factory=list)  # 写入值


@dataclass
class ModbusResponse:
    """Modbus 响应"""
    slave_id: int
    function_code: int
    data: bytes              # 原始数据段
    values: list[int] = field(default_factory=list)  # 解析后的寄存器值
    is_error: bool = False
    error_code: int = 0
    raw_tx: bytes = b""      # 原始发送帧
    raw_rx: bytes = b""      # 原始接收帧
    timestamp: float = 0.0


@dataclass
class MotorStatus:
    """电机实时状态快照"""
    status_word: int = 0
    state: MotorState = MotorState.UNKNOWN
    position: int = 0            # pulse
    speed: int = 0               # Step/s (实际值，已除10)
    voltage: int = 0             # V
    current_mode: RunMode | None = None
    direction: int = 0           # 0=反转 1=正转
    alarm_code: int = 0
    alarm_text: str = ""
    is_running: bool = False     # 状态字 bit12
```

### 3.2 registers.py — 寄存器定义表

```python
"""
完整的寄存器定义表。
基于《一体化步进电机 Modbus 通讯用户手册（开环）B02》构建。
"""

from .types import RegisterDef, RegisterType, DataType

# 保持寄存器定义
HOLDING_REGISTERS: list[RegisterDef] = [
    RegisterDef(0x0000, "从站地址", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=1, max_val=247, default_val=1, restart_required=True),
    RegisterDef(0x0001, "波特率", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=0, max_val=9, default_val=5, restart_required=True,
                description="0=9.6k 2=19.2k 3=38.4k 4=57.6k 5=115.2k 6=256k 7=500k 8=1M"),
    RegisterDef(0x0002, "网络数据格式", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=0, max_val=3, default_val=2, restart_required=True,
                description="0=偶校验 1=奇校验 2=无校验1停止 3=无校验2停止"),
    RegisterDef(0x0008, "保存所有参数", RegisterType.HOLDING, DataType.UINT16, 1,
                writable=True, description="写 0x7376"),
    RegisterDef(0x000B, "恢复默认参数", RegisterType.HOLDING, DataType.UINT16, 1,
                writable=True, restart_required=True, description="写 0x6C64"),
    RegisterDef(0x0015, "减速电流", RegisterType.HOLDING, DataType.UINT16, 1,
                unit="mA", min_val=0, max_val=10000, default_val=1000),
    RegisterDef(0x0016, "怠机电流", RegisterType.HOLDING, DataType.UINT16, 1,
                unit="mA", min_val=0, max_val=10000, default_val=500),
    RegisterDef(0x0017, "加速电流", RegisterType.HOLDING, DataType.UINT16, 1,
                unit="mA", min_val=0, max_val=10000, default_val=1000),
    RegisterDef(0x0018, "运行电流", RegisterType.HOLDING, DataType.UINT16, 1,
                unit="mA", min_val=0, max_val=10000, default_val=1000),
    RegisterDef(0x0019, "过载电流", RegisterType.HOLDING, DataType.UINT16, 1,
                unit="100mA", min_val=0, max_val=100, default_val=40),
    RegisterDef(0x001A, "细分", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=0, max_val=7, default_val=7,
                description="0=Full 1=Half 2=1:4 3=1:8 4=1:16 5=1:32 6=1:64 7=1:128"),
    RegisterDef(0x0039, "运行模式", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=1, max_val=4, default_val=1,
                description="1=位置 2=速度 3=原点回归 4=脉冲输入(仅57H)"),
    RegisterDef(0x003A, "操作启停设置", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=0, max_val=1, default_val=1, description="0=无减速 1=减速停机"),
    RegisterDef(0x003B, "急停操作设置", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=0, max_val=1, default_val=1),
    RegisterDef(0x003C, "故障操作设置", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=0, max_val=1, default_val=0),
    RegisterDef(0x0043, "失速检测阈值", RegisterType.HOLDING, DataType.UINT32, 2,
                unit="100mA", min_val=0, max_val=100, default_val=80),
    RegisterDef(0x0051, "运动控制字", RegisterType.HOLDING, DataType.UINT16, 1),
    RegisterDef(0x0052, "运动方向", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=0, max_val=1, default_val=0, description="0=反转 1=正转"),
    RegisterDef(0x0053, "目标位置", RegisterType.HOLDING, DataType.INT32, 2,
                unit="pulse", default_val=0),
    RegisterDef(0x0055, "目标速度", RegisterType.HOLDING, DataType.UINT32, 2,
                unit="Step/s", min_val=0, max_val=15610, default_val=100),
    RegisterDef(0x0057, "位置最小值", RegisterType.HOLDING, DataType.INT32, 2,
                unit="pulse", default_val=0),
    RegisterDef(0x0059, "位置最大值", RegisterType.HOLDING, DataType.INT32, 2,
                unit="pulse", default_val=0),
    RegisterDef(0x005B, "最大速度", RegisterType.HOLDING, DataType.UINT32, 2,
                unit="Step/s", min_val=0, max_val=15610, default_val=250),
    RegisterDef(0x005D, "最小速度", RegisterType.HOLDING, DataType.UINT32, 2,
                unit="Step/s", min_val=0, max_val=1000, default_val=16),
    RegisterDef(0x005F, "加速度", RegisterType.HOLDING, DataType.UINT32, 2,
                unit="Step/s²", min_val=1, max_val=59590, default_val=1000),
    RegisterDef(0x0061, "减速度", RegisterType.HOLDING, DataType.UINT32, 2,
                unit="Step/s²", min_val=1, max_val=59590, default_val=1000),
    RegisterDef(0x0069, "原点偏移值", RegisterType.HOLDING, DataType.INT32, 2,
                unit="pulse", default_val=0),
    RegisterDef(0x006B, "原点回归方式", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=17, max_val=31, default_val=17),
    RegisterDef(0x006C, "寻找开关速度", RegisterType.HOLDING, DataType.UINT32, 2,
                unit="Step/s", min_val=0, max_val=15610, default_val=100),
    RegisterDef(0x006E, "寻找零位速度", RegisterType.HOLDING, DataType.UINT32, 2,
                unit="Step/s", min_val=0, max_val=15610, default_val=100),
    RegisterDef(0x0072, "零点回归", RegisterType.HOLDING, DataType.UINT16, 1,
                min_val=0, max_val=1, default_val=0),
    RegisterDef(0x0047, "设置零点", RegisterType.HOLDING, DataType.UINT16, 1,
                description="写 0x535A"),
    RegisterDef(0x0048, "设置原点", RegisterType.HOLDING, DataType.UINT16, 1,
                description="写 0x5348"),
    RegisterDef(0x0073, "清空错误存储器", RegisterType.HOLDING, DataType.UINT16, 1,
                description="写 0x6C64"),
]

# 输入寄存器定义
INPUT_REGISTERS: list[RegisterDef] = [
    RegisterDef(0x0017, "输入电压", RegisterType.INPUT, DataType.UINT16, 1,
                unit="V", writable=False),
    RegisterDef(0x0018, "数字量输入", RegisterType.INPUT, DataType.UINT32, 2,
                writable=False),
    RegisterDef(0x001E, "当前操作模式", RegisterType.INPUT, DataType.UINT16, 1,
                writable=False),
    RegisterDef(0x001F, "运动状态字", RegisterType.INPUT, DataType.UINT16, 1,
                writable=False),
    RegisterDef(0x0020, "当前运动方向", RegisterType.INPUT, DataType.UINT16, 1,
                writable=False),
    RegisterDef(0x0021, "当前显示位置", RegisterType.INPUT, DataType.INT32, 2,
                unit="pulse", writable=False),
    RegisterDef(0x0023, "当前运行速度", RegisterType.INPUT, DataType.UINT32, 2,
                unit="Step/s", writable=False, description="显示值=实际×10"),
    RegisterDef(0x0025, "错误寄存器", RegisterType.INPUT, DataType.UINT16, 1,
                writable=False),
    RegisterDef(0x0026, "当前错误报警值", RegisterType.INPUT, DataType.UINT16, 1,
                writable=False),
    RegisterDef(0x0027, "错误存储器报警个数", RegisterType.INPUT, DataType.UINT16, 1,
                writable=False),
]

# 索引：按地址快速查找
_HOLDING_MAP: dict[int, RegisterDef] = {r.address: r for r in HOLDING_REGISTERS}
_INPUT_MAP: dict[int, RegisterDef] = {r.address: r for r in INPUT_REGISTERS}


def get_register(address: int, reg_type: RegisterType) -> RegisterDef | None:
    """按地址和类型查找寄存器定义"""
    if reg_type == RegisterType.HOLDING:
        return _HOLDING_MAP.get(address)
    return _INPUT_MAP.get(address)
```

### 3.3 error_codes.py — 错误码表

```python
"""错误码定义表"""

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
    return ERROR_CODES.get(code, f"未知错误 (0x{code:04X})")


def get_exception_text(code: int) -> str:
    return MODBUS_EXCEPTIONS.get(code, f"未知异常 (0x{code:02X})")
```

---

## 4. 通讯层设计

### 4.1 crc16.py — CRC16 Modbus

```python
"""Modbus CRC16 计算（多项式 0xA001，初始值 0xFFFF）"""


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
```

### 4.2 modbus_rtu.py — Modbus-RTU 协议

```python
"""
Modbus-RTU 帧构建与解析。
不涉及串口 IO，纯数据处理。
"""

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
        if fc == FunctionCode.READ_HOLDING or fc == FunctionCode.READ_INPUT:
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
            # 将字节数据解析为 16 位寄存器值列表
            for i in range(0, byte_count, 2):
                resp.values.append((resp.data[i] << 8) | resp.data[i + 1])
        elif fc == FunctionCode.WRITE_SINGLE:
            # 响应: [从站][功能码][地址H][地址L][值H][值L]
            resp.data = raw[2:6]
            resp.values = [(raw[4] << 8) | raw[5]]
        elif fc == FunctionCode.WRITE_MULTIPLE:
            # 响应: [从站][功能码][地址H][地址L][数量H][数量L]
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
        elif fc == FunctionCode.WRITE_SINGLE:
            return 8  # 回显请求帧
        elif fc == FunctionCode.WRITE_MULTIPLE:
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
```

### 4.3 serial_port.py — 串口封装

```python
"""串口资源管理，封装 pyserial"""

import serial
import serial.tools.list_ports
from dataclasses import dataclass


@dataclass
class SerialConfig:
    """串口配置"""
    port: str = ""
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"       # "N" / "E" / "O"
    stopbits: float = 1     # 1 / 2
    timeout: float = 0.5    # 读超时（秒）


class SerialPort:
    """
    串口管理器。
    非线程安全 — 仅应在通讯线程中调用。
    """

    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self._config = SerialConfig()

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def config(self) -> SerialConfig:
        return self._config

    @staticmethod
    def list_ports() -> list[str]:
        """枚举可用串口"""
        return [p.device for p in serial.tools.list_ports.comports()]

    def open(self, config: SerialConfig) -> None:
        """打开串口"""
        self.close()
        self._config = config
        self._serial = serial.Serial(
            port=config.port,
            baudrate=config.baudrate,
            bytesize=config.bytesize,
            parity=config.parity,
            stopbits=config.stopbits,
            timeout=config.timeout,
        )

    def close(self) -> None:
        """关闭串口"""
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def write(self, data: bytes) -> int:
        """发送数据，返回发送字节数"""
        if not self.is_open:
            raise IOError("串口未打开")
        return self._serial.write(data)

    def read(self, size: int) -> bytes:
        """读取指定字节数（可能因超时返回不足）"""
        if not self.is_open:
            raise IOError("串口未打开")
        return self._serial.read(size)

    def read_all(self) -> bytes:
        """读取缓冲区所有数据"""
        if not self.is_open:
            raise IOError("串口未打开")
        return self._serial.read_all()

    def flush_input(self) -> None:
        """清空输入缓冲区"""
        if self.is_open:
            self._serial.reset_input_buffer()
```

### 4.4 worker.py — 通讯线程

```python
"""
通讯工作线程。
独占串口资源，通过 Signal/Slot 与主线程交互。
"""

import time
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition

from .serial_port import SerialPort, SerialConfig
from .modbus_rtu import ModbusRTU
from ..models.types import ModbusRequest, ModbusResponse


class CommWorker(QThread):
    """通讯工作线程"""

    # ── Signals（通讯线程 → 主线程）──
    connected = pyqtSignal()                # 串口已连接
    disconnected = pyqtSignal()             # 串口已断开
    connection_error = pyqtSignal(str)      # 连接失败
    response_received = pyqtSignal(object)  # ModbusResponse
    raw_data_received = pyqtSignal(bytes)   # 原始数据（串口调试模式）
    raw_data_sent = pyqtSignal(bytes)       # 原始数据已发送
    bytes_count_updated = pyqtSignal(int, int)  # (tx_total, rx_total)

    # ── 内部常量 ──
    MIN_FRAME_GAP = 0.005   # 帧间最小间隔（秒）

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._serial = SerialPort()
        self._modbus = ModbusRTU()
        self._running = False
        self._tx_bytes = 0
        self._rx_bytes = 0

        # 请求队列 (用 mutex + condition 实现)
        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._pending_request: ModbusRequest | None = None
        self._pending_raw: bytes | None = None
        self._raw_mode = False  # True = 串口调试模式

    # ── 公共方法（主线程调用）──

    def connect_port(self, config: SerialConfig) -> None:
        """请求连接串口"""
        try:
            self._serial.open(config)
            self._running = True
            if not self.isRunning():
                self.start()
            self.connected.emit()
        except Exception as e:
            self.connection_error.emit(str(e))

    def disconnect_port(self) -> None:
        """请求断开串口"""
        self._running = False
        self._condition.wakeAll()
        self.wait(2000)
        self._serial.close()
        self.disconnected.emit()

    def send_modbus(self, request: ModbusRequest) -> None:
        """提交 Modbus 请求（主线程调用）"""
        self._mutex.lock()
        self._pending_request = request
        self._raw_mode = False
        self._condition.wakeOne()
        self._mutex.unlock()

    def send_raw(self, data: bytes) -> None:
        """发送原始数据（串口调试模式）"""
        self._mutex.lock()
        self._pending_raw = data
        self._raw_mode = True
        self._condition.wakeOne()
        self._mutex.unlock()

    # ── 线程主循环 ──

    def run(self) -> None:
        while self._running:
            self._mutex.lock()
            # 等待请求或超时（超时用于检测串口调试模式的持续接收）
            if self._pending_request is None and self._pending_raw is None:
                self._condition.wait(self._mutex, 50)  # 50ms 轮询
            request = self._pending_request
            raw = self._pending_raw
            raw_mode = self._raw_mode
            self._pending_request = None
            self._pending_raw = None
            self._mutex.unlock()

            try:
                if raw_mode and raw is not None:
                    self._handle_raw_send(raw)
                elif request is not None:
                    self._handle_modbus(request)

                # 串口调试模式：持续接收
                if self._serial.is_open:
                    incoming = self._serial.read_all()
                    if incoming:
                        self._rx_bytes += len(incoming)
                        self.raw_data_received.emit(incoming)
                        self.bytes_count_updated.emit(
                            self._tx_bytes, self._rx_bytes
                        )
            except Exception:
                if self._running:
                    self._serial.close()
                    self.disconnected.emit()
                    self._running = False

    def _handle_raw_send(self, data: bytes) -> None:
        """发送原始数据"""
        self._serial.write(data)
        self._tx_bytes += len(data)
        self.raw_data_sent.emit(data)
        self.bytes_count_updated.emit(self._tx_bytes, self._rx_bytes)

    def _handle_modbus(self, request: ModbusRequest) -> None:
        """发送 Modbus 请求并等待响应"""
        frame = self._modbus.build_frame(request)
        self._serial.flush_input()
        self._serial.write(frame)
        self._tx_bytes += len(frame)
        self.raw_data_sent.emit(frame)

        time.sleep(self.MIN_FRAME_GAP)

        expected_len = self._modbus.expected_response_length(request)
        raw_rx = self._serial.read(expected_len)
        self._rx_bytes += len(raw_rx)

        if len(raw_rx) == 0:
            resp = ModbusResponse(
                slave_id=request.slave_id,
                function_code=request.function_code,
                data=b"",
                is_error=True,
                error_code=-2,  # 超时特殊码
                raw_tx=frame,
                raw_rx=b"",
                timestamp=time.time(),
            )
        else:
            resp = self._modbus.parse_response(raw_rx, request)
            resp.raw_tx = frame
            resp.timestamp = time.time()

        self.response_received.emit(resp)
        self.bytes_count_updated.emit(self._tx_bytes, self._rx_bytes)
```

### 4.5 通讯层时序图

**Modbus 读寄存器**:

```
主线程                    CommWorker               串口(从站)
  │                          │                        │
  │  send_modbus(request)    │                        │
  │ ─────────────────────►   │                        │
  │                          │  build_frame()         │
  │                          │  serial.write(frame)   │
  │                          │ ───────────────────►   │
  │                          │                        │
  │                          │  serial.read(expected) │
  │                          │ ◄───────────────────   │
  │                          │  parse_response()      │
  │  response_received(resp) │                        │
  │ ◄─────────────────────   │                        │
  │  更新 UI                  │                        │
```

---

## 5. 服务层设计

### 5.1 motor_service.py — 电机操作封装

```python
"""
电机业务逻辑层。
将寄存器操作封装为语义化方法，供 UI 层调用。
"""

from PyQt5.QtCore import QObject, pyqtSignal

from ..communication.worker import CommWorker
from ..models.types import (
    ModbusRequest, ModbusResponse, FunctionCode,
    MotorState, MotorStatus, RunMode, DataType,
)
from ..models.registers import get_register, RegisterType
from ..models.error_codes import get_error_text


class MotorService(QObject):
    """电机操作服务"""

    # 状态更新信号
    status_updated = pyqtSignal(object)   # MotorStatus
    param_read = pyqtSignal(int, int)     # (地址, 值)
    operation_done = pyqtSignal(bool, str) # (成功, 消息)

    def __init__(self, worker: CommWorker, slave_id: int = 1) -> None:
        super().__init__()
        self._worker = worker
        self._slave_id = slave_id
        self._worker.response_received.connect(self._on_response)
        self._pending_callback: dict[int, callable] = {}  # function_code → callback

    @property
    def slave_id(self) -> int:
        return self._slave_id

    @slave_id.setter
    def slave_id(self, value: int) -> None:
        self._slave_id = value

    # ── 状态查询 ──

    def refresh_status(self) -> None:
        """
        读取电机实时状态。
        一次批量读取 0x17~0x27 范围的输入寄存器（17 个），
        减少通讯次数。
        """
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=FunctionCode.READ_INPUT,
            address=0x0017,
            count=16,  # 0x17 ~ 0x26
        )
        self._worker.send_modbus(req)

    # ── 状态机控制 ──

    def startup(self) -> None:
        """无故障 → 启动"""
        self._write_control_word(0x0006)

    def enable(self) -> None:
        """启动 → 使能"""
        self._write_control_word(0x0007)

    def run(self) -> None:
        """使能 → 运行"""
        self._write_control_word(0x000F)

    def stop(self) -> None:
        """运行 → 使能（减速停机）"""
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

    def quick_enable(self) -> None:
        """一键使能：脱机 → 启动 → 使能"""
        # 依次发送，每步间有帧间隔
        self._write_control_word(0x0006)
        # 后续步骤在响应回调中链式执行
        # 实际实现通过 _pending_chain 机制

    # ── 运动控制 ──

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

    # ── 参数操作 ──

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

    def write_param_32bit(self, address: int, value: int,
                          signed: bool = False) -> None:
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

    # ── 内部方法 ──

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

    def _write_32bit(self, address: int, value: int,
                     signed: bool = False) -> None:
        from ..communication.modbus_rtu import ModbusRTU
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
            for i, val in enumerate(resp.values):
                # 需要请求上下文知道起始地址（通过 raw_tx 反推）
                start_addr = (resp.raw_tx[2] << 8) | resp.raw_tx[3]
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
        status.voltage = vals[0]           # 0x17
        # vals[1], vals[2] = 0x18~0x19 (DI)
        # ...
        # vals[7] = 0x1E (当前模式)
        status.current_mode = RunMode(vals[7]) if vals[7] in (1, 2, 3, 4) else None
        # vals[8] = 0x1F (状态字)
        status.status_word = vals[8]
        status.state = self._decode_state(vals[8])
        status.is_running = bool(vals[8] & (1 << 12))
        # vals[9] = 0x20 (方向)
        status.direction = vals[9]
        # vals[10], vals[11] = 0x21~0x22 (位置, 32位)
        from ..communication.modbus_rtu import ModbusRTU
        status.position = ModbusRTU.combine_32bit(vals[10], vals[11], signed=True)
        # vals[12], vals[13] = 0x23~0x24 (速度, 32位, 值=实际×10)
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
        if word & 0x0008:                          # bit3 = 故障
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
        from ..models.error_codes import get_exception_text
        return f"Modbus 异常: {get_exception_text(resp.error_code)}"
```

---

## 6. UI 层设计

### 6.1 主窗口 — main_window.py

```
┌──────────────────────────────────────────────────┐
│  ConnectionBar (公共串口连接栏)                     │
│  [端口▼][波特率▼][数据位][校验][停止位][地址][连接] │
├──────────────────────────────────────────────────┤
│  QTabWidget                                      │
│  ┌──────────┬────────────┬────────────┐          │
│  │ 串口调试  │ Modbus 调试 │ 电机控制   │          │
│  └──────────┴────────────┴────────────┘          │
│  ┌──────────────────────────────────────┐        │
│  │                                      │        │
│  │        当前 Tab 页内容                 │        │
│  │                                      │        │
│  └──────────────────────────────────────┘        │
├──────────────────────────────────────────────────┤
│  QStatusBar: [● 已连接 COM3 115200] [TX:1024 RX:2048]│
└──────────────────────────────────────────────────┘
```

**关键职责**:
- 持有 CommWorker 单例和 MotorService 单例
- 将 CommWorker 传递给各 Tab 页
- 管理串口连接/断开生命周期
- 更新状态栏信息

### 6.2 连接栏 — connection_bar.py

**类**: `ConnectionBar(QWidget)`

**Signal**:

| Signal | 参数 | 触发时机 |
|--------|------|---------|
| `connect_requested` | `SerialConfig` | 用户点击「连接」 |
| `disconnect_requested` | 无 | 用户点击「断开」 |
| `slave_id_changed` | `int` | 从站地址变更 |

**Slot**:

| Slot | 说明 |
|------|------|
| `on_connected()` | 连接成功，禁用配置控件，按钮变为「断开」 |
| `on_disconnected()` | 断开连接，恢复控件，按钮变为「连接」 |

### 6.3 串口调试 Tab — serial_tab.py

**类**: `SerialTab(QWidget)`

**布局**:

```
QVBoxLayout
├── QGroupBox("快捷指令")
│   └── QGridLayout  →  10 个 QPushButton (2行×5列)
├── LogViewer (接收区)
│   ├── QPlainTextEdit (只读)
│   └── QHBoxLayout [HEX/ASCII] [时间戳] [清空]
└── QGroupBox("发送")
    ├── QComboBox (历史记录) + QLineEdit (输入)
    └── QHBoxLayout [HEX/ASCII] [发送] [定时发送☐] [间隔 ms]
```

**数据流**:

```
用户输入 HEX → 解析为 bytes → CommWorker.send_raw()
                                    │
CommWorker.raw_data_received ──────►│──► LogViewer 追加显示
CommWorker.raw_data_sent ──────────►│──► LogViewer 追加显示
```

**快捷指令实现**: 预定义的 `list[tuple[str, list[int]]]`，点击后替换首字节为当前从站地址，追加 CRC，填入发送框。

### 6.4 Modbus 调试 Tab — modbus_tab.py

**类**: `ModbusTab(QWidget)`

**布局**:

```
QVBoxLayout
├── QGroupBox("操作")
│   ├── QHBoxLayout [功能码▼] [起始地址] [寄存器数量] [写入值]
│   ├── QLabel (寄存器提示: 名称/范围/单位)
│   └── QHBoxLayout [读取] [写入]
├── QTableWidget("结果表格")
│   └── 列: 地址 | HEX 值 | 十进制 | 有符号 | 说明
└── LogViewer("通讯日志")
```

**地址输入联动**:

```
地址输入变化 → 查询 registers.get_register()
            → 找到: 显示 "0x001A - 细分 (0~7, 默认7)"
            → 未找到: 显示 "未知寄存器"
```

**功能码切换逻辑**:

| 功能码 | 启用控件 | 禁用控件 |
|--------|---------|---------|
| 0x03 / 0x04 | 起始地址、数量、读取按钮 | 写入值、写入按钮 |
| 0x06 | 起始地址、写入值、写入按钮 | 数量（固定1）、读取按钮 |
| 0x10 | 起始地址、数量、写入值、写入按钮 | 读取按钮 |

### 6.5 电机控制 Tab — motor_tab.py

**类**: `MotorTab(QWidget)`

**布局**:

```
QHBoxLayout
├── MotorStatusPanel (左侧固定宽度 220px)
│   └── QFormLayout: 状态/位置/速度/电压/模式/方向/报警
│       + LEDIndicator × 2 (RUN, COM)
│       + [刷新] [☐ 自动刷新] [间隔 ▼]
└── QTabWidget (右侧，子 Tab)
    ├── MotorParamsPanel   ("参数设置")
    ├── MotorControlPanel  ("运动控制")
    └── MotorAlarmPanel    ("报警信息")
```

### 6.6 状态监控面板 — motor_status.py

**类**: `MotorStatusPanel(QWidget)`

**自动刷新机制**:

```python
class MotorStatusPanel(QWidget):
    def __init__(self, motor_service: MotorService):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_poll)
        self._motor = motor_service
        self._motor.status_updated.connect(self._update_display)

    def set_auto_refresh(self, enabled: bool, interval_ms: int = 200):
        if enabled:
            self._timer.start(interval_ms)
        else:
            self._timer.stop()

    def _on_poll(self):
        self._motor.refresh_status()

    def _update_display(self, status: MotorStatus):
        # 更新各 QLabel
        self._lbl_state.setText(self._state_text(status.state))
        self._lbl_position.setText(f"{status.position} pulse")
        self._lbl_speed.setText(
            f"{status.speed} Step/s = {status.speed * 0.3:.0f} RPM"
        )
        self._lbl_voltage.setText(f"{status.voltage} V")
        # ... 更新报警、指示灯等
```

**状态字 → 文本映射**:

| MotorState | 显示文本 | 颜色 |
|------------|---------|------|
| SWITCH_ON_DISABLED | 脱机 | 灰色 |
| READY_TO_SWITCH_ON | 启动 | 蓝色 |
| SWITCHED_ON | 使能 | 绿色 |
| OPERATION_ENABLED | 运行 | 绿色加粗 |
| QUICK_STOP | 急停 | 橙色 |
| FAULT | 故障 | 红色 |
| UNKNOWN | 未知 | 灰色 |

### 6.7 参数设置面板 — motor_params.py

**类**: `MotorParamsPanel(QWidget)`

**布局**:

```
QVBoxLayout
├── QScrollArea
│   └── QVBoxLayout
│       ├── QGroupBox("通讯参数")
│       │   └── QFormLayout: 从站地址 / 波特率 / 数据格式
│       ├── QGroupBox("电流参数")
│       │   └── QFormLayout: 怠机/运行/加速/减速/过载电流
│       ├── QGroupBox("运动参数")
│       │   └── QFormLayout: 细分 / 最大速度 / 最小速度 / 加速度 / 减速度
│       └── QGroupBox("停机设置")
│           └── QFormLayout: 操作启停 / 急停 / 故障
└── QHBoxLayout
    └── [读取参数] [设置参数] [保存到EEPROM] [恢复出厂]
```

**参数对比逻辑**: 每个输入控件持有 `_read_value`（从电机读回的原始值）和当前界面值。当两者不同时，控件背景设为浅黄色 `#FFFDE7`。

### 6.8 运动控制面板 — motor_control.py

**类**: `MotorControlPanel(QWidget)`

**布局**:

```
QVBoxLayout
├── QGroupBox("状态切换")
│   └── QHBoxLayout
│       [一键使能] [启动] [使能] [运行] [停止] [急停] [脱机] [清除故障]
├── QHBoxLayout
│   └── QLabel("运行模式:") + QComboBox([位置/速度/原点回归])
└── QStackedWidget (根据模式切换)
    ├── PositionPanel  (index=0)
    ├── SpeedPanel     (index=1)
    └── HomingPanel    (index=2)
```

**模式切换联动**:

```python
def _on_mode_changed(self, index: int):
    mode = RunMode(index + 1)
    self._motor.set_run_mode(mode)
    self._stack.setCurrentIndex(index)
```

**按钮安全规则**:

| 按钮 | 当前状态要求 | 点击效果 |
|------|-----------|---------|
| 启动 | 脱机(SWITCH_ON_DISABLED) | 发 0x06 |
| 使能 | 启动(READY_TO_SWITCH_ON) | 发 0x07 |
| 运行 | 使能(SWITCHED_ON) | 发 0x0F |
| 停止 | 运行(OPERATION_ENABLED) | 发 0x07 |
| 急停 | 任何非故障状态 | 发 0x02 |
| 一键使能 | 脱机 | 依次发 0x06, 0x07 |
| 清除故障 | 故障(FAULT) | 发 0x80 |

### 6.9 报警信息面板 — motor_alarm.py

**类**: `MotorAlarmPanel(QWidget)`

**布局**:

```
QVBoxLayout
├── QGroupBox("当前报警")
│   └── QHBoxLayout: QLabel("报警码") + QLabel("报警描述")
├── QGroupBox("历史报警")
│   └── QTableWidget
│       列: 序号 | 报警码 | 描述
│       行: 1~8 (最多 8 条历史记录)
├── QHBoxLayout
│   └── [读取当前报警] [读取历史报警] [清除历史报警] [清除故障状态]
```

### 6.10 自定义控件

#### HexInput — hex_input.py

```python
class HexInput(QLineEdit):
    """
    HEX 输入框。
    - 只允许输入 0-9, A-F, a-f, 空格
    - 自动格式化为 "XX XX XX" 格式
    - 提供 get_bytes() / set_bytes() 方法
    """
    def get_bytes(self) -> bytes: ...
    def set_bytes(self, data: bytes) -> None: ...
```

#### LEDIndicator — led_indicator.py

```python
class LEDIndicator(QWidget):
    """
    圆形 LED 指示灯控件。
    支持状态: OFF(灰) / ON(绿) / WARN(黄) / ERROR(红) / BLINK(闪烁)
    """
    def set_state(self, state: str) -> None: ...
```

#### LogViewer — log_viewer.py

```python
class LogViewer(QPlainTextEdit):
    """
    日志查看器。
    - 只读
    - 自动滚动到底部
    - 最大行数限制 (默认 10000 行，超出自动删除旧行)
    - 支持 HEX/ASCII 切换
    - 支持时间戳前缀
    """
    MAX_LINES = 10000

    def append_tx(self, data: bytes) -> None: ...
    def append_rx(self, data: bytes) -> None: ...
    def set_hex_mode(self, hex_mode: bool) -> None: ...
    def set_timestamp(self, enabled: bool) -> None: ...
```

---

## 7. Signal/Slot 连接总览

```
ConnectionBar
  ├─ connect_requested ───────► MainWindow._on_connect()
  ├─ disconnect_requested ────► MainWindow._on_disconnect()
  └─ slave_id_changed ────────► MotorService.slave_id (setter)

CommWorker
  ├─ connected ───────────────► ConnectionBar.on_connected()
  ├─ disconnected ────────────► ConnectionBar.on_disconnected()
  ├─ connection_error ────────► MainWindow._show_error()
  ├─ response_received ───────► MotorService._on_response()
  │                            ► ModbusTab._on_response()
  ├─ raw_data_received ───────► SerialTab._on_data_received()
  ├─ raw_data_sent ───────────► SerialTab._on_data_sent()
  └─ bytes_count_updated ─────► MainWindow._update_status_bar()

MotorService
  ├─ status_updated ──────────► MotorStatusPanel._update_display()
  ├─ param_read ──────────────► MotorParamsPanel._on_param_read()
  └─ operation_done ──────────► MotorControlPanel._on_operation_done()

QTimer (自动刷新)
  └─ timeout ─────────────────► MotorStatusPanel._on_poll()
                                 └─► MotorService.refresh_status()
```

---

## 8. 错误处理策略

### 8.1 通讯层错误

| 错误类型 | 检测方式 | 处理方式 |
|---------|---------|---------|
| 串口打开失败 | `serial.SerialException` | 弹窗提示，保持未连接状态 |
| 串口意外断开 | 读写时 `IOError` | 自动触发 `disconnected` 信号，更新 UI |
| CRC 校验失败 | `crc16.verify()` 返回 False | `ModbusResponse.error_code = -1`，UI 标红显示 |
| 响应超时 | `serial.read()` 返回空 | `ModbusResponse.error_code = -2`，UI 提示"通讯超时" |
| Modbus 异常响应 | 功能码 bit7 = 1 | 解析异常码，显示中文含义 |

### 8.2 业务层校验

| 校验项 | 时机 | 处理 |
|--------|------|------|
| 参数范围 | 写入前 | 对照 `RegisterDef.min_val/max_val`，超范围拒绝并提示 |
| 状态前置条件 | 按钮点击时 | 检查当前 MotorState 是否满足操作要求，不满足则禁用按钮或提示 |
| 危险操作确认 | 恢复出厂、清除报警 | `QMessageBox.warning()` 二次确认 |

### 8.3 错误码常量

```python
# ModbusResponse.error_code 特殊值
ERROR_CRC_FAILED = -1
ERROR_TIMEOUT = -2
# 正值 1~6 = Modbus 标准异常码
```

---

## 9. 程序入口

### main.py

```python
"""程序入口"""

import sys
from PyQt5.QtWidgets import QApplication
from nimotion.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("NiMotion 步进电机调试工具")
    app.setStyle("Fusion")

    window = MainWindow()
    window.setWindowTitle("NiMotion 步进电机调试工具 v0.1")
    window.resize(1024, 700)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
```

---

## 10. 开发阶段规划

基于 `requirements.md` 中的优先级，细化为可执行步骤：

### P0 — 基础通讯（串口调试 Tab）

| 步骤 | 交付物 | 验收标准 |
|------|--------|---------|
| 0.1 | `models/types.py` + `models/registers.py` + `models/error_codes.py` | 数据结构定义完整 |
| 0.2 | `communication/crc16.py` | CRC 单元测试通过 |
| 0.3 | `communication/serial_port.py` | 能打开/关闭/列举串口 |
| 0.4 | `communication/modbus_rtu.py` | 帧构建+解析单元测试通过 |
| 0.5 | `communication/worker.py` | 通讯线程能收发原始数据 |
| 0.6 | `ui/main_window.py` + `ui/connection_bar.py` | 主窗口可连接/断开串口 |
| 0.7 | `ui/serial_tab.py` + 自定义控件 | 串口调试 Tab 完整可用 |

### P1 — Modbus 调试 Tab

| 步骤 | 交付物 | 验收标准 |
|------|--------|---------|
| 1.1 | `ui/modbus_tab.py` | 可选功能码、输入地址、发送读写请求 |
| 1.2 | 地址提示联动 | 输入地址后显示寄存器名称和范围 |
| 1.3 | 结果表格 + 日志 | 读取结果以表格展示，原始帧在日志显示 |

### P2 — 电机控制（状态 + 参数）

| 步骤 | 交付物 | 验收标准 |
|------|--------|---------|
| 2.1 | `services/motor_service.py` | 封装状态查询、控制字写入 |
| 2.2 | `ui/motor_status.py` | 左侧状态面板，手动/自动刷新 |
| 2.3 | `ui/motor_params.py` | 参数读取/写入/保存/恢复出厂 |

### P3 — 运动控制

| 步骤 | 交付物 | 验收标准 |
|------|--------|---------|
| 3.1 | `ui/motor_control.py` | 状态切换按钮行 |
| 3.2 | 位置模式面板 | 相对/绝对运动可执行 |
| 3.3 | 速度模式面板 | 正转/反转/停止可执行 |
| 3.4 | 原点回归面板 | 回归可执行 |

### P4 — 报警信息

| 步骤 | 交付物 | 验收标准 |
|------|--------|---------|
| 4.1 | `ui/motor_alarm.py` | 读取当前/历史报警，显示中文含义 |
| 4.2 | 清除功能 | 清除历史报警、清除故障可执行 |
