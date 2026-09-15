"""应用级本机配置的加载与保存。

存放不属于驱动器寄存器的软件侧配置（如电机方向反转），
持久化到仓库根目录 motor_config.json，与 turret_calibration.json 同级。
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[3] / "motor_config.json"

# 默认齿轮变比 132/48 = 2.75（转盘大齿轮齿数 / 电机小齿轮齿数）
DEFAULT_GEAR_TEETH: tuple[int, int] = (132, 48)


def load_direction_inverted(path: Path = CONFIG_FILE) -> bool:
    """读取电机方向反转配置；文件缺失或损坏时返回 False（不反转）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("direction_inverted", False))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def save_direction_inverted(inverted: bool, path: Path = CONFIG_FILE) -> None:
    """保存电机方向反转配置，保留文件中已有的其他字段。"""
    _save_bool(path, "direction_inverted", inverted)


def load_di_invert(path: Path = CONFIG_FILE) -> bool:
    """读取原点开关(DI)极性取反配置；文件缺失或损坏时返回 False（旧逻辑不取反）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("di_invert", False))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def save_di_invert(inverted: bool, path: Path = CONFIG_FILE) -> None:
    """保存原点开关极性取反配置，保留文件中已有的其他字段。"""
    _save_bool(path, "di_invert", inverted)


def load_gear_teeth(path: Path = CONFIG_FILE) -> tuple[int, int]:
    """读取齿轮齿数配置 (转盘齿数, 电机齿数)。

    文件缺失、损坏或齿数非法（非正整数）时返回默认 132/48。
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        turret = int(data.get("gear_teeth_turret", DEFAULT_GEAR_TEETH[0]))
        motor = int(data.get("gear_teeth_motor", DEFAULT_GEAR_TEETH[1]))
    except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return DEFAULT_GEAR_TEETH
    if turret <= 0 or motor <= 0:
        return DEFAULT_GEAR_TEETH
    return (turret, motor)


def save_gear_teeth(
    turret_teeth: int, motor_teeth: int, path: Path = CONFIG_FILE
) -> None:
    """保存齿轮齿数配置，保留文件中已有的其他字段。

    Raises:
        ValueError: 齿数不是正整数
    """
    turret_teeth, motor_teeth = int(turret_teeth), int(motor_teeth)
    if turret_teeth <= 0 or motor_teeth <= 0:
        raise ValueError(f"齿数必须为正整数: {turret_teeth}/{motor_teeth}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data["gear_teeth_turret"] = turret_teeth
    data["gear_teeth_motor"] = motor_teeth
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_gear_ratio(path: Path = CONFIG_FILE) -> float:
    """读取齿轮变比（转盘齿数/电机齿数），默认 132/48 = 2.75。"""
    turret, motor = load_gear_teeth(path)
    return turret / motor


def _save_bool(path: Path, key: str, value: bool) -> None:
    """通用保存布尔字段：保留已有其他字段，写回 JSON。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data[key] = bool(value)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
