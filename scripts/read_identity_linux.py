"""读取设备身份信息与电流参数 (Linux, /dev/ttyUSB0)。

身份: 厂商名称(0x00) 产品序列号(0x02) 硬件版本(0x04) 软件版本(0x0A) 输入电压(0x17)
电流: 减速(0x15) 怠机(0x16) 加速/堵转(0x17) 运行(0x18) 单位 x10mA; 过载(0x19) 单位 x100mA

用法: python scripts/read_identity_linux.py [--port /dev/ttyUSB0]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from nimotion.communication.serial_port import SerialConfig, SerialPort
from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.models.types import FunctionCode, ModbusRequest

SLAVE_ID = 1
BAUDRATE = 115200


def transact(sp, mb, req):
    sp.flush_input()
    sp.write(mb.build_frame(req))
    time.sleep(0.02)
    return mb.parse_response(sp.read(mb.expected_response_length(req)), req)


def read_regs(sp, mb, func, addr, count):
    req = ModbusRequest(slave_id=SLAVE_ID, function_code=func, address=addr, count=count)
    r = transact(sp, mb, req)
    return None if r.is_error else r.values


def fmt_ident(vals):
    """32 位身份寄存器: 同时给出 hex / 十进制 / ASCII 尝试"""
    raw = (vals[0] << 16) | vals[1]
    chars = bytes([(raw >> s) & 0xFF for s in (24, 16, 8, 0)])
    ascii_try = "".join(chr(b) if 32 <= b < 127 else "." for b in chars)
    return f"0x{raw:08X}  ({raw})  ASCII:'{ascii_try}'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    args = ap.parse_args()

    sp = SerialPort()
    sp.open(SerialConfig(port=args.port, baudrate=BAUDRATE))
    mb = ModbusRTU()
    print(f"=== {args.port} @ {BAUDRATE} ===\n")

    print("-- 身份信息 (输入寄存器) --")
    for addr, name in [(0x0000, "厂商名称"), (0x0002, "产品序列号"),
                       (0x0004, "硬件版本号"), (0x000A, "软件版本号")]:
        v = read_regs(sp, mb, FunctionCode.READ_INPUT, addr, 2)
        print(f"{name} 0x{addr:04X} = {fmt_ident(v) if v else '读取失败'}")

    v = read_regs(sp, mb, FunctionCode.READ_INPUT, 0x0017, 1)
    print(f"输入电压 0x0017 = {v[0] if v else '读取失败'} V")

    print("\n-- 电流参数 (保持寄存器; 0x15~0x18 x10mA, 0x19 x100mA) --")
    for addr, name, scale in [(0x0015, "减速电流", 10), (0x0016, "怠机电流", 10),
                              (0x0017, "加速/堵转电流", 10), (0x0018, "运行电流", 10),
                              (0x0019, "过载电流", 100)]:
        v = read_regs(sp, mb, FunctionCode.READ_HOLDING, addr, 1)
        print(f"{name} 0x{addr:04X} = {v[0]} ({v[0]*scale} mA)" if v else f"{name} 0x{addr:04X} = 读取失败")

    sp.close()


if __name__ == "__main__":
    main()
