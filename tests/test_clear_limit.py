"""清除限位报警并将电机移离限位

用法:
    .venv/Scripts/python -m tests.test_clear_limit [--port COM6]
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


def write_single(port, modbus, slave_id, addr, value):
    req = ModbusRequest(
        slave_id=slave_id,
        function_code=FunctionCode.WRITE_SINGLE,
        address=addr,
        values=[value & 0xFFFF],
    )
    return send_and_receive(port, req, modbus)


def write_multiple(port, modbus, slave_id, addr, values):
    req = ModbusRequest(
        slave_id=slave_id,
        function_code=FunctionCode.WRITE_MULTIPLE,
        address=addr,
        count=len(values),
        values=values,
    )
    return send_and_receive(port, req, modbus)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", default=None)
    parser.add_argument("--slave-id", "-s", type=int, default=1)
    parser.add_argument("--baudrate", "-b", type=int, default=115200)
    parser.add_argument("--pulses", type=int, default=1000,
                        help="positive direction move pulses (default 1000)")
    args = parser.parse_args()

    available = SerialPort.list_ports()
    port_name = args.port
    if not port_name:
        if len(available) == 1:
            port_name = available[0]
        elif available:
            port_name = input(f"Port {available}: ").strip()
        else:
            print("No port!")
            return

    config = SerialConfig(port=port_name, baudrate=args.baudrate, timeout=0.5)
    port = SerialPort()
    modbus = ModbusRTU()
    sid = args.slave_id

    try:
        port.open(config)
        print(f"Connected: {port_name}\n")

        # Step 1: read current alarm
        print("=== Step 1: Read current alarm ===")
        ok, _, vals = read_input(port, modbus, sid, 0x0027, 1)
        if ok and vals:
            code = vals[0]
            desc = ERROR_CODES.get(code, f"unknown (0x{code:04X})")
            print(f"  Alarm: 0x{code:04X} - {desc}")
            if code == 0:
                print("  No alarm, exiting.")
                return

        # Step 2: read status word
        print("\n=== Step 2: Read status ===")
        ok, _, vals = read_input(port, modbus, sid, 0x001F, 1)
        if ok and vals:
            sw = vals[0]
            print(f"  Status: 0x{sw:04X}, Fault={bool(sw & (1<<3))}")

        # Step 3: clear fault
        print("\n=== Step 3: Clear fault (0x0080) ===")
        write_single(port, modbus, sid, 0x0051, 0x0080)
        time.sleep(0.1)

        # Step 4: disable (back to switch on disabled)
        print("\n=== Step 4: Disable (0x0000) ===")
        write_single(port, modbus, sid, 0x0051, 0x0000)
        time.sleep(0.05)

        # Check alarm cleared
        ok, _, vals = read_input(port, modbus, sid, 0x0027, 1)
        if ok and vals:
            code = vals[0]
            desc = ERROR_CODES.get(code, f"unknown (0x{code:04X})")
            print(f"  Alarm after clear: 0x{code:04X} - {desc}")
            if code != 0:
                print("  Alarm not cleared! May need to move off limit first.")

        # Step 5: move positive direction to get off limit
        pulses = args.pulses
        print(f"\n=== Step 5: Move +{pulses} pulses (away from neg limit) ===")

        # Set position mode
        write_single(port, modbus, sid, 0x0039, 1)
        time.sleep(0.02)

        # Set target position
        high, low = ModbusRTU.split_32bit(pulses)
        write_multiple(port, modbus, sid, 0x0053, [high, low])
        time.sleep(0.02)

        # Startup -> Enable -> Run (relative move)
        write_single(port, modbus, sid, 0x0051, 0x0006)
        time.sleep(0.02)
        write_single(port, modbus, sid, 0x0051, 0x0007)
        time.sleep(0.02)
        write_single(port, modbus, sid, 0x0051, 0x004F)  # relative + run
        time.sleep(0.02)
        write_single(port, modbus, sid, 0x0051, 0x005F)  # trigger new setpoint
        print("  Move command sent, waiting...")

        # Wait for move to complete
        for i in range(30):
            time.sleep(0.2)
            ok, _, vals = read_input(port, modbus, sid, 0x001F, 1)
            if ok and vals:
                sw = vals[0]
                running = bool(sw & (1 << 12))
                fault = bool(sw & (1 << 3))
                if fault:
                    # read alarm
                    ok2, _, vals2 = read_input(port, modbus, sid, 0x0027, 1)
                    acode = vals2[0] if ok2 and vals2 else 0
                    adesc = ERROR_CODES.get(acode, f"0x{acode:04X}")
                    print(f"  Fault during move! Alarm: {adesc}")
                    break
                if not running:
                    print(f"  Move completed at {(i+1)*0.2:.1f}s")
                    break
        else:
            print("  Timeout waiting for move")

        # Final status check
        print("\n=== Final Status ===")
        ok, _, vals = read_input(port, modbus, sid, 0x0027, 1)
        if ok and vals:
            code = vals[0]
            desc = ERROR_CODES.get(code, f"unknown (0x{code:04X})")
            print(f"  Alarm: 0x{code:04X} - {desc if code else 'None'}")

        ok, _, vals = read_input(port, modbus, sid, 0x0021, 2)
        if ok and len(vals) >= 2:
            pos = ModbusRTU.combine_32bit(vals[0], vals[1], signed=True)
            print(f"  Position: {pos} pulse")

        ok, _, vals = read_input(port, modbus, sid, 0x0018, 2)
        if ok and len(vals) >= 2:
            di = ModbusRTU.combine_32bit(vals[0], vals[1])
            di1 = "HIGH" if di & 1 else "LOW"
            di2 = "HIGH" if di & 2 else "LOW"
            print(f"  DI1={di1}, DI2={di2} (limit switches)")

    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        port.close()
        print("\nPort closed")


if __name__ == "__main__":
    main()
