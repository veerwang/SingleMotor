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
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data["direction_inverted"] = bool(inverted)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
