"""回零 + 依次移动到 hole 2/3/4/1，每个位置停留 3 秒"""

import sys
import time
sys.path.insert(0, "E:/SingleMotor/src")

from nimotion.communication.serial_port import SerialConfig, SerialPort
from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.models.types import FunctionCode, ModbusRequest

PORT = "COM6"
SLAVE_ID = 1
BAUDRATE = 115200

# 转盘参数: microstep=16, gear_ratio=2.75, 4 holes
PULSES_PER_HOLE = 2200  # 200*16*2.75/4 = 2200

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


def read_input_regs(addr, count):
    req = ModbusRequest(slave_id=SLAVE_ID, function_code=FunctionCode.READ_INPUT,
                        address=addr, count=count)
    resp = transact(req)
    if resp.is_error:
        return None
    return resp.values


def read_reg(addr, count=1):
    req = ModbusRequest(slave_id=SLAVE_ID, function_code=FunctionCode.READ_HOLDING,
                        address=addr, count=count)
    resp = transact(req)
    if resp.is_error:
        return None
    return resp.values


def get_status():
    """读取状态字(0x1F)、速度(0x23-0x24)、位置(0x21-0x22)"""
    vals = read_input_regs(0x0017, 16)
    if not vals or len(vals) < 16:
        return None, None, None, None
    status_word = vals[8]   # 0x1F
    is_running = bool(status_word & (1 << 12))
    position = ModbusRTU.combine_32bit(vals[10], vals[11], signed=True)  # 0x21-0x22
    raw_speed = ModbusRTU.combine_32bit(vals[12], vals[13])  # 0x23-0x24
    speed = raw_speed // 10
    return is_running, speed, position, status_word


def wait_motion_done(timeout=30):
    """等待运动完成（is_running=False, speed=0）"""
    start = time.time()
    # 先等一下让电机开始运动
    time.sleep(0.3)
    while time.time() - start < timeout:
        is_running, speed, position, sw = get_status()
        if is_running is not None:
            if not is_running and speed == 0:
                return True, position
        time.sleep(0.2)
    return False, None


# ============================================================
# Step 0: 设置速度和加速度参数
# ============================================================
print("=== 设置运动参数 ===")
write_reg(0x0051, 0x0000)  # 停机
time.sleep(0.05)
write_32bit(0x005F, 600)   # 加速度 600 Step/s²
write_32bit(0x0061, 600)   # 减速度 600 Step/s²
write_32bit(0x005B, 60)    # 最大速度 60 Step/s
write_reg(0x0008, 0x7376)  # 保存 EEPROM
print("  speed=60 Step/s, accel=600, decel=600")

# ============================================================
# Step 1: 读取并设置 DI1 = neg_limit(1) for homing
# ============================================================
print("\n=== 回零准备 ===")
di_vals = read_reg(0x002C, 2)
if di_vals:
    original_di = (di_vals[0] << 16) | di_vals[1]
    di1_func = original_di & 0x0F
    print(f"  当前 DI 配置: 0x{original_di:08X}, DI1={di1_func}")
else:
    original_di = 0
    print("  读取 DI 配置失败，假设 DI1=0")

# 设置 DI1=neg_limit(1)
new_di = (original_di & ~0x0F) | 1
write_32bit(0x002C, new_di)
print(f"  DI1 已设置为 neg_limit(1)")

# 设置回零参数
write_reg(0x006B, 17)           # method 17: 负限位开关回归
write_32bit(0x0069, 0)          # 原点偏移 = 0
write_32bit(0x006C, 50)         # 寻找开关速度 50 Step/s
write_32bit(0x006E, 20)         # 寻找零位速度 20 Step/s
write_reg(0x0072, 0)            # 零点回归禁用
write_reg(0x0008, 0x7376)       # 保存 EEPROM
print("  回零参数已写入: method=17, offset=0, search=50, zero=20")

# ============================================================
# Step 2: 执行回零
# ============================================================
print("\n=== 开始回零 ===")
write_reg(0x0039, 3)            # 原点回归模式
time.sleep(0.02)
write_reg(0x0051, 0x0006)       # 启动
time.sleep(0.02)
write_reg(0x0051, 0x0007)       # 使能
time.sleep(0.02)
write_reg(0x0051, 0x000F)       # 运行
time.sleep(0.02)
write_reg(0x0051, 0x001F)       # 触发
print("  回零命令已发送，等待完成...")

ok, pos = wait_motion_done(timeout=30)
if ok:
    print(f"  回零完成! 位置={pos}")
else:
    print("  回零超时!")
    # 恢复 DI1
    restore_di = (original_di & ~0x0F) | 0
    write_32bit(0x002C, restore_di)
    sp.close()
    sys.exit(1)

# ============================================================
# Step 3: 恢复 DI1 = no_action(0)
# ============================================================
write_reg(0x0051, 0x0000)       # 先停机，避免 error=6
time.sleep(0.1)
restore_di = (original_di & ~0x0F) | 0
write_32bit(0x002C, restore_di)
write_reg(0x0008, 0x7376)       # 保存 EEPROM
time.sleep(0.05)
# 验证 DI1 已恢复
di_check = read_reg(0x002C, 2)
if di_check:
    check_val = (di_check[0] << 16) | di_check[1]
    print(f"  DI1 已恢复, DI配置=0x{check_val:08X}, DI1={check_val & 0x0F}")
else:
    print("  DI1 恢复验证失败")

# ============================================================
# Step 4: 依次移动到 hole 2, 3, 4, 1
# ============================================================
holes = [
    ("Hole 2", PULSES_PER_HOLE * 1),   # 1100
    ("Hole 3", PULSES_PER_HOLE * 2),   # 2200
    ("Hole 4", PULSES_PER_HOLE * 3),   # 3300
    ("Hole 1", 0),                      # 回到原点
]

for name, target in holes:
    print(f"\n=== 移动到 {name} (abs={target}) ===")
    t0 = time.time()
    write_reg(0x0051, 0x0000)       # 停机
    time.sleep(0.02)
    write_reg(0x0039, 1)            # 位置模式
    time.sleep(0.02)
    write_32bit(0x0053, target)     # 目标位置 (绝对)
    time.sleep(0.02)
    write_reg(0x0051, 0x0006)       # 启动
    time.sleep(0.02)
    write_reg(0x0051, 0x0007)       # 使能
    time.sleep(0.02)
    write_reg(0x0051, 0x000F)       # 绝对模式 + 运行
    time.sleep(0.02)
    write_reg(0x0051, 0x001F)       # 触发

    ok, pos = wait_motion_done(timeout=15)
    elapsed = time.time() - t0
    if ok:
        print(f"  到达 {name}! 位置={pos}, 耗时={elapsed:.2f}s")
    else:
        print(f"  移动超时! 耗时={elapsed:.2f}s")

    print(f"  停留 3 秒...")
    time.sleep(3)

print("\n=== 全部完成 ===")
sp.close()
