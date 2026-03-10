"""配置原点偏移和零点回归，解决回零后超负限位报警问题。"""

import sys
import time
sys.path.insert(0, "E:/SingleMotor/src")

from nimotion.communication.serial_port import SerialConfig, SerialPort
from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.models.types import FunctionCode, ModbusRequest

PORT = "COM6"
SLAVE_ID = 1
BAUDRATE = 115200

sp = SerialPort()
sp.open(SerialConfig(port=PORT, baudrate=BAUDRATE))
mb = ModbusRTU()


def transact(req):
    frame = mb.build_frame(req)
    sp.flush_input()
    sp.write(frame)
    time.sleep(0.02)
    expected = mb.expected_response_length(req)
    raw = sp.read(expected)
    resp = mb.parse_response(raw, req)
    resp.raw_tx = frame
    return resp


def read_reg(addr, count=1):
    req = ModbusRequest(slave_id=SLAVE_ID, function_code=FunctionCode.READ_HOLDING,
                        address=addr, count=count)
    resp = transact(req)
    if resp.is_error:
        print(f"  读取 0x{addr:04X} 失败: error={resp.error_code}")
        return None
    return resp.values


def write_reg(addr, value):
    req = ModbusRequest(slave_id=SLAVE_ID, function_code=FunctionCode.WRITE_SINGLE,
                        address=addr, values=[value & 0xFFFF])
    resp = transact(req)
    if resp.is_error:
        print(f"  写入 0x{addr:04X}={value} 失败: error={resp.error_code}")
        return False
    print(f"  写入 0x{addr:04X} = {value} 成功")
    return True


def write_32bit(addr, value):
    high, low = ModbusRTU.split_32bit(value)
    req = ModbusRequest(slave_id=SLAVE_ID, function_code=FunctionCode.WRITE_MULTIPLE,
                        address=addr, count=2, values=[high, low])
    resp = transact(req)
    if resp.is_error:
        print(f"  写入 0x{addr:04X}={value} (32bit) 失败: error={resp.error_code}")
        return False
    print(f"  写入 0x{addr:04X} = {value} (32bit) 成功")
    return True


print("=== 配置原点偏移和零点回归 ===\n")

# 先停机
print("[1] 停机...")
write_reg(0x0051, 0x0000)
time.sleep(0.1)

# 读取当前值
print("\n[2] 读取当前配置...")
vals = read_reg(0x0069, 2)  # 原点偏移 (32bit)
if vals:
    current_offset = ModbusRTU.combine_32bit(vals[0], vals[1], signed=True)
    print(f"  原点偏移 (0x0069) = {current_offset}")

vals = read_reg(0x0072, 1)  # 零点回归
if vals:
    print(f"  零点回归 (0x0072) = {vals[0]}")

vals = read_reg(0x006B, 1)  # 回归方式
if vals:
    print(f"  回归方式 (0x006B) = {vals[0]}")

vals = read_reg(0x002C, 1)  # DI1功能
if vals:
    print(f"  DI1功能 (0x002C) = {vals[0]}")

# 写入新配置
print("\n[3] 写入新配置...")
write_32bit(0x0069, 500)  # 原点偏移 = 500 脉冲
time.sleep(0.05)
write_reg(0x0072, 1)       # 零点回归 = 启用
time.sleep(0.05)

# 回读验证
print("\n[4] 回读验证...")
vals = read_reg(0x0069, 2)
if vals:
    new_offset = ModbusRTU.combine_32bit(vals[0], vals[1], signed=True)
    print(f"  原点偏移 = {new_offset} (期望: 500)")

vals = read_reg(0x0072, 1)
if vals:
    print(f"  零点回归 = {vals[0]} (期望: 1)")

# 保存到 EEPROM
print("\n[5] 保存到 EEPROM...")
write_reg(0x0008, 0x7376)
time.sleep(0.5)

print("\n=== 配置完成 ===")
print("现在可以打开 UI 测试原点回归，回归完成后电机应自动移离限位 500 脉冲。")

sp.close()
