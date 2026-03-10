"""
端到端测试脚本 — 连接真实硬件逐项验证。

使用方法:
    python -m tests.test_e2e [--port COM3] [--slave-id 1] [--baudrate 115200]

每个测试步骤会打印结果，遇到失败会提示是否继续。
"""

from __future__ import annotations

import argparse
import struct
import sys
import time

# 直接使用底层串口 + Modbus 协议，不依赖 Qt 事件循环
sys.path.insert(0, "src")

from nimotion.communication.crc16 import append as crc_append, verify as crc_verify
from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.communication.serial_port import SerialConfig, SerialPort
from nimotion.models.error_codes import get_error_text, get_exception_text
from nimotion.models.turret import (
    microstep_from_register,
    calculate_pulses_per_position,
)
from nimotion.models.types import FunctionCode, ModbusRequest


# ── 辅助 ──────────────────────────────────────────────────────

def hex_str(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def send_and_receive(
    port: SerialPort,
    request: ModbusRequest,
    modbus: ModbusRTU,
    timeout: float = 0.5,
) -> tuple[bool, str, list[int]]:
    """发送请求并接收响应，返回 (成功, 描述, 寄存器值列表)"""
    frame = modbus.build_frame(request)
    port.flush_input()
    port.write(frame)
    time.sleep(0.01)

    expected_len = modbus.expected_response_length(request)
    raw = port.read(expected_len)

    print(f"  TX: {hex_str(frame)}")
    print(f"  RX: {hex_str(raw)}" if raw else "  RX: (无响应)")

    if len(raw) == 0:
        return False, "通讯超时，未收到响应", []

    resp = modbus.parse_response(raw, request)
    resp.raw_tx = frame

    if resp.is_error:
        if resp.error_code == -1:
            return False, "CRC 校验失败", []
        if resp.error_code == -3:
            return False, "响应帧不完整", []
        return False, f"Modbus 异常: {get_exception_text(resp.error_code)}", []

    return True, "OK", resp.values


def read_holding(port, modbus, slave_id, addr, count=1):
    req = ModbusRequest(
        slave_id=slave_id,
        function_code=FunctionCode.READ_HOLDING,
        address=addr,
        count=count,
    )
    return send_and_receive(port, req, modbus)


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


# ── 测试项 ────────────────────────────────────────────────────

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.details: list[tuple[str, str, str]] = []  # (名称, 状态, 描述)

    def record(self, name: str, ok: bool, desc: str) -> None:
        status = "PASS" if ok else "FAIL"
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        self.details.append((name, status, desc))

    def skip(self, name: str, reason: str) -> None:
        self.skipped += 1
        self.details.append((name, "SKIP", reason))

    def summary(self) -> None:
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        for name, status, desc in self.details:
            mark = {"PASS": "[OK]", "FAIL": "[!!]", "SKIP": "[--]"}[status]
            print(f"  {mark} {name}: {desc}")
        print("-" * 60)
        total = self.passed + self.failed + self.skipped
        print(f"  总计: {total}  通过: {self.passed}  失败: {self.failed}  跳过: {self.skipped}")
        print("=" * 60)


def test_01_serial_connect(port: SerialPort, config: SerialConfig, result: TestResult):
    """测试 1: 串口连接"""
    name = "01-串口连接"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")
    print(f"  端口: {config.port}, 波特率: {config.baudrate}")
    try:
        port.open(config)
        ok = port.is_open
        result.record(name, ok, f"串口已打开" if ok else "串口打开失败")
    except Exception as e:
        result.record(name, False, str(e))
        return False
    return True


def test_02_read_device_info(port, modbus, slave_id, result: TestResult):
    """测试 2: 读取设备信息（输入寄存器）"""
    name = "02-读取设备信息"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")

    # 读取厂商名称 (0x0000, 2 reg)
    ok, msg, vals = read_input(port, modbus, slave_id, 0x0000, 2)
    if ok and len(vals) >= 2:
        vendor = ModbusRTU.combine_32bit(vals[0], vals[1])
        print(f"  厂商代码: 0x{vendor:08X}")
    else:
        print(f"  厂商名称读取失败: {msg}")

    # 读取产品序列号 (0x0002, 2 reg)
    ok2, msg2, vals2 = read_input(port, modbus, slave_id, 0x0002, 2)
    if ok2 and len(vals2) >= 2:
        sn = ModbusRTU.combine_32bit(vals2[0], vals2[1])
        print(f"  产品序列号: {sn}")

    # 读取软件版本 (0x000A, 2 reg)
    ok3, msg3, vals3 = read_input(port, modbus, slave_id, 0x000A, 2)
    if ok3 and len(vals3) >= 2:
        ver = ModbusRTU.combine_32bit(vals3[0], vals3[1])
        print(f"  软件版本: {ver}")

    # 读取工作时间 (0x000C, 2 reg)
    ok4, msg4, vals4 = read_input(port, modbus, slave_id, 0x000C, 2)
    if ok4 and len(vals4) >= 2:
        hours = ModbusRTU.combine_32bit(vals4[0], vals4[1])
        print(f"  累计工作时间: {hours} h")

    overall = ok and ok2
    result.record(name, overall, "设备信息读取成功" if overall else "部分信息读取失败")
    return overall


def test_03_read_status(port, modbus, slave_id, result: TestResult):
    """测试 3: 批量读取电机状态（输入寄存器 0x17~0x26）"""
    name = "03-读取电机状态"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")

    ok, msg, vals = read_input(port, modbus, slave_id, 0x0017, 16)
    if not ok:
        result.record(name, False, msg)
        return False

    if len(vals) < 16:
        result.record(name, False, f"返回寄存器数量不足: {len(vals)}")
        return False

    voltage = vals[0]
    mode_val = vals[7]
    status_word = vals[8]
    direction = vals[9]
    position = ModbusRTU.combine_32bit(vals[10], vals[11], signed=True)
    speed_raw = ModbusRTU.combine_32bit(vals[12], vals[13])
    alarm = vals[15]

    mode_names = {1: "位置模式", 2: "速度模式", 3: "原点回归", 4: "脉冲输入"}

    print(f"  输入电压: {voltage} V")
    print(f"  当前模式: {mode_names.get(mode_val, f'未知({mode_val})')}")
    print(f"  状态字:   0x{status_word:04X}")
    print(f"  运动方向: {'正转' if direction else '反转'}")
    print(f"  当前位置: {position} pulse")
    print(f"  当前速度: {speed_raw // 10} Step/s")
    print(f"  报警码:   0x{alarm:04X} {'(' + get_error_text(alarm) + ')' if alarm else '(无报警)'}")

    result.record(name, True, f"电压={voltage}V, 状态字=0x{status_word:04X}, 位置={position}")
    return True


def test_04_read_params(port, modbus, slave_id, result: TestResult):
    """测试 4: 读取关键保持寄存器参数"""
    name = "04-读取运动参数"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")

    params = [
        (0x0000, 1, "从站地址"),
        (0x0001, 1, "波特率"),
        (0x001A, 1, "细分"),
        (0x0039, 1, "运行模式"),
        (0x0055, 2, "目标速度"),
        (0x005B, 2, "最大速度"),
        (0x005F, 2, "加速度"),
        (0x0061, 2, "减速度"),
    ]

    all_ok = True
    for addr, count, label in params:
        ok, msg, vals = read_holding(port, modbus, slave_id, addr, count)
        if ok:
            if count == 2 and len(vals) >= 2:
                val = ModbusRTU.combine_32bit(vals[0], vals[1])
            elif vals:
                val = vals[0]
            else:
                val = "N/A"
            # 细分特殊显示
            if addr == 0x001A and isinstance(val, int):
                microstep = microstep_from_register(val)
                print(f"  {label} (0x{addr:04X}): reg={val} → 1:{microstep}")
            else:
                print(f"  {label} (0x{addr:04X}): {val}")
        else:
            print(f"  {label} (0x{addr:04X}): 失败 - {msg}")
            all_ok = False

    result.record(name, all_ok, "全部参数读取成功" if all_ok else "部分参数读取失败")
    return all_ok


def test_05_write_read_back(port, modbus, slave_id, result: TestResult):
    """测试 5: 写入参数并回读验证（使用运行模式寄存器）"""
    name = "05-写入回读验证"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")

    # 先停止电机（使能状态下不允许修改运行模式）
    write_single(port, modbus, slave_id, 0x0051, 0x0000)
    time.sleep(0.05)

    # 先读当前运行模式
    ok, msg, vals = read_holding(port, modbus, slave_id, 0x0039, 1)
    if not ok:
        result.record(name, False, f"读取失败: {msg}")
        return False

    original = vals[0] if vals else 1
    print(f"  当前运行模式: {original}")

    # 写入一个不同的值（位置=1, 速度=2），然后恢复
    test_val = 2 if original != 2 else 1
    ok_w, msg_w, _ = write_single(port, modbus, slave_id, 0x0039, test_val)
    if not ok_w:
        result.record(name, False, f"写入失败: {msg_w}")
        return False
    print(f"  写入运行模式: {test_val}")

    time.sleep(0.05)

    # 回读验证
    ok_r, msg_r, vals_r = read_holding(port, modbus, slave_id, 0x0039, 1)
    if not ok_r:
        result.record(name, False, f"回读失败: {msg_r}")
        return False

    readback = vals_r[0] if vals_r else -1
    print(f"  回读运行模式: {readback}")

    match = readback == test_val
    print(f"  写入回读{'一致' if match else '不一致!'}")

    # 恢复原值
    write_single(port, modbus, slave_id, 0x0039, original)
    print(f"  已恢复原运行模式: {original}")

    result.record(name, match, "写入回读一致" if match else f"不一致: 写{test_val} 读{readback}")
    return match


def test_06_state_machine(port, modbus, slave_id, result: TestResult):
    """测试 6: 状态机切换（无故障 → 启动 → 使能 → 回到无故障）"""
    name = "06-状态机切换"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")

    def read_status_word():
        ok, _, vals = read_input(port, modbus, slave_id, 0x001F, 1)
        return vals[0] if ok and vals else None

    steps = [
        ("初始状态", None, None),
        ("发送启动(0x06)", 0x0051, 0x0006),
        ("发送使能(0x07)", 0x0051, 0x0007),
        ("发送停止(0x00)", 0x0051, 0x0000),
    ]

    all_ok = True
    for step_name, addr, value in steps:
        if addr is not None:
            ok, msg, _ = write_single(port, modbus, slave_id, addr, value)
            if not ok:
                print(f"  {step_name}: 写入失败 - {msg}")
                all_ok = False
                continue
            time.sleep(0.05)

        sw = read_status_word()
        if sw is not None:
            print(f"  {step_name} → 状态字: 0x{sw:04X}")
        else:
            print(f"  {step_name} → 状态字读取失败")
            all_ok = False

    result.record(name, all_ok, "状态机切换完成" if all_ok else "切换过程有错误")
    return all_ok


def test_07_32bit_write_read(port, modbus, slave_id, result: TestResult):
    """测试 7: 32位寄存器写入回读（目标速度 0x0055）"""
    name = "07-32位寄存器读写"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")

    # 先读当前值
    ok, msg, vals = read_holding(port, modbus, slave_id, 0x0055, 2)
    if not ok:
        result.record(name, False, f"读取失败: {msg}")
        return False

    original = ModbusRTU.combine_32bit(vals[0], vals[1]) if len(vals) >= 2 else 100
    print(f"  当前目标速度: {original} Step/s")

    # 写入测试值
    test_val = 500
    high, low = ModbusRTU.split_32bit(test_val)
    ok_w, msg_w, _ = write_multiple(port, modbus, slave_id, 0x0055, [high, low])
    if not ok_w:
        result.record(name, False, f"写入失败: {msg_w}")
        return False
    print(f"  写入目标速度: {test_val}")

    time.sleep(0.05)

    # 回读
    ok_r, msg_r, vals_r = read_holding(port, modbus, slave_id, 0x0055, 2)
    if not ok_r:
        result.record(name, False, f"回读失败: {msg_r}")
        return False

    readback = ModbusRTU.combine_32bit(vals_r[0], vals_r[1]) if len(vals_r) >= 2 else -1
    print(f"  回读目标速度: {readback}")
    match = readback == test_val

    # 恢复原值
    high_o, low_o = ModbusRTU.split_32bit(original)
    write_multiple(port, modbus, slave_id, 0x0055, [high_o, low_o])
    print(f"  已恢复原值: {original}")

    result.record(name, match, "32位读写一致" if match else f"不一致: 写{test_val} 读{readback}")
    return match


def test_08_position_move(port, modbus, slave_id, result: TestResult, auto_confirm=False):
    """测试 8: 位置运动测试（相对运动 1000 脉冲，然后回到原位）"""
    name = "08-位置运动"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")

    if not auto_confirm:
        answer = input("  [!] 此测试将使电机运动，是否继续？(y/N): ").strip().lower()
        if answer != "y":
            result.skip(name, "用户跳过")
            return True

    # 先停止电机，确保位置模式
    write_single(port, modbus, slave_id, 0x0051, 0x0000)
    time.sleep(0.05)
    write_single(port, modbus, slave_id, 0x0039, 1)  # 位置模式
    time.sleep(0.05)

    # 读取初始位置
    ok, _, vals = read_input(port, modbus, slave_id, 0x0021, 2)
    start_pos = ModbusRTU.combine_32bit(vals[0], vals[1], signed=True) if ok and len(vals) >= 2 else 0
    print(f"  起始位置: {start_pos} pulse")

    # 设置目标位置 (相对 +1000)
    target = 1000
    high, low = ModbusRTU.split_32bit(target)
    write_multiple(port, modbus, slave_id, 0x0053, [high, low])
    time.sleep(0.02)

    # 状态机: 启动 → 使能
    write_single(port, modbus, slave_id, 0x0051, 0x0006)
    time.sleep(0.02)
    write_single(port, modbus, slave_id, 0x0051, 0x0007)
    time.sleep(0.02)
    # 相对运动: 先清 new setpoint，再置位触发
    write_single(port, modbus, slave_id, 0x0051, 0x004F)
    time.sleep(0.02)
    write_single(port, modbus, slave_id, 0x0051, 0x005F)

    print(f"  已发送相对运动 +{target} 脉冲指令...")

    # 等待运动完成
    def wait_move_done(timeout_count=30):
        for i in range(timeout_count):
            time.sleep(0.1)
            ok_s, _, vals_s = read_input(port, modbus, slave_id, 0x001F, 1)
            if ok_s and vals_s:
                if not (vals_s[0] & (1 << 12)):
                    print(f"  运动完成 (耗时约 {(i+1)*0.1:.1f}s)")
                    return True
        print("  [!] 等待超时，运动可能未完成")
        return False

    wait_move_done()

    # 读取当前位置
    ok_p, _, vals_p = read_input(port, modbus, slave_id, 0x0021, 2)
    if ok_p and len(vals_p) >= 2:
        end_pos = ModbusRTU.combine_32bit(vals_p[0], vals_p[1], signed=True)
        print(f"  当前位置: {end_pos} pulse")
        moved = end_pos - start_pos
        print(f"  实际运动: {moved} pulse (期望 +/-{target})")
        # 检查幅度正确（方向可能因硬件配置不同）
        close_enough = abs(abs(moved) - target) < 10
        if moved < 0:
            print(f"  注意: 运动方向为负，硬件方向定义与正值相反")
    else:
        close_enough = False
        moved = 0

    # 反向运动回到原位
    print(f"  反向运动回到起始位置...")
    # 用相反符号的相对距离
    ret_target = -moved if moved != 0 else -target
    high2, low2 = ModbusRTU.split_32bit(ret_target)
    write_multiple(port, modbus, slave_id, 0x0053, [high2, low2])
    time.sleep(0.02)
    # 需要先清 new setpoint 再置位，触发新的运动
    write_single(port, modbus, slave_id, 0x0051, 0x004F)
    time.sleep(0.02)
    write_single(port, modbus, slave_id, 0x0051, 0x005F)

    wait_move_done()

    ok_f, _, vals_f = read_input(port, modbus, slave_id, 0x0021, 2)
    if ok_f and len(vals_f) >= 2:
        final_pos = ModbusRTU.combine_32bit(vals_f[0], vals_f[1], signed=True)
        print(f"  最终位置: {final_pos} pulse (起始: {start_pos})")
        returned = abs(final_pos - start_pos) < 10
        print(f"  回位{'成功' if returned else '未回位'}")

    # 停止电机
    write_single(port, modbus, slave_id, 0x0051, 0x0000)

    result.record(name, close_enough, f"运动幅度{'正确' if close_enough else '不正确'} ({abs(moved)} pulse)")
    return close_enough


def test_09_speed_mode(port, modbus, slave_id, result: TestResult, auto_confirm=False):
    """测试 9: 速度模式测试（低速运行 1 秒后停止）"""
    name = "09-速度模式"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")

    if not auto_confirm:
        answer = input("  [!] 此测试将使电机以低速运转 1 秒，是否继续？(y/N): ").strip().lower()
        if answer != "y":
            result.skip(name, "用户跳过")
            return True

    # 先停止电机
    write_single(port, modbus, slave_id, 0x0051, 0x0000)
    time.sleep(0.05)

    # 切换到速度模式
    write_single(port, modbus, slave_id, 0x0039, 2)
    time.sleep(0.05)

    # 设置方向=正转, 目标速度=100
    write_single(port, modbus, slave_id, 0x0052, 1)
    high, low = ModbusRTU.split_32bit(100)
    write_multiple(port, modbus, slave_id, 0x0055, [high, low])
    time.sleep(0.02)

    # 启动 → 使能 → 运行
    write_single(port, modbus, slave_id, 0x0051, 0x0006)
    time.sleep(0.02)
    write_single(port, modbus, slave_id, 0x0051, 0x0007)
    time.sleep(0.02)
    write_single(port, modbus, slave_id, 0x0051, 0x000F)

    print("  电机正在运行 (100 Step/s)...")

    # 运行 1 秒
    time.sleep(1)

    # 读取速度
    ok, _, vals = read_input(port, modbus, slave_id, 0x0023, 2)
    if ok and len(vals) >= 2:
        speed = ModbusRTU.combine_32bit(vals[0], vals[1]) // 10
        print(f"  运行中速度: {speed} Step/s")
        was_running = speed > 0
    else:
        was_running = False

    # 停止
    write_single(port, modbus, slave_id, 0x0051, 0x0007)  # 减速停机
    time.sleep(0.5)
    write_single(port, modbus, slave_id, 0x0051, 0x0000)  # 回到无故障

    # 恢复位置模式
    write_single(port, modbus, slave_id, 0x0039, 1)
    print("  已停止，已恢复位置模式")

    result.record(name, was_running, "速度模式运行正常" if was_running else "未检测到运行速度")
    return was_running


def test_10_error_handling(port, modbus, slave_id, result: TestResult):
    """测试 10: 异常处理（读取不存在的寄存器）"""
    name = "10-异常响应处理"
    print(f"\n{'─'*50}")
    print(f"[测试] {name}")

    # 读取一个不太可能存在的高地址
    ok, msg, vals = read_holding(port, modbus, slave_id, 0x0FFF, 1)
    if not ok:
        print(f"  预期的异常响应: {msg}")
        result.record(name, True, f"异常响应正确: {msg}")
    else:
        print(f"  意外成功，值: {vals}")
        result.record(name, False, "预期异常但成功了")
    return True


# ── 主程序 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NiMotion 端到端测试")
    parser.add_argument("--port", "-p", default=None, help="串口号 (如 COM3)")
    parser.add_argument("--slave-id", "-s", type=int, default=1, help="从站地址 (默认 1)")
    parser.add_argument("--baudrate", "-b", type=int, default=115200, help="波特率 (默认 115200)")
    parser.add_argument("--auto", "-a", action="store_true", help="自动确认运动测试，不等待用户输入")
    args = parser.parse_args()

    # 自动检测串口
    available = SerialPort.list_ports()
    print(f"可用串口: {available}")

    port_name = args.port
    if not port_name:
        if len(available) == 1:
            port_name = available[0]
            print(f"自动选择: {port_name}")
        elif available:
            port_name = input(f"请输入串口号 {available}: ").strip()
        else:
            print("未检测到可用串口！")
            sys.exit(1)

    config = SerialConfig(
        port=port_name,
        baudrate=args.baudrate,
        timeout=0.5,
    )

    port = SerialPort()
    modbus = ModbusRTU()
    result = TestResult()
    slave_id = args.slave_id

    print(f"\n{'='*60}")
    print(f"NiMotion 端到端测试")
    print(f"串口: {port_name}  从站: {slave_id}  波特率: {config.baudrate}")
    print(f"{'='*60}")

    try:
        # 连接
        if not test_01_serial_connect(port, config, result):
            result.summary()
            return

        # 通讯与读取测试
        test_02_read_device_info(port, modbus, slave_id, result)
        test_03_read_status(port, modbus, slave_id, result)
        test_04_read_params(port, modbus, slave_id, result)

        # 读写测试
        test_05_write_read_back(port, modbus, slave_id, result)
        test_07_32bit_write_read(port, modbus, slave_id, result)

        # 状态机测试
        test_06_state_machine(port, modbus, slave_id, result)

        # 异常处理测试
        test_10_error_handling(port, modbus, slave_id, result)

        # 运动测试（需确认，或 --auto 跳过确认）
        test_08_position_move(port, modbus, slave_id, result, auto_confirm=args.auto)
        test_09_speed_mode(port, modbus, slave_id, result, auto_confirm=args.auto)

    except KeyboardInterrupt:
        print("\n\n用户中断测试")
    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保停止电机
        try:
            if port.is_open:
                write_single(port, modbus, slave_id, 0x0051, 0x0000)
        except Exception:
            pass
        port.close()
        print("\n串口已关闭")

    result.summary()


if __name__ == "__main__":
    main()
