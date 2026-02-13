# 服务层测试报告

**日期**: 2026-02-13
**测试范围**: `src/nimotion/services/motor_service.py`
**测试工具**: pytest 9.0.2 + pytest-cov 7.0.0 + pytest-qt 4.5.0
**Python**: 3.13.2

---

## 测试结果总览

| 指标 | 结果 |
|------|------|
| 测试用例总数 | 40 |
| 通过 | 40 |
| 失败 | 0 |
| 通过率 | **100%** |
| 代码覆盖率 | **100%** |
| 执行时间 | 0.29s |

---

## 分模块详情

### TestSlaveId (2 用例)

验证从站地址的 getter/setter。

### TestStatusQuery (1 用例)

验证 `refresh_status()` 发送正确的读输入寄存器请求 (FC=0x04, addr=0x17, count=16)。

### TestStateControl (7 用例)

| 方法 | 控制字 | 结果 |
|------|--------|------|
| startup() | 0x0006 | 通过 |
| enable() | 0x0007 | 通过 |
| run() | 0x000F | 通过 |
| stop() | 0x0007 | 通过 |
| quick_stop() | 0x0002 | 通过 |
| disable() | 0x0000 | 通过 |
| clear_fault() | 0x0080 | 通过 |

### TestMotionControl (4 用例)

| 方法 | 发送次数 | 结果 |
|------|----------|------|
| move_relative() | 3 (位置+2个控制字) | 通过 |
| move_absolute() | 3 | 通过 |
| set_speed() | 3 (方向+速度+控制字) | 通过 |
| start_homing() | 2 | 通过 |

### TestParamOperations (8 用例)

验证参数读写、保存/恢复、模式设置、原点/零点设置的 Modbus 请求构建。

### TestDecodeState (9 用例, parametrized)

| 状态字 | 期望状态 | 结果 |
|--------|---------|------|
| 0x0050 | SWITCH_ON_DISABLED | 通过 |
| 0x0031 | READY_TO_SWITCH_ON | 通过 |
| 0x0033 | SWITCHED_ON | 通过 |
| 0x0037 | OPERATION_ENABLED | 通过 |
| 0x0017 | QUICK_STOP | 通过 |
| 0x0008 | FAULT | 通过 |
| 0x0018 | FAULT (bit3) | 通过 |
| 0x0000 | UNKNOWN | 通过 |
| 0x1234 | UNKNOWN | 通过 |

### TestFormatError (3 用例)

验证 CRC 错误、超时、Modbus 异常码的中文错误消息格式化。

### TestOnResponse (6 用例)

使用 pytest-qt 的 `qtbot` 验证 Signal 发射：

| 场景 | 信号 | 结果 |
|------|------|------|
| 错误响应 | operation_done(False, msg) | 通过 |
| 写入成功 | operation_done(True, msg) | 通过 |
| 读保持寄存器 | param_read(addr, val) | 通过 |
| 读输入寄存器 (正常) | status_updated(MotorStatus) | 通过 |
| 读输入寄存器 (故障) | status_updated (带报警) | 通过 |
| 数据不足 | 无信号 | 通过 |

---

## 覆盖率详情

| 文件 | 语句 | 未覆盖 | 覆盖率 |
|------|------|--------|--------|
| services/__init__.py | 0 | 0 | 100% |
| services/motor_service.py | 129 | 0 | 100% |
| **合计** | **129** | **0** | **100%** |

---

## 结论

服务层所有业务逻辑全部验证通过，覆盖率 100%。状态机解码、控制字映射、参数操作、错误处理均按设计文档实现。可以进入 UI 层开发。
