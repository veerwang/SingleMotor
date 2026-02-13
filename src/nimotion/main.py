"""程序入口"""

from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication

from nimotion.ui.main_window import MainWindow
from nimotion.ui.theme import apply_theme


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("NiMotion 步进电机调试工具")
    app.setStyle("Fusion")
    apply_theme(app)

    window = MainWindow()
    window.setWindowTitle("NiMotion 步进电机调试工具 v0.1")
    window.resize(1024, 700)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
