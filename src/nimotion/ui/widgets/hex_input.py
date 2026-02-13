"""HEX 输入框控件"""

from __future__ import annotations

import re

from PyQt5.QtCore import QRegularExpression
from PyQt5.QtGui import QRegularExpressionValidator
from PyQt5.QtWidgets import QLineEdit


class HexInput(QLineEdit):
    """
    HEX 输入框。
    - 只允许输入 0-9, A-F, a-f, 空格
    - 自动格式化为 "XX XX XX" 格式
    - 提供 get_bytes() / set_bytes() 方法
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("例如: 01 03 00 00 00 01")
        # 允许 hex 字符和空格
        regex = QRegularExpression(r"[0-9A-Fa-f ]*")
        self.setValidator(QRegularExpressionValidator(regex, self))
        self.editingFinished.connect(self._format_text)

    def get_bytes(self) -> bytes:
        """将输入文本解析为 bytes"""
        text = self.text().strip()
        if not text:
            return b""
        # 移除所有空格，按2字符分组
        hex_str = text.replace(" ", "")
        if len(hex_str) % 2 != 0:
            hex_str = "0" + hex_str  # 补前导0
        try:
            return bytes.fromhex(hex_str)
        except ValueError:
            return b""

    def set_bytes(self, data: bytes) -> None:
        """将 bytes 显示为 HEX 格式"""
        self.setText(" ".join(f"{b:02X}" for b in data))

    def _format_text(self) -> None:
        """格式化输入文本为 "XX XX" 格式"""
        data = self.get_bytes()
        if data:
            self.set_bytes(data)
