"""Modern dark sports-management QSS stylesheet for Track & Field Manager."""

DARK_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #0f172a;
    color: #e2e8f0;
    font-family: "Segoe UI", "Inter", Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #e2e8f0;
}

QFrame#HeaderBar {
    background-color: #111c33;
    border-bottom: 1px solid #26354d;
}

QFrame#StatCard {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
}

QFrame#SectionPanel {
    background-color: #162033;
    border: 1px solid #29384f;
    border-radius: 10px;
}

QLabel#AppTitle {
    font-size: 20px;
    font-weight: 700;
    color: #f8fafc;
}

QLabel#SubTitle {
    font-size: 12px;
    color: #94a3b8;
}

QLabel#CardTitle {
    font-size: 11px;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
}

QLabel#CardValue {
    font-size: 22px;
    font-weight: 700;
    color: #f8fafc;
}

QLabel#SectionHeader {
    font-size: 15px;
    font-weight: 700;
    color: #f1f5f9;
}

QLabel#TierBadge {
    background-color: #1e3a5f;
    color: #38bdf8;
    border: 1px solid #2563eb;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 700;
    font-size: 12px;
}

QLabel#CompAlertBadge {
    background-color: #422006;
    color: #fbbf24;
    border: 1px solid #d97706;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 700;
    font-size: 12px;
}

QPushButton {
    background-color: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 7px;
    padding: 7px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #273549;
    border-color: #475569;
}

QPushButton:pressed {
    background-color: #0f172a;
}

QPushButton#AdvanceWeekButton {
    background-color: #10b981;
    color: #042f2e;
    border: none;
    border-radius: 8px;
    padding: 10px 22px;
    font-size: 14px;
    font-weight: 800;
}

QPushButton#AdvanceWeekButton:hover {
    background-color: #34d399;
}

QPushButton#AdvanceWeekButton:pressed {
    background-color: #059669;
}

QPushButton#PrimaryButton {
    background-color: #0284c7;
    color: #f8fafc;
    border: none;
}

QPushButton#PrimaryButton:hover {
    background-color: #0ea5e9;
}

QPushButton#DangerButton {
    background-color: #7f1d1d;
    color: #fecaca;
    border: 1px solid #991b1b;
}

QPushButton#DangerButton:hover {
    background-color: #991b1b;
}

QTabWidget::pane {
    border: 1px solid #29384f;
    border-radius: 8px;
    background-color: #111827;
    top: -1px;
}

QTabBar::tab {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #29384f;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 9px 18px;
    margin-right: 4px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #111827;
    color: #38bdf8;
    border-bottom: 2px solid #38bdf8;
}

QTabBar::tab:hover:!selected {
    color: #e2e8f0;
    background-color: #263449;
}

QTableWidget {
    background-color: #0f172a;
    alternate-background-color: #141f33;
    gridline-color: #243247;
    border: 1px solid #29384f;
    border-radius: 6px;
    selection-background-color: #1e3a5f;
    selection-color: #f8fafc;
}

QHeaderView::section {
    background-color: #1e293b;
    color: #cbd5e1;
    border: none;
    border-bottom: 1px solid #334155;
    border-right: 1px solid #243247;
    padding: 7px 8px;
    font-weight: 700;
    font-size: 12px;
}

QComboBox, QLineEdit {
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px 8px;
}

QComboBox:hover, QLineEdit:focus {
    border-color: #38bdf8;
}

QComboBox QAbstractItemView {
    background-color: #1e293b;
    color: #f1f5f9;
    selection-background-color: #0284c7;
    border: 1px solid #334155;
}

QListWidget {
    background-color: #0f172a;
    border: 1px solid #29384f;
    border-radius: 6px;
    padding: 4px;
}

QListWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #1e293b;
}

QProgressBar {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #f8fafc;
    font-weight: 600;
    height: 18px;
}

QProgressBar::chunk {
    background-color: #0ea5e9;
    border-radius: 5px;
}

QStatusBar {
    background-color: #0b1220;
    color: #94a3b8;
    border-top: 1px solid #1e293b;
}
"""
