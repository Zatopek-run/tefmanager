"""Tab views: Dashboard, Roster, Youth Academy, Calendar & Meets, Relays, Rivals, Staff & Facilities, Finances."""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from controllers.game_controller import GameController
from views.athlete_dialog import AthleteDetailDialog
from models.entities import (
    BANKRUPTCY_THRESHOLD,
    PROMOTION_SPOTS,
    RELEGATION_SPOTS,
    COACH_COMFORT_LOAD,
    COACH_STAT_LABELS,
    COACH_STATS,
    MAX_SPECIALIZED_COACHES,
    MAX_YOUTH_COACHES,
    RELAY_CHANGE_COOLDOWN_WEEKS,
    RELAYS,
    Athlete,
    harmony_grade,
    EVENTS,
    GYM_MAX_LEVEL,
    GYM_TRAINING_BONUS_PER_LEVEL,
    GYM_UPKEEP_PER_LEVEL,
    STAND_EXPANSION_SEATS,
    STAND_MAX_SEATS,
    TICKET_PRICE,
    WEEKLY_SCOUTING_POINTS,
    YOUTH_SQUAD_MAX,
    CompetitionSummary,
    GameState,
    PeriodizationPhase,
    RaceAttitude,
    Specialty,
    TrainingFocus,
    gym_upgrade_cost,
    stand_expansion_cost,
)
from controllers.game_controller import scouting_search_cost
from models.simulation import expected_event_score, relay_leg_score, weekly_finances
from views.dialogs import CompetitionResultsDialog, HireCoachDialog, RecruitAthleteDialog


def _coach_combo(controller: GameController, state: GameState, athlete: Athlete) -> QComboBox:
    """Dropdown with the coaches allowed to train this athlete (and their current load)."""
    combo = QComboBox()
    combo.addItem("— Nessuno —", None)
    for coach in state.coaches:
        if coach.can_train(athlete):
            combo.addItem(f"{coach.name} ({state.coach_load(coach)} atl.)", coach.id)
    current = state.coach_of(athlete)
    idx = combo.findData(current.id if current is not None else None)
    combo.setCurrentIndex(max(0, idx))
    athlete_id = athlete.id

    def on_change(_index: int) -> None:
        if athlete_id is not None:
            controller.assign_coach(athlete_id, combo.currentData())

    combo.currentIndexChanged.connect(on_change)
    return combo


def _make_stat_card(title: str, value: str = "-") -> tuple[QFrame, QLabel, QLabel]:
    card = QFrame()
    card.setObjectName("StatCard")
    vbox = QVBoxLayout(card)
    vbox.setContentsMargins(14, 10, 14, 10)
    vbox.setSpacing(3)

    title_lbl = QLabel(title)
    title_lbl.setObjectName("CardTitle")
    value_lbl = QLabel(value)
    value_lbl.setObjectName("CardValue")
    sub_lbl = QLabel("")
    sub_lbl.setObjectName("SubTitle")

    vbox.addWidget(title_lbl)
    vbox.addWidget(value_lbl)
    vbox.addWidget(sub_lbl)
    return card, value_lbl, sub_lbl


class DashboardTab(QWidget):
    """Overview tab with KPIs, seasonal objectives, club records, and milestones."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        c1, self.budget_val, self.budget_sub = _make_stat_card("Bilancio Società")
        c2, self.prestige_val, self.prestige_sub = _make_stat_card("Prestigio & Etica")
        c3, self.squad_val, self.squad_sub = _make_stat_card("Rosa & Pista Tartan")
        c4, self.comp_val, self.comp_sub = _make_stat_card("Prossima Gara")
        for c in (c1, c2, c3, c4):
            cards_row.addWidget(c)
        root.addLayout(cards_row)

        # Tier progress + Objectives row
        mid_row = QHBoxLayout()
        mid_row.setSpacing(12)

        tier_panel = QFrame()
        tier_panel.setObjectName("SectionPanel")
        tier_layout = QVBoxLayout(tier_panel)
        tier_layout.setContentsMargins(14, 10, 14, 10)
        self.tier_progress_label = QLabel("Percorso Categoria")
        self.tier_progress_label.setObjectName("SectionHeader")
        self.tier_progress = QProgressBar()
        self.records_label = QLabel("Record Sociali: nessuno ancora stabilito")
        self.records_label.setObjectName("SubTitle")
        self.records_label.setWordWrap(True)
        tier_layout.addWidget(self.tier_progress_label)
        tier_layout.addWidget(self.tier_progress)
        tier_layout.addWidget(self.records_label)
        mid_row.addWidget(tier_panel, stretch=3)

        obj_panel = QFrame()
        obj_panel.setObjectName("SectionPanel")
        obj_layout = QVBoxLayout(obj_panel)
        obj_layout.setContentsMargins(14, 10, 14, 10)
        obj_title = QLabel("Obiettivi di Stagione")
        obj_title.setObjectName("SectionHeader")
        obj_layout.addWidget(obj_title)
        self.objectives_list = QListWidget()
        self.objectives_list.setWordWrap(True)
        self.objectives_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.objectives_list.setMaximumHeight(108)
        obj_layout.addWidget(self.objectives_list)
        mid_row.addWidget(obj_panel, stretch=2)

        root.addLayout(mid_row)

        # Lower split: Squad snapshot + Milestones & News
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        left_panel = QFrame()
        left_panel.setObjectName("SectionPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(14, 12, 14, 12)
        left_title = QLabel("Migliori Atleti in Rosa")
        left_title.setObjectName("SectionHeader")
        left_layout.addWidget(left_title)

        self.top_table = QTableWidget(0, 7)
        self.top_table.setHorizontalHeaderLabels(
            ["Atleta", "Disciplina", "Carattere", "OVR", "Forma", "Fatica", "Stato"]
        )
        self.top_table.setAlternatingRowColors(True)
        self.top_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.top_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.top_table.verticalHeader().setVisible(False)
        left_layout.addWidget(self.top_table)
        bottom_row.addWidget(left_panel, stretch=3)

        right_panel = QFrame()
        right_panel.setObjectName("SectionPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_title = QLabel("Momenti Memorabili & Cronaca")
        right_title.setObjectName("SectionHeader")
        right_layout.addWidget(right_title)
        self.news_list = QListWidget()
        self.news_list.setWordWrap(True)
        self.news_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_layout.addWidget(self.news_list)
        bottom_row.addWidget(right_panel, stretch=2)

        root.addLayout(bottom_row, stretch=1)

    def refresh(self, state: GameState) -> None:
        net = weekly_finances(state)["net"]

        self.budget_val.setText(f"${state.budget:,}")
        self.budget_val.setStyleSheet("color: #f87171;" if state.budget < 0 else "")
        sign = "+" if net >= 0 else ""
        if state.bankrupt:
            self.budget_sub.setText("SOCIETÀ FALLITA — avvia una nuova partita")
        elif state.budget < 0:
            self.budget_sub.setText(
                f"In rosso: 5% interessi/sett, fallimento sotto -${-BANKRUPTCY_THRESHOLD:,}"
            )
        else:
            self.budget_sub.setText(f"Flusso netto {sign}${net:,}/sett")

        self.prestige_val.setText(f"{state.prestige} pt")
        self.prestige_sub.setText(f"Reputazione Etica: {state.reputation}%")

        pos = state.league_position
        standings = state.league_standings()
        pts = dict(standings).get(state.team_name, 0)
        weeks_left = state.weeks_to_season_end
        if weeks_left is None:
            self.tier_progress_label.setText(
                f"Lega {state.tier.value}: {pos}° su {len(standings)} con {pts} pt "
                "(promozioni e retrocessioni solo in Carriera)"
            )
            self.tier_progress.setMaximum(8)
            self.tier_progress.setValue(min(8, state.week))
            self.tier_progress.setFormat(f"Prototipo: settimana {min(8, state.week)} di 8")
        else:
            if pos <= PROMOTION_SPOTS and state.tier.next_tier is not None:
                zone = f"zona promozione → {state.tier.next_tier.value}"
            elif pos <= PROMOTION_SPOTS:
                zone = "in corsa per il titolo" if pos > 1 else "in testa: verso il titolo"
            elif pos > len(standings) - RELEGATION_SPOTS and state.tier.previous_tier is not None:
                zone = f"zona retrocessione → {state.tier.previous_tier.value}"
            else:
                zone = "metà classifica"
            self.tier_progress_label.setText(
                f"Lega {state.tier.value}: {pos}° su {len(standings)} con {pts} pt — {zone}"
            )
            done = 36 - weeks_left
            self.tier_progress.setMaximum(36)
            self.tier_progress.setValue(done)
            self.tier_progress.setFormat(
                f"Stagione {state.season_number}: mancano {weeks_left} settimane al verdetto "
                f"(prime {PROMOTION_SPOTS} su, ultima giù)"
            )
        if state.season_history:
            last = state.season_history[0]
            self.tier_progress.setToolTip(
                f"Stagione {last.season}: {last.placement}° in {last.tier.value} — {last.outcome.value}"
            )

        rec_sections = []
        if state.club_records:
            rec_parts_m = [f"{ev}: {disp} ({ath})" for ev, (_v, disp, ath) in state.club_records.items()]
            rec_sections.append("M: " + "  |  ".join(rec_parts_m))
        if state.club_records_f:
            rec_parts_f = [f"{ev}: {disp} ({ath})" for ev, (_v, disp, ath) in state.club_records_f.items()]
            rec_sections.append("F: " + "  |  ".join(rec_parts_f))
        if rec_sections:
            self.records_label.setText("Record Sociali — " + "   •   ".join(rec_sections))
        else:
            self.records_label.setText("Record Sociali: nessun record ancora omologato.")

        squad = state.main_squad
        fit_count = sum(1 for a in squad if not a.is_injured)
        self.squad_val.setText(f"{fit_count}/{len(squad)} Sani")
        self.squad_sub.setText(
            f"Vivaio {len(state.youth_squad)}/{YOUTH_SQUAD_MAX} · Pista {state.track_condition}%"
        )

        if state.is_vertical_slice_complete:
            self.comp_val.setText("Prototipo OK")
            self.comp_val.setStyleSheet("color: #34d399;")
            self.comp_sub.setText("2 gare completate — avvia Carriera!")
        elif state.is_competition_week:
            self.comp_val.setText("QUESTA SETT!")
            self.comp_val.setStyleSheet("color: #fbbf24;")
            self.comp_sub.setText("Prepara lo Scarico & gareggia")
        else:
            rem = state.weeks_until_competition
            self.comp_val.setText(f"Tra {rem} sett.")
            self.comp_val.setStyleSheet("")
            venue = "In casa" if state.next_meet_is_home else "In trasferta"
            self.comp_sub.setText(f"{venue} · {state.season_phase.value}")

        self.objectives_list.clear()
        for obj in state.objectives:
            prefix = "[COMPLETATO] " if obj.completed else "[ ] "
            self.objectives_list.addItem(f"{prefix}{obj.title}")

        sorted_athletes = sorted(state.main_squad, key=lambda a: a.overall, reverse=True)
        self.top_table.setRowCount(len(sorted_athletes))
        for row, a in enumerate(sorted_athletes):
            vals = [
                f"{a.name} ({a.gender})",
                a.specialty.value,
                a.personality.value,
                str(a.overall),
                str(a.form),
                str(a.fatigue),
                a.status_label,
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 6:
                    if a.is_injured or a.doping_boost_weeks > 0:
                        item.setForeground(QColor("#f87171"))
                    elif a.fatigue >= 75:
                        item.setForeground(QColor("#fbbf24"))
                    else:
                        item.setForeground(QColor("#34d399"))
                self.top_table.setItem(row, col, item)

        self.news_list.clear()
        for m in state.milestones[:6]:
            self.news_list.addItem(f"★ {m}")
        for entry in state.news_log[:18]:
            self.news_list.addItem(entry)


class RosterTab(QWidget):
    """Roster management, periodization cycles, recovery, and youth scouting."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._athlete_row_ids: list[int] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        toolbar = QHBoxLayout()
        title = QLabel("Rosa, Periodizzazione & Recupero")
        title.setObjectName("SectionHeader")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.bulk_period_combo = QComboBox()
        for phase in PeriodizationPhase:
            self.bulk_period_combo.addItem(f"Ciclo Tutti: {phase.value}", phase)
        self.bulk_period_combo.activated.connect(self._apply_bulk_period)
        toolbar.addWidget(self.bulk_period_combo)

        btn_rest = QPushButton("Tutti: Riposo")
        btn_rest.clicked.connect(
            lambda: self.controller.set_all_training(TrainingFocus.REST)
        )
        toolbar.addWidget(btn_rest)

        btn_detail = QPushButton("Scheda Atleta")
        btn_detail.clicked.connect(self._open_detail_selected)
        toolbar.addWidget(btn_detail)

        btn_recover = QPushButton("Recupero Selezionato ($250)")
        btn_recover.clicked.connect(self._recover_selected)
        toolbar.addWidget(btn_recover)

        btn_recruit = QPushButton("Mercato Svincolati")
        btn_recruit.setObjectName("PrimaryButton")
        btn_recruit.clicked.connect(self._open_recruit_dialog)
        toolbar.addWidget(btn_recruit)

        btn_release = QPushButton("Svincola")
        btn_release.setObjectName("DangerButton")
        btn_release.clicked.connect(self._release_selected)
        toolbar.addWidget(btn_release)

        root.addLayout(toolbar)

        hint = QLabel(
            "Gestisci carico e periodizzazione: Prep. Specifica accelera la crescita ma stanca; "
            "Scarico (Tapering) prima delle gare riduce la fatica e fa salire il picco di Forma."
        )
        hint.setObjectName("SubTitle")
        root.addWidget(hint)

        self.table = QTableWidget(0, 17)
        self.table.setHorizontalHeaderLabels(
            [
                "Nome",
                "Età",
                "Disciplina",
                "Carattere",
                "OVR/Pot",
                "Potenza",
                "Resist.",
                "Tecnica",
                "Resil.",
                "Forma",
                "Fatica",
                "Stato",
                "PB",
                "Fan",
                "Allenamento",
                "Periodizzazione",
                "Allenatore",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(14, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(15, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(16, QHeaderView.ResizeMode.ResizeToContents)

        self.table.cellDoubleClicked.connect(lambda row, _col: self._open_detail(row))
        root.addWidget(self.table, stretch=1)

    def _open_detail_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Scheda Atleta", "Seleziona prima un atleta nella tabella.")
            return
        self._open_detail(rows[0].row())

    def _open_detail(self, row: int) -> None:
        if 0 <= row < len(self._athlete_row_ids) and self._athlete_row_ids[row] != -1:
            AthleteDetailDialog(self.controller, self._athlete_row_ids[row], parent=self).exec()

    def refresh(self, state: GameState) -> None:
        self._athlete_row_ids = []
        squad = state.main_squad
        self.table.setRowCount(len(squad))

        for row, a in enumerate(squad):
            self._athlete_row_ids.append(a.id or -1)
            name_str = f"{a.name} ({a.gender})" + (" *" if a.is_youth_prospect else "")
            cells = [
                name_str,
                str(a.age),
                a.specialty.value,
                a.personality.value,
                f"{a.overall}/{a.potential}",
                str(a.power),
                str(a.stamina),
                str(a.technique),
                str(a.resilience),
                str(a.form),
                str(a.fatigue),
                a.status_label,
                a.personal_best_display or "—",
                f"{a.fans:,}",
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                elif col == 9:
                    item.setForeground(
                        QColor("#34d399" if a.form >= 70 else ("#fbbf24" if a.form >= 45 else "#f87171"))
                    )
                elif col == 10:
                    item.setForeground(
                        QColor("#f87171" if a.fatigue >= 75 else ("#fbbf24" if a.fatigue >= 50 else "#34d399"))
                    )
                elif col == 11:
                    item.setForeground(
                        QColor("#f87171" if a.is_injured else ("#fbbf24" if a.fatigue >= 75 else "#34d399"))
                    )
                self.table.setItem(row, col, item)

            focus_combo = QComboBox()
            for focus in TrainingFocus:
                focus_combo.addItem(focus.value, focus)
            idx = focus_combo.findData(a.training_focus)
            if idx >= 0:
                focus_combo.setCurrentIndex(idx)
            focus_combo.setEnabled(not a.is_injured)
            focus_combo.currentIndexChanged.connect(
                lambda _i, c=focus_combo, aid=a.id: self._on_focus_changed(aid, c)
            )
            self.table.setCellWidget(row, 14, focus_combo)

            period_combo = QComboBox()
            for phase in PeriodizationPhase:
                period_combo.addItem(phase.value, phase)
            pidx = period_combo.findData(a.periodization)
            if pidx >= 0:
                period_combo.setCurrentIndex(pidx)
            period_combo.setEnabled(not a.is_injured)
            period_combo.currentIndexChanged.connect(
                lambda _i, c=period_combo, aid=a.id: self._on_period_changed(aid, c)
            )
            self.table.setCellWidget(row, 15, period_combo)
            self.table.setCellWidget(row, 16, _coach_combo(self.controller, state, a))

    def _on_focus_changed(self, athlete_id: Optional[int], combo: QComboBox) -> None:
        if athlete_id is not None and isinstance(combo.currentData(), TrainingFocus):
            self.controller.set_athlete_training(athlete_id, combo.currentData())

    def _on_period_changed(self, athlete_id: Optional[int], combo: QComboBox) -> None:
        if athlete_id is not None and isinstance(combo.currentData(), PeriodizationPhase):
            self.controller.set_athlete_periodization(athlete_id, combo.currentData())

    def _apply_bulk_period(self) -> None:
        phase = self.bulk_period_combo.currentData()
        if isinstance(phase, PeriodizationPhase):
            self.controller.set_all_periodization(phase)

    def _recover_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Recupero", "Seleziona prima un atleta nella tabella.")
            return
        row = rows[0].row()
        if 0 <= row < len(self._athlete_row_ids):
            self.controller.apply_recovery_session(self._athlete_row_ids[row])

    def _open_recruit_dialog(self) -> None:
        prospects = self.controller.generate_free_agents(count=5)
        dlg = RecruitAthleteDialog(prospects, self.controller.state.budget, parent=self)
        if dlg.exec() and dlg.selected_prospect is not None:
            self.controller.recruit_athlete(dlg.selected_prospect)

    def _release_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Svincola Atleta", "Seleziona prima una riga.")
            return
        row = rows[0].row()
        if 0 <= row < len(self._athlete_row_ids):
            aid = self._athlete_row_ids[row]
            athlete = next((a for a in self.controller.state.athletes if a.id == aid), None)
            if athlete and QMessageBox.question(self, "Conferma", f"Svincolare {athlete.name}?") == QMessageBox.StandardButton.Yes:
                self.controller.release_athlete(aid)


class CalendarTab(QWidget):
    """Competition schedule, active event lineup selection, and past meet results."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._event_combos: Dict[str, QComboBox] = {}
        self._history_list: list[CompetitionSummary] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        banner = QFrame()
        banner.setObjectName("StatCard")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(14, 12, 14, 12)
        self.cycle_label = QLabel("Calendario Gare")
        self.cycle_label.setObjectName("SectionHeader")
        banner_layout.addWidget(self.cycle_label)
        banner_layout.addStretch()

        auto_btn = QPushButton("Formazione Ottimale")
        auto_btn.setObjectName("PrimaryButton")
        auto_btn.clicked.connect(self.controller.auto_fill_lineup)
        banner_layout.addWidget(auto_btn)
        root.addWidget(banner)

        lineup_panel = QFrame()
        lineup_panel.setObjectName("SectionPanel")
        lineup_layout = QVBoxLayout(lineup_panel)
        lineup_layout.setContentsMargins(14, 12, 14, 12)

        lineup_title = QLabel(
            "Convocazioni & Atteggiamento (Aggressivo: risultato migliore ma più fatica e rischio "
            "di ritiro; Prudente: il contrario)"
        )
        lineup_title.setWordWrap(True)
        lineup_title.setObjectName("SectionHeader")
        lineup_layout.addWidget(lineup_title)

        self.lineup_table = QTableWidget(0, 5)
        self.lineup_table.setHorizontalHeaderLabels(
            ["Gara", "Specialità", "Fattori Chiave", "Atleta Convocato", "Atteggiamento"]
        )
        self.lineup_table.setAlternatingRowColors(True)
        self.lineup_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.lineup_table.verticalHeader().setVisible(False)
        self.lineup_table.verticalHeader().setDefaultSectionSize(38)
        self.lineup_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        lineup_layout.addWidget(self.lineup_table)
        root.addWidget(lineup_panel, stretch=1)

        lower_row = QHBoxLayout()
        lower_row.setSpacing(12)

        league_panel = QFrame()
        league_panel.setObjectName("SectionPanel")
        league_layout = QVBoxLayout(league_panel)
        league_layout.setContentsMargins(14, 12, 14, 12)
        self.league_title = QLabel("Classifica di Lega")
        self.league_title.setObjectName("SectionHeader")
        league_layout.addWidget(self.league_title)
        league_hint = QLabel(
            "Punti per piazzamento in ogni gara (1° = 8 … 8° = 1). Gare senza convocato regalano punti "
            "ai rivali. In Carriera, a fine stagione le prime 2 salgono di categoria e l'ultima scende."
        )
        league_hint.setObjectName("SubTitle")
        league_hint.setWordWrap(True)
        league_layout.addWidget(league_hint)
        self.league_table = QTableWidget(0, 3)
        self.league_table.setHorizontalHeaderLabels(["Pos", "Società", "Punti"])
        self.league_table.setAlternatingRowColors(True)
        self.league_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.league_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.league_table.verticalHeader().setVisible(False)
        league_layout.addWidget(self.league_table)
        lower_row.addWidget(league_panel, stretch=2)

        hist_panel = QFrame()
        hist_panel.setObjectName("SectionPanel")
        hist_layout = QVBoxLayout(hist_panel)
        hist_layout.setContentsMargins(14, 12, 14, 12)

        hist_header = QHBoxLayout()
        hist_title = QLabel("Archivio Gare Disputate (Doppio clic per classifiche e vento)")
        hist_title.setObjectName("SectionHeader")
        hist_header.addWidget(hist_title)
        hist_header.addStretch()
        view_btn = QPushButton("Apri Risultati")
        view_btn.clicked.connect(self._open_selected_history)
        hist_header.addWidget(view_btn)
        hist_layout.addLayout(hist_header)

        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(
            ["Sett.", "Meeting", "Sede", "Meteo", "Società", "Premi", "Prestigio"]
        )
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.cellDoubleClicked.connect(lambda _r, _c: self._open_selected_history())
        hist_layout.addWidget(self.history_table)

        lower_row.addWidget(hist_panel, stretch=3)
        root.addLayout(lower_row, stretch=1)

    def refresh(self, state: GameState) -> None:
        if state.is_vertical_slice_complete:
            self.cycle_label.setText(
                "Prototipo Stagione Outdoor completato (2 gare disputate)! "
                "Puoi continuare a testare il loop o avviare una Carriera Completa."
            )
            self.cycle_label.setStyleSheet("color: #34d399;")
        elif state.is_competition_week:
            self.cycle_label.setText(
                f"Sett. {state.week} ({state.current_date:%d %b %Y}) — "
                f"SETTIMANA DI GARA ({state.season_phase.value})! Conferma le convocazioni e avanza."
            )
            self.cycle_label.setStyleSheet("color: #fbbf24;")
        else:
            rem = state.weeks_until_competition
            venue = "in casa" if state.next_meet_is_home else "in trasferta"
            self.cycle_label.setText(
                f"Sett. {state.week} ({state.current_date:%d %b %Y}) — "
                f"Prossimo meeting {venue} tra {rem} settimana/e (Sett. {state.week + rem})."
            )
            self.cycle_label.setStyleSheet("")

        active_events = state.active_events
        self._event_combos.clear()
        divisions = ("M", "F")
        self.lineup_table.setRowCount(len(active_events) * len(divisions))

        for ev_idx, event_name in enumerate(active_events):
            event_def = EVENTS[event_name]
            key_stats = ", ".join(
                f"{k.capitalize()} {int(v * 100)}%"
                for k, v in event_def.weights.items()
                if v >= 0.15
            )
            for div_idx, gender in enumerate(divisions):
                row = ev_idx * len(divisions) + div_idx
                for col, text in enumerate((f"{event_name} ({gender})", event_def.specialty.value, key_stats)):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.lineup_table.setItem(row, col, item)

                combo = QComboBox()
                combo.addItem("-- Nessun Atleta --", None)
                for a in state.main_squad:
                    if a.is_injured or a.gender != gender:
                        continue
                    label = f"{a.name} ({a.specialty.value}, OVR {a.overall}, Forma {a.form})"
                    combo.addItem(label, a.id)
                assigned_id = state.lineup_for(gender).get(event_name)
                idx = combo.findData(assigned_id)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
                combo.currentIndexChanged.connect(
                    lambda _i, en=event_name, g=gender, c=combo: self.controller.set_event_athlete(
                        en, c.currentData(), gender=g
                    )
                )
                self._event_combos[f"{event_name}:{gender}"] = combo
                self.lineup_table.setCellWidget(row, 3, combo)

                att_combo = QComboBox()
                for att in RaceAttitude:
                    att_combo.addItem(att.value, att)
                att_combo.setCurrentIndex(max(0, att_combo.findData(state.attitude_for(event_name))))
                att_combo.currentIndexChanged.connect(
                    lambda _i, en=event_name, c=att_combo: self.controller.set_event_attitude(
                        en, c.currentData()
                    )
                )
                self.lineup_table.setCellWidget(row, 4, att_combo)

        league_rows = state.league_standings()
        if state.game_mode == "career":
            self.league_title.setText(
                f"Classifica di Lega — {state.tier.value} (verdetto tra {state.weeks_to_season_end} sett.)"
            )
        else:
            self.league_title.setText(f"Classifica di Lega — {state.tier.value}")
        self.league_table.setRowCount(len(league_rows))
        for row, (team, pts) in enumerate(league_rows):
            for col, text in enumerate((str(row + 1), team, str(pts))):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if team == state.team_name:
                    item.setForeground(QColor("#38bdf8"))
                elif state.game_mode == "career" and row < PROMOTION_SPOTS:
                    item.setForeground(QColor("#34d399"))
                elif state.game_mode == "career" and row >= len(league_rows) - RELEGATION_SPOTS:
                    item.setForeground(QColor("#f87171"))
                self.league_table.setItem(row, col, item)

        self._history_list = list(state.competition_history)
        self.history_table.setRowCount(len(self._history_list))
        for row, comp in enumerate(self._history_list):
            team_place = comp.team_placement
            vals = [
                f"Sett. {comp.week}",
                comp.meet_name,
                f"Casa ({comp.spectators:,})" if comp.is_home else "Trasferta",
                comp.weather.value,
                f"{team_place}ª" if team_place else "—",
                f"${comp.total_prize_money + comp.ticket_income:,}",
                f"+{comp.total_prestige_gained}",
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.history_table.setItem(row, col, item)

    def _open_selected_history(self) -> None:
        rows = self.history_table.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        if 0 <= idx < len(self._history_list):
            dlg = CompetitionResultsDialog(self._history_list[idx], parent=self)
            dlg.exec()


class StaffTab(QWidget):
    """Club technical & medical staff hiring plus tartan track maintenance."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        track_card = QFrame()
        track_card.setObjectName("StatCard")
        track_layout = QHBoxLayout(track_card)
        track_layout.setContentsMargins(14, 12, 14, 12)
        self.track_label = QLabel("Condizione Pista in Tartan: 82%")
        self.track_label.setObjectName("SectionHeader")
        track_layout.addWidget(self.track_label)
        track_layout.addStretch()

        maint_btn = QPushButton("Manutenzione Pista Tartan ($900)")
        maint_btn.setObjectName("PrimaryButton")
        maint_btn.clicked.connect(self.controller.maintain_track)
        track_layout.addWidget(maint_btn)
        root.addWidget(track_card)

        facilities_row = QHBoxLayout()
        facilities_row.setSpacing(12)

        gym_card = QFrame()
        gym_card.setObjectName("StatCard")
        gym_layout = QVBoxLayout(gym_card)
        gym_layout.setContentsMargins(14, 12, 14, 12)
        self.gym_label = QLabel("Palestra")
        self.gym_label.setObjectName("SectionHeader")
        self.gym_sub = QLabel("")
        self.gym_sub.setObjectName("SubTitle")
        self.gym_sub.setWordWrap(True)
        self.gym_btn = QPushButton("Amplia Palestra")
        self.gym_btn.setObjectName("PrimaryButton")
        self.gym_btn.clicked.connect(self.controller.upgrade_gym)
        gym_layout.addWidget(self.gym_label)
        gym_layout.addWidget(self.gym_sub)
        gym_layout.addWidget(self.gym_btn)
        facilities_row.addWidget(gym_card)

        stand_card = QFrame()
        stand_card.setObjectName("StatCard")
        stand_layout = QVBoxLayout(stand_card)
        stand_layout.setContentsMargins(14, 12, 14, 12)
        self.stand_label = QLabel("Tribune")
        self.stand_label.setObjectName("SectionHeader")
        self.stand_sub = QLabel("")
        self.stand_sub.setObjectName("SubTitle")
        self.stand_sub.setWordWrap(True)
        self.stand_btn = QPushButton("Amplia Tribune")
        self.stand_btn.setObjectName("PrimaryButton")
        self.stand_btn.clicked.connect(self.controller.expand_stands)
        stand_layout.addWidget(self.stand_label)
        stand_layout.addWidget(self.stand_sub)
        stand_layout.addWidget(self.stand_btn)
        facilities_row.addWidget(stand_card)

        root.addLayout(facilities_row)

        coach_panel = QFrame()
        coach_panel.setObjectName("SectionPanel")
        coach_layout = QVBoxLayout(coach_panel)
        coach_layout.setContentsMargins(14, 12, 14, 12)
        coach_head = QHBoxLayout()
        self.coach_title = QLabel("Allenatori")
        self.coach_title.setObjectName("SectionHeader")
        coach_head.addWidget(self.coach_title)
        coach_head.addStretch()
        self.hire_coach_btn = QPushButton("Assumi Allenatore")
        self.hire_coach_btn.setObjectName("PrimaryButton")
        self.hire_coach_btn.clicked.connect(self._open_hire_coach)
        coach_head.addWidget(self.hire_coach_btn)
        coach_layout.addLayout(coach_head)
        coach_hint = QLabel(
            "Più alta è l'abilità dell'allenatore in una qualità, più crescono gli atleti che la "
            f"allenano. Oltre {COACH_COMFORT_LOAD} atleti a testa l'effetto cala. Le abilità calano "
            "lentamente col tempo: prima o poi va sostituito. Un'assunzione a settimana."
        )
        coach_hint.setObjectName("SubTitle")
        coach_hint.setWordWrap(True)
        coach_layout.addWidget(coach_hint)
        self.coach_table = QTableWidget(0, 9)
        self.coach_table.setHorizontalHeaderLabels(
            ["Nome", "Tipo", *[COACH_STAT_LABELS[s] for s in COACH_STATS], "Atleti", "Stipendio", "Azione"]
        )
        self.coach_table.setAlternatingRowColors(True)
        self.coach_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.coach_table.verticalHeader().setVisible(False)
        self.coach_table.verticalHeader().setDefaultSectionSize(38)
        ch = self.coach_table.horizontalHeader()
        ch.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        ch.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        coach_layout.addWidget(self.coach_table)
        root.addWidget(coach_panel, stretch=3)

        panel = QFrame()
        panel.setObjectName("SectionPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)

        title = QLabel("Staff Medico e Preparazione Mentale")
        title.setObjectName("SectionHeader")
        panel_layout.addWidget(title)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Nome", "Ruolo", "Livello", "Costo/sett", "Effetto", "Azione"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        panel_layout.addWidget(self.table)
        root.addWidget(panel, stretch=1)

    def refresh(self, state: GameState) -> None:
        self.track_label.setText(
            f"Condizione Pista in Tartan: {state.track_condition}% "
            "(una pista usurata rallenta leggermente tempi e salti)"
        )
        lvl = state.gym_level
        self.gym_label.setText(f"Palestra — livello {lvl}/{GYM_MAX_LEVEL}")
        self.gym_sub.setText(
            f"+{int(lvl * GYM_TRAINING_BONUS_PER_LEVEL * 100)}% probabilità di miglioramento in allenamento · "
            f"gestione ${lvl * GYM_UPKEEP_PER_LEVEL}/sett"
        )
        if lvl >= GYM_MAX_LEVEL:
            self.gym_btn.setText("Livello massimo")
            self.gym_btn.setEnabled(False)
        else:
            self.gym_btn.setText(f"Amplia a livello {lvl + 1} (${gym_upgrade_cost(lvl):,})")
            self.gym_btn.setEnabled(True)

        price = TICKET_PRICE[state.tier.value]
        self.stand_label.setText(f"Tribune — {state.stand_seats:,} posti")
        self.stand_sub.setText(
            f"Nei meeting in casa niente trasferta e incasso biglietti (${price}/biglietto in "
            f"{state.tier.value}). Il pubblico cresce con prestigio, categoria e reputazione."
        )
        if state.stand_seats >= STAND_MAX_SEATS:
            self.stand_btn.setText("Capienza massima")
            self.stand_btn.setEnabled(False)
        else:
            self.stand_btn.setText(
                f"+{STAND_EXPANSION_SEATS} posti (${stand_expansion_cost(state.stand_seats):,})"
            )
            self.stand_btn.setEnabled(True)
        n_spec = sum(1 for c in state.coaches if not c.is_youth_coach)
        n_youth = len(state.coaches) - n_spec
        self.coach_title.setText(
            f"Allenatori — specializzati {n_spec}/{MAX_SPECIALIZED_COACHES}, "
            f"vivaio {n_youth}/{MAX_YOUTH_COACHES}"
        )
        hired_this_week = state.coach_hired_week == state.week
        self.hire_coach_btn.setEnabled(not hired_this_week)
        self.hire_coach_btn.setText(
            "Già assunto questa settimana" if hired_this_week else "Assumi Allenatore"
        )
        self.coach_table.setRowCount(len(state.coaches))
        for row, coach in enumerate(state.coaches):
            load = state.coach_load(coach)
            vals = [
                coach.name,
                coach.kind_label,
                *[str(coach.skills.get(stat, 0)) for stat in COACH_STATS],
                f"{load}/{COACH_COMFORT_LOAD}",
                f"${coach.weekly_wage}",
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if 2 <= col <= 5 and int(text) >= 80:
                    item.setForeground(QColor("#34d399"))
                if col == 6 and load > COACH_COMFORT_LOAD:
                    item.setForeground(QColor("#fbbf24"))
                self.coach_table.setItem(row, col, item)
            fire_btn = QPushButton("Licenzia")
            fire_btn.setObjectName("DangerButton")
            fire_btn.clicked.connect(lambda _c=False, cid=coach.id: self._fire_coach(cid))
            self.coach_table.setCellWidget(row, 8, fire_btn)

        self.table.setRowCount(len(state.staff))
        for row, s in enumerate(state.staff):
            vals = [
                s.name,
                s.role.value,
                "★" * s.skill,
                f"${s.weekly_cost}",
                s.description,
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                    if col in (0, 4)
                    else Qt.AlignmentFlag.AlignCenter
                )
                if s.hired and col == 0:
                    item.setForeground(QColor("#34d399"))
                self.table.setItem(row, col, item)

            btn = QPushButton("Licenzia" if s.hired else "Assumi")
            btn.setObjectName("DangerButton" if s.hired else "PrimaryButton")
            btn.clicked.connect(lambda _c=False, sid=s.id: self.controller.toggle_staff(sid))
            self.table.setCellWidget(row, 5, btn)

    def _open_hire_coach(self) -> None:
        state = self.controller.state
        allowed = sorted(
            {EVENTS[ev].specialty for ev in state.active_events}, key=lambda sp: list(Specialty).index(sp)
        )
        dlg = HireCoachDialog(state.budget, allowed, parent=self)
        if dlg.exec():
            self.controller.hire_coach(dlg.specialty, dlg.primary, dlg.secondary, dlg.tier)

    def _fire_coach(self, coach_id: Optional[int]) -> None:
        coach = next((c for c in self.controller.state.coaches if c.id == coach_id), None)
        if coach is None:
            return
        load = self.controller.state.coach_load(coach)
        if QMessageBox.question(
            self,
            "Conferma",
            f"Licenziare {coach.name}? I suoi {load} atleti passeranno a un altro allenatore "
            "adatto, se c'è.",
        ) == QMessageBox.StandardButton.Yes:
            self.controller.fire_coach(coach.id)


class FinancesTab(QWidget):
    """Club finances overview and transaction ledger."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        c1, self.balance_val, self.balance_sub = _make_stat_card("Saldo Attuale")
        c2, self.sponsor_val, self.sponsor_sub = _make_stat_card("Entrate Settimanali")
        c3, self.payroll_val, self.payroll_sub = _make_stat_card("Spese Fisse Settimanali")
        c4, self.net_val, self.net_sub = _make_stat_card("Flusso Netto")
        for c in (c1, c2, c3, c4):
            cards_row.addWidget(c)
        root.addLayout(cards_row)

        ledger_panel = QFrame()
        ledger_panel.setObjectName("SectionPanel")
        ledger_layout = QVBoxLayout(ledger_panel)
        ledger_layout.setContentsMargins(14, 12, 14, 12)

        title = QLabel("Libro Mastro & Movimenti")
        title.setObjectName("SectionHeader")
        ledger_layout.addWidget(title)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Settimana", "Categoria", "Descrizione", "Importo"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        ledger_layout.addWidget(self.table)

        root.addWidget(ledger_panel, stretch=1)

    def refresh(self, state: GameState) -> None:
        fin = weekly_finances(state)
        net = fin["net"]

        self.balance_val.setText(f"${state.budget:,}")
        self.balance_val.setStyleSheet("color: #f87171;" if state.budget < 0 else "")
        self.balance_sub.setText(
            f"Fedeltà sponsor {state.fidelity}% (scende con acquisti/cessioni)"
            if state.budget >= 0
            else f"In rosso: 5% interessi/sett · fallimento sotto -${-BANKRUPTCY_THRESHOLD:,}"
        )

        self.sponsor_val.setText(f"+${fin['income']:,}")
        self.sponsor_sub.setText(
            f"Società ${fin['sponsor']:,} + Individuali ${fin['individual_sponsors']:,} "
            f"+ Quote ${fin['member_fees']:,}"
        )

        self.payroll_val.setText(f"-${fin['expenses']:,}")
        self.payroll_sub.setText(
            f"Atleti ${fin['athlete_wages']:,} + Allenatori ${fin['coach_cost']:,} "
            f"+ Staff ${fin['staff_cost']:,} + Palestra ${fin['gym_upkeep']:,}"
        )

        sign = "+" if net >= 0 else ""
        self.net_val.setText(f"{sign}${net:,}")
        self.net_val.setStyleSheet("color: #34d399;" if net >= 0 else "color: #f87171;")
        self.net_sub.setText("Esclusi premi, biglietti e trasferte")

        self.table.setRowCount(len(state.transactions))
        for row, tx in enumerate(state.transactions):
            amt_text = f"+${tx.amount:,}" if tx.amount >= 0 else f"-${abs(tx.amount):,}"
            vals = [f"Sett. {tx.week}", tx.category, tx.description, amt_text]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 3:
                    item.setForeground(QColor("#34d399" if tx.amount >= 0 else "#f87171"))
                self.table.setItem(row, col, item)


class YouthTab(QWidget):
    """Youth academy (vivaio): weekly scouting with points, faster training, promotion at 18."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._youth_row_ids: list[int] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        squad_panel = QFrame()
        squad_panel.setObjectName("SectionPanel")
        squad_layout = QVBoxLayout(squad_panel)
        squad_layout.setContentsMargins(14, 12, 14, 12)

        head = QHBoxLayout()
        self.squad_title = QLabel("Vivaio")
        self.squad_title.setObjectName("SectionHeader")
        head.addWidget(self.squad_title)
        head.addStretch()
        promote_btn = QPushButton("Promuovi in Prima Squadra")
        promote_btn.setObjectName("PrimaryButton")
        promote_btn.clicked.connect(self._promote_selected)
        head.addWidget(promote_btn)
        release_btn = QPushButton("Svincola")
        release_btn.setObjectName("DangerButton")
        release_btn.clicked.connect(self._release_selected)
        head.addWidget(release_btn)
        squad_layout.addLayout(head)

        hint = QLabel(
            "I ragazzi del vivaio (14-17 anni) non gareggiano e non prendono stipendio, ma si allenano "
            "il 50% più in fretta. A 18 anni passano in Prima Squadra in automatico."
        )
        hint.setObjectName("SubTitle")
        hint.setWordWrap(True)
        squad_layout.addWidget(hint)

        self.youth_table = QTableWidget(0, 12)
        self.youth_table.setHorizontalHeaderLabels(
            ["Nome", "Età", "Disciplina", "Carattere", "OVR/Pot", "Vel.", "Resist.",
             "Forza", "Tecnica", "Fatica", "Allenamento", "Allenatore"]
        )
        self.youth_table.setAlternatingRowColors(True)
        self.youth_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.youth_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.youth_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.youth_table.verticalHeader().setVisible(False)
        self.youth_table.verticalHeader().setDefaultSectionSize(38)
        yh = self.youth_table.horizontalHeader()
        yh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        yh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        yh.setSectionResizeMode(10, QHeaderView.ResizeMode.ResizeToContents)
        yh.setSectionResizeMode(11, QHeaderView.ResizeMode.ResizeToContents)
        squad_layout.addWidget(self.youth_table)
        root.addWidget(squad_panel, stretch=1)

        scout_panel = QFrame()
        scout_panel.setObjectName("SectionPanel")
        scout_layout = QVBoxLayout(scout_panel)
        scout_layout.setContentsMargins(14, 12, 14, 12)

        self.scout_title = QLabel("Osservatori")
        self.scout_title.setObjectName("SectionHeader")
        scout_layout.addWidget(self.scout_title)

        scout_hint = QLabel(
            f"Ogni settimana hai {WEEKLY_SCOUTING_POINTS} punti. Una ricerca costa 2 punti, "
            "+1 per ogni filtro. Il costo in denaro cresce con i punti già spesi nella settimana. "
            "I ragazzi segnalati e non presi se ne vanno a fine settimana."
        )
        scout_hint.setObjectName("SubTitle")
        scout_hint.setWordWrap(True)
        scout_layout.addWidget(scout_hint)

        controls = QHBoxLayout()
        self.spec_combo = QComboBox()
        self.spec_combo.addItem("Qualsiasi disciplina", None)
        for spec in Specialty:
            self.spec_combo.addItem(f"Solo {spec.value} (+1 punto)", spec)
        self.spec_combo.currentIndexChanged.connect(lambda _i: self._update_cost_label())
        controls.addWidget(self.spec_combo)
        self.high_pot_check = QCheckBox("Solo alto potenziale ≥85 (+1 punto)")
        self.high_pot_check.toggled.connect(lambda _b: self._update_cost_label())
        controls.addWidget(self.high_pot_check)
        controls.addStretch()
        self.cost_label = QLabel("")
        self.cost_label.setObjectName("SubTitle")
        controls.addWidget(self.cost_label)
        self.search_btn = QPushButton("Avvia Ricerca")
        self.search_btn.setObjectName("PrimaryButton")
        self.search_btn.clicked.connect(self._run_search)
        controls.addWidget(self.search_btn)
        scout_layout.addLayout(controls)

        self.results_table = QTableWidget(0, 7)
        self.results_table.setHorizontalHeaderLabels(
            ["Nome", "Età", "Disciplina", "Carattere", "OVR", "Potenziale", "Resilienza"]
        )
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        scout_layout.addWidget(self.results_table)

        sign_row = QHBoxLayout()
        sign_row.addStretch()
        sign_btn = QPushButton("Inserisci nel Vivaio")
        sign_btn.setObjectName("PrimaryButton")
        sign_btn.clicked.connect(self._sign_selected)
        sign_row.addWidget(sign_btn)
        scout_layout.addLayout(sign_row)

        root.addWidget(scout_panel, stretch=1)

    def _filters(self) -> tuple[Optional[Specialty], bool]:
        spec = self.spec_combo.currentData()
        return (spec if isinstance(spec, Specialty) else None), self.high_pot_check.isChecked()

    def _update_cost_label(self) -> None:
        state = self.controller.state
        spec, high = self._filters()
        filters = (1 if spec is not None else 0) + (1 if high else 0)
        points, fee = scouting_search_cost(state.scouting_points_used, filters)
        enough = points <= state.scouting_points_left
        self.cost_label.setText(f"Costo: {points} punti · ${fee:,}")
        self.search_btn.setEnabled(enough and len(state.youth_squad) < YOUTH_SQUAD_MAX)

    def refresh(self, state: GameState) -> None:
        youth = state.youth_squad
        self.squad_title.setText(f"Vivaio — {len(youth)}/{YOUTH_SQUAD_MAX} ragazzi")
        self.scout_title.setText(
            f"Osservatori — {state.scouting_points_left}/{WEEKLY_SCOUTING_POINTS} punti disponibili questa settimana"
        )

        # Hide disciplines that are not played in the prototype
        allowed = (
            {Specialty.SPRINTS, Specialty.JUMPS, Specialty.MIDDLE_DISTANCE}
            if state.game_mode == "vertical_slice"
            else set(Specialty)
        )
        view = self.spec_combo.view()
        for i in range(self.spec_combo.count()):
            data = self.spec_combo.itemData(i)
            if isinstance(data, Specialty):
                view.setRowHidden(i, data not in allowed)
        if isinstance(self.spec_combo.currentData(), Specialty) and self.spec_combo.currentData() not in allowed:
            self.spec_combo.setCurrentIndex(0)

        self._youth_row_ids = []
        self.youth_table.setRowCount(len(youth))
        for row, a in enumerate(youth):
            self._youth_row_ids.append(a.id or -1)
            cells = [
                f"{a.name} ({a.gender})", str(a.age), a.specialty.value, a.personality.value,
                f"{a.overall}/{a.potential}", str(a.speed), str(a.stamina),
                str(a.strength), str(a.technique), str(a.fatigue),
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 4 and a.potential >= 88:
                    item.setForeground(QColor("#fbbf24"))
                self.youth_table.setItem(row, col, item)

            focus_combo = QComboBox()
            for focus in TrainingFocus:
                focus_combo.addItem(focus.value, focus)
            idx = focus_combo.findData(a.training_focus)
            if idx >= 0:
                focus_combo.setCurrentIndex(idx)
            focus_combo.currentIndexChanged.connect(
                lambda _i, c=focus_combo, aid=a.id: self._on_focus_changed(aid, c)
            )
            self.youth_table.setCellWidget(row, 10, focus_combo)
            self.youth_table.setCellWidget(row, 11, _coach_combo(self.controller, state, a))

        results = self.controller.scouting_results
        self.results_table.setRowCount(len(results))
        for row, k in enumerate(results):
            vals = [f"{k.name} ({k.gender})", str(k.age), k.specialty.value, k.personality.value,
                    str(k.overall), str(k.potential), str(k.resilience)]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 5 and k.potential >= 88:
                    item.setForeground(QColor("#fbbf24"))
                self.results_table.setItem(row, col, item)
        if results:
            self.results_table.selectRow(0)

        self._update_cost_label()

    def _on_focus_changed(self, athlete_id: Optional[int], combo: QComboBox) -> None:
        if athlete_id is not None and isinstance(combo.currentData(), TrainingFocus):
            self.controller.set_athlete_training(athlete_id, combo.currentData())

    def _run_search(self) -> None:
        spec, high = self._filters()
        self.controller.run_youth_scouting(specialty=spec, high_potential=high)

    def _sign_selected(self) -> None:
        rows = self.results_table.selectionModel().selectedRows()
        results = self.controller.scouting_results
        if not rows or not (0 <= rows[0].row() < len(results)):
            QMessageBox.information(self, "Vivaio", "Seleziona prima un ragazzo segnalato.")
            return
        self.controller.sign_youth(results[rows[0].row()])

    def _selected_youth_id(self) -> Optional[int]:
        rows = self.youth_table.selectionModel().selectedRows()
        if not rows or not (0 <= rows[0].row() < len(self._youth_row_ids)):
            QMessageBox.information(self, "Vivaio", "Seleziona prima un ragazzo del vivaio.")
            return None
        return self._youth_row_ids[rows[0].row()]

    def _promote_selected(self) -> None:
        aid = self._selected_youth_id()
        if aid is not None:
            self.controller.promote_youth(aid)

    def _release_selected(self) -> None:
        aid = self._selected_youth_id()
        if aid is None:
            return
        athlete = next((a for a in self.controller.state.athletes if a.id == aid), None)
        if athlete and QMessageBox.question(
            self, "Conferma", f"Svincolare {athlete.name} dal vivaio?"
        ) == QMessageBox.StandardButton.Yes:
            self.controller.release_athlete(aid)


class RelayTab(QWidget):
    """4x100m / 4x400m relay teams: legs order, reserve and harmony."""

    SLOT_LABELS = ["1ª frazione", "2ª frazione", "3ª frazione", "4ª frazione (ultima)", "Riserva"]

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._slot_combos: Dict[str, list[QComboBox]] = {}
        self._titles: Dict[str, QLabel] = {}
        self._bars: Dict[str, QProgressBar] = {}
        self._notes: Dict[str, QLabel] = {}
        self._auto_btns: Dict[str, QPushButton] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        top_bar = QHBoxLayout()
        hint = QLabel(
            "Ogni atleta può correre in una sola staffetta della propria categoria (M/F). L'affiatamento "
            "(da E ad A++) cresce di settimana in settimana se i 4 titolari sono sani, e di più quando "
            "la staffetta gareggia. Con poco affiatamento aumenta il rischio di squalifica per cambio "
            "fuori zona. Cambiare l'ordine è gratis; sostituire un titolare sano costa il 25% "
            f"dell'affiatamento ed è possibile una volta ogni {RELAY_CHANGE_COOLDOWN_WEEKS} settimane. "
            "Se un titolare è infortunato entra la riserva. Le staffette non consumano forma e non danno fan."
        )
        hint.setObjectName("SubTitle")
        hint.setWordWrap(True)
        top_bar.addWidget(hint, stretch=1)
        top_bar.addWidget(QLabel("Categoria:"))
        self.division_combo = QComboBox()
        self.division_combo.addItem("Maschile (M)", "M")
        self.division_combo.addItem("Femminile (F)", "F")
        self.division_combo.currentIndexChanged.connect(lambda _i: self.refresh(self.controller.state))
        top_bar.addWidget(self.division_combo)
        root.addLayout(top_bar)

        row = QHBoxLayout()
        row.setSpacing(12)
        for name in RELAYS:
            panel = QFrame()
            panel.setObjectName("SectionPanel")
            lay = QVBoxLayout(panel)
            lay.setContentsMargins(14, 12, 14, 12)
            title = QLabel(f"Staffetta {name}")
            title.setObjectName("SectionHeader")
            lay.addWidget(title)
            bar = QProgressBar()
            bar.setMaximum(100)
            lay.addWidget(bar)
            note = QLabel("")
            note.setObjectName("SubTitle")
            note.setWordWrap(True)
            lay.addWidget(note)
            combos: list[QComboBox] = []
            for slot, label in enumerate(self.SLOT_LABELS):
                line = QHBoxLayout()
                lbl = QLabel(label)
                lbl.setMinimumWidth(150)
                line.addWidget(lbl)
                combo = QComboBox()
                combo.currentIndexChanged.connect(
                    lambda _i, n=name, sl=slot, c=combo: self._on_slot_changed(n, sl, c)
                )
                line.addWidget(combo, stretch=1)
                lay.addLayout(line)
                combos.append(combo)
            auto_btn = QPushButton("Componi automaticamente")
            auto_btn.setObjectName("PrimaryButton")
            auto_btn.clicked.connect(
                lambda _c=False, n=name: self.controller.auto_build_relay(
                    n, gender=self.division_combo.currentData() or "M"
                )
            )
            lay.addWidget(auto_btn)
            lay.addStretch()
            row.addWidget(panel)
            self._slot_combos[name] = combos
            self._titles[name] = title
            self._bars[name] = bar
            self._notes[name] = note
            self._auto_btns[name] = auto_btn
        root.addLayout(row, stretch=1)

    def refresh(self, state: GameState) -> None:
        active = set(state.active_relays)
        gender = self.division_combo.currentData() or "M"
        relays = state.relays_for(gender)
        for name, rdef in RELAYS.items():
            relay = relays.get(name)
            harmony = relay.harmony if relay else 0
            self._titles[name].setText(
                f"Staffetta {name} ({gender}) — affiatamento {harmony_grade(harmony)} ({harmony}/100)"
            )
            self._bars[name].setValue(harmony)
            self._bars[name].setFormat(f"Affiatamento {harmony_grade(harmony)}")

            if name not in active:
                if rdef.requires_event not in state.active_events:
                    why = f"Non in programma: serve la gara dei {rdef.requires_event} (Carriera)."
                else:
                    why = f"Non si corre nella stagione {state.season_phase.value}."
                self._notes[name].setText(why)
            elif relay is None or not relay.is_complete:
                self._notes[name].setText("Squadra incompleta: senza 4 frazionisti non gareggia.")
            else:
                wait = RELAY_CHANGE_COOLDOWN_WEEKS - (state.week - relay.last_change_week)
                self._notes[name].setText(
                    f"Prossimo cambio di un titolare tra {wait} settimana/e." if wait > 0
                    else "Puoi sostituire un titolare (costa il 25% di affiatamento)."
                )

            slots = (list(relay.member_ids) + [relay.reserve_id]) if relay else [None] * 5
            for slot, combo in enumerate(self._slot_combos[name]):
                combo.blockSignals(True)
                combo.clear()
                combo.addItem("— vuoto —", None)
                for a in state.main_squad:
                    if a.gender != gender:
                        continue
                    other = state.relay_of(a.id, gender=gender)
                    if other is not None and other != name:
                        continue
                    tag = " (infort.)" if a.is_injured else ""
                    combo.addItem(
                        f"{a.name} — {a.specialty.value}, valore {relay_leg_score(a, rdef):.0f}{tag}", a.id
                    )
                combo.setCurrentIndex(max(0, combo.findData(slots[slot])))
                combo.setEnabled(name in active)
                combo.blockSignals(False)
            self._auto_btns[name].setEnabled(name in active)

    def _on_slot_changed(self, name: str, slot: int, combo: QComboBox) -> None:
        gender = self.division_combo.currentData() or "M"
        if not self.controller.set_relay_slot(name, slot, combo.currentData(), gender=gender):
            self.refresh(self.controller.state)  # refused: show the real line-up again


def _trend_text(delta: float) -> str:
    if delta >= 0.5:
        return f"↑ +{delta:.1f}"
    if delta <= -0.5:
        return f"↓ {delta:.1f}"
    return f"= {delta:+.1f}"


class RivalsTab(QWidget):
    """Rival clubs of the current category: level, trend, ambition and their athletes."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._club_names: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        banner = QFrame()
        banner.setObjectName("StatCard")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(14, 12, 14, 12)
        self.summary_label = QLabel("Rivali")
        self.summary_label.setObjectName("SectionHeader")
        banner_layout.addWidget(self.summary_label)
        hint = QLabel(
            "Le società rivali si allenano anche loro: i giovani migliorano, i veterani calano e "
            "a fine stagione si ritirano, sostituiti da nuovi atleti ogni anno un po' più forti. "
            "Le società che batti diventano più ambiziose e investono di più; quelle che ti "
            "staccano si rilassano. Il livello è sulla stessa scala del valore atteso dei tuoi atleti."
        )
        hint.setObjectName("SubTitle")
        hint.setWordWrap(True)
        banner_layout.addWidget(hint)
        root.addWidget(banner)

        compare_panel = QFrame()
        compare_panel.setObjectName("SectionPanel")
        compare_layout = QVBoxLayout(compare_panel)
        compare_layout.setContentsMargins(14, 12, 14, 12)
        compare_header = QHBoxLayout()
        compare_title = QLabel("Confronto per gara (valore atteso in una giornata normale)")
        compare_title.setObjectName("SectionHeader")
        compare_header.addWidget(compare_title)
        compare_header.addStretch()
        compare_header.addWidget(QLabel("Categoria:"))
        self.division_combo = QComboBox()
        self.division_combo.addItem("Maschile (M)", "M")
        self.division_combo.addItem("Femminile (F)", "F")
        self.division_combo.currentIndexChanged.connect(lambda _i: self.refresh(self.controller.state))
        compare_header.addWidget(self.division_combo)
        compare_layout.addLayout(compare_header)
        self.compare_table = QTableWidget(0, 5)
        self.compare_table.setHorizontalHeaderLabels(
            ["Gara", "Tuo convocato", "Media categoria", "Miglior rivale", "Margine sul migliore"]
        )
        self.compare_table.setAlternatingRowColors(True)
        self.compare_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.compare_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.compare_table.verticalHeader().setVisible(False)
        compare_layout.addWidget(self.compare_table)
        root.addWidget(compare_panel, stretch=2)

        lower = QHBoxLayout()
        lower.setSpacing(12)

        clubs_panel = QFrame()
        clubs_panel.setObjectName("SectionPanel")
        clubs_layout = QVBoxLayout(clubs_panel)
        clubs_layout.setContentsMargins(14, 12, 14, 12)
        clubs_title = QLabel("Società della categoria (seleziona per vedere gli atleti)")
        clubs_title.setObjectName("SectionHeader")
        clubs_layout.addWidget(clubs_title)
        self.clubs_table = QTableWidget(0, 5)
        self.clubs_table.setHorizontalHeaderLabels(
            ["Società", "Livello", "Ultimo anno", "Atteggiamento", "Punti lega"]
        )
        self.clubs_table.setAlternatingRowColors(True)
        self.clubs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.clubs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.clubs_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.clubs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.clubs_table.verticalHeader().setVisible(False)
        self.clubs_table.itemSelectionChanged.connect(self._show_selected_club)
        clubs_layout.addWidget(self.clubs_table)
        lower.addWidget(clubs_panel, stretch=3)

        roster_panel = QFrame()
        roster_panel.setObjectName("SectionPanel")
        roster_layout = QVBoxLayout(roster_panel)
        roster_layout.setContentsMargins(14, 12, 14, 12)
        self.roster_title = QLabel("Atleti")
        self.roster_title.setObjectName("SectionHeader")
        roster_layout.addWidget(self.roster_title)
        self.roster_table = QTableWidget(0, 5)
        self.roster_table.setHorizontalHeaderLabels(["Gara", "Atleta", "Età", "Livello", "PB"])
        self.roster_table.setAlternatingRowColors(True)
        self.roster_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.roster_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.roster_table.verticalHeader().setVisible(False)
        roster_layout.addWidget(self.roster_table)
        lower.addWidget(roster_panel, stretch=2)

        root.addLayout(lower, stretch=3)

    @staticmethod
    def _cell(text: str, color: Optional[str] = None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if color:
            item.setForeground(QColor(color))
        return item

    def refresh(self, state: GameState) -> None:
        clubs = state.rivals_in()
        events = state.active_events
        gender = self.division_combo.currentData() or "M"
        lineup = state.lineup_for(gender)
        avg = sum(c.level(events, gender=gender) for c in clubs) / len(clubs) if clubs else 0.0
        trend = sum(c.trend for c in clubs) / len(clubs) if clubs else 0.0
        by_id = {a.id: a for a in state.main_squad}
        mine = [
            expected_event_score(by_id[aid], EVENTS[ev], state.track_condition)
            for ev, aid in lineup.items()
            if ev in events and aid in by_id
        ]
        mine_avg = sum(mine) / len(mine) if mine else 0.0
        self.summary_label.setText(
            f"Categoria {state.tier.value} ({gender}): livello medio rivali {avg:.1f} "
            f"({_trend_text(trend)} nell'ultimo anno) · la tua formazione {mine_avg:.1f}"
        )

        self.compare_table.setRowCount(len(events))
        for row, ev in enumerate(events):
            levels = [(c, c.athlete_for(ev, gender)) for c in clubs]
            levels = [(c, a) for c, a in levels if a is not None]
            ev_avg = sum(a.skill for _c, a in levels) / len(levels) if levels else 0.0
            best_club, best = max(levels, key=lambda ca: ca[1].skill) if levels else (None, None)
            aid = lineup.get(ev)
            athlete = by_id.get(aid) if aid is not None else None
            mine_val = expected_event_score(athlete, EVENTS[ev], state.track_condition) if athlete else None
            vals = [
                (f"{ev} ({gender})", None),
                (f"{athlete.name} ({mine_val:.1f})" if athlete else "— nessuno —", None),
                (f"{ev_avg:.1f}", None),
                (f"{best.name}, {best_club.name} ({best.skill:.1f})" if best else "—", None),
            ]
            if mine_val is not None and best is not None:
                margin = mine_val - best.skill
                vals.append((f"{margin:+.1f}", "#34d399" if margin >= 0 else ("#fbbf24" if margin > -4 else "#f87171")))
            else:
                vals.append(("—", None))
            for col, (text, color) in enumerate(vals):
                self.compare_table.setItem(row, col, self._cell(text, color))

        selected = self._selected_club_name()
        ordered = sorted(clubs, key=lambda c: c.level(events), reverse=True)
        self._club_names = [c.name for c in ordered]
        self.clubs_table.blockSignals(True)
        self.clubs_table.setRowCount(len(ordered))
        for row, club in enumerate(ordered):
            trend_color = "#34d399" if club.trend >= 0.5 else ("#f87171" if club.trend <= -0.5 else None)
            amb_color = "#fbbf24" if club.ambition >= 1.2 else None
            vals = [
                (club.name, None),
                (f"{club.level(events):.1f}", None),
                (_trend_text(club.trend), trend_color),
                (club.ambition_label, amb_color),
                (str(state.league_table.get(club.name, 0)), None),
            ]
            for col, (text, color) in enumerate(vals):
                self.clubs_table.setItem(row, col, self._cell(text, color))
        self.clubs_table.blockSignals(False)
        if self._club_names:
            row = self._club_names.index(selected) if selected in self._club_names else 0
            self.clubs_table.selectRow(row)
        self._show_selected_club()

    def _selected_club_name(self) -> Optional[str]:
        rows = self.clubs_table.selectionModel().selectedRows()
        if rows and 0 <= rows[0].row() < len(self._club_names):
            return self._club_names[rows[0].row()]
        return None

    def _show_selected_club(self) -> None:
        state = self.controller.state
        name = self._selected_club_name()
        club = next((c for c in state.rivals_in() if c.name == name), None)
        if club is None:
            self.roster_table.setRowCount(0)
            return
        gender = self.division_combo.currentData() or "M"
        athletes_map = club.athletes_for(gender)
        self.roster_title.setText(f"Atleti ({gender}) — {club.name}")
        events = [ev for ev in state.active_events if ev in athletes_map]
        self.roster_table.setRowCount(len(events))
        for row, ev in enumerate(events):
            a = athletes_map[ev]
            age_color = "#34d399" if a.age <= 23 else ("#f87171" if a.age >= 30 else None)
            vals = [(f"{ev} ({gender})", None), (a.name, None), (str(a.age), age_color),
                    (f"{a.skill:.1f}", None), (a.pb_display or "—", None)]
            for col, (text, color) in enumerate(vals):
                self.roster_table.setItem(row, col, self._cell(text, color))
