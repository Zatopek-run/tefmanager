"""Start screen (Schermo di Partenza): Continue, New Career/Mode setup, and Save Slot management."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from views import theme
from controllers.game_controller import GameController
from models.database import SaveSlotInfo
from models.entities import GAME_MODE_OPTIONS, CompetitionTier
from models.generator import LAZIO_PROVINCES


def tier_label(raw: str) -> str:
    """Nome mostrato del livello a partire dal testo salvato nel DB (Q18); un valore sconosciuto resta com'è."""
    try:
        return CompetitionTier(raw).display_name
    except ValueError:
        return raw


class StartScreen(QWidget):
    """Landing screen displayed on startup and when returning to the main menu."""

    game_ready = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("StartScreen")
        self._slots: List[SaveSlotInfo] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 24)
        outer.setSpacing(18)

        container = QWidget()
        container.setMinimumWidth(860)
        container.setMaximumWidth(1040)
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # Hero banner
        hero = QFrame()
        hero.setObjectName("StartHeroCard")
        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(24, 20, 24, 20)
        hero_lay.setSpacing(16)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(4)
        title = QLabel("TRACK & FIELD MANAGER")
        title.setObjectName("StartTitle")
        tagline = QLabel(
            "Gestionale di Atletica Leggera — Pista, Concorsi, Staffette, Vivaio & Diretta Gare 3D"
        )
        tagline.setObjectName("StartTagline")
        hero_text.addWidget(title)
        hero_text.addWidget(tagline)
        hero_lay.addLayout(hero_text, stretch=1)

        self.slots_badge = QLabel("Nessun salvataggio")
        self.slots_badge.setObjectName("TierBadge")
        hero_lay.addWidget(self.slots_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(hero)

        # Continue most recent career card
        self.continue_card = QFrame()
        self.continue_card.setObjectName("ContinueCard")
        cont_lay = QHBoxLayout(self.continue_card)
        cont_lay.setContentsMargins(22, 16, 22, 16)
        cont_lay.setSpacing(16)

        cont_info = QVBoxLayout()
        cont_info.setSpacing(4)
        cont_kicker = QLabel("CONTINUA ULTIMA PARTITA")
        cont_kicker.setObjectName("CardTitle")
        self.cont_club = QLabel("Atletica Aurora")
        self.cont_club.setObjectName("CardValue")
        self.cont_meta = QLabel("")
        self.cont_meta.setObjectName("SubTitle")
        cont_info.addWidget(cont_kicker)
        cont_info.addWidget(self.cont_club)
        cont_info.addWidget(self.cont_meta)
        cont_lay.addLayout(cont_info, stretch=1)

        self.continue_btn = QPushButton("Continua Partita")
        self.continue_btn.setObjectName("AdvanceWeekButton")
        self.continue_btn.setMinimumHeight(44)
        self.continue_btn.clicked.connect(self._on_continue)
        cont_lay.addWidget(self.continue_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self.continue_card)

        # Lower split: New Game setup (left) + Save Slots list (right)
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # Left: New Game card
        new_panel = QFrame()
        new_panel.setObjectName("SectionPanel")
        new_lay = QVBoxLayout(new_panel)
        new_lay.setContentsMargins(20, 18, 20, 18)
        new_lay.setSpacing(10)

        new_title = QLabel("Nuova Società")
        new_title.setObjectName("SectionHeader")
        new_lay.addWidget(new_title)

        new_sub = QLabel(
            "Scegli il nome del club, la modalità e la provincia iniziale per iniziare una nuova avventura."
        )
        new_sub.setObjectName("SubTitle")
        new_sub.setWordWrap(True)
        new_lay.addWidget(new_sub)

        lbl_name = QLabel("Nome della Società Sportiva")
        lbl_name.setObjectName("CardTitle")
        new_lay.addWidget(lbl_name)
        self.name_input = QLineEdit("Atletica Aurora")
        self.name_input.setPlaceholderText("Es. Atletica Roma Sud")
        new_lay.addWidget(self.name_input)

        lbl_mode = QLabel("Modalità di Gioco")
        lbl_mode.setObjectName("CardTitle")
        new_lay.addWidget(lbl_mode)
        self.mode_combo = QComboBox()
        for mode, label in GAME_MODE_OPTIONS:
            self.mode_combo.addItem(label, mode)
        self.mode_combo.currentIndexChanged.connect(lambda _i: self._update_mode_hint())
        new_lay.addWidget(self.mode_combo)

        self.mode_hint = QLabel("")
        self.mode_hint.setObjectName("SubTitle")
        self.mode_hint.setWordWrap(True)
        new_lay.addWidget(self.mode_hint)

        lbl_prov = QLabel("Provincia di Partenza (Lazio)")
        lbl_prov.setObjectName("CardTitle")
        new_lay.addWidget(lbl_prov)
        self.province_combo = QComboBox()
        self.province_combo.addItem("Standard (Selezione Lazio)", None)
        for prov in LAZIO_PROVINCES:
            self.province_combo.addItem(f"{prov} (società reali dal CSV)", prov)
        new_lay.addWidget(self.province_combo)

        new_lay.addStretch()

        self.start_new_btn = QPushButton("Avvia Nuova Partita")
        self.start_new_btn.setObjectName("PrimaryButton")
        self.start_new_btn.setMinimumHeight(40)
        self.start_new_btn.clicked.connect(self._on_start_new)
        new_lay.addWidget(self.start_new_btn)

        columns.addWidget(new_panel, stretch=4)

        # Right: Save slots
        saves_panel = QFrame()
        saves_panel.setObjectName("SectionPanel")
        saves_lay = QVBoxLayout(saves_panel)
        saves_lay.setContentsMargins(20, 18, 20, 18)
        saves_lay.setSpacing(10)

        saves_head = QHBoxLayout()
        saves_title = QLabel("Salvataggi")
        saves_title.setObjectName("SectionHeader")
        saves_head.addWidget(saves_title)
        saves_head.addStretch()
        self.saves_hint = QLabel("Doppio clic per caricare")
        self.saves_hint.setObjectName("SubTitle")
        saves_head.addWidget(self.saves_hint)
        saves_lay.addLayout(saves_head)

        self.saves_table = QTableWidget(0, 6)
        self.saves_table.setHorizontalHeaderLabels(
            ["Società", "Modalità", "Categoria", "Sett.", "Bilancio", "Salvato"]
        )
        self.saves_table.setAlternatingRowColors(True)
        self.saves_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.saves_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.saves_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.saves_table.verticalHeader().setVisible(False)
        self.saves_table.verticalHeader().setDefaultSectionSize(34)
        sh = self.saves_table.horizontalHeader()
        sh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        sh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.saves_table.cellDoubleClicked.connect(lambda _r, _c: self._on_load_selected())
        self.saves_table.itemSelectionChanged.connect(self._update_slot_buttons)
        saves_lay.addWidget(self.saves_table, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.load_btn = QPushButton("Carica Selezionato")
        self.load_btn.setObjectName("PrimaryButton")
        self.load_btn.clicked.connect(self._on_load_selected)
        self.delete_btn = QPushButton("Elimina")
        self.delete_btn.setObjectName("DangerButton")
        self.delete_btn.clicked.connect(self._on_delete_selected)
        self.quit_btn = QPushButton("Esci")
        self.quit_btn.clicked.connect(self.quit_requested.emit)
        btn_row.addWidget(self.load_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.quit_btn)
        saves_lay.addLayout(btn_row)

        columns.addWidget(saves_panel, stretch=6)
        root.addLayout(columns, stretch=1)

        outer.addStretch(1)
        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(container, stretch=1)
        center_row.addStretch()
        outer.addLayout(center_row, stretch=10)
        outer.addStretch(1)

        self._update_mode_hint()

    def _update_mode_hint(self) -> None:
        mode = self.mode_combo.currentData()
        if mode == "career":
            self.mode_hint.setText(
                "Stagioni complete da 36 settimane con promozioni, retrocessioni e tutte le discipline."
            )
        else:
            self.mode_hint.setText(
                "Sessione breve di prova: 10 atleti, 3 discipline (100m, Lungo, 1500m) e 2 gare."
            )

    def refresh(self) -> None:
        self._slots = self.controller.list_save_slots()
        n = len(self._slots)
        self.slots_badge.setText(
            "Nessun salvataggio" if n == 0 else ("1 salvataggio" if n == 1 else f"{n} salvataggi")
        )

        latest = self._latest_supported_slot()
        if latest is not None:
            self.continue_card.setVisible(True)
            status_tag = " · SOCIETÀ FALLITA" if latest.bankrupt else ""
            self.cont_club.setText(latest.team_name)
            self.cont_meta.setText(
                f"Cat. {tier_label(latest.tier)}  •  {latest.mode_label}  •  "
                f"Stagione {latest.season_number}, Sett. {latest.week} ({latest.in_game_date:%d %b %Y})  •  "
                f"Bilancio €{latest.budget:,}  ·  Prestigio {latest.prestige}{status_tag}"
            )
        else:
            self.continue_card.setVisible(False)

        self.saves_table.setRowCount(n)
        for row, s in enumerate(self._slots):
            mode_short = "Prototipo" if s.game_mode == "vertical_slice" else "Carriera"
            vals = [
                s.team_name,
                mode_short,
                tier_label(s.tier),
                f"S{s.season_number}·W{s.week}",
                f"€{s.budget:,}",
                s.updated_at.strftime("%d/%m %H:%M"),
            ]
            if not s.is_supported:  # solo i metadati affidabili: file, data, versione
                vals = [s.team_name, "—", "—", "—", f"{s.size_bytes // 1024} KiB", vals[5]]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                    if col == 0
                    else Qt.AlignmentFlag.AlignCenter
                )
                if col == 4 and s.budget < 0:
                    item.setForeground(QColor(theme.BAD))
                if not s.is_supported:
                    item.setForeground(QColor(theme.WARN))
                    item.setToolTip(f"{s.path.name} — versione del salvataggio: v{s.schema_version}")
                self.saves_table.setItem(row, col, item)

        if n > 0:
            self.saves_table.selectRow(0)
        self._update_slot_buttons()

    def _selected_slot(self) -> Optional[SaveSlotInfo]:
        rows = self.saves_table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._slots):
            return self._slots[idx]
        return None

    def _update_slot_buttons(self) -> None:
        has_sel = self._selected_slot() is not None
        self.load_btn.setEnabled(has_sel)
        self.delete_btn.setEnabled(has_sel)

    def _latest_supported_slot(self) -> Optional[SaveSlotInfo]:
        """Lo slot più recente che il gioco sa aprire (gli altri compaiono solo nell'elenco)."""
        return next((s for s in self._slots if s.is_supported), None)

    def _show_load_error(self) -> None:
        """Avvisa che lo slot non si è aperto: testo breve + dettagli (backup e traceback)."""
        text, _, details = self.controller.last_load_error.partition("\n\n")
        box = QMessageBox(
            QMessageBox.Icon.Warning, "Impossibile aprire il salvataggio", text, parent=self
        )
        if details:
            box.setDetailedText(details)
        box.exec()

    def _load_slot(self, slot: SaveSlotInfo) -> None:
        if self.controller.load_save_slot(slot.path):
            self.game_ready.emit()
        elif self.controller.last_load_error:
            self._show_load_error()

    def _on_continue(self) -> None:
        slot = self._latest_supported_slot()
        if slot is not None:
            self._load_slot(slot)

    def _on_load_selected(self) -> None:
        slot = self._selected_slot()
        if slot is not None:
            self._load_slot(slot)

    def _on_delete_selected(self) -> None:
        slot = self._selected_slot()
        if slot is None:
            return
        ans = QMessageBox.question(
            self,
            "Elimina Salvataggio",
            f"Eliminare definitivamente il salvataggio di '{slot.team_name}' (Sett. {slot.week})?"
            if slot.is_supported
            else f"Eliminare definitivamente il file '{slot.path.name}'? Non è apribile da questa versione.",
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.controller.delete_save_slot(slot.path)
            self.refresh()

    def _on_start_new(self) -> None:
        name = self.name_input.text().strip() or "Atletica Aurora"
        mode = str(self.mode_combo.currentData())
        prov_data = self.province_combo.currentData()
        province = str(prov_data) if prov_data else None
        self.controller.start_new_game(team_name=name, game_mode=mode, province=province)
        self.game_ready.emit()
