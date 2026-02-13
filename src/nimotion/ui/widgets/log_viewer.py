"""日志查看器控件"""

from __future__ import annotations

from datetime import datetime

from PyQt5.QtWidgets import QPlainTextEdit


class LogViewer(QPlainTextEdit):
    """
    日志查看器。
    - 只读
    - 自动滚动到底部
    - 最大行数限制
    - 支持 HEX/ASCII 切换
    - 支持时间戳前缀
    """

    MAX_LINES = 10000

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(self.MAX_LINES)
        self._hex_mode = True
        self._show_timestamp = True

    @property
    def hex_mode(self) -> bool:
        return self._hex_mode

    def set_hex_mode(self, hex_mode: bool) -> None:
        self._hex_mode = hex_mode

    def set_timestamp(self, enabled: bool) -> None:
        self._show_timestamp = enabled

    def append_tx(self, data: bytes) -> None:
        """追加发送数据记录"""
        text = self._format_data(data)
        prefix = self._timestamp_prefix()
        self.appendPlainText(f"{prefix}TX >> {text}")
        self._scroll_to_bottom()

    def append_rx(self, data: bytes) -> None:
        """追加接收数据记录"""
        text = self._format_data(data)
        prefix = self._timestamp_prefix()
        self.appendPlainText(f"{prefix}RX << {text}")
        self._scroll_to_bottom()

    def append_info(self, message: str) -> None:
        """追加信息记录"""
        prefix = self._timestamp_prefix()
        self.appendPlainText(f"{prefix}INFO: {message}")
        self._scroll_to_bottom()

    def _format_data(self, data: bytes) -> str:
        if self._hex_mode:
            return " ".join(f"{b:02X}" for b in data)
        return data.decode("latin-1", errors="replace")

    def _timestamp_prefix(self) -> str:
        if self._show_timestamp:
            return f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
        return ""

    def _scroll_to_bottom(self) -> None:
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
