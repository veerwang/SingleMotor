# NiMotion 项目迁移文档

> 本文档完整描述 NiMotion 步进电机调试工具的架构、协议、代码结构和实现细节，
> 用于将项目迁移到新工程时提供完整上下文。

---

## 1. 项目概述

**名称:** NiMotion 步进电机调试工具
**版本:** 0.1.0
**语言:** Python 3.10+
**GUI:** PyQt5 + Fusion 风格 + 自定义工业 HMI 主题（黑底黄字）
**通讯:** RS-485 / Modbus-RTU（pyserial）
**适用设备:** 北京立迈胜 STM86/STM57/STM42 系列一体化步进电机，SDM57V/SDM42 驱动器

**功能:**
- Tab 1：串口原始调试（HEX 收发、快捷命令、CRC 自动追加）
- Tab 2：Modbus 寄存器调试（结构化读写、寄存器提示、响应表格）
- Tab 3：电机控制（状态面板 + 运动控制 + 参数设置 + 报警 + 转盘）

---

## 2. 目录结构

```
SingleMotor/
├── pyproject.toml                  # 项目配置（hatchling 构建）
├── build.bat                       # Windows PyInstaller 打包脚本
├── run.sh                          # Unix 运行脚本
│
├── documents/                      # 技术文档（PDF + Markdown 摘要）
│   ├── 一体化步进电机Modbus通讯手册_摘要.md
│   ├── STM系列常见问题及解决方法_摘要.md
│   └── SDM42系列485总线电机驱动器使用说明书_摘要.md
│
├── src/nimotion/
│   ├── __init__.py
│   ├── main.py                     # 入口：QApplication + MainWindow
│   │
│   ├── models/                     # 数据模型层（纯数据，无外部依赖）
│   │   ├── types.py                # 枚举 + 数据类
│   │   ├── registers.py            # 完整寄存器定义表（66 保持 + 16 输入）
│   │   ├── error_codes.py          # 电机/Modbus 错误码映射
│   │   └── turret.py               # 转盘位置模型
│   │
│   ├── communication/              # 通讯协议层
│   │   ├── crc16.py                # CRC-16/Modbus
│   │   ├── modbus_rtu.py           # Modbus-RTU 帧构建/解析
│   │   ├── serial_port.py          # 串口封装（pyserial）
│   │   └── worker.py               # 通讯工作线程（QThread）
│   │
│   ├── services/                   # 业务逻辑层
│   │   └── motor_service.py        # 电机服务（状态机、运动、参数）
│   │
│   └── ui/                         # GUI 层（PyQt5）
│       ├── theme.py                # 工业 HMI 主题（513 行 QSS）
│       ├── main_window.py          # 主窗口（连接栏 + Tab + 状态栏）
│       ├── connection_bar.py       # 串口连接控件
│       ├── serial_tab.py           # 串口调试 Tab
│       ├── modbus_tab.py           # Modbus 调试 Tab
│       ├── motor_tab.py            # 电机控制 Tab（容器）
│       ├── motor_status.py         # 电机状态面板
│       ├── motor_control.py        # 运动控制面板
│       ├── motor_params.py         # 参数设置面板
│       ├── motor_alarm.py          # 报警面板
│       ├── turret_panel.py         # 转盘控制面板
│       └── widgets/                # 自定义控件
│           ├── hex_input.py        # HEX 输入框
│           ├── led_indicator.py    # LED 指示灯（动画）
│           ├── log_viewer.py       # 日志查看器
│           └── turret_widget.py    # 转盘可视化
│
└── tests/                          # 单元测试（178 用例全通过）
    ├── test_models/
    │   ├── test_types.py
    │   ├── test_registers.py
    │   ├── test_error_codes.py
    │   └── test_turret.py
    ├── test_communication/
    │   ├── test_crc16.py
    │   ├── test_modbus_rtu.py
    │   └── test_serial_port.py
    └── test_services/
        └── test_motor_service.py
```

---

## 3. 分层架构

```
┌──────────────────────────────────────────────────┐
│                   UI 层 (PyQt5)                   │
│  MainWindow / ConnectionBar / 3 个 Tab / Widgets  │
├──────────────────────────────────────────────────┤
│                 服务层 (Business)                  │
│  MotorService: 状态机 / 运动控制 / 参数读写        │
├──────────────────────────────────────────────────┤
│                 通讯层 (Protocol)                  │
│  CommWorker(QThread) / ModbusRTU / SerialPort     │
├──────────────────────────────────────────────────┤
│                 模型层 (Data)                      │
│  RegisterDef / Enums / ErrorCodes / Turret        │
└──────────────────────────────────────────────────┘
```

**线程模型:**
- 主线程：PyQt5 事件循环 + UI 渲染 + QTimer 轮询
- 通讯线程：CommWorker(QThread)，独占串口，帧收发
- 主线程 ↔ 通讯线程：通过 Qt Signal/Slot 通信（线程安全）

---

## 4. 模型层详细定义

### 4.1 枚举类型 (`models/types.py`)

```python
class FunctionCode(IntEnum):
    READ_HOLDING    = 0x03   # 读保持寄存器
    READ_INPUT      = 0x04   # 读输入寄存器
    WRITE_SINGLE    = 0x06   # 写单个寄存器
    WRITE_MULTIPLE  = 0x10   # 写多个寄存器

class MotorState(IntEnum):
    UNKNOWN         = -1
    NOT_READY       = 0      # 未就绪
    SWITCH_DISABLED = 1      # 上电禁止
    READY           = 2      # 准备就绪
    SWITCHED_ON     = 3      # 启动
    OPERATION       = 4      # 运行
    QUICK_STOP      = 5      # 快速停止
    FAULT_REACTION  = 6      # 故障响应
    FAULT           = 7      # 故障

class RunMode(IntEnum):
    POSITION = 1             # 位置模式
    SPEED    = 2             # 速度模式
    HOMING   = 3             # 原点回归
    PULSE    = 4             # 脉冲输入

class RegisterType(IntEnum):
    HOLDING = 0              # 保持寄存器（可读写）
    INPUT   = 1              # 输入寄存器（只读）

class DataType(IntEnum):
    UINT16 = 0
    INT16  = 1
    UINT32 = 2
    INT32  = 3
```

### 4.2 数据类 (`models/types.py`)

```python
@dataclass
class RegisterDef:
    address: int             # 寄存器地址
    name: str                # 名称
    type: RegisterType       # 保持/输入
    data_type: DataType      # 数据类型
    count: int = 1           # 寄存器个数（32位=2）
    unit: str = ""           # 单位
    min_val: int | None = None
    max_val: int | None = None
    default_val: int | None = None
    writable: bool = True
    restart_required: bool = False

@dataclass
class ModbusRequest:
    slave_id: int = 1
    function_code: FunctionCode = FunctionCode.READ_HOLDING
    address: int = 0
    count: int = 1
    values: list[int] = field(default_factory=list)

@dataclass
class ModbusResponse:
    slave_id: int = 0
    function_code: FunctionCode = FunctionCode.READ_HOLDING
    data: bytes = b""
    values: list[int] = field(default_factory=list)
    is_error: bool = False
    error_code: int = 0
    raw_tx: bytes = b""
    raw_rx: bytes = b""
    timestamp: float = 0.0

@dataclass
class MotorStatus:
    status_word: int = 0
    state: MotorState = MotorState.UNKNOWN
    position: int = 0        # 当前位置（脉冲数）
    speed: int = 0           # 当前速度（Step/s）
    voltage: float = 0.0     # 总线电压（V）
    mode: RunMode = RunMode.POSITION
    direction: int = 0       # 0=反转, 1=正转
    alarm_code: int = 0
    is_running: bool = False
```

### 4.3 寄存器定义表 (`models/registers.py`)

**保持寄存器（HOLDING_REGISTERS）— 66 条：**

| 地址 | 名称 | 数据类型 | 范围 | 默认值 | 说明 |
|------|------|---------|------|-------|------|
| 0x0000 | slave_id | UINT16 | 1-247 | 1 | 从站地址 |
| 0x0001 | baudrate | UINT16 | 0-7 | 5 | 波特率(0=2400..7=256000) |
| 0x0002 | data_format | UINT16 | 0-5 | 0 | 数据格式(校验/停止位) |
| 0x0003 | response_wait | UINT16 | 0-30000 | 0 | 响应等待(ms) |
| 0x0008 | save_params | UINT16 | — | — | 写0x7376保存到EEPROM |
| 0x000B | restore_defaults | UINT16 | — | — | 写0x6C64恢复出厂 |
| 0x000E | phase_resistance | UINT16 | 1-50000 | — | 相电阻(mΩ) |
| 0x000F | phase_inductance | UINT16 | 1-50000 | — | 相电感(μH) |
| 0x0010 | back_emf | UINT16 | 0-65535 | — | 反电动势常数 |
| 0x0014 | rated_voltage | UINT16 | 0-65535 | — | 额定电压(0.1V) |
| 0x0015 | decel_current | UINT16 | 0-65535 | — | 减速电流(mA) |
| 0x0016 | idle_current | UINT16 | 0-65535 | — | 静止电流(mA) |
| 0x0017 | accel_current | UINT16 | 0-65535 | — | 加速电流(mA) |
| 0x0018 | run_current | UINT16 | 0-65535 | — | 运行电流(mA) |
| 0x0019 | overload_current | UINT16 | 0-65535 | — | 过载电流(mA) |
| 0x001A | microstep | UINT16 | 0-7 | 7 | 细分(0=1,1=2,..,7=128) |
| 0x001F | low_speed_opt | UINT16 | 0-1 | 0 | 低速优化 |
| 0x002C-0x0037 | I/O配置 | — | — | — | 输入输出功能/极性/触发 |
| 0x0039 | run_mode | UINT16 | 1-4 | 1 | 运行模式 |
| 0x003A | operation_stop | UINT16 | 0-2 | 0 | 运行停止方式 |
| 0x003B | emergency_stop | UINT16 | 0-2 | 0 | 急停方式 |
| 0x003C | fault_stop | UINT16 | 0-2 | 0 | 故障停止方式 |
| 0x0043 | stall_threshold | UINT16 | 0-65535 | 0 | 堵转检测阈值 |
| 0x0047 | set_zero | UINT16 | — | — | 写0x535A设置零点 |
| 0x0048 | set_origin | UINT16 | — | — | 写0x5348设置原点 |
| 0x0051 | control_word | UINT16 | — | — | 控制字(状态机切换) |
| 0x0052 | direction | UINT16 | 0-1 | 1 | 方向(0=反,1=正) |
| 0x0053 | target_position | INT32(2reg) | — | 0 | 目标位置(脉冲) |
| 0x0055 | target_speed | UINT16 | 0-15610 | 0 | 目标速度(Step/s) |
| 0x0057 | accel_time | UINT16 | 0-65535 | 200 | 加速时间(ms) |
| 0x0058 | decel_time | UINT16 | 0-65535 | 200 | 减速时间(ms) |
| 0x0069 | home_offset | INT32(2reg) | — | 0 | 回零偏移(脉冲) |
| 0x006B | home_method | UINT16 | 17-31 | 17 | 回零方式 |
| 0x006C | home_search_speed | UINT16 | 1-15610 | 1000 | 回零搜索速度 |
| 0x006E | home_approach_speed | UINT16 | 1-15610 | 200 | 回零接近速度 |
| 0x0073 | clear_alarm_history | UINT16 | — | — | 写0x6C64清除历史报警 |

**输入寄存器（INPUT_REGISTERS）— 16 条：**

| 地址 | 名称 | 数据类型 | 说明 |
|------|------|---------|------|
| 0x0000 | manufacturer | UINT16 | 厂商编码 |
| 0x0001-0x0004 | serial_number | UINT16×4 | 序列号 |
| 0x0005-0x0006 | hw_version | UINT16×2 | 硬件版本 |
| 0x0007-0x000A | sw_version | UINT16×4 | 软件版本 |
| 0x0017 | bus_voltage | UINT16 | 总线电压(0.1V) |
| 0x0018 | di_status | UINT16 | 数字输入状态 |
| 0x0019 | run_mode | UINT16 | 当前运行模式 |
| 0x001A | state_word | UINT16 | 状态字 |
| 0x001B | current_position | INT32(2reg) | 当前位置(脉冲) |
| 0x001D | current_speed | INT16 | 当前速度(Step/s) |
| 0x0026 | current_alarm | UINT16 | 当前报警码 |
| 0x0027 | alarm_count | UINT16 | 历史报警数量 |
| 0x0028-0x002F | alarm_history | UINT16×8 | 历史报警码 |

### 4.4 错误码 (`models/error_codes.py`)

**电机错误码：**
| 码 | 含义 |
|----|------|
| 0x2200 | 过流 |
| 0x3110 | 过压 |
| 0x3120 | 欠压 |
| 0x4310 | 过温 |
| 0x7121 | 堵转检测 |
| 0x8612 | 限位开关 |
| 0xFF00-0xFF0F | 各类故障 |

**Modbus 异常码：** 0x01(非法功能) / 0x02(非法地址) / 0x03(非法数据) / 0x04(设备故障) / 0x05(设备忙) / 0x06(忙碌拒绝)

### 4.5 转盘模型 (`models/turret.py`)

```python
GEAR_RATIO = 132 / 48  # 2.75
MOTOR_STEPS_PER_REV = 200
MICROSTEP_REG_ADDR = 0x001A
POSITION_TOLERANCE = 50  # 脉冲容差

class TurretPosition(IntEnum):
    UNKNOWN = -1
    POS_1 = 0    # 0° (Home)
    POS_2 = 1    # 90°
    POS_3 = 2    # 180°
    POS_4 = 3    # 270°

# 从寄存器值计算细分：microstep = 2 ** reg_value (0→1, 7→128)
def microstep_from_register(reg_value: int) -> int
# 计算每个位置的脉冲数：steps_per_rev * microstep * gear_ratio / 4
def calculate_pulses_per_position(microstep: int) -> int
# 返回 {TurretPosition: pulse_count} 字典
def calculate_position_pulses(microstep: int) -> dict[TurretPosition, int]
# 根据当前脉冲匹配最近位置（容差内）
def pulse_to_turret_position(pulse: int, position_pulses: dict) -> TurretPosition
```

---

## 5. 通讯层详细实现

### 5.1 CRC-16/Modbus (`communication/crc16.py`)

- 多项式：0xA001，初始值：0xFFFF
- 字节序：低字节在前（little-endian）
- `calculate(data) → int`
- `append(data) → bytes` — 追加 2 字节 CRC
- `verify(frame) → bool` — 校验完整帧

### 5.2 Modbus-RTU 协议 (`communication/modbus_rtu.py`)

**帧格式：**
```
请求: [从站ID(1)] [功能码(1)] [数据(N)] [CRC(2)]
响应: [从站ID(1)] [功能码(1)] [数据(N)] [CRC(2)]
异常: [从站ID(1)] [功能码+0x80(1)] [异常码(1)] [CRC(2)]
```

**ModbusRTU 类方法：**
- `build_frame(ModbusRequest) → bytes` — 构建完整 RTU 帧
- `parse_response(bytes, ModbusRequest) → ModbusResponse` — 解析响应/异常
- `expected_response_length(ModbusRequest) → int` — 计算预期响应长度
- `combine_32bit(high, low, signed) → int` — 合并两个 16 位为 32 位
- `split_32bit(value) → (high, low)` — 拆分 32 位为高低 16 位

**功能码实现细节：**
- FC 0x03/0x04：请求 = `[slave][fc][addr_h][addr_l][count_h][count_l][crc]`，响应 = `[slave][fc][byte_count][data...][crc]`
- FC 0x06：请求 = `[slave][fc][addr_h][addr_l][value_h][value_l][crc]`，响应 = 回显请求
- FC 0x10：请求 = `[slave][fc][addr_h][addr_l][count_h][count_l][byte_count][data...][crc]`，响应 = `[slave][fc][addr_h][addr_l][count_h][count_l][crc]`

### 5.3 串口管理 (`communication/serial_port.py`)

```python
@dataclass
class SerialConfig:
    port: str = ""
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"       # "N"/"E"/"O"
    stopbits: float = 1     # 1 or 2
    timeout: float = 0.5    # 读超时(秒)
```

**SerialPort 类：** open/close/write/read/read_all/flush_input + list_ports(静态)

### 5.4 通讯工作线程 (`communication/worker.py`)

**CommWorker(QThread) 信号：**
```python
connected = pyqtSignal()
disconnected = pyqtSignal()
connection_error = pyqtSignal(str)
response_received = pyqtSignal(object)    # ModbusResponse
raw_data_received = pyqtSignal(bytes)
raw_data_sent = pyqtSignal(bytes)
bytes_count_updated = pyqtSignal(int, int)  # (tx_total, rx_total)
```

**公开方法：**
- `connect_port(SerialConfig)` — 发起连接
- `disconnect_port()` — 断开
- `send_modbus(ModbusRequest)` — 发送 Modbus 请求（排队）
- `send_raw(bytes)` — 发送原始数据
- `reset_counters()` — 重置字节计数

**内部机制：**
- QMutex + QWaitCondition 实现线程安全队列
- 帧间最小间隔 5ms（MIN_FRAME_GAP）
- 按预期长度读取响应，超时 500ms

---

## 6. 服务层详细实现

### 6.1 MotorService(QObject)

**信号：**
```python
status_updated = pyqtSignal(object)     # MotorStatus
param_read = pyqtSignal(int, int)       # (address, value)
operation_done = pyqtSignal(bool, str)  # (success, message)
```

### 6.2 状态机控制

电机状态机遵循 CiA 402 协议：

```
上电 → 未就绪 → 上电禁止 → 准备就绪(0x0050)
                                  ↓ Ctrl 0x06
                              启动(0x0031)
                                  ↓ Ctrl 0x07
                              使能(0x0033)
                                  ↓ Ctrl 0x0F
                              运行(0x0037)
                                  ↓ Ctrl 0x07 (减速停) / 0x02 (急停)
                              使能 / 快速停止(0x0017)

故障(0x0008) → Ctrl 0x80 → 上电禁止(0x0050)
```

**控制字写入（寄存器 0x0051）：**
| 方法 | 控制字 | 动作 |
|------|-------|------|
| `startup()` | 0x06 | 切换到启动状态 |
| `enable()` | 0x07 | 切换到使能状态 |
| `run()` | 0x0F | 开始运行 |
| `stop()` | 0x07 | 减速停止 |
| `quick_stop()` | 0x02 | 急停 |
| `disable()` | 0x00 | 禁止 |
| `clear_fault()` | 0x80 | 清除故障 |

### 6.3 运动控制

**位置模式 (mode=1)：**
```python
def move_relative(self, position: int) -> None:
    # 写目标位置 0x0053 (32-bit)
    # 写控制字 0x0051 = 0x4F, 然后 0x5F（相对触发）

def move_absolute(self, position: int) -> None:
    # 写目标位置 0x0053 (32-bit)
    # 写控制字 0x0051 = 0x0F, 然后 0x1F（绝对触发）
```

**速度模式 (mode=2)：**
```python
def set_speed(self, speed: int, direction: int = 1) -> None:
    # 写方向 0x0052
    # 写目标速度 0x0055
    # 写控制字 0x0051 = 0x0F
```

**原点回归 (mode=3)：**
```python
def start_homing(self) -> None:
    # 写控制字 0x0051 = 0x0F, 然后 0x1F
```

### 6.4 参数操作

| 方法 | 说明 |
|------|------|
| `read_param(addr, count)` | 批量读保持寄存器 |
| `write_param(addr, value)` | 写单个寄存器 (FC 0x06) |
| `write_param_32bit(addr, value, signed)` | 写 32 位值 (FC 0x10, 2 寄存器) |
| `set_run_mode(RunMode)` | 写 0x0039 |
| `save_params()` | 写 0x0008 = 0x7376 |
| `restore_defaults()` | 写 0x000B = 0x6C64 |
| `set_origin()` | 写 0x0048 = 0x5348 |
| `set_zero()` | 写 0x0047 = 0x535A |

### 6.5 状态刷新

```python
def refresh_status(self) -> None:
    # 读输入寄存器 0x0017-0x0026 (16个)
    # 解析: bus_voltage, di_status, run_mode, state_word,
    #       position(32-bit), speed(signed), alarm_code
    # 发射 status_updated(MotorStatus)
```

---

## 7. UI 层详细实现

### 7.1 整体布局

```
MainWindow (1280×800)
├── ConnectionBar ─────────────────────────────────
│  [端口▼] [波特率▼] [校验▼] [停止位▼] [从站ID↕] [连接]
├── QTabWidget ────────────────────────────────────
│  ┌─[串口调试]─[Modbus调试]─[电机控制]──────────┐
│  │                                              │
│  │  (当前 Tab 内容)                              │
│  │                                              │
│  └──────────────────────────────────────────────┘
└── StatusBar ─────────────────────────────────────
   [连接状态]                        [TX: xxx  RX: xxx]
```

### 7.2 串口调试 Tab (`serial_tab.py`)

**快捷命令按钮 (5×2 网格)：**
- 读状态字 / 读电压 / 读位置 / 读速度 / 读报警
- 启动 / 使能 / 运行 / 停止 / 清除故障
- 每个按钮预设 Modbus 帧模板，自动替换从站 ID 和 CRC

**收发区域：**
- 日志查看器（最大 10K 行），支持 HEX/ASCII 切换，时间戳
- HEX 输入框 + 发送历史（最近 20 条）
- 自动追加 CRC 选项
- 定时发送（50-60000ms 间隔）

### 7.3 Modbus 调试 Tab (`modbus_tab.py`)

- 功能码选择（0x03/0x04/0x06/0x10）
- 地址输入 + 寄存器名自动提示
- 结果表格：地址 | HEX | 十进制 | 有符号 | 说明
- 通讯日志（TX/RX 帧 HEX 显示）

### 7.4 电机控制 Tab (`motor_tab.py`)

```
┌──────────┬──────────────────────────────────┐
│ 状态面板  │  [运动控制] [参数设置] [报警] [转盘] │
│ (220px)  │                                   │
│          │  (子 Tab 内容)                      │
│ LED指示   │                                   │
│ 状态/位置 │                                   │
│ 速度/电压 │                                   │
│ 模式/方向 │                                   │
│ 报警码    │                                   │
│          │                                   │
│ [刷新]   │                                   │
│ [自动刷新]│                                   │
└──────────┴──────────────────────────────────┘
```

### 7.5 状态面板 (`motor_status.py`)

- RUN / COM LED 指示灯
- 状态（颜色编码：灰/蓝/绿/橙/红）
- 位置/速度/电压/模式/方向/报警码实时显示
- 手动刷新 + 自动刷新（200ms/500ms/1s/2s 可选）

### 7.6 运动控制面板 (`motor_control.py`)

**位置面板：** 目标位置输入 + 相对/绝对移动按钮
**速度面板：** 目标速度输入 + RPM 换算 + 方向 + 运行/停止
**回零面板：** 回零方式选择 + 启动回零/设置原点/设置零点

### 7.7 参数面板 (`motor_params.py`)

- 分组显示：通讯/电流/运动/停止设置
- 带 * 标记需重启参数
- 修改后黄色高亮
- 按钮：读取全部 / 写入修改 / 保存EEPROM / 恢复出厂

### 7.8 报警面板 (`motor_alarm.py`)

- 当前报警码 + 描述（红色高亮）
- 历史报警表格（序号/码/描述）
- 读取当前/读取历史/清除历史/清除故障

### 7.9 转盘面板 (`turret_panel.py`)

- 4 孔转盘可视化（12/3/6/9 点钟位置）
- 启动时异步读取细分寄存器 0x001A
- 归零按钮 + 4 个位置切换按钮
- 运动中禁用按钮，超时 30s

### 7.10 自定义控件

| 控件 | 说明 |
|------|------|
| `HexInput(QLineEdit)` | HEX 字节输入，自动格式化，`get_bytes()/set_bytes()` |
| `LEDIndicator(QWidget)` | 动画 LED，OFF/ON/WARN/ERROR/BLINK 状态 |
| `LogViewer(QPlainTextEdit)` | 时间戳日志，TX/RX/INFO 格式，最大 10K 行 |
| `TurretWidget(QWidget)` | 4 孔转盘可视化，活跃孔黄色发光，未归零覆盖层 |

### 7.11 工业主题 (`theme.py`)

- 513 行 QSS 样式表
- 黑色背景 (#0C0C0C)，黄色强调 (#FFD600)
- Segoe UI 界面字体，JetBrains Mono 输入字体
- Tab 顶部黄色边框，GroupBox 左侧黄色边框
- 表格斑马条纹，按钮悬停/按压动效
- 危险按钮红色变体

---

## 8. 信号流与数据路径

### 8.1 连接流程
```
ConnectionBar.connect_requested(SerialConfig)
  → MainWindow._on_connect()
    → CommWorker.connect_port(SerialConfig)
      → SerialPort.open()
        → CommWorker.connected signal
          → MainWindow._on_connected()
            → UI 状态更新
```

### 8.2 Modbus 读写流程
```
UI 操作（如点击刷新）
  → MotorService.refresh_status()
    → CommWorker.send_modbus(ModbusRequest)
      → [通讯线程] ModbusRTU.build_frame() → SerialPort.write()
      → [通讯线程] SerialPort.read() → ModbusRTU.parse_response()
        → CommWorker.response_received(ModbusResponse)
          → MotorService._on_response()
            → MotorService.status_updated(MotorStatus)
              → MotorStatusPanel._update_display()
```

### 8.3 转盘初始化流程
```
TurretPanel.__init__()
  → 连接 MotorService.param_read 信号
  → MotorService.read_param(0x001A, 1)  # 读细分寄存器
    → [异步] param_read(0x001A, value)
      → microstep_from_register(value)
      → calculate_position_pulses(microstep)
      → 缓存 _position_pulses, 启用按钮
```

---

## 9. 依赖与构建

### 9.1 pyproject.toml 配置

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "nimotion"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["pyserial>=3.5", "PyQt5>=5.15"]

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-cov>=4.0", "pytest-qt>=4.0", "mypy>=1.0", "ruff>=0.1.0"]

[project.scripts]
nimotion = "nimotion.main:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py310"
select = ["E", "F", "W", "I"]

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
```

### 9.2 打包 (PyInstaller)

```bash
pyinstaller --onefile --windowed --name "NiMotion" \
  --paths src \
  --hidden-import nimotion.models.types \
  --hidden-import nimotion.models.registers \
  --hidden-import nimotion.models.error_codes \
  --hidden-import nimotion.models.turret \
  --hidden-import nimotion.communication.crc16 \
  --hidden-import nimotion.communication.modbus_rtu \
  --hidden-import nimotion.communication.serial_port \
  --hidden-import nimotion.communication.worker \
  --hidden-import nimotion.services.motor_service \
  --hidden-import nimotion.ui.theme \
  --hidden-import nimotion.ui.main_window \
  --hidden-import nimotion.ui.connection_bar \
  --hidden-import nimotion.ui.serial_tab \
  --hidden-import nimotion.ui.modbus_tab \
  --hidden-import nimotion.ui.motor_tab \
  --hidden-import nimotion.ui.motor_status \
  --hidden-import nimotion.ui.motor_control \
  --hidden-import nimotion.ui.motor_params \
  --hidden-import nimotion.ui.motor_alarm \
  --hidden-import nimotion.ui.turret_panel \
  --hidden-import nimotion.ui.widgets.hex_input \
  --hidden-import nimotion.ui.widgets.led_indicator \
  --hidden-import nimotion.ui.widgets.log_viewer \
  --hidden-import nimotion.ui.widgets.turret_widget \
  src/nimotion/main.py
```

---

## 10. 测试覆盖

| 层 | 测试文件 | 用例数 | 覆盖率 |
|----|---------|--------|--------|
| 模型层 | test_types/registers/error_codes/turret | ~80 | ~95%+ |
| 通讯层 | test_crc16/modbus_rtu/serial_port | ~57 | ~90%+ |
| 服务层 | test_motor_service | ~40 | ~85%+ |
| UI层 | (手动测试) | — | — |
| **合计** | **8 个测试文件** | **178** | — |

运行测试：`pytest tests/ -v --cov=src/nimotion`

---

## 11. 迁移指南

### 可直接复用的模块（无 Qt 依赖）

| 模块 | 路径 | 说明 |
|------|------|------|
| 数据类型 | `models/types.py` | 枚举 + 数据类，纯 Python |
| 寄存器表 | `models/registers.py` | 完整寄存器定义，纯 Python |
| 错误码 | `models/error_codes.py` | 纯字典映射 |
| 转盘模型 | `models/turret.py` | 纯计算逻辑 |
| CRC-16 | `communication/crc16.py` | 纯算法 |
| Modbus-RTU | `communication/modbus_rtu.py` | 纯协议，无 I/O 依赖 |

### 需适配的模块

| 模块 | 依赖 | 迁移建议 |
|------|------|---------|
| `serial_port.py` | pyserial | 接口简单，直接复用或适配其他串口库 |
| `worker.py` | QThread/QMutex | 替换为 threading/asyncio，保留队列+信号模式 |
| `motor_service.py` | QObject/pyqtSignal | 将信号替换为回调/观察者/事件总线 |
| `ui/` 全部 | PyQt5 | 需完全重写，但业务逻辑可参考 |

### 迁移步骤建议

1. **复制模型层** — 直接使用，无需修改
2. **复制通讯协议** — crc16 + modbus_rtu 直接使用
3. **适配串口层** — 替换 pyserial 或保留
4. **重写通讯线程** — 根据目标框架选择线程/协程模型
5. **重写服务层** — 替换 Qt 信号为目标框架的事件机制
6. **重写 UI** — 根据目标框架（Web/桌面/嵌入式）重新设计

---

## 12. 关键设计决策备忘

1. **32 位寄存器用 2 个连续 16 位表示**，高位在前（big-endian register order）
2. **状态字解析**遵循 CiA 402 协议标准
3. **帧间间隔 5ms** 确保从站有足够处理时间
4. **转盘细分数运行时读取**，不硬编码，支持不同配置的电机
5. **异步通讯模式**：所有 Modbus 操作非阻塞，通过信号返回结果
6. **UI 状态轮询**：QTimer 驱动周期性状态刷新（可选 200ms~2s）
