"""物镜转盘模型 — 齿轮参数、位置枚举与脉冲映射"""

from __future__ import annotations

from enum import IntEnum

# -- 齿轮机械参数 --
GEAR_RATIO = 132 / 48  # 齿轮比 = 2.75
MOTOR_STEPS_PER_REV = 200  # 电机每转步数
MICROSTEP = 128  # 细分数
MOTOR_PULSES_PER_REV = MOTOR_STEPS_PER_REV * MICROSTEP  # 25600 脉冲/转

# 每个物镜孔位(转盘旋转90°)对应的电机脉冲数
# 转盘90° → 电机转 90° × 2.75 = 247.5° → 247.5/360 × 25600 = 17600
PULSES_PER_POSITION = int(MOTOR_PULSES_PER_REV * GEAR_RATIO / 4)  # 17600

# 位置匹配容差（脉冲）
POSITION_TOLERANCE = 50


class TurretPosition(IntEnum):
    """物镜转盘位置"""

    UNKNOWN = -1
    POS_1 = 0  # Home 位置
    POS_2 = 1
    POS_3 = 2
    POS_4 = 3


# 位置 → 绝对脉冲数映射
POSITION_PULSES: dict[TurretPosition, int] = {
    TurretPosition.POS_1: 0,
    TurretPosition.POS_2: PULSES_PER_POSITION,      # 17600
    TurretPosition.POS_3: PULSES_PER_POSITION * 2,  # 35200
    TurretPosition.POS_4: PULSES_PER_POSITION * 3,  # 52800
}


def pulse_to_turret_position(pulse: int) -> TurretPosition:
    """从电机当前脉冲数推断转盘位置。

    Args:
        pulse: 电机当前绝对位置（脉冲数）

    Returns:
        匹配的转盘位置，无法匹配时返回 UNKNOWN
    """
    for pos, target_pulse in POSITION_PULSES.items():
        if abs(pulse - target_pulse) <= POSITION_TOLERANCE:
            return pos
    return TurretPosition.UNKNOWN
