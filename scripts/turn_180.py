"""转动 180 度（相对运动）"""

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
    return mb.parse_response(raw, req)


def write_reg(addr, value):
    req = ModbusRequest(slave_id=SLAVE_ID, function_code=FunctionCode.WRITE_SINGLE,
                        address=addr, values=[value & 0xFFFF])
    resp = transact(req)
    if resp.is_error:
        print(f"  写入 0x{addr:04X}={value} 失败: error={resp.error_code}")
    return not resp.is_error


def write_32bit(addr, value):
    high, low = ModbusRTU.split_32bit(value)
    req = ModbusRequest(slave_id=SLAVE_ID, function_code=FunctionCode.WRITE_MULTIPLE,
                        address=addr, count=2, values=[high, low])
    resp = transact(req)
    if resp.is_error:
        print(f"  写入 0x{addr:04X}={value} 失败: error={resp.error_code}")
    return not resp.is_error


def read_reg(addr, count=1):
    req = ModbusRequest(slave_id=SLAVE_ID, function_code=FunctionCode.READ_HOLDING,
                        address=addr, count=count)
    resp = transact(req)
    if resp.is_error:
        return None
    return resp.values


# 先读取细分值
vals = read_reg(0x001A, 1)
if vals:
    microstep = 2 ** vals[0]
    pulses_per_rev = 200 * microstep
    pulses_180 = pulses_per_rev // 2
    print(f"细分寄存器值={vals[0]}, 细分数={microstep}, 每圈={pulses_per_rev} pulses")
    print(f"180° = {pulses_180} pulses")
else:
    pulses_180 = 1600  # fallback: 细分16
    print(f"读取细分失败，使用默认值: 180° = {pulses_180} pulses")

print(f"\n正在转动 180° ({pulses_180} pulses)...")

# 相对运动
write_reg(0x0051, 0x0000)       # 停机
time.sleep(0.02)
write_reg(0x0039, 1)            # 位置模式
time.sleep(0.02)
write_32bit(0x0053, pulses_180) # 目标位置 (正向)
time.sleep(0.02)
write_reg(0x0051, 0x0006)       # 启动
time.sleep(0.02)
write_reg(0x0051, 0x0007)       # 使能
time.sleep(0.02)
write_reg(0x0051, 0x004F)       # 相对模式 + 运行
time.sleep(0.02)
write_reg(0x0051, 0x005F)       # 触发

print("命令已发送，电机转动中...")

sp.close()
