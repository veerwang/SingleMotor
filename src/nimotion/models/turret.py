"""物镜转盘模型 — 齿轮参数、位置枚举与脉冲映射"""

from __future__ import annotations

import json
from enum import IntEnum
from pathlib import Path

# -- 齿轮机械参数 --
GEAR_RATIO = 132 / 48  # 齿轮比 = 2.75
MOTOR_STEPS_PER_REV = 200  # 电机每转步数

# 细分数寄存器地址 (保持寄存器 0x001A, UINT16, 值 0~7)
MICROSTEP_REG_ADDR = 0x001A

# 位置匹配容差（脉冲）
POSITION_TOLERANCE = 50


class TurretPosition(IntEnum):
    """物镜转盘位置"""

    UNKNOWN = -1
    POS_1 = 0  # Home 位置
    POS_2 = 1
    POS_3 = 2
    POS_4 = 3


def microstep_from_register(reg_value: int) -> int:
    """将细分寄存器值转换为实际细分数。

    寄存器 0x001A 值 0~7 对应细分 1, 2, 4, 8, 16, 32, 64, 128。

    Args:
        reg_value: 寄存器原始值 (0~7)

    Returns:
        实际细分数

    Raises:
        ValueError: 寄存器值超出有效范围
    """
    if not 0 <= reg_value <= 7:
        raise ValueError(f"细分寄存器值必须在 0~7 范围内，收到: {reg_value}")
    return 2**reg_value


def calculate_pulses_per_position(microstep: int) -> int:
    """计算每个物镜孔位(转盘旋转90°)对应的电机脉冲数。

    转盘90° → 电机转 90° × GEAR_RATIO → 对应脉冲数

    Args:
        microstep: 实际细分数 (1, 2, 4, ..., 128)

    Returns:
        每孔位脉冲数
    """
    motor_pulses_per_rev = MOTOR_STEPS_PER_REV * microstep
    return int(motor_pulses_per_rev * GEAR_RATIO / 4)


def calculate_position_pulses(microstep: int) -> dict[TurretPosition, int]:
    """计算位置→绝对脉冲数映射。

    Args:
        microstep: 实际细分数 (1, 2, 4, ..., 128)

    Returns:
        各位置对应的绝对脉冲数字典
    """
    ppp = calculate_pulses_per_position(microstep)
    return {
        TurretPosition.POS_1: 0,
        TurretPosition.POS_2: ppp,
        TurretPosition.POS_3: ppp * 2,
        TurretPosition.POS_4: ppp * 3,
    }


# -- 孔位标定（回零点→各孔位实测绝对脉冲）持久化 --
#
# 回零点通常不等于孔位 1 的物理位置。用户在 GUI 上点动对位后，
# 把当前电机绝对位置标定为该孔位目标，持久化到此文件。移动时直接
# 用标定的绝对脉冲值 move_absolute，未标定的孔位回退到理论计算值。
CALIBRATION_FILE = Path(__file__).resolve().parents[3] / "turret_calibration.json"


def load_calibration(path: Path = CALIBRATION_FILE) -> dict[TurretPosition, int]:
    """从 JSON 加载已标定的孔位绝对脉冲值。

    Returns:
        {孔位: 绝对脉冲}，仅包含文件中存在的孔位；文件缺失或损坏时返回空字典。
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[TurretPosition, int] = {}
    for pos in TurretPosition:
        if pos == TurretPosition.UNKNOWN:
            continue
        raw = data.get(str(int(pos)))
        if raw is None:
            continue
        try:
            result[pos] = int(raw)
        except (TypeError, ValueError):
            continue
    return result


def save_calibration(
    calibration: dict[TurretPosition, int], path: Path = CALIBRATION_FILE
) -> None:
    """将孔位标定绝对脉冲值写入 JSON。"""
    data = {str(int(pos)): int(val) for pos, val in calibration.items()}
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def effective_position_pulses(
    microstep: int, calibration: dict[TurretPosition, int] | None = None
) -> dict[TurretPosition, int]:
    """计算实际用于移动的孔位绝对脉冲：已标定用标定值，否则用理论值。

    Args:
        microstep: 实际细分数
        calibration: 已标定孔位绝对脉冲（可为 None 或部分孔位）

    Returns:
        各孔位最终采用的绝对脉冲数
    """
    theoretical = calculate_position_pulses(microstep)
    if not calibration:
        return theoretical
    return {pos: calibration.get(pos, theoretical[pos]) for pos in theoretical}


def pulse_to_turret_position(
    pulse: int, position_pulses: dict[TurretPosition, int]
) -> TurretPosition:
    """从电机当前脉冲数推断转盘位置。

    Args:
        pulse: 电机当前绝对位置（脉冲数）
        position_pulses: 位置→脉冲映射字典

    Returns:
        匹配的转盘位置，无法匹配时返回 UNKNOWN
    """
    for pos, target_pulse in position_pulses.items():
        if abs(pulse - target_pulse) <= POSITION_TOLERANCE:
            return pos
    return TurretPosition.UNKNOWN
