"""物镜转盘模型 — 齿轮参数、位置枚举与脉冲映射"""

from __future__ import annotations

from enum import IntEnum

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
