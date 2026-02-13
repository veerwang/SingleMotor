"""
工业风格主题 — 黑黄配色 HMI 风格
灵感来源：工厂控制面板、SCADA 系统、重型机械仪表盘
"""

from __future__ import annotations

# ── 颜色常量 ──

BLACK_BG = "#0C0C0C"
DARK_PANEL = "#1A1A1A"
PANEL_BG = "#222222"
PANEL_BORDER = "#333333"
STEEL_GRAY = "#2D2D2D"
STEEL_LIGHT = "#3A3A3A"
STEEL_HIGHLIGHT = "#444444"

YELLOW_PRIMARY = "#FFD600"
YELLOW_BRIGHT = "#FFEA00"
YELLOW_DIM = "#B8960F"
YELLOW_DARK = "#8B7300"
YELLOW_TEXT = "#FFD600"
YELLOW_HOVER = "#FFE740"
YELLOW_PRESSED = "#CCAB00"

ORANGE_WARN = "#FF9800"
RED_ALARM = "#FF3D00"
RED_GLOW = "#FF1744"
GREEN_OK = "#00E676"
GREEN_DIM = "#2E7D32"
CYAN_INFO = "#00E5FF"

TEXT_PRIMARY = "#E0E0E0"
TEXT_SECONDARY = "#9E9E9E"
TEXT_DIM = "#666666"
TEXT_ON_YELLOW = "#0C0C0C"

HAZARD_STRIPE = f"""
    background: repeating-linear-gradient(
        -45deg,
        {YELLOW_PRIMARY},
        {YELLOW_PRIMARY} 10px,
        {BLACK_BG} 10px,
        {BLACK_BG} 20px
    );
"""

# ── 字体 ──
FONT_MONO = "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace"
FONT_UI = "'Segoe UI', 'Noto Sans SC', 'Microsoft YaHei', sans-serif"

# ── QSS 样式表 ──

STYLESHEET = f"""
/* ═══════════════════════════════════════════════════
   NiMotion 工业风格主题 — 黑黄 HMI
   ═══════════════════════════════════════════════════ */

/* ── 全局 ── */
* {{
    font-family: {FONT_UI};
    font-size: 20px;
    outline: none;
}}

QMainWindow {{
    background-color: {BLACK_BG};
}}

QWidget {{
    background-color: {BLACK_BG};
    color: {TEXT_PRIMARY};
}}

/* ── 菜单栏 ── */
QMenuBar {{
    background-color: {DARK_PANEL};
    color: {TEXT_PRIMARY};
    border-bottom: 1px solid {PANEL_BORDER};
    padding: 2px 0;
}}
QMenuBar::item:selected {{
    background-color: {STEEL_HIGHLIGHT};
    color: {YELLOW_PRIMARY};
}}
QMenu {{
    background-color: {PANEL_BG};
    border: 1px solid {PANEL_BORDER};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 24px;
}}
QMenu::item:selected {{
    background-color: {STEEL_HIGHLIGHT};
    color: {YELLOW_PRIMARY};
}}
QMenu::separator {{
    height: 1px;
    background-color: {PANEL_BORDER};
    margin: 4px 8px;
}}

/* ── 标签页 Tab ── */
QTabWidget::pane {{
    border: 1px solid {PANEL_BORDER};
    background-color: {DARK_PANEL};
    border-top: 2px solid {YELLOW_PRIMARY};
}}
QTabBar {{
    background-color: {BLACK_BG};
}}
QTabBar::tab {{
    background-color: {STEEL_GRAY};
    color: {TEXT_SECONDARY};
    border: 1px solid {PANEL_BORDER};
    border-bottom: none;
    padding: 8px 20px;
    margin-right: 2px;
    font-weight: bold;
    font-size: 20px;
    min-width: 100px;
}}
QTabBar::tab:selected {{
    background-color: {DARK_PANEL};
    color: {YELLOW_PRIMARY};
    border-top: 3px solid {YELLOW_PRIMARY};
    padding-top: 6px;
}}
QTabBar::tab:hover:!selected {{
    background-color: {STEEL_LIGHT};
    color: {YELLOW_DIM};
}}

/* ── 分组框 GroupBox ── */
QGroupBox {{
    background-color: {PANEL_BG};
    border: 1px solid {PANEL_BORDER};
    border-left: 3px solid {YELLOW_DIM};
    border-radius: 0px;
    margin-top: 16px;
    padding: 12px 8px 8px 8px;
    font-weight: bold;
    font-size: 20px;
    color: {YELLOW_PRIMARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 12px;
    background-color: {STEEL_GRAY};
    border: 1px solid {PANEL_BORDER};
    color: {YELLOW_PRIMARY};
    font-weight: bold;
    letter-spacing: 1px;
}}

/* ── 按钮 ── */
QPushButton {{
    background-color: {STEEL_GRAY};
    color: {TEXT_PRIMARY};
    border: 1px solid {PANEL_BORDER};
    border-bottom: 2px solid {YELLOW_DARK};
    padding: 6px 16px;
    font-weight: bold;
    font-size: 18px;
    min-height: 24px;
}}
QPushButton:hover {{
    background-color: {STEEL_HIGHLIGHT};
    border-bottom-color: {YELLOW_PRIMARY};
    color: {YELLOW_PRIMARY};
}}
QPushButton:pressed {{
    background-color: {YELLOW_DARK};
    color: {TEXT_ON_YELLOW};
    border-bottom: 1px solid {YELLOW_PRIMARY};
    padding-top: 7px;
}}
QPushButton:disabled {{
    background-color: {DARK_PANEL};
    color: {TEXT_DIM};
    border-color: {PANEL_BORDER};
    border-bottom-color: {PANEL_BORDER};
}}

/* 黄色醒目按钮（连接/发送等关键操作） */
QPushButton[cssClass="primary"] {{
    background-color: {YELLOW_DARK};
    color: {TEXT_ON_YELLOW};
    border: 1px solid {YELLOW_PRIMARY};
    border-bottom: 2px solid {YELLOW_PRIMARY};
    font-weight: bold;
}}
QPushButton[cssClass="primary"]:hover {{
    background-color: {YELLOW_PRIMARY};
    color: {TEXT_ON_YELLOW};
}}
QPushButton[cssClass="primary"]:pressed {{
    background-color: {YELLOW_PRESSED};
}}

/* 危险按钮（急停等） */
QPushButton[cssClass="danger"] {{
    background-color: #4A1010;
    color: {RED_ALARM};
    border: 1px solid {RED_ALARM};
    border-bottom: 2px solid {RED_ALARM};
    font-weight: bold;
}}
QPushButton[cssClass="danger"]:hover {{
    background-color: {RED_ALARM};
    color: white;
}}
QPushButton[cssClass="danger"]:pressed {{
    background-color: #CC3300;
}}

/* ── 输入框 ── */
QLineEdit {{
    background-color: {DARK_PANEL};
    color: {YELLOW_BRIGHT};
    border: 1px solid {PANEL_BORDER};
    border-bottom: 2px solid {STEEL_HIGHLIGHT};
    padding: 5px 8px;
    font-family: {FONT_MONO};
    font-size: 20px;
    selection-background-color: {YELLOW_DARK};
    selection-color: {TEXT_ON_YELLOW};
}}
QLineEdit:focus {{
    border-bottom: 2px solid {YELLOW_PRIMARY};
}}
QLineEdit:disabled {{
    background-color: {BLACK_BG};
    color: {TEXT_DIM};
    border-bottom-color: {PANEL_BORDER};
}}

/* ── 下拉框 ── */
QComboBox {{
    background-color: {STEEL_GRAY};
    color: {TEXT_PRIMARY};
    border: 1px solid {PANEL_BORDER};
    padding: 5px 8px;
    padding-right: 24px;
    min-height: 20px;
}}
QComboBox:hover {{
    border-color: {YELLOW_DIM};
}}
QComboBox:focus {{
    border-color: {YELLOW_PRIMARY};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid {PANEL_BORDER};
    background-color: {STEEL_LIGHT};
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {YELLOW_PRIMARY};
    margin-right: 4px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {YELLOW_DIM};
    selection-background-color: {STEEL_HIGHLIGHT};
    selection-color: {YELLOW_PRIMARY};
    outline: none;
}}

/* ── 数值输入 SpinBox ── */
QSpinBox, QDoubleSpinBox {{
    background-color: {DARK_PANEL};
    color: {YELLOW_BRIGHT};
    border: 1px solid {PANEL_BORDER};
    border-bottom: 2px solid {STEEL_HIGHLIGHT};
    padding: 4px 8px;
    font-family: {FONT_MONO};
    font-size: 20px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-bottom: 2px solid {YELLOW_PRIMARY};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    background-color: {STEEL_GRAY};
    border-left: 1px solid {PANEL_BORDER};
    border-bottom: 1px solid {PANEL_BORDER};
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
    background-color: {STEEL_HIGHLIGHT};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {YELLOW_PRIMARY};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    background-color: {STEEL_GRAY};
    border-left: 1px solid {PANEL_BORDER};
    border-top: 1px solid {PANEL_BORDER};
}}
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {STEEL_HIGHLIGHT};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {YELLOW_PRIMARY};
}}

/* ── 复选框 ── */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    background-color: {DARK_PANEL};
    border: 1px solid {PANEL_BORDER};
}}
QCheckBox::indicator:checked {{
    background-color: {YELLOW_PRIMARY};
    border-color: {YELLOW_PRIMARY};
    image: none;
}}
QCheckBox::indicator:hover {{
    border-color: {YELLOW_DIM};
}}
QCheckBox:disabled {{
    color: {TEXT_DIM};
}}

/* ── 表格 ── */
QTableWidget {{
    background-color: {DARK_PANEL};
    color: {TEXT_PRIMARY};
    border: 1px solid {PANEL_BORDER};
    gridline-color: {PANEL_BORDER};
    font-family: {FONT_MONO};
    font-size: 18px;
    alternate-background-color: {STEEL_GRAY};
    selection-background-color: {YELLOW_DARK};
    selection-color: {TEXT_ON_YELLOW};
}}
QTableWidget::item {{
    padding: 4px 8px;
    border-bottom: 1px solid {PANEL_BORDER};
}}
QTableWidget::item:selected {{
    background-color: {YELLOW_DARK};
    color: {TEXT_ON_YELLOW};
}}
QHeaderView::section {{
    background-color: {STEEL_GRAY};
    color: {YELLOW_PRIMARY};
    border: none;
    border-bottom: 2px solid {YELLOW_DIM};
    border-right: 1px solid {PANEL_BORDER};
    padding: 6px 8px;
    font-weight: bold;
    font-size: 17px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QHeaderView::section:hover {{
    background-color: {STEEL_HIGHLIGHT};
}}

/* ── 文本编辑区 / 日志查看器 ── */
QPlainTextEdit, QTextEdit {{
    background-color: #0E0E0E;
    color: {GREEN_OK};
    border: 1px solid {PANEL_BORDER};
    font-family: {FONT_MONO};
    font-size: 18px;
    padding: 4px;
    selection-background-color: {YELLOW_DARK};
    selection-color: {TEXT_ON_YELLOW};
}}

/* ── 滚动条 ── */
QScrollBar:vertical {{
    background-color: {DARK_PANEL};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {STEEL_HIGHLIGHT};
    min-height: 30px;
    border-radius: 0px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {YELLOW_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background-color: {DARK_PANEL};
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {STEEL_HIGHLIGHT};
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {YELLOW_DIM};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ── 滚动区域 ── */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

/* ── 状态栏 ── */
QStatusBar {{
    background-color: {DARK_PANEL};
    color: {TEXT_SECONDARY};
    border-top: 2px solid {YELLOW_DARK};
    font-family: {FONT_MONO};
    font-size: 18px;
    padding: 2px 8px;
}}
QStatusBar::item {{
    border: none;
}}

/* ── 标签 Label ── */
QLabel {{
    color: {TEXT_PRIMARY};
    background-color: transparent;
}}

/* ── 表单行标签 ── */
QFormLayout QLabel {{
    color: {TEXT_SECONDARY};
    font-weight: bold;
    font-size: 18px;
}}

/* ── 消息框 ── */
QMessageBox {{
    background-color: {PANEL_BG};
}}
QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
    font-size: 20px;
}}

/* ── 工具提示 ── */
QToolTip {{
    background-color: {YELLOW_PRIMARY};
    color: {TEXT_ON_YELLOW};
    border: 1px solid {YELLOW_DARK};
    padding: 4px 8px;
    font-weight: bold;
    font-size: 18px;
}}

/* ── 进度条（备用） ── */
QProgressBar {{
    background-color: {DARK_PANEL};
    border: 1px solid {PANEL_BORDER};
    text-align: center;
    color: {TEXT_PRIMARY};
    font-weight: bold;
    height: 20px;
}}
QProgressBar::chunk {{
    background-color: {YELLOW_PRIMARY};
}}

/* ── 分割线 ── */
QFrame[frameShape="4"] {{ /* HLine */
    background-color: {PANEL_BORDER};
    border: none;
    max-height: 1px;
}}
QFrame[frameShape="5"] {{ /* VLine */
    background-color: {PANEL_BORDER};
    border: none;
    max-width: 1px;
}}
"""


def apply_theme(app) -> None:
    """应用工业风格主题到 QApplication"""
    app.setStyleSheet(STYLESHEET)
