"""Modern TV-broadcast dark sports-management QSS stylesheet for Track & Field Manager."""

DARK_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #080d22;
    color: #eef3ff;
    font-family: "Bahnschrift", "Segoe UI", "Inter", Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #eef3ff;
}

QToolTip {
    background-color: #101738;
    color: #f8fafc;
    border: 1px solid #0de0cc;
    border-radius: 4px;
    padding: 5px 8px;
}

QFrame#HeaderBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0b112c, stop:0.6 #11193f, stop:1 #0b112c);
    border-bottom: 2px solid #0de0cc;
}

QFrame#StatCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141e48, stop:1 #0e1637);
    border: 1px solid #243266;
    border-left: 4px solid #0de0cc;
    border-radius: 6px;
}

QFrame#SectionPanel {
    background-color: #0e1535;
    border: 1px solid #1f2d5c;
    border-top: 2px solid #2a3d7a;
    border-radius: 6px;
}

QLabel#AppTitle {
    font-size: 20px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.4px;
}

QLabel#SubTitle {
    font-size: 12px;
    color: #8ea0c8;
}

QLabel#CardTitle {
    font-size: 11px;
    font-weight: 700;
    color: #0de0cc;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

QLabel#CardValue {
    font-size: 23px;
    font-weight: 800;
    color: #ffffff;
}

QLabel#SectionHeader {
    font-size: 14px;
    font-weight: 800;
    color: #f8fafc;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}

QLabel#TierBadge {
    background-color: #15214d;
    color: #0de0cc;
    border: 1px solid #0de0cc;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: 800;
    font-size: 12px;
    letter-spacing: 0.4px;
}

QLabel#CompAlertBadge {
    background-color: #3f0d28;
    color: #ff6aa6;
    border: 1px solid #eb297a;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: 800;
    font-size: 12px;
    letter-spacing: 0.5px;
}

QLabel#HudBudgetPill {
    background-color: #0f1b3d;
    color: #34f5c5;
    border: 1px solid #1f3c66;
    border-left: 3px solid #0de0cc;
    border-radius: 4px;
    padding: 5px 11px;
    font-weight: 800;
    font-size: 13px;
}

QLabel#HudPrestigePill {
    background-color: #161b3d;
    color: #fbbf24;
    border: 1px solid #3d3566;
    border-left: 3px solid #fbbf24;
    border-radius: 4px;
    padding: 5px 11px;
    font-weight: 800;
    font-size: 13px;
}

QPushButton {
    background-color: #16204a;
    color: #e2e8f0;
    border: 1px solid #2b3c78;
    border-radius: 5px;
    padding: 7px 14px;
    font-weight: 700;
}

QPushButton:hover {
    background-color: #1f2d64;
    border-color: #0de0cc;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #0c122d;
}

QPushButton:disabled {
    background-color: #111733;
    color: #54648c;
    border-color: #1b254b;
}

QPushButton#AdvanceWeekButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0de0cc, stop:1 #2ef2df);
    color: #060e26;
    border: none;
    border-radius: 5px;
    padding: 9px 20px;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.4px;
}

QPushButton#AdvanceWeekButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38f3e1, stop:1 #6ff9ec);
}

QPushButton#AdvanceWeekButton:pressed {
    background-color: #0ab8a7;
}

QPushButton#PrimaryButton {
    background-color: #1648a8;
    color: #ffffff;
    border: 1px solid #2563eb;
}

QPushButton#PrimaryButton:hover {
    background-color: #1d5bd1;
    border-color: #0de0cc;
}

QPushButton#DangerButton {
    background-color: #5c122e;
    color: #ffd5e4;
    border: 1px solid #eb297a;
}

QPushButton#DangerButton:hover {
    background-color: #7c183e;
}

QTabWidget::pane {
    border: 1px solid #1f2d5c;
    border-top: 2px solid #243670;
    border-radius: 6px;
    background-color: #0b112b;
    top: -1px;
}

QTabBar::tab {
    background-color: #10183c;
    color: #8ea0c8;
    border: 1px solid #1e2c5c;
    border-bottom: 2px solid transparent;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    padding: 9px 16px;
    margin-right: 4px;
    font-weight: 700;
    font-size: 12px;
}

QTabBar::tab:selected {
    background-color: #16214f;
    color: #ffffff;
    border-color: #2b3f80;
    border-bottom: 3px solid #0de0cc;
}

QTabBar::tab:hover:!selected {
    color: #ffffff;
    background-color: #151f4a;
}

QTableWidget {
    background-color: #0a1029;
    alternate-background-color: #10173a;
    gridline-color: #1b2856;
    border: 1px solid #202f63;
    border-radius: 5px;
    selection-background-color: #163b69;
    selection-color: #ffffff;
}

QTableWidget::item {
    padding: 4px 6px;
}

QHeaderView::section {
    background-color: #151f4b;
    color: #0de0cc;
    border: none;
    border-bottom: 2px solid #0de0cc;
    border-right: 1px solid #1e2c5c;
    padding: 6px 4px;
    font-weight: 800;
    font-size: 11px;
}

QTableWidget QComboBox {
    padding: 2px 6px;
    font-size: 12px;
}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #131c44;
    color: #f8fafc;
    border: 1px solid #2b3c78;
    border-radius: 5px;
    padding: 5px 8px;
}

QComboBox:hover, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #0de0cc;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background-color: #131c44;
    color: #f8fafc;
    selection-background-color: #1648a8;
    border: 1px solid #0de0cc;
}

QCheckBox {
    spacing: 8px;
    color: #e2e8f0;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #354a91;
    background-color: #0e1535;
}

QCheckBox::indicator:checked {
    background-color: #0de0cc;
    border-color: #0de0cc;
}

QGroupBox {
    border: 1px solid #223166;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 700;
    color: #0de0cc;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}

QListWidget {
    background-color: #0a1029;
    border: 1px solid #202f63;
    border-radius: 5px;
    padding: 4px;
}

QListWidget::item {
    padding: 7px 10px;
    border-bottom: 1px solid #162049;
}

QListWidget::item:selected {
    background-color: #163b69;
    color: #ffffff;
}

QProgressBar {
    background-color: #090e24;
    border: 1px solid #25356e;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-weight: 800;
    font-size: 11px;
    height: 20px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0aa89e, stop:1 #0de0cc);
    border-radius: 3px;
}

QScrollBar:vertical {
    background: #090e24;
    width: 9px;
    margin: 0px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #283a75;
    min-height: 26px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #0de0cc;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    height: 0px;
}

QScrollBar:horizontal {
    background: #090e24;
    height: 9px;
    margin: 0px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #283a75;
    min-width: 26px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #0de0cc;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
    width: 0px;
}

QStatusBar {
    background-color: #060a1b;
    color: #8ea0c8;
    border-top: 1px solid #1c2856;
}

QMenu {
    background-color: #101738;
    color: #eef3ff;
    border: 1px solid #2b3c78;
    border-radius: 5px;
    padding: 4px;
}

QMenu::item {
    padding: 7px 18px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #1648a8;
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background: #1f2d5c;
    margin: 4px 8px;
}

/* ---------------- Start Screen ---------------- */
QWidget#StartScreen {
    background: qradialgradient(cx:0.25, cy:0.15, radius:1.0, stop:0 #142254, stop:0.55 #0b1230, stop:1 #06091a);
}

QFrame#StartHeroCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #111b44, stop:1 #0c1433);
    border: 1px solid #263a7a;
    border-top: 3px solid #0de0cc;
    border-radius: 10px;
}

QFrame#ContinueCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10244a, stop:1 #132c59);
    border: 1px solid #0de0cc;
    border-left: 5px solid #0de0cc;
    border-radius: 8px;
}

QLabel#StartTitle {
    font-size: 30px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 1.2px;
}

QLabel#StartTagline {
    font-size: 13px;
    color: #9bb0db;
}

/* ---------------- Left Sidebar Navigation ---------------- */
QFrame#SideNav {
    background-color: #0a1029;
    border-right: 1px solid #1c2957;
}

QPushButton#NavButton {
    background-color: transparent;
    color: #93a7d1;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    padding: 11px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 700;
}

QPushButton#NavButton:hover {
    background-color: #111b42;
    color: #ffffff;
}

QPushButton#NavButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #152b5e, stop:1 #0e183b);
    color: #ffffff;
    border-left: 3px solid #0de0cc;
}

QLabel#NavSectionLabel {
    color: #5c709e;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
    padding: 10px 14px 4px 14px;
}

/* ---------------- Dashboard Action Center & Filter Pills ---------------- */
QPushButton#ActionItemButton {
    background-color: #131c44;
    color: #eef3ff;
    border: 1px solid #263875;
    border-left: 3px solid #fbbf24;
    border-radius: 5px;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
}

QPushButton#ActionItemButton:hover {
    background-color: #1b285e;
    border-color: #0de0cc;
}

QPushButton#ActionItemButton[severity="danger"] {
    border-left: 3px solid #eb297a;
}

QPushButton#ActionItemButton[severity="ok"] {
    border-left: 3px solid #34d399;
}

QPushButton#FilterPill {
    background-color: #11183c;
    color: #8ea0c8;
    border: 1px solid #23336b;
    border-radius: 4px;
    padding: 5px 11px;
    font-size: 12px;
    font-weight: 700;
}

QPushButton#FilterPill:hover {
    color: #ffffff;
    border-color: #0de0cc;
}

QPushButton#FilterPill:checked {
    background-color: #1648a8;
    color: #ffffff;
    border-color: #0de0cc;
}
"""
