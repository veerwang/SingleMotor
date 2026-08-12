"""应用级本机配置的加载与保存。

存放不属于驱动器寄存器的软件侧配置（如电机方向反转），
持久化到仓库根目录 motor_config.json，与 turret_calibration.json 同级。
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[3] / "motor_config.json"


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
