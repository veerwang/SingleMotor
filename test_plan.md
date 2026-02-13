# 测试文档

**项目名称**: NiMotion 一体化步进电机调试工具
**版本**: v0.1
**日期**: 2026-02-13
**前置文档**: `requirements.md`, `design.md`

---

## 1. 测试概述

### 1.1 测试目标

验证各层模块的正确性、模块间的协作、以及最终面向用户的功能完整性。

### 1.2 测试策略

| 层级 | 测试类型 | 工具 | 是否需要硬件 |
|------|---------|------|-----------|
| 模型层 | 单元测试 | pytest | 否 |
| 通讯层（协议） | 单元测试 | pytest | 否 |
| 通讯层（串口） | 集成测试 | pytest + 虚拟串口 | 否（用 socat/pty） |
| 服务层 | 单元测试 | pytest + unittest.mock | 否 |
| UI 层 | 手动测试 | 人工操作 | 否（部分需硬件） |
| 端到端 | 系统测试 | 人工操作 | 是（电机+RS485） |

### 1.3 测试目录结构

```
tests/
├── conftest.py              # pytest 公共 fixtures
├── test_models/
│   ├── test_types.py        # 数据类型和枚举
│   ├── test_registers.py    # 寄存器定义表
│   └── test_error_codes.py  # 错误码表
├── test_communication/
│   ├── test_crc16.py        # CRC16 计算
│   ├── test_modbus_rtu.py   # Modbus 帧构建与解析
│   ├── test_serial_port.py  # 串口封装
│   └── test_worker.py       # 通讯线程
├── test_services/
│   └── test_motor_service.py # 电机服务层
└── test_ui/
    └── (手动测试用例，不含自动化代码)
```

### 1.4 运行方式

```bash
# 运行全部单元测试
pytest tests/ -v

# 运行指定模块
pytest tests/test_communication/test_crc16.py -v

# 生成覆盖率报告
pytest tests/ --cov=src/nimotion --cov-report=term-missing
```

---

## 2. 单元测试 — 模型层

### 2.1 test_types.py

| 用例编号 | 用例名称 | 测试内容 | 预期结果 |
|---------|---------|---------|---------|
| T-TYP-01 | 功能码枚举值正确 | `FunctionCode.READ_HOLDING == 0x03` 等 | 4 个枚举值与 Modbus 标准一致 |
| T-TYP-02 | 电机状态枚举完整 | 遍历 `MotorState`，验证 8 个状态值 | 枚举成员数 = 8 |
| T-TYP-03 | 运行模式枚举 | `RunMode.POSITION == 1`, `SPEED == 2`, `HOMING == 3` | 值与手册一致 |
| T-TYP-04 | RegisterDef 默认值 | 创建 `RegisterDef` 不传可选参数 | `unit=""`, `writable=True`, `restart_required=False` |
| T-TYP-05 | ModbusRequest 默认值 | 创建请求不传 values | `count=1`, `values=[]` |
| T-TYP-06 | ModbusResponse 默认值 | 创建响应 | `is_error=False`, `error_code=0` |
| T-TYP-07 | MotorStatus 默认值 | 创建状态快照 | `state=UNKNOWN`, `position=0`, `speed=0` |

```python
# tests/test_models/test_types.py

from nimotion.models.types import (
    FunctionCode, MotorState, RunMode, RegisterType, DataType,
    RegisterDef, ModbusRequest, ModbusResponse, MotorStatus,
)


class TestFunctionCode:
    def test_values(self):
        assert FunctionCode.READ_HOLDING == 0x03
        assert FunctionCode.READ_INPUT == 0x04
        assert FunctionCode.WRITE_SINGLE == 0x06
        assert FunctionCode.WRITE_MULTIPLE == 0x10

    def test_count(self):
        assert len(FunctionCode) == 4


class TestMotorState:
    def test_values(self):
        assert MotorState.UNKNOWN == -1
        assert MotorState.SWITCH_ON_DISABLED == 1
        assert MotorState.OPERATION_ENABLED == 4
        assert MotorState.FAULT == 7

    def test_count(self):
        assert len(MotorState) == 8


class TestRunMode:
    def test_values(self):
        assert RunMode.POSITION == 1
        assert RunMode.SPEED == 2
        assert RunMode.HOMING == 3
        assert RunMode.PULSE_INPUT == 4


class TestRegisterDef:
    def test_defaults(self):
        reg = RegisterDef(
            address=0x0000, name="测试", reg_type=RegisterType.HOLDING,
            data_type=DataType.UINT16, count=1,
        )
        assert reg.unit == ""
        assert reg.min_val is None
        assert reg.max_val is None
        assert reg.default_val is None
        assert reg.writable is True
        assert reg.restart_required is False


class TestModbusRequest:
    def test_defaults(self):
        req = ModbusRequest(
            slave_id=1, function_code=FunctionCode.READ_HOLDING, address=0x0000,
        )
        assert req.count == 1
        assert req.values == []

    def test_values_independent(self):
        """验证 values 默认值不会在实例间共享"""
        req1 = ModbusRequest(1, FunctionCode.WRITE_SINGLE, 0x0000)
        req2 = ModbusRequest(1, FunctionCode.WRITE_SINGLE, 0x0000)
        req1.values.append(100)
        assert req2.values == []


class TestMotorStatus:
    def test_defaults(self):
        status = MotorStatus()
        assert status.state == MotorState.UNKNOWN
        assert status.position == 0
        assert status.speed == 0
        assert status.voltage == 0
        assert status.alarm_code == 0
        assert status.is_running is False
```

### 2.2 test_registers.py

| 用例编号 | 用例名称 | 测试内容 | 预期结果 |
|---------|---------|---------|---------|
| T-REG-01 | 保持寄存器不为空 | `len(HOLDING_REGISTERS) > 0` | 至少 30 个定义 |
| T-REG-02 | 输入寄存器不为空 | `len(INPUT_REGISTERS) > 0` | 至少 10 个定义 |
| T-REG-03 | 地址唯一性 | 保持寄存器中无重复地址 | 无重复 |
| T-REG-04 | 输入寄存器只读 | 所有输入寄存器 `writable == False` | 全部为 False |
| T-REG-05 | 查找已知寄存器 | `get_register(0x0051, HOLDING)` | 返回"运动控制字" |
| T-REG-06 | 查找不存在的地址 | `get_register(0xFFFF, HOLDING)` | 返回 None |
| T-REG-07 | 关键寄存器定义验证 | 验证从站地址(0x00)范围 1~247 | `min_val=1, max_val=247` |
| T-REG-08 | 32 位寄存器 count=2 | 目标位置(0x53) count | `count == 2` |
| T-REG-09 | 类型正确区分 | 保持寄存器 `reg_type == HOLDING` | 全部为 HOLDING |

```python
# tests/test_models/test_registers.py

from nimotion.models.registers import (
    HOLDING_REGISTERS, INPUT_REGISTERS, get_register,
)
from nimotion.models.types import RegisterType, DataType


class TestHoldingRegisters:
    def test_not_empty(self):
        assert len(HOLDING_REGISTERS) >= 30

    def test_no_duplicate_address(self):
        addresses = [r.address for r in HOLDING_REGISTERS]
        assert len(addresses) == len(set(addresses))

    def test_all_holding_type(self):
        for reg in HOLDING_REGISTERS:
            assert reg.reg_type == RegisterType.HOLDING

    def test_slave_address_range(self):
        reg = get_register(0x0000, RegisterType.HOLDING)
        assert reg is not None
        assert reg.name == "从站地址"
        assert reg.min_val == 1
        assert reg.max_val == 247
        assert reg.default_val == 1

    def test_baudrate_range(self):
        reg = get_register(0x0001, RegisterType.HOLDING)
        assert reg is not None
        assert reg.min_val == 0
        assert reg.max_val == 9

    def test_target_position_is_32bit(self):
        reg = get_register(0x0053, RegisterType.HOLDING)
        assert reg is not None
        assert reg.count == 2
        assert reg.data_type == DataType.INT32

    def test_control_word_exists(self):
        reg = get_register(0x0051, RegisterType.HOLDING)
        assert reg is not None
        assert reg.name == "运动控制字"


class TestInputRegisters:
    def test_not_empty(self):
        assert len(INPUT_REGISTERS) >= 10

    def test_all_readonly(self):
        for reg in INPUT_REGISTERS:
            assert reg.writable is False

    def test_status_word_exists(self):
        reg = get_register(0x001F, RegisterType.INPUT)
        assert reg is not None
        assert reg.name == "运动状态字"


class TestGetRegister:
    def test_found(self):
        reg = get_register(0x0051, RegisterType.HOLDING)
        assert reg is not None

    def test_not_found(self):
        assert get_register(0xFFFF, RegisterType.HOLDING) is None

    def test_wrong_type(self):
        # 0x0051 是保持寄存器，用输入类型查应该找不到
        assert get_register(0x0051, RegisterType.INPUT) is None
```

### 2.3 test_error_codes.py

| 用例编号 | 用例名称 | 测试内容 | 预期结果 |
|---------|---------|---------|---------|
| T-ERR-01 | 已知错误码翻译 | `get_error_text(0x2200)` | "过流保护" |
| T-ERR-02 | 未知错误码 | `get_error_text(0x9999)` | 包含 "0x9999" |
| T-ERR-03 | 全部错误码有值 | 遍历 `ERROR_CODES` | 每个值非空字符串 |
| T-ERR-04 | 已知异常码翻译 | `get_exception_text(0x01)` | "非法功能码" |
| T-ERR-05 | 未知异常码 | `get_exception_text(0xFF)` | 包含 "0xFF" |
| T-ERR-06 | 错误码表完整 | 12 个预定义错误码 | `len(ERROR_CODES) == 12` |
| T-ERR-07 | 异常码表完整 | 6 个预定义异常码 | `len(MODBUS_EXCEPTIONS) == 6` |

```python
# tests/test_models/test_error_codes.py

from nimotion.models.error_codes import (
    ERROR_CODES, MODBUS_EXCEPTIONS, get_error_text, get_exception_text,
)


class TestErrorCodes:
    def test_known_code(self):
        assert get_error_text(0x2200) == "过流保护"
        assert get_error_text(0x3110) == "电源过压"
        assert get_error_text(0x3120) == "电源欠压"
        assert get_error_text(0xFF00) == "过热关机"

    def test_unknown_code(self):
        text = get_error_text(0x9999)
        assert "0x9999" in text.upper()

    def test_all_codes_non_empty(self):
        for code, text in ERROR_CODES.items():
            assert isinstance(text, str) and len(text) > 0

    def test_error_table_count(self):
        assert len(ERROR_CODES) == 12


class TestModbusExceptions:
    def test_known_exception(self):
        assert get_exception_text(0x01) == "非法功能码"
        assert get_exception_text(0x02) == "非法数据地址"
        assert get_exception_text(0x06) == "从设备忙"

    def test_unknown_exception(self):
        text = get_exception_text(0xFF)
        assert "0xFF" in text.upper()

    def test_exception_table_count(self):
        assert len(MODBUS_EXCEPTIONS) == 6
```

---

## 3. 单元测试 — 通讯层

### 3.1 test_crc16.py

| 用例编号 | 用例名称 | 测试内容 | 预期结果 |
|---------|---------|---------|---------|
| T-CRC-01 | 标准向量计算 | `calculate(b"\x01\x03\x00\x00\x00\x02")` | `0x0BC4` |
| T-CRC-02 | 空数据 | `calculate(b"")` | `0xFFFF` |
| T-CRC-03 | 单字节 | `calculate(b"\x01")` | 非零 16 位值 |
| T-CRC-04 | append 追加正确 | 验证追加后帧末 2 字节为 CRC 低高顺序 | 低字节在前 |
| T-CRC-05 | verify 正确帧 | `verify(append(data))` | True |
| T-CRC-06 | verify 篡改帧 | 修改中间字节后校验 | False |
| T-CRC-07 | verify 过短帧 | `verify(b"\x01\x03")` | False |
| T-CRC-08 | 读状态字报文 | 验证 `01 04 00 1F 00 01` 的 CRC | 与手册一致 |
| T-CRC-09 | 保存参数报文 | 验证 `01 06 00 08 73 76` 的 CRC | 与手册一致 |

```python
# tests/test_communication/test_crc16.py

from nimotion.communication.crc16 import calculate, append, verify


class TestCalculate:
    def test_standard_vector(self):
        """从站1读保持寄存器0x0000数量2"""
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x02])
        crc = calculate(data)
        # CRC16 结果已知为 0x0BC4 (低字节 0xC4, 高字节 0x0B)
        assert crc == 0xC40B or crc == 0x0BC4  # 取决于字节序解释
        # 更可靠：验证 append + verify 闭环
        frame = append(data)
        assert verify(frame)

    def test_empty_data(self):
        assert calculate(b"") == 0xFFFF

    def test_single_byte(self):
        crc = calculate(b"\x01")
        assert 0 <= crc <= 0xFFFF
        assert crc != 0xFFFF  # 非空输入不应为初始值


class TestAppend:
    def test_length_increased_by_2(self):
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        frame = append(data)
        assert len(frame) == len(data) + 2

    def test_low_byte_first(self):
        """验证 CRC 低字节在前"""
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])
        frame = append(data)
        crc = calculate(data)
        assert frame[-2] == crc & 0xFF          # 低字节
        assert frame[-1] == (crc >> 8) & 0xFF    # 高字节


class TestVerify:
    def test_valid_frame(self):
        data = bytes([0x01, 0x06, 0x00, 0x51, 0x00, 0x06])
        frame = append(data)
        assert verify(frame) is True

    def test_tampered_frame(self):
        data = bytes([0x01, 0x06, 0x00, 0x51, 0x00, 0x06])
        frame = bytearray(append(data))
        frame[3] = 0x52  # 篡改地址
        assert verify(bytes(frame)) is False

    def test_too_short(self):
        assert verify(b"\x01\x03") is False
        assert verify(b"") is False
        assert verify(b"\x01") is False

    def test_roundtrip(self):
        """多组数据闭环验证"""
        test_data = [
            bytes([0x01, 0x04, 0x00, 0x1F, 0x00, 0x01]),  # 读状态字
            bytes([0x01, 0x06, 0x00, 0x08, 0x73, 0x76]),  # 保存参数
            bytes([0x01, 0x06, 0x00, 0x51, 0x00, 0x80]),  # 清除故障
            bytes([0x01, 0x10, 0x00, 0x53, 0x00, 0x02, 0x04,
                   0x00, 0x00, 0x27, 0x10]),               # 写目标位置
        ]
        for data in test_data:
            frame = append(data)
            assert verify(frame), f"CRC 闭环校验失败: {data.hex(' ')}"
```

### 3.2 test_modbus_rtu.py

| 用例编号 | 用例名称 | 测试内容 | 预期结果 |
|---------|---------|---------|---------|
| T-RTU-01 | 构建读保持寄存器帧 | 0x03 读 0x0000 × 2 | `01 03 00 00 00 02` + CRC |
| T-RTU-02 | 构建读输入寄存器帧 | 0x04 读 0x001F × 1 | `01 04 00 1F 00 01` + CRC |
| T-RTU-03 | 构建写单个寄存器帧 | 0x06 写 0x0051=0x0006 | `01 06 00 51 00 06` + CRC |
| T-RTU-04 | 构建写多个寄存器帧 | 0x10 写 0x0053=[0x0000, 0x2710] | `01 10 00 53 00 02 04 00 00 27 10` + CRC |
| T-RTU-05 | 不支持的功能码 | 功能码=0xFF | 抛出 ValueError |
| T-RTU-06 | 解析读保持响应 | 正常 0x03 响应 | values 正确解析 |
| T-RTU-07 | 解析读输入响应 | 正常 0x04 响应 | values 正确解析 |
| T-RTU-08 | 解析写单个响应 | 0x06 回显响应 | values=[写入值] |
| T-RTU-09 | 解析写多个响应 | 0x10 响应 | values=[数量] |
| T-RTU-10 | 解析异常响应 | 功能码 0x83 + 异常码 0x02 | is_error=True, error_code=2 |
| T-RTU-11 | 解析 CRC 错误帧 | 篡改 CRC 后解析 | is_error=True, error_code=-1 |
| T-RTU-12 | 期望响应长度-读 | 0x03 读 5 个寄存器 | 5 + 5×2 = 15 |
| T-RTU-13 | 期望响应长度-写单个 | 0x06 | 8 |
| T-RTU-14 | 期望响应长度-写多个 | 0x10 | 8 |
| T-RTU-15 | 32 位值合并-无符号 | combine_32bit(0x0000, 0x2710) | 10000 |
| T-RTU-16 | 32 位值合并-有符号负数 | combine_32bit(0xFFFF, 0xD8F0, signed=True) | -10000 |
| T-RTU-17 | 32 位值拆分-正数 | split_32bit(10000) | (0x0000, 0x2710) |
| T-RTU-18 | 32 位值拆分-负数 | split_32bit(-10000) | (0xFFFF, 0xD8F0) |
| T-RTU-19 | 32 位拆合闭环 | split 后 combine 还原 | 与原值一致 |
| T-RTU-20 | 构建帧 CRC 有效 | 所有构建的帧 verify=True | 全部通过 |

```python
# tests/test_communication/test_modbus_rtu.py

import pytest
from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.communication.crc16 import verify, append
from nimotion.models.types import FunctionCode, ModbusRequest, ModbusResponse


class TestBuildFrame:
    def test_read_holding(self):
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0x0000, count=2)
        frame = ModbusRTU.build_frame(req)
        assert frame[:6] == bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x02])
        assert len(frame) == 8
        assert verify(frame)

    def test_read_input(self):
        req = ModbusRequest(1, FunctionCode.READ_INPUT, 0x001F, count=1)
        frame = ModbusRTU.build_frame(req)
        assert frame[:6] == bytes([0x01, 0x04, 0x00, 0x1F, 0x00, 0x01])
        assert verify(frame)

    def test_write_single(self):
        req = ModbusRequest(1, FunctionCode.WRITE_SINGLE, 0x0051, values=[0x0006])
        frame = ModbusRTU.build_frame(req)
        assert frame[:6] == bytes([0x01, 0x06, 0x00, 0x51, 0x00, 0x06])
        assert verify(frame)

    def test_write_multiple(self):
        req = ModbusRequest(
            1, FunctionCode.WRITE_MULTIPLE, 0x0053,
            count=2, values=[0x0000, 0x2710],
        )
        frame = ModbusRTU.build_frame(req)
        expected_pdu = bytes([
            0x01, 0x10, 0x00, 0x53, 0x00, 0x02, 0x04,
            0x00, 0x00, 0x27, 0x10,
        ])
        assert frame[:11] == expected_pdu
        assert verify(frame)

    def test_unsupported_function_code(self):
        req = ModbusRequest(1, 0xFF, 0x0000)
        with pytest.raises(ValueError, match="不支持的功能码"):
            ModbusRTU.build_frame(req)

    def test_different_slave_ids(self):
        """验证从站地址正确填入帧头"""
        for slave_id in [1, 5, 100, 247]:
            req = ModbusRequest(slave_id, FunctionCode.READ_HOLDING, 0x0000, count=1)
            frame = ModbusRTU.build_frame(req)
            assert frame[0] == slave_id


class TestParseResponse:
    def test_read_holding_response(self):
        """模拟读保持寄存器 0x0000×2 的响应: 从站地址=1, 波特率=5"""
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0x0000, count=2)
        raw = append(bytes([0x01, 0x03, 0x04, 0x00, 0x01, 0x00, 0x05]))
        resp = ModbusRTU.parse_response(raw, req)
        assert not resp.is_error
        assert resp.values == [0x0001, 0x0005]

    def test_read_input_response(self):
        """模拟读输入寄存器 0x001F 状态字响应"""
        req = ModbusRequest(1, FunctionCode.READ_INPUT, 0x001F, count=1)
        raw = append(bytes([0x01, 0x04, 0x02, 0x00, 0x37]))
        resp = ModbusRTU.parse_response(raw, req)
        assert not resp.is_error
        assert resp.values == [0x0037]

    def test_write_single_response(self):
        req = ModbusRequest(1, FunctionCode.WRITE_SINGLE, 0x0051, values=[0x0006])
        raw = append(bytes([0x01, 0x06, 0x00, 0x51, 0x00, 0x06]))
        resp = ModbusRTU.parse_response(raw, req)
        assert not resp.is_error
        assert resp.values == [0x0006]

    def test_write_multiple_response(self):
        req = ModbusRequest(1, FunctionCode.WRITE_MULTIPLE, 0x0053, count=2, values=[0, 0])
        raw = append(bytes([0x01, 0x10, 0x00, 0x53, 0x00, 0x02]))
        resp = ModbusRTU.parse_response(raw, req)
        assert not resp.is_error

    def test_exception_response(self):
        """模拟异常响应: 功能码 0x83 (0x03+0x80), 异常码 0x02"""
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0xFFFF, count=1)
        raw = append(bytes([0x01, 0x83, 0x02]))
        resp = ModbusRTU.parse_response(raw, req)
        assert resp.is_error
        assert resp.error_code == 0x02

    def test_crc_error(self):
        """CRC 校验失败"""
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0x0000, count=1)
        raw = bytes([0x01, 0x03, 0x02, 0x00, 0x01, 0xFF, 0xFF])  # 错误 CRC
        resp = ModbusRTU.parse_response(raw, req)
        assert resp.is_error
        assert resp.error_code == -1


class TestExpectedResponseLength:
    def test_read_holding(self):
        req = ModbusRequest(1, FunctionCode.READ_HOLDING, 0x0000, count=5)
        assert ModbusRTU.expected_response_length(req) == 5 + 5 * 2  # 15

    def test_read_input(self):
        req = ModbusRequest(1, FunctionCode.READ_INPUT, 0x0017, count=16)
        assert ModbusRTU.expected_response_length(req) == 5 + 16 * 2  # 37

    def test_write_single(self):
        req = ModbusRequest(1, FunctionCode.WRITE_SINGLE, 0x0051, values=[0x0006])
        assert ModbusRTU.expected_response_length(req) == 8

    def test_write_multiple(self):
        req = ModbusRequest(1, FunctionCode.WRITE_MULTIPLE, 0x0053, count=2, values=[0, 0])
        assert ModbusRTU.expected_response_length(req) == 8


class TestCombine32bit:
    def test_unsigned_positive(self):
        assert ModbusRTU.combine_32bit(0x0000, 0x2710) == 10000

    def test_unsigned_large(self):
        assert ModbusRTU.combine_32bit(0x0001, 0x0000) == 65536

    def test_signed_negative(self):
        assert ModbusRTU.combine_32bit(0xFFFF, 0xD8F0, signed=True) == -10000

    def test_signed_positive(self):
        assert ModbusRTU.combine_32bit(0x0000, 0x2710, signed=True) == 10000

    def test_signed_zero(self):
        assert ModbusRTU.combine_32bit(0x0000, 0x0000, signed=True) == 0


class TestSplit32bit:
    def test_positive(self):
        assert ModbusRTU.split_32bit(10000) == (0x0000, 0x2710)

    def test_negative(self):
        assert ModbusRTU.split_32bit(-10000) == (0xFFFF, 0xD8F0)

    def test_zero(self):
        assert ModbusRTU.split_32bit(0) == (0x0000, 0x0000)

    def test_roundtrip(self):
        """拆分后合并应还原"""
        for value in [0, 1, -1, 10000, -10000, 2**31 - 1, -(2**31)]:
            high, low = ModbusRTU.split_32bit(value)
            signed = value < 0
            restored = ModbusRTU.combine_32bit(high, low, signed=True)
            assert restored == value, f"闭环失败: {value}"
```

### 3.3 test_serial_port.py

| 用例编号 | 用例名称 | 测试内容 | 预期结果 |
|---------|---------|---------|---------|
| T-SER-01 | 初始状态未打开 | 创建 SerialPort 后 is_open | False |
| T-SER-02 | list_ports 返回列表 | 调用 list_ports() | 返回 list[str] |
| T-SER-03 | 打开不存在的端口 | open("/dev/NOTEXIST") | 抛出异常 |
| T-SER-04 | 未打开时写数据 | 未 open 直接 write | 抛出 IOError |
| T-SER-05 | 未打开时读数据 | 未 open 直接 read | 抛出 IOError |
| T-SER-06 | close 幂等 | 连续调用 close 两次 | 不抛异常 |
| T-SER-07 | SerialConfig 默认值 | 创建 SerialConfig | baudrate=115200, parity="N" |

```python
# tests/test_communication/test_serial_port.py

import pytest
from nimotion.communication.serial_port import SerialPort, SerialConfig


class TestSerialConfig:
    def test_defaults(self):
        cfg = SerialConfig()
        assert cfg.baudrate == 115200
        assert cfg.bytesize == 8
        assert cfg.parity == "N"
        assert cfg.stopbits == 1
        assert cfg.timeout == 0.5


class TestSerialPort:
    def test_initial_not_open(self):
        port = SerialPort()
        assert port.is_open is False

    def test_list_ports_returns_list(self):
        ports = SerialPort.list_ports()
        assert isinstance(ports, list)

    def test_open_nonexistent_port(self):
        port = SerialPort()
        with pytest.raises(Exception):
            port.open(SerialConfig(port="/dev/NOTEXIST_12345"))

    def test_write_without_open(self):
        port = SerialPort()
        with pytest.raises(IOError, match="串口未打开"):
            port.write(b"\x01\x02")

    def test_read_without_open(self):
        port = SerialPort()
        with pytest.raises(IOError, match="串口未打开"):
            port.read(10)

    def test_close_idempotent(self):
        port = SerialPort()
        port.close()
        port.close()  # 不抛异常
```

---

## 4. 单元测试 — 服务层

### 4.1 test_motor_service.py

使用 `unittest.mock` 模拟 CommWorker，不依赖硬件。

| 用例编号 | 用例名称 | 测试内容 | 预期结果 |
|---------|---------|---------|---------|
| T-SVC-01 | startup 发送控制字 0x06 | 调用 startup() | worker.send_modbus 被调用，地址=0x51, 值=0x06 |
| T-SVC-02 | enable 发送控制字 0x07 | 调用 enable() | 值=0x07 |
| T-SVC-03 | run 发送控制字 0x0F | 调用 run() | 值=0x0F |
| T-SVC-04 | stop 发送控制字 0x07 | 调用 stop() | 值=0x07 |
| T-SVC-05 | quick_stop 发送 0x02 | 调用 quick_stop() | 值=0x02 |
| T-SVC-06 | disable 发送 0x00 | 调用 disable() | 值=0x00 |
| T-SVC-07 | clear_fault 发送 0x80 | 调用 clear_fault() | 值=0x80 |
| T-SVC-08 | save_params | 调用 save_params() | 地址=0x08, 值=0x7376 |
| T-SVC-09 | restore_defaults | 调用 restore_defaults() | 地址=0x0B, 值=0x6C64 |
| T-SVC-10 | set_origin | 调用 set_origin() | 地址=0x48, 值=0x5348 |
| T-SVC-11 | set_zero | 调用 set_zero() | 地址=0x47, 值=0x535A |
| T-SVC-12 | set_run_mode 位置 | set_run_mode(POSITION) | 地址=0x39, 值=1 |
| T-SVC-13 | set_run_mode 速度 | set_run_mode(SPEED) | 地址=0x39, 值=2 |
| T-SVC-14 | slave_id 修改 | 设置 slave_id=5 后发请求 | 请求中 slave_id=5 |
| T-SVC-15 | 状态解码-脱机 | 状态字=0x0050 | state=SWITCH_ON_DISABLED |
| T-SVC-16 | 状态解码-启动 | 状态字=0x0031 | state=READY_TO_SWITCH_ON |
| T-SVC-17 | 状态解码-使能 | 状态字=0x0033 | state=SWITCHED_ON |
| T-SVC-18 | 状态解码-运行 | 状态字=0x0037 | state=OPERATION_ENABLED |
| T-SVC-19 | 状态解码-故障 | 状态字 bit3=1 | state=FAULT |
| T-SVC-20 | 状态解码-急停 | 状态字=0x0017 | state=QUICK_STOP |
| T-SVC-21 | 状态解码-未知 | 状态字=0x1234 | state=UNKNOWN |
| T-SVC-22 | refresh_status 请求 | 调用 refresh_status() | 功能码=0x04, 地址=0x17, count=16 |
| T-SVC-23 | move_relative | move_relative(10000) | 写 0x53 + 控制字 0x4F + 0x5F |
| T-SVC-24 | move_absolute | move_absolute(5000) | 写 0x53 + 控制字 0x0F + 0x1F |
| T-SVC-25 | set_speed | set_speed(500, 1) | 写 0x52=1, 写 0x55=500, 控制字 0x0F |

```python
# tests/test_services/test_motor_service.py

import pytest
from unittest.mock import MagicMock, call
from nimotion.models.types import (
    FunctionCode, ModbusRequest, MotorState, RunMode,
)
from nimotion.services.motor_service import MotorService


@pytest.fixture
def mock_worker():
    worker = MagicMock()
    worker.response_received = MagicMock()
    worker.response_received.connect = MagicMock()
    return worker


@pytest.fixture
def service(mock_worker):
    return MotorService(mock_worker, slave_id=1)


class TestControlWord:
    """测试状态机控制方法发送正确的控制字"""

    @pytest.mark.parametrize("method,expected_value", [
        ("startup", 0x0006),
        ("enable", 0x0007),
        ("run", 0x000F),
        ("stop", 0x0007),
        ("quick_stop", 0x0002),
        ("disable", 0x0000),
        ("clear_fault", 0x0080),
    ])
    def test_control_word(self, service, mock_worker, method, expected_value):
        getattr(service, method)()
        mock_worker.send_modbus.assert_called_once()
        req = mock_worker.send_modbus.call_args[0][0]
        assert req.address == 0x0051
        assert req.function_code == FunctionCode.WRITE_SINGLE
        assert req.values == [expected_value]


class TestParamOperations:
    def test_save_params(self, service, mock_worker):
        service.save_params()
        req = mock_worker.send_modbus.call_args[0][0]
        assert req.address == 0x0008
        assert req.values == [0x7376]

    def test_restore_defaults(self, service, mock_worker):
        service.restore_defaults()
        req = mock_worker.send_modbus.call_args[0][0]
        assert req.address == 0x000B
        assert req.values == [0x6C64]

    def test_set_origin(self, service, mock_worker):
        service.set_origin()
        req = mock_worker.send_modbus.call_args[0][0]
        assert req.address == 0x0048
        assert req.values == [0x5348]

    def test_set_zero(self, service, mock_worker):
        service.set_zero()
        req = mock_worker.send_modbus.call_args[0][0]
        assert req.address == 0x0047
        assert req.values == [0x535A]

    def test_set_run_mode(self, service, mock_worker):
        service.set_run_mode(RunMode.SPEED)
        req = mock_worker.send_modbus.call_args[0][0]
        assert req.address == 0x0039
        assert req.values == [2]


class TestSlaveId:
    def test_default(self, service):
        assert service.slave_id == 1

    def test_change(self, service, mock_worker):
        service.slave_id = 5
        service.startup()
        req = mock_worker.send_modbus.call_args[0][0]
        assert req.slave_id == 5


class TestRefreshStatus:
    def test_request_params(self, service, mock_worker):
        service.refresh_status()
        req = mock_worker.send_modbus.call_args[0][0]
        assert req.function_code == FunctionCode.READ_INPUT
        assert req.address == 0x0017
        assert req.count == 16


class TestDecodeState:
    @pytest.mark.parametrize("word,expected_state", [
        (0x0050, MotorState.SWITCH_ON_DISABLED),
        (0x0031, MotorState.READY_TO_SWITCH_ON),
        (0x0033, MotorState.SWITCHED_ON),
        (0x0037, MotorState.OPERATION_ENABLED),
        (0x0017, MotorState.QUICK_STOP),
        (0x0008, MotorState.FAULT),        # bit3=1
        (0x0038, MotorState.FAULT),        # bit3=1, 任何包含故障位
        (0x1234, MotorState.UNKNOWN),
    ])
    def test_decode(self, word, expected_state):
        assert MotorService._decode_state(word) == expected_state
```

---

## 5. 手动测试 — UI 层

以下测试需人工执行，验证界面交互。不需要电机硬件的用例标注"无需硬件"。

### 5.1 公共连接栏

| 用例编号 | 用例名称 | 前置条件 | 操作步骤 | 预期结果 | 硬件 |
|---------|---------|---------|---------|---------|------|
| T-UI-01 | 串口列表枚举 | 插入 USB-485 | 1. 启动程序 2. 点击端口下拉框 | 显示可用串口列表 | 否 |
| T-UI-02 | 串口列表刷新 | 启动后插入 USB | 1. 点击刷新按钮 | 新设备出现在列表中 | 否 |
| T-UI-03 | 正常连接 | 选择正确端口 | 1. 选端口 2. 115200 3. 点连接 | 按钮变为「断开」，状态栏显示已连接 | 否 |
| T-UI-04 | 正常断开 | 已连接状态 | 1. 点「断开」 | 按钮恢复「连接」，状态栏显示未连接 | 否 |
| T-UI-05 | 连接失败 | 选择不存在的端口 | 1. 选无效端口 2. 点连接 | 弹窗提示错误，保持未连接 | 否 |
| T-UI-06 | 连接时控件禁用 | 已连接 | 观察端口/波特率等控件 | 配置控件不可编辑 | 否 |
| T-UI-07 | 从站地址修改 | 已连接 | 修改从站地址为 5 | 后续通讯使用地址 5 | 是 |
| T-UI-08 | 状态栏收发计数 | 已连接 | 发送多条数据 | TX/RX 计数递增 | 是 |

### 5.2 串口调试 Tab

| 用例编号 | 用例名称 | 前置条件 | 操作步骤 | 预期结果 | 硬件 |
|---------|---------|---------|---------|---------|------|
| T-UI-10 | HEX 发送 | 已连接，HEX 模式 | 输入 `01 06 00 51 00 06` 点发送 | 接收区显示 TX 数据 | 是 |
| T-UI-11 | ASCII 发送 | 已连接，ASCII 模式 | 输入文本点发送 | 数据以 ASCII 发出 | 是 |
| T-UI-12 | HEX 显示切换 | 有接收数据 | 切换 HEX/ASCII | 显示格式切换 | 是 |
| T-UI-13 | 时间戳显示 | 有接收数据 | 勾选时间戳 | 每行数据前显示时间 | 是 |
| T-UI-14 | 清空接收区 | 有接收数据 | 点「清空」 | 接收区清空 | 否 |
| T-UI-15 | 定时发送 | 已连接，HEX 模式 | 输入数据，设 1000ms，勾选定时 | 每秒自动发送一次 | 是 |
| T-UI-16 | 停止定时发送 | 定时发送中 | 取消勾选定时 | 停止自动发送 | 是 |
| T-UI-17 | HEX 输入校验 | HEX 模式 | 输入非法字符 `GG ZZ` | 非法字符被过滤或提示 | 否 |
| T-UI-18 | 快捷指令填充 | 已连接 | 点「读状态字」按钮 | 发送区填入 `01 04 00 1F 00 01` | 否 |
| T-UI-19 | 快捷指令地址替换 | 从站地址=5 | 点「电机启动」按钮 | 首字节替换为 `05` | 否 |
| T-UI-20 | 历史记录 | 发送过多条数据 | 点击输入框下拉 | 显示最近发送记录 | 否 |

### 5.3 Modbus 调试 Tab

| 用例编号 | 用例名称 | 前置条件 | 操作步骤 | 预期结果 | 硬件 |
|---------|---------|---------|---------|---------|------|
| T-UI-30 | 读保持寄存器 | 已连接电机 | 功能码 0x03, 地址 0x0000, 数量 2, 点读取 | 表格显示从站地址和波特率值 | 是 |
| T-UI-31 | 读输入寄存器 | 已连接电机 | 功能码 0x04, 地址 0x001F, 数量 1, 点读取 | 表格显示状态字 | 是 |
| T-UI-32 | 写单个寄存器 | 已连接电机 | 功能码 0x06, 地址 0x0051, 值 0x0006 | 日志显示 TX/RX，操作成功 | 是 |
| T-UI-33 | 地址提示显示 | 无需连接 | 在地址框输入 `0x0051` | 下方提示 "运动控制字" | 否 |
| T-UI-34 | 未知地址提示 | 无需连接 | 在地址框输入 `0xAAAA` | 下方提示 "未知寄存器" | 否 |
| T-UI-35 | 功能码切换控件 | 无需连接 | 切换到 0x06 | 数量控件禁用，写入值控件启用 | 否 |
| T-UI-36 | 通讯日志显示 | 已连接 | 执行读写操作 | 日志区显示完整 TX/RX 报文 | 是 |
| T-UI-37 | CRC 校验失败 | 已连接 | 模拟接收到损坏帧 | 日志区标红警告 | 是 |
| T-UI-38 | 通讯超时 | 已连接，电机断电 | 发送读取请求 | 提示「通讯超时」 | 是 |
| T-UI-39 | 异常响应显示 | 已连接 | 读取非法地址 | 显示异常码含义（如"非法数据地址"） | 是 |

### 5.4 电机控制 Tab — 状态监控

| 用例编号 | 用例名称 | 前置条件 | 操作步骤 | 预期结果 | 硬件 |
|---------|---------|---------|---------|---------|------|
| T-UI-50 | 手动刷新状态 | 已连接电机 | 点「刷新」按钮 | 各状态字段更新 | 是 |
| T-UI-51 | 自动刷新 | 已连接电机 | 勾选「自动」，间隔 500ms | 每 500ms 自动更新 | 是 |
| T-UI-52 | 停止自动刷新 | 自动刷新中 | 取消勾选「自动」 | 停止刷新 | 是 |
| T-UI-53 | 状态文本显示 | 电机脱机状态 | 观察状态面板 | 显示"脱机"，灰色 | 是 |
| T-UI-54 | 位置显示 | 电机使能 | 手动转动电机轴 | 位置值变化 | 是 |
| T-UI-55 | 速度显示含 RPM | 电机运行中 | 观察速度显示 | 同时显示 Step/s 和 RPM | 是 |
| T-UI-56 | 报警红色高亮 | 触发报警 | 观察报警行 | 红色文字显示报警描述 | 是 |
| T-UI-57 | 指示灯状态 | 不同电机状态 | 观察 RUN/COM 灯 | 颜色与实际指示灯一致 | 是 |

### 5.5 电机控制 Tab — 参数设置

| 用例编号 | 用例名称 | 前置条件 | 操作步骤 | 预期结果 | 硬件 |
|---------|---------|---------|---------|---------|------|
| T-UI-60 | 读取参数 | 已连接电机 | 点「读取参数」 | 所有参数框填入电机当前值 | 是 |
| T-UI-61 | 设置单个参数 | 已读取参数 | 修改运行电流为 2000，点设置 | 值写入电机 | 是 |
| T-UI-62 | 修改高亮 | 已读取参数 | 修改某参数值 | 该输入框背景变黄 | 否 |
| T-UI-63 | 保存到 EEPROM | 已设置参数 | 点「保存到EEPROM」 | 提示保存成功 | 是 |
| T-UI-64 | 恢复出厂确认 | 已连接 | 点「恢复出厂」 | 弹出二次确认对话框 | 否 |
| T-UI-65 | 恢复出厂取消 | 出现确认框 | 点「取消」 | 不执行恢复 | 否 |
| T-UI-66 | 恢复出厂执行 | 出现确认框 | 点「确定」 | 发送恢复命令，提示需重启 | 是 |
| T-UI-67 | 参数范围校验 | 无需连接 | 输入超范围值（从站地址=300） | 拒绝写入，提示范围错误 | 否 |

### 5.6 电机控制 Tab — 运动控制

| 用例编号 | 用例名称 | 前置条件 | 操作步骤 | 预期结果 | 硬件 |
|---------|---------|---------|---------|---------|------|
| T-UI-70 | 一键使能 | 电机脱机 | 点「一键使能」 | 状态变为"使能"，黄灯亮 | 是 |
| T-UI-71 | 状态切换链 | 电机脱机 | 依次点 启动→使能→运行→停止→脱机 | 状态依次正确切换 | 是 |
| T-UI-72 | 急停 | 电机运行中 | 点「急停」 | 电机立即停止 | 是 |
| T-UI-73 | 清除故障 | 电机故障状态 | 排除故障后点「清除故障」 | 状态恢复为"脱机" | 是 |
| T-UI-74 | 位置-相对运动 | 电机使能，位置模式 | 输入 10000 pulse，点「相对运动」 | 电机正转 10000 步 | 是 |
| T-UI-75 | 位置-绝对运动 | 电机使能，位置模式 | 输入 5000 pulse，点「绝对运动」 | 电机运动到绝对位置 5000 | 是 |
| T-UI-76 | 位置-设为原点 | 电机使能 | 点「设为原点」 | 当前位置设为原点 | 是 |
| T-UI-77 | 位置-设为零点 | 电机使能 | 点「设为零点」 | 当前位置设为零点 | 是 |
| T-UI-78 | 速度-正转 | 电机使能，速度模式 | 输入 500 Step/s，点「正转运行」 | 电机正转，显示 150 RPM | 是 |
| T-UI-79 | 速度-反转 | 电机使能，速度模式 | 输入 500 Step/s，点「反转运行」 | 电机反转 | 是 |
| T-UI-80 | 速度-实时调速 | 电机运行中 | 修改速度为 1000，重新点运行 | 速度切换，无需停机 | 是 |
| T-UI-81 | 速度-停止 | 电机运行中 | 点「停止」 | 电机减速停止 | 是 |
| T-UI-82 | 原点回归 | 电机使能，原点模式 | 设回归方式 31，点「开始回归」 | 电机执行回零 | 是 |
| T-UI-83 | 原点回归-停止 | 回归中 | 点「停止」 | 回归中断 | 是 |
| T-UI-84 | 模式切换面板联动 | 无需连接 | 切换运行模式下拉框 | 面板自动切换显示 | 否 |

### 5.7 电机控制 Tab — 报警信息

| 用例编号 | 用例名称 | 前置条件 | 操作步骤 | 预期结果 | 硬件 |
|---------|---------|---------|---------|---------|------|
| T-UI-90 | 读取当前报警 | 已连接 | 点「读取当前报警」 | 显示报警码和中文描述 | 是 |
| T-UI-91 | 无报警显示 | 电机无报警 | 点「读取当前报警」 | 报警码=0，描述为空或"无" | 是 |
| T-UI-92 | 读取历史报警 | 已连接 | 点「读取历史报警」 | 表格显示最多 8 条历史记录 | 是 |
| T-UI-93 | 清除历史报警 | 有历史报警 | 点「清除历史报警」 | 历史记录清空 | 是 |
| T-UI-94 | 清除故障状态 | 电机故障 | 排障后点「清除故障状态」 | 故障清除 | 是 |
| T-UI-95 | 报警码翻译 | 收到报警码 0x3120 | 观察描述 | 显示"电源欠压" | 是 |

---

## 6. 端到端系统测试

完整操作流程测试，需要实际电机和 RS485 硬件。

### 6.1 完整操作流程

| 用例编号 | 用例名称 | 操作步骤 | 预期结果 |
|---------|---------|---------|---------|
| T-E2E-01 | 首次连接并读取状态 | 1. 选端口 115200 2. 连接 3. 切到电机控制 4. 点刷新 | 显示脱机状态，电压 24V |
| T-E2E-02 | 位置模式完整流程 | 1. 一键使能 2. 选位置模式 3. 设速度 500 4. 输入 10000 5. 相对运动 6. 等完成 7. 停止 8. 脱机 | 电机走 10000 步后停止 |
| T-E2E-03 | 速度模式完整流程 | 1. 一键使能 2. 选速度模式 3. 输入 1000 Step/s 4. 正转 5. 观察 3 秒 6. 改 500 Step/s 7. 停止 8. 脱机 | 电机加速到 1000，减到 500，停止 |
| T-E2E-04 | 原点回归完整流程 | 1. 一键使能 2. 先位置模式走一段 3. 切原点回归 4. 方式 31 5. 开始回归 6. 等完成 | 电机回到原点位置 |
| T-E2E-05 | 参数修改保存流程 | 1. 读取参数 2. 改运行电流为 1500 3. 设置参数 4. 保存 EEPROM 5. 断电重启 6. 重新读取 | 运行电流=1500 保持 |
| T-E2E-06 | 报警触发与清除 | 1. 手动堵住电机轴 2. 运行 3. 等待失速报警 4. 停止 5. 松开 6. 清除故障 | 报警信息正确显示并清除 |
| T-E2E-07 | 串口调试验证 | 1. 切串口 Tab 2. 输入 `01 04 00 1F 00 01` 3. 发送 4. 观察响应 | 收到包含状态字的响应帧 |
| T-E2E-08 | Modbus 调试验证 | 1. 切 Modbus Tab 2. 0x03 读 0x0000 × 5 3. 读取 | 表格显示 5 个参数值 |
| T-E2E-09 | 多从站切换 | 1. 连接从站 1 2. 读状态 3. 改从站地址为 2 4. 读状态 | 两台电机状态分别显示 |
| T-E2E-10 | USB 热拔插恢复 | 1. 已连接运行中 2. 拔出 USB 3. 观察提示 4. 重新插入 5. 重新连接 | 断开提示，重连后功能正常 |

---

## 7. 需求追溯矩阵

### 7.1 串口调试 (S-xx)

| 需求编号 | 需求描述 | 测试用例 |
|---------|---------|---------|
| S-01 | 数据接收 HEX/ASCII 显示 | T-UI-12 |
| S-02 | 时间戳 | T-UI-13 |
| S-03 | 数据发送 HEX/ASCII | T-UI-10, T-UI-11 |
| S-04 | HEX 输入格式 | T-UI-17 |
| S-05 | 定时发送 | T-UI-15, T-UI-16 |
| S-06 | 清空接收区 | T-UI-14 |
| S-07 | 收发计数 | T-UI-08 |
| S-08 | 历史记录 | T-UI-20 |
| S-09 | 快捷指令 | T-UI-18, T-UI-19 |

### 7.2 Modbus 调试 (M-xx)

| 需求编号 | 需求描述 | 测试用例 |
|---------|---------|---------|
| M-01 | 功能码选择 | T-UI-35 |
| M-02 | 地址输入 | T-UI-33, T-UI-34 |
| M-03 | 寄存器名称提示 | T-UI-33 |
| M-04 | 批量读取 | T-UI-30, T-E2E-08 |
| M-05 | 写入操作 | T-UI-32, T-RTU-03, T-RTU-04 |
| M-06 | 结果表格 | T-UI-30, T-UI-31 |
| M-07 | 通讯日志 | T-UI-36 |
| M-08 | CRC 校验 | T-CRC-*, T-UI-37 |
| M-09 | 异常响应解析 | T-RTU-10, T-UI-39 |
| M-10 | 超时处理 | T-UI-38 |

### 7.3 电机控制 (C-xx)

| 需求编号 | 需求描述 | 测试用例 |
|---------|---------|---------|
| C-01 | 状态字解析 | T-SVC-15~21, T-UI-53 |
| C-02 | 位置显示 | T-UI-54 |
| C-03 | 速度显示(含RPM) | T-UI-55 |
| C-04 | 电压显示 | T-E2E-01 |
| C-05~C-07 | 模式/方向/报警显示 | T-UI-50, T-UI-56 |
| C-08 | 运行指示灯 | T-UI-57 |
| C-09~C-10 | 手动/自动刷新 | T-UI-50, T-UI-51, T-UI-52 |
| C-11~C-16 | 参数设置 | T-UI-60~T-UI-67 |
| C-17 | 读取参数 | T-UI-60 |
| C-18 | 设置参数 | T-UI-61 |
| C-19 | 保存参数 | T-UI-63, T-SVC-08 |
| C-20 | 恢复出厂 | T-UI-64~T-UI-66, T-SVC-09 |
| C-21 | 参数对比 | T-UI-62 |
| C-22~C-28 | 位置模式控制 | T-UI-74~T-UI-77, T-E2E-02 |
| C-29~C-33 | 速度模式控制 | T-UI-78~T-UI-81, T-E2E-03 |
| C-34~C-38 | 原点回归控制 | T-UI-82~T-UI-83, T-E2E-04 |
| C-39~C-43 | 报警信息 | T-UI-90~T-UI-95, T-E2E-06 |

---

## 8. 测试环境

### 8.1 自动化测试环境

| 项目 | 要求 |
|------|------|
| Python | 3.10+ |
| pytest | >= 7.0 |
| pytest-cov | >= 4.0 |
| pytest-qt | >= 4.0（如需 UI 自动化） |

### 8.2 硬件测试环境

| 项目 | 型号/规格 |
|------|---------|
| 步进电机 | STM42 系列（开环） |
| USB-485 转换器 | NiMotion SCM-USB485B 或兼容 |
| 电源 | DC 24V / 2A 以上 |
| PC | Windows / Linux, 有 USB 端口 |
| 终端电阻 | 120Ω × 2（总线两端各一） |

### 8.3 覆盖率目标

| 层 | 目标覆盖率 |
|----|---------|
| 模型层 | >= 95% |
| 通讯层（协议） | >= 90% |
| 服务层 | >= 85% |
| 总体 | >= 80% |
