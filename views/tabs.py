"""Tab views for Dashboard, Roster & Periodization, Calendar & Meets, Staff, and Finances."""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
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
from models.entities import (
    EVENTS,
    TIER_CONFIG,
    CompetitionSummary,
    GameState,
    PeriodizationPhase,
    TrainingFocus,
)
from views.dialogs import CompetitionResultsDialog, RecruitAthleteDialog


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
        self.objectives_list.setMaximumHeight(92)
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
        right_layout.addWidget(self.news_list)
        bottom_row.addWidget(right_panel, stretch=2)

        root.addLayout(bottom_row, stretch=1)

    def refresh(self, state: GameState) -> None:
        cfg = TIER_CONFIG[state.tier]
        rep_mult = 0.65 + (state.reputation / 100.0) * 0.55
        income = round(cfg["weekly_sponsor"] * rep_mult) + state.member_fees_weekly
        wages = sum(a.weekly_wage for a in state.athletes) + sum(
            s.weekly_cost for s in state.staff if s.hired
        )
        net = income - wages

        self.budget_val.setText(f"${state.budget:,}")
        sign = "+" if net >= 0 else ""
        self.budget_sub.setText(f"Flusso netto {sign}${net:,}/sett")

        self.prestige_val.setText(f"{state.prestige} pt")
        self.prestige_sub.setText(f"Reputazione Etica: {state.reputation}%")

        next_tier = state.tier.next_tier
        if next_tier is not None:
            req = TIER_CONFIG[next_tier]["prestige_required"]
            self.tier_progress_label.setText(
                f"Categoria: {state.tier.value} -> {next_tier.value} ({state.prestige}/{req} pt)"
            )
            self.tier_progress.setMaximum(req)
            self.tier_progress.setValue(min(state.prestige, req))
            self.tier_progress.setFormat(f"{state.prestige} / {req} Prestigio")
        else:
            self.tier_progress_label.setText("Categoria: Internazionale (Massimo Livello)")
            self.tier_progress.setMaximum(100)
            self.tier_progress.setValue(100)
            self.tier_progress.setFormat("Élite Mondiale")

        if state.club_records:
            rec_parts = [f"{ev}: {disp} ({ath})" for ev, (_v, disp, ath) in state.club_records.items()]
            self.records_label.setText("Record Sociali: " + "  |  ".join(rec_parts))
        else:
            self.records_label.setText("Record Sociali: nessun record ancora omologato.")

        fit_count = sum(1 for a in state.athletes if not a.is_injured)
        self.squad_val.setText(f"{fit_count}/{len(state.athletes)} Sani")
        self.squad_sub.setText(f"Pista in Tartan: {state.track_condition}%")

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
            self.comp_sub.setText(f"{state.season_phase.value}")

        self.objectives_list.clear()
        for obj in state.objectives:
            prefix = "[COMPLETATO] " if obj.completed else "[ ] "
            self.objectives_list.addItem(f"{prefix}{obj.title}")

        sorted_athletes = sorted(state.athletes, key=lambda a: a.overall, reverse=True)
        self.top_table.setRowCount(len(sorted_athletes))
        for row, a in enumerate(sorted_athletes):
            vals = [
                a.name,
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

        btn_recover = QPushButton("Recupero Selezionato ($250)")
        btn_recover.clicked.connect(self._recover_selected)
        toolbar.addWidget(btn_recover)

        btn_recruit = QPushButton("Scouting Studentesco")
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

        self.table = QTableWidget(0, 15)
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
                "Allenamento",
                "Periodizzazione",
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
        header.setSectionResizeMode(13, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(14, QHeaderView.ResizeMode.ResizeToContents)

        root.addWidget(self.table, stretch=1)

    def refresh(self, state: GameState) -> None:
        self._athlete_row_ids = []
        self.table.setRowCount(len(state.athletes))

        for row, a in enumerate(state.athletes):
            self._athlete_row_ids.append(a.id or -1)
            name_str = f"{a.name} *" if a.is_youth_prospect else a.name
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
            self.table.setCellWidget(row, 13, focus_combo)

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
            self.table.setCellWidget(row, 14, period_combo)

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

        lineup_title = QLabel("Convocazioni Gara (Vento > +2.0 m/s annulla i record nei 100m e Lungo)")
        lineup_title.setObjectName("SectionHeader")
        lineup_layout.addWidget(lineup_title)

        self.lineup_table = QTableWidget(0, 4)
        self.lineup_table.setHorizontalHeaderLabels(
            ["Gara", "Specialità", "Fattori Chiave", "Atleta Convocato"]
        )
        self.lineup_table.setAlternatingRowColors(True)
        self.lineup_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.lineup_table.verticalHeader().setVisible(False)
        self.lineup_table.verticalHeader().setDefaultSectionSize(38)
        self.lineup_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        lineup_layout.addWidget(self.lineup_table)
        root.addWidget(lineup_panel, stretch=1)

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

        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(
            ["Sett.", "Meeting", "Meteo", "Categoria", "Premi", "Prestigio"]
        )
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.cellDoubleClicked.connect(lambda _r, _c: self._open_selected_history())
        hist_layout.addWidget(self.history_table)

        root.addWidget(hist_panel, stretch=1)

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
            self.cycle_label.setText(
                f"Sett. {state.week} ({state.current_date:%d %b %Y}) — "
                f"Prossimo meeting tra {rem} settimana/e (Sett. {state.week + rem})."
            )
            self.cycle_label.setStyleSheet("")

        active_events = state.active_events
        self._event_combos.clear()
        self.lineup_table.setRowCount(len(active_events))

        for row, event_name in enumerate(active_events):
            event_def = EVENTS[event_name]
            key_stats = ", ".join(
                f"{k.capitalize()} {int(v * 100)}%"
                for k, v in event_def.weights.items()
                if v >= 0.15
            )
            for col, text in enumerate((event_name, event_def.specialty.value, key_stats)):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.lineup_table.setItem(row, col, item)

            combo = QComboBox()
            combo.addItem("-- Nessun Atleta --", None)
            for a in state.athletes:
                if a.is_injured:
                    continue
                label = f"{a.name} ({a.specialty.value}, OVR {a.overall}, Forma {a.form})"
                combo.addItem(label, a.id)
            assigned_id = state.event_lineup.get(event_name)
            idx = combo.findData(assigned_id)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.currentIndexChanged.connect(
                lambda _i, en=event_name, c=combo: self.controller.set_event_athlete(
                    en, c.currentData()
                )
            )
            self._event_combos[event_name] = combo
            self.lineup_table.setCellWidget(row, 3, combo)

        self._history_list = list(state.competition_history)
        self.history_table.setRowCount(len(self._history_list))
        for row, comp in enumerate(self._history_list):
            vals = [
                f"Sett. {comp.week}",
                comp.meet_name,
                comp.weather.value,
                comp.tier.value,
                f"${comp.total_prize_money:,}",
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

        panel = QFrame()
        panel.setObjectName("SectionPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)

        title = QLabel("Staff Tecnico, Medico e Preparazione Mentale")
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
        rep_mult = 0.65 + (state.reputation / 100.0) * 0.55
        sponsor = round(TIER_CONFIG[state.tier]["weekly_sponsor"] * rep_mult)
        income = sponsor + state.member_fees_weekly
        athlete_wages = sum(a.weekly_wage for a in state.athletes)
        staff_wages = sum(s.weekly_cost for s in state.staff if s.hired)
        expenses = athlete_wages + staff_wages
        net = income - expenses

        self.balance_val.setText(f"${state.budget:,}")
        self.balance_sub.setText("Cassa disponibile")

        self.sponsor_val.setText(f"+${income:,}")
        self.sponsor_sub.setText(f"Sponsor ${sponsor:,} + Quote ${state.member_fees_weekly:,}")

        self.payroll_val.setText(f"-${expenses:,}")
        self.payroll_sub.setText(f"Atleti ${athlete_wages:,} + Staff ${staff_wages:,}")

        sign = "+" if net >= 0 else ""
        self.net_val.setText(f"{sign}${net:,}")
        self.net_val.setStyleSheet("color: #34d399;" if net >= 0 else "color: #f87171;")
        self.net_sub.setText("Esclusi premi gara e trasferte")

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
