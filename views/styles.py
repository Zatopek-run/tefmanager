"""Foglio di stile del gioco (PIANOLAVORO G): **generato dai token** di `views/theme.py`, una sola fonte per tutta l'interfaccia.

Cambiare un colore, un raggio o una dimensione in `theme.py` lo cambia ovunque. Niente più valori scritti a mano qui dentro: i segnaposto
`$nome` sono sostituiti con `_tokens()`. Le viste disegnate a mano (`widgets.py`, QML) leggono gli stessi token.
"""
from __future__ import annotations

from string import Template

from views import theme as t


def _tokens() -> dict:
    return {
        "bg": t.BG, "bgRaised": t.BG_RAISED, "surface": t.SURFACE, "surface2": t.SURFACE_2, "border": t.BORDER,
        "borderStrong": t.BORDER_STRONG, "text": t.TEXT, "muted": t.TEXT_MUTED, "faint": t.TEXT_FAINT, "accent": t.ACCENT,
        "accentDim": t.ACCENT_DIM, "good": t.GOOD, "warn": t.WARN, "bad": t.BAD, "info": t.INFO, "orange": t.ORANGE,
        "fonts": t.font_stack(),
        "xs": t.FS_XS, "sm": t.FS_SM, "md": t.FS_MD, "lg": t.FS_LG, "xl": t.FS_XL, "xxl": t.FS_XXL,
        "sp1": t.SP_1, "sp2": t.SP_2, "sp3": t.SP_3, "sp4": t.SP_4, "sp5": t.SP_5,
        "rsm": t.RADIUS_SM, "rmd": t.RADIUS_MD, "rlg": t.RADIUS_LG,
        # tinte trasparenti dei colori di stato (sfondi di pillole e avvisi)
        "goodTint": "rgba(52, 211, 153, 0.13)", "goodLine": "rgba(52, 211, 153, 0.5)",
        "warnTint": "rgba(251, 191, 36, 0.13)", "warnLine": "rgba(251, 191, 36, 0.5)",
        "badTint": "rgba(248, 113, 113, 0.14)", "badLine": "rgba(248, 113, 113, 0.55)",
        "accentTint": "rgba(25, 211, 192, 0.12)", "hover": "#1d2858", "pressed": "#0c122d",
        "primary": "#1b4fb8", "primaryHover": "#2563eb",
    }


_QSS = Template("""
/* ============ Base ============ */
QMainWindow, QDialog { background-color: $bg; color: $text; font-family: $fonts; font-size: ${md}px; }
QWidget { color: $text; font-family: $fonts; }
QWidget#DashboardPage { background-color: $bg; }
QScrollArea { background: transparent; border: none; }
QToolTip { background-color: $surface2; color: $text; border: 1px solid $borderStrong; border-radius: ${rsm}px; padding: 5px 8px; }

/* ============ Testi ============ */
QLabel#PageTitle { font-size: ${xl}px; font-weight: 700; color: $text; }
QLabel#AppTitle { font-size: ${xl}px; font-weight: 700; color: $text; }
QLabel#SubTitle { font-size: ${sm}px; color: $muted; }
QLabel#SectionHeader { font-size: ${md}px; font-weight: 700; color: $text; letter-spacing: 0.3px; }
QLabel#CardHeading { font-size: ${md}px; font-weight: 700; color: $text; }
QLabel#CardHint { font-size: ${sm}px; color: $muted; }
QLabel#CardLead { font-size: ${lg}px; font-weight: 600; color: $text; }
QLabel#CardTitle { font-size: ${xs}px; font-weight: 600; color: $muted; letter-spacing: 0.6px; }
QLabel#CardValue { font-size: ${xxl}px; font-weight: 700; color: $text; }
QLabel#NavSectionLabel { color: $faint; font-size: ${xs}px; font-weight: 700; letter-spacing: 1px; padding: 14px 18px 4px 18px; }

/* ============ Schede (Card, StatCard, SectionPanel) ============ */
QFrame#Card, QFrame#SectionPanel { background-color: $surface; border: 1px solid $border; border-radius: ${rlg}px; }
QFrame#Card QLabel, QFrame#SectionPanel QLabel, QFrame#StatCard QLabel { background: transparent; }
QFrame#StatCard { background-color: $surface; border: 1px solid $border; border-radius: ${rlg}px; }
QFrame#StatCard:hover { border-color: $accentDim; background-color: $surface2; }

/* ============ Intestazione e barra laterale ============ */
QFrame#HeaderBar { background-color: $bgRaised; border: none; border-bottom: 1px solid $border; }
QFrame#SideNav { background-color: $bgRaised; border: none; border-right: 1px solid $border; }
QPushButton#NavButton {
    background-color: transparent; color: $muted; border: none; border-left: 3px solid transparent; border-radius: 0px;
    padding: 10px 14px 10px 16px; text-align: left; font-size: ${md}px; font-weight: 600;
}
QPushButton#NavButton:hover { background-color: $surface; color: $text; }
QPushButton#NavButton:checked { background-color: $accentTint; color: $text; border-left: 3px solid $accent; font-weight: 700; }
QLabel#TierBadge { background-color: $surface2; color: $accent; border: 1px solid $accentDim; border-radius: ${rmd}px; padding: 5px 12px; font-weight: 700; font-size: ${sm}px; }
QLabel#CompAlertBadge { background-color: $badTint; color: $bad; border: 1px solid $badLine; border-radius: ${rmd}px; padding: 5px 12px; font-weight: 700; font-size: ${sm}px; letter-spacing: 0.4px; }
QLabel#HudBudgetPill { background-color: $surface; color: $good; border: 1px solid $border; border-radius: ${rmd}px; padding: 6px 12px; font-weight: 700; font-size: ${md}px; }
QLabel#HudPrestigePill { background-color: $surface; color: $warn; border: 1px solid $border; border-radius: ${rmd}px; padding: 6px 12px; font-weight: 700; font-size: ${md}px; }
QStatusBar { background-color: $bgRaised; color: $muted; border-top: 1px solid $border; }

/* ============ Pulsanti ============ */
QPushButton {
    background-color: $surface2; color: $text; border: 1px solid $borderStrong; border-radius: ${rmd}px;
    padding: 6px 12px; font-weight: 600; font-size: ${sm}px;
}
QPushButton:hover { background-color: $hover; border-color: $accent; }
QPushButton:pressed { background-color: $pressed; }
QPushButton:disabled { background-color: $surface; color: $faint; border-color: $border; }
QPushButton:focus { outline: none; }
QPushButton#AdvanceWeekButton { background-color: $accent; color: $bg; border: none; border-radius: ${rmd}px; padding: 9px 20px; font-size: ${md}px; font-weight: 700; }
QPushButton#AdvanceWeekButton:hover { background-color: #3ae3d1; }
QPushButton#AdvanceWeekButton:pressed { background-color: $accentDim; }
QPushButton#AdvanceWeekButton:disabled { background-color: $border; color: $faint; }
QPushButton#PrimaryButton { background-color: $primary; color: #ffffff; border: 1px solid $primaryHover; }
QPushButton#PrimaryButton:hover { background-color: $primaryHover; border-color: $accent; }
QPushButton#DangerButton { background-color: rgba(248, 113, 113, 0.16); color: #ffd5d5; border: 1px solid $badLine; }
QPushButton#DangerButton:hover { background-color: rgba(248, 113, 113, 0.3); border-color: $bad; }
QPushButton#FilterPill { background-color: $surface; color: $muted; border: 1px solid $border; border-radius: 14px; padding: 5px 14px; font-size: ${sm}px; font-weight: 600; }
QPushButton#FilterPill:hover { color: $text; border-color: $accent; }
QPushButton#FilterPill:checked { background-color: $accentTint; color: $accent; border-color: $accentDim; }
QPushButton#ActionItemButton {
    text-align: left; padding: 10px 14px; border-radius: ${rmd}px; font-weight: 500; font-size: ${md}px;
    background-color: $surface2; border: 1px solid $border; border-left: 3px solid $warn; color: $text;
}
QPushButton#ActionItemButton:hover { border-color: $borderStrong; border-left-color: $warn; background-color: $hover; }
QPushButton#ActionItemButton[severity="danger"] { border-left-color: $bad; }
QPushButton#ActionItemButton[severity="ok"] { border-left-color: $good; }

/* ============ Semaforo ============ */
QLabel#StatusPill { font-size: ${sm}px; font-weight: 600; border-radius: 13px; padding: 5px 14px; border: 1px solid $border; }
QLabel#StatusPill[level="ok"] { color: $good; background-color: $goodTint; border-color: $goodLine; }
QLabel#StatusPill[level="warn"] { color: $warn; background-color: $warnTint; border-color: $warnLine; }
QLabel#StatusPill[level="danger"] { color: $bad; background-color: $badTint; border-color: $badLine; }

/* ============ Schede a linguetta ============ */
QTabWidget::pane { border: 1px solid $border; border-radius: ${rmd}px; background-color: $bg; top: -1px; }
QTabBar { background: transparent; }
QTabBar::tab { background-color: transparent; color: $muted; border: none; border-bottom: 2px solid transparent; padding: 10px 18px; margin-right: 2px; font-weight: 600; font-size: ${sm}px; }
QTabBar::tab:selected { color: $text; border-bottom: 2px solid $accent; }
QTabBar::tab:hover:!selected { color: $text; background-color: $surface; }

/* ============ Tabelle ============ */
QTableWidget {
    background-color: transparent; alternate-background-color: rgba(255, 255, 255, 0.025); border: 1px solid $border; border-radius: ${rmd}px;
    gridline-color: $border; selection-background-color: $surface2; selection-color: $text; outline: none;
}
QTableWidget::item { padding: 3px 6px; border-bottom: 1px solid $border; }
QTableWidget::item:selected { background-color: $surface2; color: $text; }
QHeaderView { background-color: transparent; border: none; }
QTableCornerButton::section { background-color: transparent; border: none; }
QHeaderView::section {
    background-color: $surface; color: $muted; border: none; border-bottom: 1px solid $borderStrong; border-right: 1px solid $border;
    padding: 7px 8px; font-size: ${xs}px; font-weight: 600; letter-spacing: 0.3px;
}
QHeaderView::section:hover { color: $text; }
QTableWidget QComboBox { padding: 2px 6px; font-size: ${sm}px; min-height: 22px; }
QTableWidget QPushButton { padding: 3px 10px; font-size: ${sm}px; }

/* ============ Campi ============ */
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {
    background-color: $surface2; color: $text; border: 1px solid $borderStrong; border-radius: ${rsm}px; padding: 5px 9px; selection-background-color: $accentDim;
}
QComboBox:hover, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background-color: $surface2; color: $text; selection-background-color: $primary; border: 1px solid $accent; outline: none; }
QCheckBox { spacing: 8px; color: $text; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid $borderStrong; background-color: $surface; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background-color: $accent; border-color: $accent; }
QGroupBox { border: 1px solid $border; border-radius: ${rmd}px; margin-top: 14px; padding-top: 12px; font-weight: 700; color: $text; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: $muted; }

/* ============ Liste ============ */
QListWidget { background-color: transparent; border: 1px solid $border; border-radius: ${rmd}px; padding: 4px; outline: none; }
QListWidget::item { padding: 8px 10px; border-bottom: 1px solid $border; }
QListWidget::item:selected { background-color: $surface2; color: $text; }
QListWidget#FlatList { background: transparent; border: none; padding: 0; }
QListWidget#FlatList::item { padding: 8px 4px; }
QListWidget#FlatList::item:hover { background: transparent; }

/* ============ Barre ============ */
QProgressBar { background-color: $bg; border: 1px solid $border; border-radius: 9px; text-align: center; color: $text; font-size: ${xs}px; font-weight: 600; height: 18px; }
QProgressBar::chunk { background-color: $accentDim; border-radius: 8px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $borderStrong; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: $faint; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $borderStrong; border-radius: 4px; min-width: 36px; }
QScrollBar::handle:horizontal:hover { background: $faint; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: none; height: 0px; width: 0px; }

/* ============ Menu ============ */
QMenu { background-color: $surface2; color: $text; border: 1px solid $borderStrong; border-radius: ${rmd}px; padding: 5px; }
QMenu::item { padding: 8px 20px; border-radius: ${rsm}px; }
QMenu::item:selected { background-color: $primary; color: #ffffff; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }

/* ============ Schermata iniziale ============ */
QWidget#StartScreen { background: qradialgradient(cx:0.25, cy:0.15, radius:1.1, stop:0 #131d44, stop:0.6 $bg, stop:1 #060916); }
QFrame#StartHeroCard { background-color: $surface; border: 1px solid $border; border-top: 3px solid $accent; border-radius: ${rlg}px; }
QFrame#ContinueCard { background-color: $accentTint; border: 1px solid $accentDim; border-left: 4px solid $accent; border-radius: ${rmd}px; }
QLabel#StartTitle { font-size: 32px; font-weight: 800; color: $text; letter-spacing: 1px; }
QLabel#StartTagline { font-size: ${md}px; color: $muted; }
""")


def build_stylesheet() -> str:
    """Il foglio di stile completo, con i valori dei token di `views/theme.py`."""
    return _QSS.substitute(_tokens())


DARK_STYLESHEET = build_stylesheet()
