"""测试细分寄存器 (0x001A) 写入回读

用法:
    .venv/Scripts/python -m tests.test_subdivision [--port COM3]
"""

from __future__ import annotations

import argparse
import time

from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.communication.serial_port import SerialConfig, SerialPort
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
        return False, "超时无响应", []
    resp = modbus.parse_response(raw, request)
    resp.raw_tx = frame
    if resp.is_error:
        return False, f"错误码 {resp.error_code}", []
    return True, "OK", resp.values


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", default=None)
    parser.add_argument("--slave-id", "-s", type=int, default=1)
    parser.add_argument("--baudrate", "-b", type=int, default=115200)
    args = parser.parse_args()

    available = SerialPort.list_ports()
    print(f"可用串口: {available}")

    port_name = args.port
    if not port_name:
        if len(available) == 1:
            port_name = available[0]
        elif available:
            port_name = input(f"请输入串口号 {available}: ").strip()
        else:
            print("未检测到串口！")
            return

    config = SerialConfig(port=port_name, baudrate=args.baudrate, timeout=0.5)
    port = SerialPort()
    modbus = ModbusRTU()
    slave_id = args.slave_id

    try:
        port.open(config)
        print(f"串口已连接: {port_name}\n")

        # 步骤1: 读取当前细分值
        print("=== 步骤1: 读取当前细分值 (0x001A) ===")
        ok, msg, vals = read_holding(port, modbus, slave_id, 0x001A, 1)
        if not ok:
            print(f"  读取失败: {msg}")
            return
        original = vals[0]
        print(f"  当前细分值: {original}")

        # 步骤2: 先脱机（细分参数要求脱机状态才能写入）
        new_val = 4 if original != 4 else 3
        print(f"\n=== 步骤2: 脱机 (控制字=0x0000) ===")
        ok_d, msg_d, _ = write_single(port, modbus, slave_id, 0x0051, 0x0000)
        print(f"  脱机结果: {msg_d}")
        time.sleep(0.05)

        # 步骤3: 写入新值
        print(f"\n=== 步骤3: 写入细分值 = {new_val} ===")
        ok_w, msg_w, vals_w = write_single(port, modbus, slave_id, 0x001A, new_val)
        print(f"  写入结果: {msg_w}")
        if vals_w:
            print(f"  写响应值: {vals_w}")

        time.sleep(0.05)

        # 步骤4: 回读验证
        print(f"\n=== 步骤4: 回读细分值 ===")
        ok_r, msg_r, vals_r = read_holding(port, modbus, slave_id, 0x001A, 1)
        if not ok_r:
            print(f"  回读失败: {msg_r}")
            return
        readback = vals_r[0]
        print(f"  回读值: {readback}")

        if readback == new_val:
            print(f"\n  [OK] 写入成功！{original} → {new_val}")
        else:
            print(f"\n  [FAIL] 写入未生效！写入 {new_val}，回读 {readback}")
            print(f"    可能原因: 细分参数需要保存 EEPROM 并重启才能生效")

        # 步骤5: 尝试保存 EEPROM 后再读
        print(f"\n=== 步骤5: 保存到 EEPROM (0x0008 = 0x7376) ===")
        ok_s, msg_s, _ = write_single(port, modbus, slave_id, 0x0008, 0x7376)
        print(f"  保存结果: {msg_s}")
        time.sleep(0.1)

        print(f"\n=== 步骤6: 保存后再次回读 ===")
        ok_r2, msg_r2, vals_r2 = read_holding(port, modbus, slave_id, 0x001A, 1)
        if ok_r2:
            readback2 = vals_r2[0]
            print(f"  回读值: {readback2}")
            if readback2 == new_val:
                print(f"  [OK] 保存 EEPROM 后生效！")
            else:
                print(f"  [FAIL] 保存后仍未生效（回读 {readback2}）")

        # 步骤7: 恢复原值
        print(f"\n=== 步骤6: 恢复原值 = {original} ===")
        write_single(port, modbus, slave_id, 0x001A, original)
        time.sleep(0.05)
        write_single(port, modbus, slave_id, 0x0008, 0x7376)  # 保存
        print("  已恢复")

    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        port.close()
        print("\n串口已关闭")


if __name__ == "__main__":
    main()
