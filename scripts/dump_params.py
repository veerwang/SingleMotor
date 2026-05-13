"""读取驱动器全部参数并保存为 Markdown，便于跨设备核对。

用法:
    python scripts/dump_params.py [--port /dev/ttyUSB0] [--slave 1] [--baud 115200] [--out reports/params_baseline.md]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# 让脚本在仓库根目录直接运行
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nimotion.communication.modbus_rtu import ModbusRTU
from nimotion.communication.serial_port import SerialConfig, SerialPort
from nimotion.models.error_codes import get_error_text, get_exception_text
from nimotion.models.registers import HOLDING_REGISTERS, INPUT_REGISTERS
from nimotion.models.types import DataType, FunctionCode, ModbusRequest, RegisterDef, RegisterType


# 写命令型寄存器：读取它们意义不大，常常返回 0 或报错，单独标注
COMMAND_ONLY_ADDRS = {
    0x0008,  # 保存所有参数 (写 0x7376)
    0x000B,  # 恢复默认参数 (写 0x6C64)
    0x0047,  # 设置零点 (写 0x535A)
    0x0048,  # 设置原点 (写 0x5348)
    0x0051,  # 运动控制字
    0x0073,  # 清空错误存储器 (写 0x6C64)
    0x0074,  # 硬件自检 (写 0x7465)
}


def transact(sp: SerialPort, mb: ModbusRTU, req: ModbusRequest, retries: int = 2):
    """发起一次 Modbus 事务，带简易重试"""
    for attempt in range(retries + 1):
        frame = mb.build_frame(req)
        sp.flush_input()
        sp.write(frame)
        time.sleep(0.02)
        expected = mb.expected_response_length(req)
        raw = sp.read(expected)
        resp = mb.parse_response(raw, req)
        if not resp.is_error:
            return resp
        time.sleep(0.05)
    return resp  # 返回最后一次的失败响应


def decode_value(reg: RegisterDef, values: list[int]) -> int:
    """根据数据类型解析寄存器原始值"""
    if reg.count == 1:
        raw = values[0] & 0xFFFF
        if reg.data_type == DataType.INT16 and raw >= 0x8000:
            raw -= 0x10000
        return raw
    # 32-bit: [高, 低]
    return ModbusRTU.combine_32bit(values[0], values[1], signed=(reg.data_type == DataType.INT32))


def format_raw_hex(reg: RegisterDef, values: list[int]) -> str:
    """构造原始 hex 表示，便于完全核对"""
    if reg.count == 1:
        return f"0x{values[0] & 0xFFFF:04X}"
    return f"0x{values[0] & 0xFFFF:04X} 0x{values[1] & 0xFFFF:04X}"


def format_value(reg: RegisterDef, decoded: int) -> str:
    """格式化解码后的值（带单位/十进制）"""
    txt = f"{decoded}"
    if reg.unit:
        txt += f" {reg.unit}"
    return txt


def value_matches_default(reg: RegisterDef, decoded: int) -> str:
    if reg.default_val is None:
        return ""
    return "✓" if decoded == reg.default_val else "⚠"


def read_register(sp: SerialPort, mb: ModbusRTU, slave_id: int, reg: RegisterDef):
    """读取单个寄存器，返回 (decoded_value, raw_hex, error_text)"""
    fc = FunctionCode.READ_HOLDING if reg.reg_type == RegisterType.HOLDING else FunctionCode.READ_INPUT
    req = ModbusRequest(slave_id=slave_id, function_code=fc, address=reg.address, count=reg.count)
    resp = transact(sp, mb, req)
    if resp.is_error:
        if resp.error_code == -1:
            return None, "", "CRC 错误"
        if resp.error_code == -3:
            return None, "", "帧长度不足/超时"
        return None, "", f"异常码 0x{resp.error_code:02X} ({get_exception_text(resp.error_code)})"
    if len(resp.values) < reg.count:
        return None, "", "返回数据不足"
    decoded = decode_value(reg, resp.values[: reg.count])
    raw_hex = format_raw_hex(reg, resp.values[: reg.count])
    return decoded, raw_hex, ""


def render_md(slave_id: int, baud: int, port: str,
              holding_rows: list[dict], input_rows: list[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 驱动器参数基线",
        "",
        f"- 生成时间: {now}",
        f"- 串口: `{port}`",
        f"- 从站地址: {slave_id}",
        f"- 波特率: {baud}",
        "",
        "> 用途：作为正常驱动器的参考基线，与异常驱动器逐项比对。",
        "> `匹配默认` 列：✓ = 与手册默认值一致；⚠ = 与默认值不同（可能是已校准的现场参数，不一定是问题）。",
        "",
        "## 保持寄存器（EEPROM 可写参数）",
        "",
        "| 地址 | 名称 | 原始值 | 解析值 | 默认值 | 匹配默认 | 单位 | 描述 |",
        "|------|------|--------|--------|--------|----------|------|------|",
    ]
    for r in holding_rows:
        default = "—" if r["default"] is None else str(r["default"])
        desc = r["description"].replace("|", "\\|").replace("\n", " ")
        name = r["name"]
        if r["error"]:
            lines.append(
                f"| 0x{r['address']:04X} | {name} | — | **读取失败:** {r['error']} | {default} | — | {r['unit'] or '—'} | {desc} |"
            )
            continue
        if r["is_command"]:
            note = f"{r['raw_hex']} (命令型寄存器)"
            lines.append(
                f"| 0x{r['address']:04X} | {name} | {r['raw_hex']} | {note} | {default} | — | {r['unit'] or '—'} | {desc} |"
            )
            continue
        lines.append(
            f"| 0x{r['address']:04X} | {name} | {r['raw_hex']} | {r['value']} | {default} | {r['match']} | {r['unit'] or '—'} | {desc} |"
        )

    lines += [
        "",
        "## 输入寄存器（只读，设备信息/运行状态）",
        "",
        "| 地址 | 名称 | 原始值 | 解析值 | 单位 | 描述 |",
        "|------|------|--------|--------|------|------|",
    ]
    for r in input_rows:
        desc = r["description"].replace("|", "\\|").replace("\n", " ")
        name = r["name"]
        if r["error"]:
            lines.append(
                f"| 0x{r['address']:04X} | {name} | — | **读取失败:** {r['error']} | {r['unit'] or '—'} | {desc} |"
            )
            continue
        lines.append(
            f"| 0x{r['address']:04X} | {name} | {r['raw_hex']} | {r['value']} | {r['unit'] or '—'} | {desc} |"
        )

    # 报警/错误码解读
    lines += ["", "## 报警解读", ""]
    alarm_codes = []
    for r in input_rows:
        if not r["error"] and r["name"].startswith("历史报警"):
            alarm_codes.append((r["name"], r["raw_decoded"]))
    cur = next((r for r in input_rows if r["name"] == "当前错误报警值" and not r["error"]), None)
    if cur:
        code = cur["raw_decoded"]
        lines.append(f"- 当前错误报警值: 0x{code:04X} ({get_error_text(code) if code else '无'})")
    for name, code in alarm_codes:
        if code:
            lines.append(f"- {name}: 0x{code:04X} ({get_error_text(code)})")
        else:
            lines.append(f"- {name}: 无")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="读取驱动器全部寄存器并生成 Markdown 报告")
    ap.add_argument("--port", default="/dev/ttyUSB0", help="串口设备 (默认 /dev/ttyUSB0)")
    ap.add_argument("--slave", type=int, default=1, help="从站地址 (默认 1)")
    ap.add_argument("--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--out", default="reports/params_baseline.md", help="输出 Markdown 路径")
    args = ap.parse_args()

    out_path = (ROOT / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sp = SerialPort()
    sp.open(SerialConfig(port=args.port, baudrate=args.baud))
    mb = ModbusRTU()

    print(f"连接 {args.port} @ {args.baud}, slave={args.slave}")
    print(f"开始读取 {len(HOLDING_REGISTERS)} 个保持寄存器...")

    holding_rows = []
    for reg in HOLDING_REGISTERS:
        is_cmd = reg.address in COMMAND_ONLY_ADDRS
        decoded, raw_hex, err = read_register(sp, mb, args.slave, reg)
        row = {
            "address": reg.address,
            "name": reg.name,
            "unit": reg.unit,
            "default": reg.default_val,
            "description": reg.description,
            "is_command": is_cmd,
            "raw_hex": raw_hex,
            "raw_decoded": decoded if decoded is not None else 0,
            "value": format_value(reg, decoded) if decoded is not None else "",
            "match": value_matches_default(reg, decoded) if decoded is not None else "",
            "error": err,
        }
        holding_rows.append(row)
        status = "OK" if not err else f"ERR({err})"
        print(f"  0x{reg.address:04X} {reg.name:<20} {row['raw_hex']:>12}  {status}")

    print(f"\n开始读取 {len(INPUT_REGISTERS)} 个输入寄存器...")
    input_rows = []
    for reg in INPUT_REGISTERS:
        decoded, raw_hex, err = read_register(sp, mb, args.slave, reg)
        row = {
            "address": reg.address,
            "name": reg.name,
            "unit": reg.unit,
            "description": reg.description,
            "raw_hex": raw_hex,
            "raw_decoded": decoded if decoded is not None else 0,
            "value": format_value(reg, decoded) if decoded is not None else "",
            "error": err,
        }
        input_rows.append(row)
        status = "OK" if not err else f"ERR({err})"
        print(f"  0x{reg.address:04X} {reg.name:<22} {row['raw_hex']:>12}  {status}")

    sp.close()

    md = render_md(args.slave, args.baud, args.port, holding_rows, input_rows)
    out_path.write_text(md, encoding="utf-8")
    print(f"\n报告已保存: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
