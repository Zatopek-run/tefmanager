"""Modal dialogs for Competition Results, Scouting, Ethical Dilemmas, and New Career."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
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
)

from models.entities import Athlete, CompetitionSummary, EthicalDilemma
from models.generator import get_recruitment_fee


class CompetitionResultsDialog(QDialog):
    """Displays simulated competition results including wind legality, weather, and records."""

    def __init__(self, summary: CompetitionSummary, parent=None) -> None:
        super().__init__(parent)
        self.summary = summary
        self.setWindowTitle(f"Risultati Gara — {summary.meet_name}")
        self.resize(880, 640)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        title = QLabel(f"{self.summary.meet_name} (Settimana {self.summary.week})")
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        venue = (
            f"In casa ({self.summary.spectators:,} spettatori)"
            if self.summary.is_home
            else "In trasferta"
        )
        conditions = QLabel(
            f"Stagione: {self.summary.season_phase.value}  |  "
            f"Meteo: {self.summary.weather.value}  |  "
            f"Pista: {self.summary.track_surface}  |  {venue}"
        )
        conditions.setObjectName("SubTitle")
        layout.addWidget(conditions)

        gate = (
            f"Biglietti: +${self.summary.ticket_income:,}"
            if self.summary.is_home
            else f"Trasferta Pullman: -${self.summary.travel_cost:,}"
        )
        team_place = self.summary.team_placement
        team_txt = (
            f"Società: {team_place}ª su {len(self.summary.team_standings)}   |   "
            if team_place
            else ""
        )
        totals = QLabel(
            f"{team_txt}Premi Totali: ${self.summary.total_prize_money:,}   |   "
            f"{gate}   |   Prestigio: +{self.summary.total_prestige_gained}"
        )
        totals.setObjectName("SectionHeader")
        layout.addWidget(totals)

        if self.summary.promoted_to is not None:
            promo = QFrame()
            promo.setObjectName("StatCard")
            promo_layout = QHBoxLayout(promo)
            promo_label = QLabel(
                f"PROMOZIONE SBLOCCATA: Benvenuto in categoria {self.summary.promoted_to.value}!"
            )
            promo_label.setStyleSheet("color: #34d399; font-weight: 800; font-size: 14px;")
            promo_layout.addWidget(promo_label)
            layout.addWidget(promo)

        summary_label = QLabel("Piazzamenti della squadra (seleziona una gara per la classifica completa):")
        summary_label.setObjectName("SubTitle")
        layout.addWidget(summary_label)

        self.events_table = QTableWidget(len(self.summary.event_results), 8)
        self.events_table.setHorizontalHeaderLabels(
            ["Gara", "Atleta", "Atteggiamento", "Misura / Tempo", "Vento", "Posizione", "Premio", "Note"]
        )
        self.events_table.setAlternatingRowColors(True)
        self.events_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.events_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.events_table.verticalHeader().setVisible(False)

        for row, res in enumerate(self.summary.event_results):
            if res.wind_ms is None:
                wind_str = "—"
            elif res.wind_illegal:
                wind_str = f"{res.wind_ms:+.1f} m/s (w)"
            else:
                wind_str = f"{res.wind_ms:+.1f} m/s"

            notes = []
            if res.withdrew_injured:
                notes.append("Ritirato per infortunio")
            if res.is_club_record:
                notes.append("RECORD SOCIALE!")
            elif res.is_pb:
                notes.append("PB")
            if res.wind_illegal:
                notes.append("Vento > 2.0 (non omol.)")
            note_str = " · ".join(notes) if notes else "—"

            items = [
                QTableWidgetItem(res.event_name),
                QTableWidgetItem(res.player_athlete_name),
                QTableWidgetItem(res.attitude),
                QTableWidgetItem(res.player_mark),
                QTableWidgetItem(wind_str),
                QTableWidgetItem(
                    "RIT." if res.withdrew_injured else f"#{res.placement} / {res.total_competitors}"
                ),
                QTableWidgetItem(f"${res.prize_money:,}"),
                QTableWidgetItem(note_str),
            ]
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if res.withdrew_injured:
                    item.setForeground(QColor("#f87171"))
                elif col == 4 and res.wind_illegal:
                    item.setForeground(QColor("#fbbf24"))
                elif res.placement == 1:
                    item.setForeground(QColor("#fbbf24"))
                elif res.placement <= 3:
                    item.setForeground(QColor("#34d399"))
                self.events_table.setItem(row, col, item)

        self.events_table.itemSelectionChanged.connect(self._on_event_selected)
        layout.addWidget(self.events_table, stretch=1)

        lower = QHBoxLayout()
        lower.setSpacing(12)

        standings_box = QVBoxLayout()
        standings_label = QLabel("Ordine d'arrivo completo:")
        standings_label.setObjectName("SectionHeader")
        standings_box.addWidget(standings_label)
        self.standings_table = QTableWidget(0, 4)
        self.standings_table.setHorizontalHeaderLabels(["Pos", "Atleta", "Società", "Risultato"])
        self.standings_table.setAlternatingRowColors(True)
        self.standings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.standings_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.standings_table.verticalHeader().setVisible(False)
        standings_box.addWidget(self.standings_table)
        lower.addLayout(standings_box, stretch=3)

        team_box = QVBoxLayout()
        team_label = QLabel("Classifica Società (meeting):")
        team_label.setObjectName("SectionHeader")
        team_box.addWidget(team_label)
        self.team_table = QTableWidget(len(self.summary.team_standings), 3)
        self.team_table.setHorizontalHeaderLabels(["Pos", "Società", "Punti"])
        self.team_table.setAlternatingRowColors(True)
        self.team_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.team_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.team_table.verticalHeader().setVisible(False)
        for row, (team, pts) in enumerate(self.summary.team_standings):
            for col, text in enumerate((str(row + 1), team, str(pts))):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if team == self.summary.player_team:
                    item.setForeground(QColor("#38bdf8"))
                self.team_table.setItem(row, col, item)
        team_box.addWidget(self.team_table)
        lower.addLayout(team_box, stretch=2)

        layout.addLayout(lower, stretch=1)

        if self.summary.event_results:
            self.events_table.selectRow(0)
            self._populate_standings(0)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Chiudi Riepilogo")
        close_btn.setObjectName("PrimaryButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_event_selected(self) -> None:
        rows = self.events_table.selectionModel().selectedRows()
        if rows:
            self._populate_standings(rows[0].row())

    def _populate_standings(self, event_idx: int) -> None:
        if not (0 <= event_idx < len(self.summary.event_results)):
            return
        standings = self.summary.event_results[event_idx].standings
        self.standings_table.setRowCount(len(standings))
        for row, s in enumerate(standings):
            mark_txt = f"{s.mark_display} (w)" if s.wind_illegal else s.mark_display
            vals = [f"#{s.placement}", s.athlete_name, s.team_name, mark_txt]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if s.is_player:
                    item.setForeground(QColor("#38bdf8"))
                self.standings_table.setItem(row, col, item)


class RecruitAthleteDialog(QDialog):
    """Scouting dialog featuring Campionati Studenteschi youth talents & free agents."""

    def __init__(self, prospects: List[Athlete], budget: int, parent=None) -> None:
        super().__init__(parent)
        self.prospects = prospects
        self.budget = budget
        self.selected_prospect: Optional[Athlete] = None
        self.setWindowTitle("Scouting & Campionati Studenteschi")
        self.resize(940, 440)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        header = QLabel(f"Talenti Osservati (Budget Disponibile: ${self.budget:,})")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        sub = QLabel(
            "I ragazzi dei Campionati Studenteschi (15-17 anni) hanno alto Potenziale ma vanno fatti maturare con pazienza."
        )
        sub.setObjectName("SubTitle")
        layout.addWidget(sub)

        self.table = QTableWidget(len(self.prospects), 11)
        self.table.setHorizontalHeaderLabels(
            [
                "Nome",
                "Età",
                "Provenienza",
                "Disciplina",
                "OVR",
                "Potenziale",
                "Resilienza",
                "Carattere",
                "Ingaggio/sett",
                "Costo",
                "Note",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)

        for row, a in enumerate(self.prospects):
            fee = get_recruitment_fee(a)
            origin = "Camp. Studenteschi" if a.is_youth_prospect else "Svincolato"
            note = f"Vel {a.speed} · Res {a.stamina} · Tec {a.technique}"
            vals = [
                a.name,
                str(a.age),
                origin,
                a.specialty.value,
                str(a.overall),
                str(a.potential),
                str(a.resilience),
                a.personality.value,
                f"${a.weekly_wage}",
                f"${fee:,}",
                note,
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 5 and a.potential >= 85:
                    item.setForeground(QColor("#34d399"))
                elif col == 9 and fee > self.budget:
                    item.setForeground(QColor("#f87171"))
                self.table.setItem(row, col, item)

        if self.prospects:
            self.table.selectRow(0)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        sign_btn = QPushButton("Tessera Atleta Selezionato")
        sign_btn.setObjectName("PrimaryButton")
        sign_btn.clicked.connect(self._on_sign)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(sign_btn)
        layout.addLayout(btn_row)

    def _on_sign(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        prospect = self.prospects[rows[0].row()]
        fee = get_recruitment_fee(prospect)
        if fee > self.budget:
            QMessageBox.warning(
                self,
                "Budget Insufficiente",
                f"Servono ${fee:,} per tesserare {prospect.name}, ma hai ${self.budget:,}.",
            )
            return
        self.selected_prospect = prospect
        self.accept()


class EthicalDilemmaDialog(QDialog):
    """Modal presenting an ethical choice with sporting vs moral trade-offs."""

    def __init__(self, dilemma: EthicalDilemma, parent=None) -> None:
        super().__init__(parent)
        self.dilemma = dilemma
        self.accepted_shortcut: bool = False
        self.setWindowTitle(f"Dilemma Etico — {dilemma.title}")
        self.resize(540, 280)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(self.dilemma.title)
        title.setObjectName("AppTitle")
        title.setStyleSheet("color: #fbbf24; font-size: 18px; font-weight: 800;")
        layout.addWidget(title)

        desc = QLabel(self.dilemma.description)
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 13px; color: #e2e8f0;")
        layout.addWidget(desc)
        layout.addStretch()

        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)

        accept_btn = QPushButton(self.dilemma.accept_label)
        accept_btn.setObjectName("DangerButton")
        accept_btn.clicked.connect(self._choose_accept)

        reject_btn = QPushButton(self.dilemma.reject_label)
        reject_btn.setObjectName("PrimaryButton")
        reject_btn.clicked.connect(self._choose_reject)

        btn_col.addWidget(accept_btn)
        btn_col.addWidget(reject_btn)
        layout.addLayout(btn_col)

    def _choose_accept(self) -> None:
        self.accepted_shortcut = True
        self.accept()

    def _choose_reject(self) -> None:
        self.accepted_shortcut = False
        self.accept()


class NewGameDialog(QDialog):
    """Dialog to choose club name and game mode (Vertical Slice Prototype vs Full Career)."""

    def __init__(self, default_name: str = "Atletica Aurora", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nuova Partita — Track & Field Manager")
        self.resize(460, 220)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        label = QLabel("Nome della Società Sportiva:")
        label.setObjectName("SectionHeader")
        layout.addWidget(label)

        self.name_input = QLineEdit(default_name)
        layout.addWidget(self.name_input)

        mode_label = QLabel("Modalità di Gioco:")
        mode_label.setObjectName("SectionHeader")
        layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem(
            "Prototipo Outdoor (10 atleti, 3 discipline, 2 gare)", "vertical_slice"
        )
        self.mode_combo.addItem(
            "Carriera Completa (Stagioni Outdoor/Cross/Indoor)", "career"
        )
        layout.addWidget(self.mode_combo)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        start_btn = QPushButton("Avvia Stagione")
        start_btn.setObjectName("PrimaryButton")
        start_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(start_btn)
        layout.addLayout(btn_row)

    @property
    def club_name(self) -> str:
        return self.name_input.text().strip() or "Atletica Aurora"

    @property
    def game_mode(self) -> str:
        return str(self.mode_combo.currentData())
