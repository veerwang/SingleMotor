"""读取 DI 输入状态，检查传感器是否触发。"""

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
    return resp


# 读取 0x0018 (数字量输入, 2 registers, INPUT)
req = ModbusRequest(
    slave_id=SLAVE_ID,
    function_code=FunctionCode.READ_INPUT,
    address=0x0018,
    count=2,
)
resp = transact(req)

if resp.is_error:
    print(f"读取失败: error={resp.error_code}")
else:
    high = resp.values[0]
    low = resp.values[1]
    combined = (high << 16) | low
    print(f"原始值: 0x{combined:08X} (high=0x{high:04X}, low=0x{low:04X})")
    print()
    # 高16位: DI输入值
    print("=== DI 输入原始值 ===")
    print(f"  DI1:  {(combined >> 16) & 1}  {'触发' if (combined >> 16) & 1 else '未触发'}")
    print(f"  DI2:  {(combined >> 17) & 1}  {'触发' if (combined >> 17) & 1 else '未触发'}")
    print(f"  DI3:  {(combined >> 18) & 1}  {'触发' if (combined >> 18) & 1 else '未触发'}")
    print(f"  DX1:  {(combined >> 19) & 1}  {'触发' if (combined >> 19) & 1 else '未触发'}")
    print(f"  DX2:  {(combined >> 20) & 1}  {'触发' if (combined >> 20) & 1 else '未触发'}")
    print()
    # 低16位: DI特殊功能值
    print("=== DI 特殊功能状态 ===")
    print(f"  负限位开关: {combined & 1}  {'触发' if combined & 1 else '未触发'}")
    print(f"  正限位开关: {(combined >> 1) & 1}  {'触发' if (combined >> 1) & 1 else '未触发'}")
    print(f"  原点开关:   {(combined >> 2) & 1}  {'触发' if (combined >> 2) & 1 else '未触发'}")

# 同时读取 DI1 功能配置 (0x002C)
req2 = ModbusRequest(
    slave_id=SLAVE_ID,
    function_code=FunctionCode.READ_HOLDING,
    address=0x002C,
    count=2,
)
resp2 = transact(req2)
if not resp2.is_error:
    di_func = (resp2.values[0] << 16) | resp2.values[1]
    di1_func = di_func & 0x0F
    func_names = {0: "无动作", 1: "负限位", 2: "正限位", 3: "原点开关",
                  4: "立即停机", 5: "减速停机", 6: "方向", 7: "使能", 8: "运行/停止"}
    print(f"\n=== DI1 功能配置 (0x002C) ===")
    print(f"  DI1 = {di1_func} ({func_names.get(di1_func, '未知')})")
    print(f"  完整值: 0x{di_func:08X}")

sp.close()
