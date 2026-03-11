"""读取电机报警信息诊断脚本

用法:
    .venv/Scripts/python -m tests.test_alarm [--port COM6]
"""

from __future__ import annotations

import argparse
import time

from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.communication.serial_port import SerialConfig, SerialPort
from nimotion.models.error_codes import ERROR_CODES
from nimotion.models.types import FunctionCode, ModbusRequest


def hex_str(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def send_and_receive(port, request, modbus):
    frame = modbus.build_frame(request)
    port.flush_input()
    port.write(frame)
    time.sleep(0.01)
    expected_len = modbus.expected_response_length(request)
    raw = port.read(expected_len)
    print(f"  TX: {hex_str(frame)}")
    print(f"  RX: {hex_str(raw)}")
    if len(raw) == 0:
        return False, "timeout", []
    resp = modbus.parse_response(raw, request)
    resp.raw_tx = frame
    if resp.is_error:
        return False, f"error {resp.error_code}", []
    return True, "OK", resp.values


def read_input(port, modbus, slave_id, addr, count=1):
    req = ModbusRequest(
        slave_id=slave_id,
        function_code=FunctionCode.READ_INPUT,
        address=addr,
        count=count,
    )
    return send_and_receive(port, req, modbus)


def read_holding(port, modbus, slave_id, addr, count=1):
    req = ModbusRequest(
        slave_id=slave_id,
        function_code=FunctionCode.READ_HOLDING,
        address=addr,
        count=count,
    )
    return send_and_receive(port, req, modbus)


def write_single(port, modbus, slave_id, addr, value):
    req = ModbusRequest(
        slave_id=slave_id,
        function_code=FunctionCode.WRITE_SINGLE,
        address=addr,
        values=[value & 0xFFFF],
    )
    return send_and_receive(port, req, modbus)


def decode_alarm(code):
    if code == 0:
        return "无报警"
    return ERROR_CODES.get(code, f"未知报警 (0x{code:04X})")


def decode_status_word(sw):
    """解析状态字各 bit"""
    bits = [
        (0, "Ready to switch on"),
        (1, "Switched on"),
        (2, "Operation enabled"),
        (3, "Fault"),
        (4, "Voltage enabled"),
        (5, "Quick stop"),
        (6, "Switch on disabled"),
        (7, "Warning"),
        (9, "Remote"),
        (10, "Target reached"),
        (12, "Running"),
    ]
    active = []
    for bit, name in bits:
        if sw & (1 << bit):
            active.append(f"  bit{bit:2d} = 1  {name}")
    return active


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", default=None)
    parser.add_argument("--slave-id", "-s", type=int, default=1)
    parser.add_argument("--baudrate", "-b", type=int, default=115200)
    args = parser.parse_args()

    available = SerialPort.list_ports()
    print(f"Available: {available}")

    port_name = args.port
    if not port_name:
        if len(available) == 1:
            port_name = available[0]
        elif available:
            port_name = input(f"Port {available}: ").strip()
        else:
            print("No port found!")
            return

    config = SerialConfig(port=port_name, baudrate=args.baudrate, timeout=0.5)
    port = SerialPort()
    modbus = ModbusRTU()
    slave_id = args.slave_id

    try:
        port.open(config)
        print(f"Connected: {port_name}\n")

        # 1. 读取状态字 (输入寄存器 0x001F)
        print("=" * 50)
        print("1. Status Word (Input 0x001F)")
        print("=" * 50)
        ok, msg, vals = read_input(port, modbus, slave_id, 0x001F, 1)
        if ok and vals:
            sw = vals[0]
            print(f"  Status Word: 0x{sw:04X} ({sw})")
            is_fault = bool(sw & (1 << 3))
            print(f"  Fault bit: {'YES' if is_fault else 'NO'}")
            for line in decode_status_word(sw):
                print(line)
        else:
            print(f"  Failed: {msg}")

        # 2. 读取当前报警码 (输入寄存器 0x0027)
        print(f"\n{'=' * 50}")
        print("2. Current Alarm (Input 0x0027)")
        print("=" * 50)
        ok, msg, vals = read_input(port, modbus, slave_id, 0x0027, 1)
        if ok and vals:
            code = vals[0]
            print(f"  Alarm Code: 0x{code:04X}")
            print(f"  Description: {decode_alarm(code)}")
        else:
            print(f"  Failed: {msg}")

        # 3. 读取电压 (输入寄存器 0x0017)
        print(f"\n{'=' * 50}")
        print("3. Voltage (Input 0x0017)")
        print("=" * 50)
        ok, msg, vals = read_input(port, modbus, slave_id, 0x0017, 1)
        if ok and vals:
            print(f"  Voltage: {vals[0] / 10:.1f} V")
        else:
            print(f"  Failed: {msg}")

        # 4. 读取 DI 状态 (输入寄存器 0x0018, 2 regs = 32bit)
        print(f"\n{'=' * 50}")
        print("4. DI Status (Input 0x0018-0x0019)")
        print("=" * 50)
        ok, msg, vals = read_input(port, modbus, slave_id, 0x0018, 2)
        if ok and len(vals) >= 2:
            di_val = ModbusRTU.combine_32bit(vals[0], vals[1])
            print(f"  DI raw: 0x{di_val:08X}")
            # 逐 bit 解析常见 DI
            di_names = {0: "DI1", 1: "DI2", 2: "DI3", 3: "DI4"}
            for bit, name in di_names.items():
                state = "HIGH" if di_val & (1 << bit) else "LOW"
                print(f"  {name}: {state}")
        else:
            print(f"  Failed: {msg}")

        # 5. 读取历史报警个数 (保持寄存器 0x0027)
        print(f"\n{'=' * 50}")
        print("5. Alarm History (Holding 0x0027, then 0x0028~0x002F)")
        print("=" * 50)
        ok, msg, vals = read_holding(port, modbus, slave_id, 0x0027, 1)
        if ok and vals:
            count = vals[0]
            print(f"  History count: {count}")
            if count > 0:
                max_read = min(count, 8)
                ok2, msg2, vals2 = read_holding(
                    port, modbus, slave_id, 0x0028, max_read
                )
                if ok2:
                    for i, v in enumerate(vals2):
                        print(f"  [{i+1}] 0x{v:04X} - {decode_alarm(v)}")
                else:
                    print(f"  Read history failed: {msg2}")
        else:
            print(f"  Failed: {msg}")

        # 6. 读取控制字当前值 (保持寄存器 0x0051)
        print(f"\n{'=' * 50}")
        print("6. Control Word (Holding 0x0051)")
        print("=" * 50)
        ok, msg, vals = read_holding(port, modbus, slave_id, 0x0051, 1)
        if ok and vals:
            print(f"  Control Word: 0x{vals[0]:04X}")
        else:
            print(f"  Failed: {msg}")

        # 7. 读取运行模式 (输入寄存器 0x001E)
        print(f"\n{'=' * 50}")
        print("7. Current Mode (Input 0x001E)")
        print("=" * 50)
        ok, msg, vals = read_input(port, modbus, slave_id, 0x001E, 1)
        if ok and vals:
            mode_names = {1: "Position", 2: "Speed", 3: "Homing", 4: "Pulse"}
            mode = vals[0]
            print(f"  Mode: {mode} ({mode_names.get(mode, 'Unknown')})")
        else:
            print(f"  Failed: {msg}")

        # 8. 尝试清除故障
        print(f"\n{'=' * 50}")
        print("8. Try Clear Fault (0x0051 = 0x0080)")
        print("=" * 50)
        ok_c, msg_c, _ = write_single(port, modbus, slave_id, 0x0051, 0x0080)
        print(f"  Result: {msg_c}")
        time.sleep(0.05)

        # 再次读取状态
        ok2, _, vals2 = read_input(port, modbus, slave_id, 0x001F, 1)
        if ok2 and vals2:
            sw2 = vals2[0]
            is_fault2 = bool(sw2 & (1 << 3))
            print(f"  After clear - Status: 0x{sw2:04X}, Fault: {'YES' if is_fault2 else 'NO'}")

        ok3, _, vals3 = read_input(port, modbus, slave_id, 0x0027, 1)
        if ok3 and vals3:
            print(f"  After clear - Alarm: 0x{vals3[0]:04X} ({decode_alarm(vals3[0])})")

    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        port.close()
        print(f"\nPort closed")


if __name__ == "__main__":
    main()
