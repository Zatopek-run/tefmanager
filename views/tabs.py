"""Tab views: Dashboard, Roster, Youth Academy, Calendar & Meets, Relays, Rivals, Ranking, Staff & Facilities, Finances."""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from controllers.game_controller import GameController
from views.athlete_dialog import AthleteDetailDialog
from views.finance_chart import MonthlyBarsWidget
from views import theme
from views.widgets import (
    BADGE_LEVEL_ROLE,
    BadgeDelegate,
    HeatMapWidget,
    SeasonTimelineWidget,
    StatusPill,
    TrendChart,
    check_icon,
    make_card,
)
from models.dashboard import heat_map, season_timeline, squad_trend
from models.board import progress_text
from models.ranking import (
    club_points,
    club_ranking,
    national_ranking,
    world_ranking,
)
from models.entities import (
    BANKRUPTCY_THRESHOLD,
    BOARD_KEYS,
    BOARD_MAX_FAILED_STREAK,
    HISTORY_WEEKS,
    PROMOTION_SPOTS,
    RELEGATION_SPOTS,
    COACH_BASE_SKILL,
    COACH_COMFORT_LOAD,
    COACH_STAT_LABELS,
    COACH_STATS,
    RETIRED_COACH_HIRE_COST,
    MAX_SPECIALIZED_COACHES,
    MAX_YOUTH_COACHES,
    RELAY_CHANGE_COOLDOWN_WEEKS,
    RELAYS,
    Athlete,
    harmony_grade,
    EVENTS,
    ACADEMY_MAX_LEVEL,
    FACILITY_LABELS,
    FACILITY_ORDER,
    SCOUT_REGION_EXTRA_POINTS,
    SCOUT_REGION_FEE,
    SCOUT_REGIONS,
    GYM_MAX_LEVEL,
    GYM_TRAINING_BONUS_PER_LEVEL,
    GYM_UPKEEP_PER_LEVEL,
    NATIONALITIES,
    RANKING_NATIONAL_SIZE,
    RANKING_WORLD_SIZE,
    STAND_EXPANSION_SEATS,
    STAND_MAX_SEATS,
    TICKET_PRICE,
    WEEKLY_SCOUTING_POINTS,
    YOUTH_SQUAD_MAX,
    CompetitionSummary,
    GameState,
    PeriodizationPhase,
    RaceAttitude,
    FieldRisk,
    RaceKick,
    RacePace,
    RelayChange,
    FIELD_STRATEGY_EVENTS,
    STRATEGY_EVENTS,
    SPONSOR_TOP_N,
    SeasonOutcome,
    Specialty,
    TrainingFocus,
    gym_upgrade_cost,
    stand_expansion_cost,
    StaffRole,
)
from controllers.game_controller import scouting_search_cost
from models.facilities import FACILITY_EFFECTS, facility_cost, owns
from models.scouting import (
    academy_growth_multiplier,
    academy_upgrade_cost,
    current_band_text,
    current_half_width,
    potential_band_text,
    potential_half_width,
    region_search_extras,
    region_specialty,
    scout_candidates,
)
from models.staff import describe_attributes, hired_of_role, severance_pay
from models.finances import recent_reports
from models.simulation import expected_event_score, relay_leg_score, weekly_finances
from views.dialogs import (
    CompetitionResultsDialog,
    HireCoachDialog,
    RecruitAthleteDialog,
    release_question_text,
)


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


def _toggle_sort(active: bool, col: int, desc: bool, clicked_col: int, desc_cols: set[int]) -> tuple[bool, int, bool]:
    """Click-to-sort state machine shared by tables that re-sort their own Python row list."""
    if active and col == clicked_col:
        return True, clicked_col, not desc
    return True, clicked_col, clicked_col in desc_cols


class _ClickableCard(QFrame):
    """StatCard frame that emits `clicked` when pressed."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _make_stat_card(
    title: str, value: str = "-", clickable: bool = False
) -> tuple[QFrame, QLabel, QLabel]:
    card: QFrame = _ClickableCard() if clickable else QFrame()
    card.setObjectName("StatCard")
    if clickable:
        card.setCursor(Qt.CursorShape.PointingHandCursor)
    vbox = QVBoxLayout(card)
    vbox.setContentsMargins(14, 10, 14, 10)
    vbox.setSpacing(3)

    title_lbl = QLabel(title)
    title_lbl.setObjectName("CardTitle")
    value_lbl = QLabel(value)
    value_lbl.setObjectName("CardValue")
    sub_lbl = QLabel("")
    sub_lbl.setObjectName("SubTitle")
    sub_lbl.setWordWrap(True)

    vbox.addWidget(title_lbl)
    vbox.addWidget(value_lbl)
    vbox.addWidget(sub_lbl)
    return card, value_lbl, sub_lbl


from models.dashboard import EMPTY_SQUAD_TEXT, weekly_action_items as _weekly_action_items  # noqa: E402 - spostati nel modello (G.1 in QML)


def _empty_hint(text: str) -> QLabel:
    """Riquadro di aiuto per le schede senza dati (società appena nata): dice che cosa fare, non lascia lo schermo vuoto."""
    label = QLabel(text.replace("&&", "&"))
    label.setObjectName("SubTitle")
    label.setWordWrap(True)
    label.setStyleSheet("color: #fbbf24; border: 1px solid #fbbf24; border-radius: 6px; padding: 8px 10px;")
    label.hide()
    return label


class WidgetDashboardTab(QWidget):
    """Panoramica (G.1) in QWidget: **ripiego** della Dashboard QML (`views/dashboard_qml.py`) se QML non parte o con `TEF_NO_QML=1`."""

    navigate_requested = pyqtSignal(int)
    TOP_ATHLETES = 8  # righe della tabella dei migliori atleti

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._top_athlete_ids: list[int] = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        page = QWidget()
        page.setObjectName("DashboardPage")
        scroll.setWidget(page)
        root = QVBoxLayout(page)
        root.setContentsMargins(theme.SP_5, theme.SP_4, theme.SP_5, theme.SP_5)
        root.setSpacing(theme.SP_4)

        # Intestazione: titolo e semaforo delle notifiche (rosso = dilemma o urgenza, ambra = da guardare, verde = tutto ok)
        head = QHBoxLayout()
        title = QLabel("Panoramica")
        title.setObjectName("PageTitle")
        head.addWidget(title)
        head.addStretch()
        self.status_pill = StatusPill()
        head.addWidget(self.status_pill)
        root.addLayout(head)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(theme.SP_4)
        c1, self.budget_val, self.budget_sub = _make_stat_card("Bilancio Società", clickable=True)
        c2, self.prestige_val, self.prestige_sub = _make_stat_card("Prestigio & Etica", clickable=True)
        c3, self.squad_val, self.squad_sub = _make_stat_card("Rosa & Pista Tartan", clickable=True)
        c4, self.comp_val, self.comp_sub = _make_stat_card("Prossima Gara", clickable=True)
        c1.setToolTip("Clicca per aprire Finanze")
        c2.setToolTip("Clicca per aprire Rivali & Classifica")
        c3.setToolTip("Clicca per aprire Rosa & Allenamenti")
        c4.setToolTip("Clicca per aprire Calendario & Gare")
        c1.clicked.connect(lambda: self.navigate_requested.emit(7))
        c2.clicked.connect(lambda: self.navigate_requested.emit(5))
        c3.clicked.connect(lambda: self.navigate_requested.emit(1))
        c4.clicked.connect(lambda: self.navigate_requested.emit(3))
        for c in (c1, c2, c3, c4):
            cards_row.addWidget(c, stretch=1)
        root.addLayout(cards_row)

        # Andamento della rosa + priorità (l'azione sta sopra la piega anche a 840 px di altezza)
        row2 = QHBoxLayout()
        row2.setSpacing(theme.SP_4)
        trend_card, trend_body, _ = make_card("Forma e fatica della rosa", f"ultime {HISTORY_WEEKS} settimane")
        self.trend_chart = TrendChart()
        trend_body.addWidget(self.trend_chart, stretch=1)
        row2.addWidget(trend_card, stretch=3)

        actions_card, actions_outer, _ = make_card("Priorità della settimana")
        self.actions_box = QVBoxLayout()
        self.actions_box.setSpacing(theme.SP_2)
        actions_outer.addLayout(self.actions_box)
        actions_outer.addStretch()
        row2.addWidget(actions_card, stretch=2)
        root.addLayout(row2)

        # Stagione (timeline, posizione in lega, record) + obiettivi
        row3 = QHBoxLayout()
        row3.setSpacing(theme.SP_4)
        tier_card, tier_body, _ = make_card("Stagione")
        self.tier_progress_label = QLabel("Percorso Categoria")
        self.tier_progress_label.setObjectName("CardLead")
        self.tier_progress_label.setWordWrap(True)
        tier_body.addWidget(self.tier_progress_label)
        self.timeline = SeasonTimelineWidget()
        tier_body.addWidget(self.timeline)
        self.tier_progress = QProgressBar()
        tier_body.addWidget(self.tier_progress)
        rec_row = QHBoxLayout()
        rec_texts = QVBoxLayout()
        rec_texts.setSpacing(2)
        self.records_label = QLabel("Record Sociali: nessuno ancora stabilito")
        self.records_label.setObjectName("CardHint")
        self.records_label.setWordWrap(True)
        rec_texts.addWidget(self.records_label)
        self.contracts_label = QLabel("")
        self.contracts_label.setObjectName("CardHint")
        self.contracts_label.setWordWrap(True)
        rec_texts.addWidget(self.contracts_label)
        rec_row.addLayout(rec_texts, stretch=1)
        albo_btn = QPushButton("Albo && Record →")  # «&&»: un «&» solo sarebbe il mnemonico di tastiera e sparirebbe
        albo_btn.clicked.connect(lambda: self.navigate_requested.emit(8))
        rec_row.addWidget(albo_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        tier_body.addLayout(rec_row)
        row3.addWidget(tier_card, stretch=3)

        obj_card, obj_body, _ = make_card("Obiettivi di stagione")
        self.objectives_list = QListWidget()
        self.objectives_list.setObjectName("FlatList")
        self.objectives_list.setWordWrap(True)
        self.objectives_list.setIconSize(QSize(18, 18))
        self.objectives_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.objectives_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.objectives_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        obj_body.addWidget(self.objectives_list, stretch=1)
        row3.addWidget(obj_card, stretch=2)
        root.addLayout(row3)

        # Heat map + cronaca
        row4 = QHBoxLayout()
        row4.setSpacing(theme.SP_4)
        heat_card, heat_body, _ = make_card("Dove sono forti e deboli", "punteggio atteso per gara, oggi")
        self.heat_map_widget = HeatMapWidget()
        heat_body.addWidget(self.heat_map_widget)
        row4.addWidget(heat_card, stretch=3)

        news_card, news_body, _ = make_card("Momenti memorabili & cronaca")
        self.news_list = QListWidget()
        self.news_list.setObjectName("FlatList")
        self.news_list.setWordWrap(True)
        self.news_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.news_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.news_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.news_list.setMinimumHeight(200)
        news_body.addWidget(self.news_list, stretch=1)
        row4.addWidget(news_card, stretch=2)
        root.addLayout(row4)

        # Migliori atleti (a tutta larghezza: i nomi stanno interi)
        top_card, top_body, _ = make_card("Migliori atleti in rosa", "doppio clic per la Scheda Atleta")
        self.top_table = QTableWidget(0, 6)
        self.top_table.setHorizontalHeaderLabels(["Atleta", "Disciplina", "OVR", "Forma", "Fatica", "Stato"])
        self.top_table.setAlternatingRowColors(False)
        self.top_table.setShowGrid(False)
        self.top_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.top_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.top_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.top_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.top_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)  # niente più «Giulia ...» né «isciplir»
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(64)
        self.top_table.verticalHeader().setVisible(False)
        self.top_table.verticalHeader().setDefaultSectionSize(self.TOP_ROW_H)
        self.top_table.setItemDelegateForColumn(5, BadgeDelegate(self.top_table))
        self.top_table.cellDoubleClicked.connect(lambda row, _col: self._open_top_detail(row))
        top_body.addWidget(self.top_table)
        root.addWidget(top_card)
        root.addStretch()

    TOP_ROW_H = 40

    def _open_top_detail(self, row: int) -> None:
        if 0 <= row < len(self._top_athlete_ids) and self._top_athlete_ids[row] != -1:
            AthleteDetailDialog(self.controller, self._top_athlete_ids[row], parent=self).exec()

    def refresh(self, state: GameState) -> None:
        net = weekly_finances(state)["net"]

        self.budget_val.setText(f"€{state.budget:,}")
        self.budget_val.setStyleSheet(f"color: {theme.BAD};" if state.budget < 0 else "")
        sign = "+" if net >= 0 else ""
        if state.bankrupt:
            self.budget_sub.setText("SOCIETÀ FALLITA — avvia una nuova partita")
        elif state.budget < 0:
            self.budget_sub.setText(
                f"In rosso: 5% interessi/sett, fallimento sotto -€{-BANKRUPTCY_THRESHOLD:,}"
            )
        else:
            self.budget_sub.setText(f"Flusso netto {sign}€{net:,}/sett")

        self.prestige_val.setText(f"{state.prestige} pt")
        self.prestige_sub.setText(f"Reputazione Etica: {state.reputation}%")

        pos = state.league_position
        standings = state.league_standings()
        pts = dict(standings).get(state.team_name, 0)
        weeks_left = state.weeks_to_season_end
        if weeks_left is None:
            self.tier_progress_label.setText(
                f"Lega {state.tier.display_name}: {pos}° su {len(standings)} con {pts} pt "
                "(promozioni e retrocessioni solo in Carriera)"
            )
            self.tier_progress.setMaximum(8)
            self.tier_progress.setValue(min(8, state.week))
            self.tier_progress.setFormat(f"Prototipo: settimana {min(8, state.week)} di 8")
        else:
            if pos <= PROMOTION_SPOTS and state.tier.next_tier is not None:
                zone = f"zona promozione → {state.tier.next_tier.display_name}"
            elif pos <= PROMOTION_SPOTS:
                zone = "in corsa per il titolo" if pos > 1 else "in testa: verso il titolo"
            elif pos > len(standings) - RELEGATION_SPOTS and state.tier.previous_tier is not None:
                zone = f"zona retrocessione → {state.tier.previous_tier.display_name}"
            else:
                zone = "metà classifica"
            self.tier_progress_label.setText(
                f"Lega {state.tier.display_name}: {pos}° su {len(standings)} con {pts} pt — {zone}"
            )
            done = state.season_length - weeks_left
            self.tier_progress.setMaximum(state.season_length)
            self.tier_progress.setValue(done)
            self.tier_progress.setFormat(
                f"Stagione {state.season_number}: mancano {weeks_left} settimane al verdetto "
                f"(prime {PROMOTION_SPOTS} su, ultima giù)"
            )
        if state.season_history:
            last = state.season_history[0]
            self.tier_progress.setToolTip(
                f"Stagione {last.season}: {last.placement}° in {last.tier.display_name} — {last.outcome.value}"
            )

        timeline = season_timeline(state)
        in_career = state.game_mode == "career"  # il Prototipo dura 8 settimane e non ha stagioni né contratti: niente timeline
        self.timeline.setVisible(in_career)
        self.timeline.set_timeline(timeline, [p.value.split(" (")[0] for p in state.season_cycle])
        if in_career and timeline.expiring:
            shown = ", ".join(timeline.expiring[:2]) + (f" e altri {len(timeline.expiring) - 2}" if len(timeline.expiring) > 2 else "")
            self.contracts_label.setText(f"Contratti in scadenza a fine stagione: {shown}")
        else:
            self.contracts_label.setText("")

        n_m = len(state.club_records)
        n_f = len(state.club_records_f)
        if n_m or n_f:
            seasons_note = (
                f" · {len(state.season_history)} stagioni in archivio"
                if state.season_history
                else ""
            )
            self.records_label.setText(
                f"Record Sociali omologati: {n_m} maschili · {n_f} femminili{seasons_note}"
            )
        else:
            self.records_label.setText("Record Sociali: nessun record ancora omologato.")

        squad = state.main_squad
        fit_count = sum(1 for a in squad if not a.is_injured)
        if squad:
            self.squad_val.setText(f"{fit_count}/{len(squad)} Sani")
            self.squad_sub.setText(
                f"Vivaio {len(state.youth_squad)}/{YOUTH_SQUAD_MAX} · Pista {state.track_condition}%"
            )
        else:
            self.squad_val.setText("Nessun atleta")
            self.squad_sub.setText("Vai a Vivaio & Osservatori o al Mercato per tesserare")

        if state.is_vertical_slice_complete:
            self.comp_val.setText("Prototipo OK")
            self.comp_val.setStyleSheet(f"color: {theme.GOOD};")
            self.comp_sub.setText("2 gare completate — avvia Carriera!")
        elif state.is_competition_week:
            self.comp_val.setText("QUESTA SETT!")
            self.comp_val.setStyleSheet(f"color: {theme.WARN};")
            self.comp_sub.setText("Prepara lo Scarico & gareggia")
        else:
            rem = state.weeks_until_competition
            self.comp_val.setText(f"Tra {rem} sett.")
            self.comp_val.setStyleSheet("")
            venue = "In casa" if state.next_meet_is_home else "In trasferta"
            self.comp_sub.setText(f"{venue} · {state.season_phase.value}")

        trend = squad_trend(state)
        self.trend_chart.set_empty_text(
            "Lo storico si riempie giocando: avanza la prima settimana."
            if state.main_squad
            else "Nessun atleta in rosa: lo storico parte quando tessererai i primi atleti."
        )
        self.trend_chart.set_series([t[0] for t in trend], [t[1] for t in trend])
        self.heat_map_widget.set_heat_map(heat_map(state))

        self.objectives_list.clear()
        for obj in state.objectives:
            progress = progress_text(state, obj) if obj.key in BOARD_KEYS else ""
            item = QListWidgetItem(check_icon(obj.completed), obj.title + (f" — {progress}" if progress else ""))
            if obj.completed:
                item.setForeground(QColor(theme.TEXT_MUTED))
            self.objectives_list.addItem(item)
        if state.fired:
            self.objectives_list.addItem("ESONERATO dal Board: la partita è finita.")
        elif state.board_failed_streak:
            self.objectives_list.addItem(
                f"Attenzione: {state.board_failed_streak} stagione/i fallita/e di fila. "
                f"Alla {BOARD_MAX_FAILED_STREAK}ª arriva l'esonero."
            )
        self._fit_list_height(self.objectives_list)

        sorted_athletes = sorted(state.main_squad, key=lambda a: a.overall, reverse=True)[: self.TOP_ATHLETES]
        self._top_athlete_ids = [a.id or -1 for a in sorted_athletes]
        self.top_table.clearSpans()
        self.top_table.setRowCount(len(sorted_athletes) or 1)
        if not sorted_athletes:
            placeholder = QTableWidgetItem(EMPTY_SQUAD_TEXT.replace("&&", "&"))
            placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.top_table.setItem(0, 0, placeholder)
            self.top_table.setSpan(0, 0, 1, self.top_table.columnCount())
        for row, a in enumerate(sorted_athletes):
            vals = [
                f"{a.name} ({a.gender})",
                a.specialty.value,
                str(a.overall),
                str(a.form),
                str(a.fatigue),
                a.status_label,
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    (Qt.AlignmentFlag.AlignLeft if col == 0 else Qt.AlignmentFlag.AlignCenter) | Qt.AlignmentFlag.AlignVCenter
                )
                if col == 5:
                    if a.is_injured or a.doping_boost_weeks > 0:
                        level = "danger"
                    elif a.fatigue >= 75:
                        level = "warn"
                    else:
                        level = "ok"
                    item.setData(BADGE_LEVEL_ROLE, level)
                self.top_table.setItem(row, col, item)
        header_h = self.top_table.horizontalHeader().height() or 34
        self.top_table.setFixedHeight(header_h + self.TOP_ROW_H * self.top_table.rowCount() + 6)

        while self.actions_box.count():
            child = self.actions_box.takeAt(0)
            old_btn = child.widget()
            if old_btn is not None:
                old_btn.hide()  # senza questo il vecchio pulsante resta disegnato (e coprirebbe la scheda) fino al deleteLater
                old_btn.setParent(None)
                old_btn.deleteLater()
        items = _weekly_action_items(state, self.controller.free_agent_pool)
        for text, severity, target_idx in items:
            btn = QPushButton(text)
            btn.setObjectName("ActionItemButton")
            btn.setProperty("severity", severity)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.clicked.connect(lambda _c=False, idx=target_idx: self.navigate_requested.emit(idx))
            self.actions_box.addWidget(btn)
        self._update_status(state, items)

        self.news_list.clear()
        for m in state.milestones[:6]:
            self.news_list.addItem(f"★ {m}")
        for entry in state.news_log[:18]:
            self.news_list.addItem(entry)

    def _update_status(self, state: GameState, items: list) -> None:
        """Semaforo: rosso se c'è un dilemma da risolvere o un'urgenza, ambra se c'è qualcosa da guardare, verde se tutto ok."""
        danger = sum(1 for _t, sev, _i in items if sev == "danger")
        warn = sum(1 for _t, sev, _i in items if sev == "warn")
        if state.pending_dilemma is not None:
            self.status_pill.set_level("danger", "Dilemma da risolvere")
        elif danger:
            self.status_pill.set_level("danger", f"{danger} urgenz{'a' if danger == 1 else 'e'}")
        elif warn:
            self.status_pill.set_level("warn", f"{warn} da guardare")
        else:
            self.status_pill.set_level("ok", "Tutto ok")

    @staticmethod
    def _fit_list_height(lst: QListWidget) -> None:
        """Altezza della lista = somma delle righe, così la scheda non lascia vuoti né taglia le voci."""
        total = 8 + sum(lst.sizeHintForRow(i) for i in range(lst.count()))
        lst.setMinimumHeight(max(120, total))


class RosterTab(QWidget):
    """Roster management, periodization cycles, recovery, and youth scouting."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._athlete_row_ids: list[int] = []
        self._gender_filter: str = "ALL"
        self._sort_col: int = 4  # OVR/Pot descending by default? Keep insertion order until user sorts!
        self._sort_active: bool = False
        self._sort_desc: bool = True
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        self.empty_hint = _empty_hint(EMPTY_SQUAD_TEXT)
        root.addWidget(self.empty_hint)

        toolbar = QHBoxLayout()
        title = QLabel("Rosa")  # il resto («periodizzazione e recupero») è nei pulsanti: con Inter il titolo lungo non ci stava
        title.setObjectName("SectionHeader")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.bulk_period_combo = QComboBox()
        for phase in PeriodizationPhase:
            self.bulk_period_combo.addItem(f"Ciclo Tutti: {phase.value}", phase)
        self.bulk_period_combo.activated.connect(self._apply_bulk_period)
        self.bulk_period_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        toolbar.addWidget(self.bulk_period_combo)

        btn_rest = QPushButton("Tutti: Riposo")
        btn_rest.clicked.connect(
            lambda: self.controller.set_all_training(TrainingFocus.REST)
        )
        toolbar.addWidget(btn_rest)

        self.btn_detail = QPushButton("Scheda Atleta")
        self.btn_detail.clicked.connect(self._open_detail_selected)
        toolbar.addWidget(self.btn_detail)

        self.btn_recover = QPushButton("Recupero Selezionato (€250)")
        self.btn_recover.clicked.connect(self._recover_selected)
        toolbar.addWidget(self.btn_recover)

        btn_recruit = QPushButton("Mercato Svincolati")
        btn_recruit.setObjectName("PrimaryButton")
        btn_recruit.clicked.connect(self._open_recruit_dialog)
        toolbar.addWidget(btn_recruit)

        self.btn_release = QPushButton("Svincola")
        self.btn_release.setObjectName("DangerButton")
        self.btn_release.clicked.connect(self._release_selected)
        toolbar.addWidget(self.btn_release)

        root.addLayout(toolbar)

        # Quick filter & search bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)
        self._gender_group = QButtonGroup(self)
        for label, code in (("Tutti", "ALL"), ("Maschile (M)", "M"), ("Femminile (F)", "F")):
            pill = QPushButton(label)
            pill.setObjectName("FilterPill")
            pill.setCheckable(True)
            if code == "ALL":
                pill.setChecked(True)
            pill.clicked.connect(lambda _c=False, c=code: self._set_gender_filter(c))
            self._gender_group.addButton(pill)
            filter_bar.addWidget(pill)

        self.spec_filter = QComboBox()
        self.spec_filter.addItem("Tutte le discipline", None)
        for spec in Specialty:
            self.spec_filter.addItem(spec.value, spec)
        self.spec_filter.currentIndexChanged.connect(lambda _i: self.refresh(self.controller.state))
        filter_bar.addWidget(self.spec_filter)

        self.healthy_only_check = QCheckBox("Solo disponibili")
        self.healthy_only_check.toggled.connect(lambda _b: self.refresh(self.controller.state))
        filter_bar.addWidget(self.healthy_only_check)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca atleta per nome...")
        self.search_input.setMinimumWidth(170)
        self.search_input.setMaximumWidth(230)
        self.search_input.textChanged.connect(lambda _t: self.refresh(self.controller.state))
        filter_bar.addWidget(self.search_input)

        filter_bar.addStretch()
        self.count_label = QLabel("")
        self.count_label.setObjectName("SubTitle")
        filter_bar.addWidget(self.count_label)
        root.addLayout(filter_bar)

        hint = QLabel(
            "Clicca sulle intestazioni per ordinare. Prep. Specifica accelera la crescita ma stanca; "
            "Scarico prima delle gare riduce la fatica e fa salire la Forma."
        )
        hint.setObjectName("SubTitle")
        hint.setWordWrap(True)
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
        header.setMinimumSectionSize(38)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(14, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(15, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(16, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(14, 128)
        self.table.setColumnWidth(15, 132)
        self.table.setColumnWidth(16, 150)
        header.sectionClicked.connect(self._on_header_clicked)

        self.table.cellDoubleClicked.connect(lambda row, _col: self._open_detail(row))
        self.table.itemSelectionChanged.connect(self._update_selection_buttons)
        root.addWidget(self.table, stretch=1)
        self._update_selection_buttons()

    def _update_selection_buttons(self) -> None:
        has_selection = bool(self.table.selectionModel().selectedRows())
        self.btn_detail.setEnabled(has_selection)
        self.btn_recover.setEnabled(has_selection)
        self.btn_release.setEnabled(has_selection)

    def _set_gender_filter(self, code: str) -> None:
        self._gender_filter = code
        self.refresh(self.controller.state)

    def _on_header_clicked(self, col: int) -> None:
        if col >= 14:
            return
        if self._sort_active and self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_active = True
            self._sort_col = col
            self._sort_desc = col in (4, 5, 6, 7, 8, 9, 13)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(
            col, Qt.SortOrder.DescendingOrder if self._sort_desc else Qt.SortOrder.AscendingOrder
        )
        self.refresh(self.controller.state)

    @staticmethod
    def _sort_key(a: Athlete, col: int):
        keys = {
            0: a.name.lower(),
            1: a.age,
            2: a.specialty.value,
            3: a.personality.value,
            4: (a.overall, a.potential),
            5: a.power,
            6: a.stamina,
            7: a.technique,
            8: a.resilience,
            9: a.form,
            10: a.fatigue,
            11: a.status_label,
            12: a.personal_best or 0.0,
            13: a.fans,
        }
        return keys.get(col, a.name.lower())

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
        full_squad = state.main_squad
        self.empty_hint.setVisible(not full_squad)
        query = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        spec_val = self.spec_filter.currentData() if hasattr(self, "spec_filter") else None
        healthy_only = self.healthy_only_check.isChecked() if hasattr(self, "healthy_only_check") else False

        squad = [
            a
            for a in full_squad
            if (self._gender_filter == "ALL" or a.gender == self._gender_filter)
            and (not isinstance(spec_val, Specialty) or a.specialty == spec_val)
            and (not healthy_only or not a.is_injured)
            and (not query or query in a.name.lower())
        ]
        if self._sort_active:
            squad.sort(key=lambda a: self._sort_key(a, self._sort_col), reverse=self._sort_desc)
        if hasattr(self, "count_label"):
            self.count_label.setText(f"Mostrati {len(squad)}/{len(full_squad)} atleti")
        self.table.clearContents()
        self.table.setRowCount(0)
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
        self._update_selection_buttons()

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
        prospects = self.controller.get_free_agent_market(count=5)
        dlg = RecruitAthleteDialog(
            prospects,
            self.controller.state.budget,
            roster=self.controller.state.main_squad,
            parent=self,
            agents=self.controller.state.agents,
        )
        if dlg.exec() and dlg.selected_prospect is not None:
            self.controller.recruit_athlete(dlg.selected_prospect, terms=dlg.selected_terms)

    def _release_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Svincola Atleta", "Seleziona prima una riga.")
            return
        row = rows[0].row()
        if 0 <= row < len(self._athlete_row_ids):
            aid = self._athlete_row_ids[row]
            athlete = next((a for a in self.controller.state.athletes if a.id == aid), None)
            if athlete and QMessageBox.question(
                self, "Conferma", release_question_text(athlete, self.controller.state.budget)
            ) == QMessageBox.StandardButton.Yes:
                self.controller.release_athlete(aid)


class CalendarTab(QWidget):
    """Competition schedule, active event lineup selection, and past meet results."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._event_combos: Dict[str, QComboBox] = {}
        self._history_list: list[CompetitionSummary] = []
        self._division_filter: str = "ALL"
        self._hist_sort_active = False
        self._hist_sort_col = 0
        self._hist_sort_desc = True
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        self.empty_hint = _empty_hint(
            "Nessun atleta da convocare: senza atleti la società non si iscrive ai meeting (nessuna sanzione). "
            + EMPTY_SQUAD_TEXT
        )
        root.addWidget(self.empty_hint)

        banner = QFrame()
        banner.setObjectName("StatCard")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(14, 12, 14, 12)
        self.cycle_label = QLabel("Calendario Gare")
        self.cycle_label.setObjectName("SectionHeader")
        self.cycle_label.setWordWrap(True)
        banner_layout.addWidget(self.cycle_label, stretch=1)

        div_group = QButtonGroup(self)
        for label, code in (("Tutte", "ALL"), ("M", "M"), ("F", "F")):
            pill = QPushButton(label)
            pill.setObjectName("FilterPill")
            pill.setCheckable(True)
            if code == "ALL":
                pill.setChecked(True)
            pill.clicked.connect(lambda _c=False, c=code: self._set_division_filter(c))
            div_group.addButton(pill)
            banner_layout.addWidget(pill)
        self._div_group = div_group

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

        self.lineup_table = QTableWidget(0, 6)
        self.lineup_table.setHorizontalHeaderLabels(
            ["Gara", "Specialità", "Fattori Chiave", "Atleta Convocato", "Atteggiamento", "Piano gara / Rischio"]
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
        hist_title = QLabel("Archivio Gare Disputate (Doppio clic per classifiche e vento; clic sull'intestazione per ordinare)")
        hist_title.setObjectName("SectionHeader")
        hist_header.addWidget(hist_title)
        hist_header.addStretch()
        self.hist_search = QLineEdit()
        self.hist_search.setPlaceholderText("Cerca meeting...")
        self.hist_search.setMaximumWidth(180)
        self.hist_search.textChanged.connect(lambda _t: self.refresh(self.controller.state))
        hist_header.addWidget(self.hist_search)
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
        self.history_table.horizontalHeader().sectionClicked.connect(self._on_history_header_clicked)
        hist_layout.addWidget(self.history_table)

        lower_row.addWidget(hist_panel, stretch=3)
        root.addLayout(lower_row, stretch=1)

    def _build_strategy_widget(self, state: GameState, event_name: str) -> QWidget:
        """Ritmo iniziale e scatto finale di un 800m/1500m (B.1): due menu a tendina nella stessa cella."""
        pace, kick = state.strategy_for(event_name)
        pace_combo, kick_combo = QComboBox(), QComboBox()
        for p in RacePace:
            pace_combo.addItem(f"Ritmo {p.value}", p)
        for k in RaceKick:
            kick_combo.addItem(f"Scatto: {k.value}", k)
        pace_combo.setCurrentIndex(max(0, pace_combo.findData(pace)))
        kick_combo.setCurrentIndex(max(0, kick_combo.findData(kick)))
        pace_combo.setToolTip(
            "Veloce: più punteggio ma più fatica (se l'atleta ha poca resistenza il vantaggio svanisce). Lento: meno punteggio, meno fatica."
        )
        kick_combo.setToolTip("Lo scatto finale dà punteggio in più al prezzo di fatica; richiede resistenza.")

        def changed(_i: int = 0, en: str = event_name) -> None:
            self.controller.set_race_strategy(en, pace_combo.currentData(), kick_combo.currentData())

        pace_combo.currentIndexChanged.connect(changed)
        kick_combo.currentIndexChanged.connect(changed)
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.addWidget(pace_combo)
        layout.addWidget(kick_combo)
        return box

    def _build_risk_widget(self, state: GameState, event_name: str) -> QWidget:
        """Rischio di un concorso (B.2): un solo menu a tendina."""
        combo = QComboBox()
        for risk in FieldRisk:
            combo.addItem(f"Rischio {risk.value}", risk)
        combo.setCurrentIndex(max(0, combo.findData(state.risk_for(event_name))))
        combo.setToolTip(
            "Bilanciato: +1 tecnica, 5% di tentativo nullo. Aggressivo: +3 tecnica, 15% di nullo. "
            "Un nullo fa perdere il tentativo migliore: la misura scende un poco."
        )
        combo.currentIndexChanged.connect(
            lambda _i, en=event_name: self.controller.set_field_risk(en, combo.currentData())
        )
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.addWidget(combo)
        return box

    def _pick_lineup_athlete(self, event_name: str, gender: str, combo: QComboBox) -> None:
        """Convoca l'atleta scelto; se il controller rifiuta (tetto di gare, età) rimette la scelta di prima."""
        ok = self.controller.set_event_athlete(event_name, combo.currentData(), gender=gender)
        if not ok:
            current = self.controller.state.lineup_for(gender).get(event_name)
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(current)))
            combo.blockSignals(False)
        # le altre tendine devono riflettere il nuovo tetto di gare: si ricostruiscono fuori dal segnale in corso
        QTimer.singleShot(0, lambda: self.refresh(self.controller.state))

    def refresh(self, state: GameState) -> None:
        self.empty_hint.setVisible(not state.main_squad)
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
        divisions = ("M", "F") if self._division_filter == "ALL" else (self._division_filter,)
        self.lineup_table.clearContents()
        self.lineup_table.setRowCount(0)
        self.lineup_table.setRowCount(len(active_events) * len(divisions))
        by_id = {a.id: a for a in state.main_squad}

        for ev_idx, event_name in enumerate(active_events):
            event_def = EVENTS[event_name]
            key_stats = ", ".join(
                f"{k.capitalize()} {int(v * 100)}%"
                for k, v in event_def.weights.items()
                if v >= 0.15
            )
            for div_idx, gender in enumerate(divisions):
                row = ev_idx * len(divisions) + div_idx
                assigned_id = state.lineup_for(gender).get(event_name)
                assigned_ath = by_id.get(assigned_id) if assigned_id is not None else None
                uncovered = assigned_ath is None or assigned_ath.is_injured

                for col, text in enumerate((f"{event_name} ({gender})", event_def.specialty.value, key_stats)):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if col == 0 and uncovered:
                        item.setForeground(QColor("#f87171"))
                    self.lineup_table.setItem(row, col, item)

                combo = QComboBox()
                combo.addItem("-- Nessun Atleta --", None)
                for a in state.main_squad:
                    if a.is_injured or a.gender != gender:
                        continue
                    # chi non è ammesso (tetto di 2 gare individuali, età minima) non si offre, salvo il già convocato
                    if a.id != assigned_id and state.lineup_problem(a, event_name, gender) is not None:
                        continue
                    label = f"{a.name} ({a.specialty.value}, OVR {a.overall}, Forma {a.form})"
                    combo.addItem(label, a.id)
                idx = combo.findData(assigned_id)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
                combo.currentIndexChanged.connect(
                    lambda _i, en=event_name, g=gender, c=combo: self._pick_lineup_athlete(en, g, c)
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

                if event_name in STRATEGY_EVENTS:
                    self.lineup_table.setCellWidget(row, 5, self._build_strategy_widget(state, event_name))
                elif event_name in FIELD_STRATEGY_EVENTS:
                    self.lineup_table.setCellWidget(row, 5, self._build_risk_widget(state, event_name))

        league_rows = state.league_standings()
        if state.game_mode == "career":
            self.league_title.setText(
                f"Classifica di Lega — {state.tier.display_name} (verdetto tra {state.weeks_to_season_end} sett.)"
            )
        else:
            self.league_title.setText(f"Classifica di Lega — {state.tier.display_name}")
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

        query = self.hist_search.text().strip().lower() if hasattr(self, "hist_search") else ""
        self._history_list = [
            c for c in state.competition_history if not query or query in c.meet_name.lower()
        ]
        if self._hist_sort_active:
            sort_keys = {
                0: lambda c: c.week,
                1: lambda c: c.meet_name.lower(),
                2: lambda c: c.is_home,
                3: lambda c: c.weather.value,
                4: lambda c: c.team_placement or 99,
                5: lambda c: c.total_prize_money + c.ticket_income,
                6: lambda c: c.total_prestige_gained,
            }
            self._history_list.sort(
                key=sort_keys.get(self._hist_sort_col, sort_keys[0]), reverse=self._hist_sort_desc
            )
        self.history_table.setRowCount(len(self._history_list))
        for row, comp in enumerate(self._history_list):
            team_place = comp.team_placement
            vals = [
                f"Sett. {comp.week}",
                comp.meet_name,
                f"Casa ({comp.spectators:,})" if comp.is_home else "Trasferta",
                comp.weather.value,
                f"{team_place}ª" if team_place else "—",
                f"€{comp.total_prize_money + comp.ticket_income:,}",
                f"+{comp.total_prestige_gained}",
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.history_table.setItem(row, col, item)

    def _set_division_filter(self, code: str) -> None:
        self._division_filter = code
        self.refresh(self.controller.state)

    def _open_selected_history(self) -> None:
        rows = self.history_table.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        if 0 <= idx < len(self._history_list):
            dlg = CompetitionResultsDialog(self._history_list[idx], parent=self)
            dlg.exec()

    def _on_history_header_clicked(self, col: int) -> None:
        self._hist_sort_active, self._hist_sort_col, self._hist_sort_desc = _toggle_sort(
            self._hist_sort_active, self._hist_sort_col, self._hist_sort_desc, col, desc_cols={0, 5, 6}
        )
        self.refresh(self.controller.state)


class StaffTab(QWidget):
    """Club technical & medical staff hiring plus tartan track maintenance."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._coach_sort_active = False
        self._coach_sort_col = 0
        self._coach_sort_desc = False
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

        maint_btn = QPushButton("Manutenzione Pista Tartan (€900)")
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

        # Impianti avanzati (E.2): una scheda per impianto, acquisto una tantum.
        advanced_row = QHBoxLayout()
        advanced_row.setSpacing(12)
        self.facility_btns: Dict[str, QPushButton] = {}
        self.facility_subs: Dict[str, QLabel] = {}
        for key in FACILITY_ORDER:
            card = QFrame()
            card.setObjectName("StatCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            head = QLabel(FACILITY_LABELS[key])
            head.setObjectName("SectionHeader")
            sub = QLabel(FACILITY_EFFECTS[key])
            sub.setObjectName("SubTitle")
            sub.setWordWrap(True)
            btn = QPushButton("")
            btn.setObjectName("PrimaryButton")
            btn.clicked.connect(lambda _checked=False, k=key: self.controller.buy_facility(k))
            card_layout.addWidget(head)
            card_layout.addWidget(sub)
            card_layout.addWidget(btn)
            self.facility_btns[key] = btn
            self.facility_subs[key] = sub
            advanced_row.addWidget(card)
        root.addLayout(advanced_row)

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
        ch.sectionClicked.connect(self._on_coach_header_clicked)
        coach_layout.addWidget(self.coach_table)
        root.addWidget(coach_panel, stretch=2)

        panel = QFrame()
        panel.setObjectName("SectionPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)

        title = QLabel("Staff Medico e Preparazione Mentale")
        title.setObjectName("SectionHeader")
        panel_layout.addWidget(title)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Nome", "Ruolo", "Livello", "Costo/sett", "Attributi (1-20)", "Effetto", "Azione"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        panel_layout.addWidget(self.table)
        root.addWidget(panel, stretch=3)  # 9 candidati dello staff (E.1): serve più altezza di prima

    def refresh(self, state: GameState) -> None:
        self.track_label.setText(
            f"Condizione Pista in Tartan: {state.track_condition}% "
            "(una pista usurata rallenta leggermente tempi e salti)"
        )
        lvl = state.gym_level
        self.gym_label.setText(f"Palestra — livello {lvl}/{GYM_MAX_LEVEL}")
        self.gym_sub.setText(
            f"+{int(lvl * GYM_TRAINING_BONUS_PER_LEVEL * 100)}% probabilità di miglioramento in allenamento · "
            f"gestione €{lvl * GYM_UPKEEP_PER_LEVEL}/sett"
        )
        if lvl >= GYM_MAX_LEVEL:
            self.gym_btn.setText("Livello massimo")
            self.gym_btn.setEnabled(False)
        else:
            self.gym_btn.setText(f"Amplia a livello {lvl + 1} (€{gym_upgrade_cost(lvl):,})")
            self.gym_btn.setEnabled(True)

        for key, btn in self.facility_btns.items():
            if owns(state.facilities, key):
                btn.setText("Posseduto")
                btn.setEnabled(False)
            else:
                btn.setText(f"Acquista (€{facility_cost(key):,})")
                btn.setEnabled(True)

        price = TICKET_PRICE[state.tier.value]
        self.stand_label.setText(f"Tribune — {state.stand_seats:,} posti")
        self.stand_sub.setText(
            f"Nei meeting in casa niente trasferta e incasso biglietti (€{price}/biglietto in "
            f"{state.tier.display_name}). Il pubblico cresce con prestigio, categoria e reputazione."
        )
        if state.stand_seats >= STAND_MAX_SEATS:
            self.stand_btn.setText("Capienza massima")
            self.stand_btn.setEnabled(False)
        else:
            self.stand_btn.setText(
                f"+{STAND_EXPANSION_SEATS} posti (€{stand_expansion_cost(state.stand_seats):,})"
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
        coaches = list(state.coaches)
        if self._coach_sort_active:
            col = self._coach_sort_col
            if col == 0:
                key = lambda c: c.name.lower()
            elif col == 1:
                key = lambda c: c.kind_label
            elif 2 <= col <= 5:
                stat = COACH_STATS[col - 2]
                key = lambda c: c.skills.get(stat, 0)
            elif col == 6:
                key = lambda c: state.coach_load(c)
            else:
                key = lambda c: c.weekly_wage
            coaches.sort(key=key, reverse=self._coach_sort_desc)
        self.coach_table.setRowCount(len(coaches))
        for row, coach in enumerate(coaches):
            load = state.coach_load(coach)
            vals = [
                coach.name,
                coach.kind_label,
                *[str(coach.skills.get(stat, 0)) for stat in COACH_STATS],
                f"{load}/{COACH_COMFORT_LOAD}",
                f"€{coach.weekly_wage}",
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

        # Mercato dello staff (E.1): raggruppato per ruolo, dal più economico al più caro
        role_order = list(StaffRole)
        staff_rows = sorted(state.staff, key=lambda m: (role_order.index(m.role), m.weekly_cost))
        self.table.setRowCount(len(staff_rows))
        for row, s in enumerate(staff_rows):
            vals = [
                s.name,
                s.role.value,
                "★" * s.skill,
                f"€{s.weekly_cost}",
                describe_attributes(s),
                s.description,
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                    if col in (0, 4, 5)
                    else Qt.AlignmentFlag.AlignCenter
                )
                if s.hired and col == 0:
                    item.setForeground(QColor("#34d399"))
                self.table.setItem(row, col, item)

            current = hired_of_role(state, s.role)  # chi sarebbe sostituito, se non è già s
            if s.hired:
                label = f"Licenzia (€{severance_pay(s):,})"
            elif current is not None:
                label = f"Sostituisci (€{severance_pay(current):,})"
            else:
                label = "Assumi"
            btn = QPushButton(label)
            btn.setObjectName("DangerButton" if s.hired else "PrimaryButton")
            btn.clicked.connect(lambda _c=False, sid=s.id: self.controller.toggle_staff(sid))
            self.table.setCellWidget(row, 6, btn)

    def _on_coach_header_clicked(self, col: int) -> None:
        if col == 8:  # "Azione" column: button, not sortable data
            return
        self._coach_sort_active, self._coach_sort_col, self._coach_sort_desc = _toggle_sort(
            self._coach_sort_active, self._coach_sort_col, self._coach_sort_desc, col, desc_cols={2, 3, 4, 5, 6, 7}
        )
        self.refresh(self.controller.state)

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
        self._ledger_sort_active = False
        self._ledger_sort_col = 0
        self._ledger_sort_desc = True
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

        ledger_head = QHBoxLayout()
        title = QLabel("Libro Mastro & Movimenti (clic sull'intestazione per ordinare)")
        title.setObjectName("SectionHeader")
        ledger_head.addWidget(title)
        ledger_head.addStretch()
        self.ledger_search = QLineEdit()
        self.ledger_search.setPlaceholderText("Cerca categoria o descrizione...")
        self.ledger_search.setMaximumWidth(220)
        self.ledger_search.textChanged.connect(lambda _t: self.refresh(self.controller.state))
        ledger_head.addWidget(self.ledger_search)
        ledger_layout.addLayout(ledger_head)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Settimana", "Categoria", "Descrizione", "Importo"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().sectionClicked.connect(self._on_ledger_header_clicked)
        self.table.verticalHeader().setVisible(False)
        ledger_layout.addWidget(self.table)

        self.sections = QTabWidget()
        self.sections.addTab(self._build_monthly_page(), "Bilancio mensile")
        self.sections.addTab(ledger_panel, "Libro mastro")
        root.addWidget(self.sections, stretch=1)

    def _build_monthly_page(self) -> QWidget:
        """Bilancio mensile (D.3): grafico degli ultimi mesi, elenco dei mesi e dettaglio per categoria del mese scelto."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 10, 0, 0)
        self.chart = MonthlyBarsWidget()
        lay.addWidget(self.chart)
        body = QHBoxLayout()
        self._monthly_list: list = []
        self.months_table = QTableWidget(0, 5)
        self.months_table.setHorizontalHeaderLabels(["Mese", "Entrate", "Uscite", "Saldo mese", "Budget a fine mese"])
        self.breakdown_table = QTableWidget(0, 3)
        self.breakdown_table.setHorizontalHeaderLabels(["Categoria", "Entrate", "Uscite"])
        for table in (self.months_table, self.breakdown_table):
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.verticalHeader().setVisible(False)
        self.months_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # etichetta lunga
        self.months_table.itemSelectionChanged.connect(self._show_breakdown)
        body.addWidget(self.months_table, stretch=3)
        body.addWidget(self.breakdown_table, stretch=2)
        lay.addLayout(body, stretch=1)
        return page

    @staticmethod
    def _money(amount: int, signed: bool = False) -> str:
        if amount == 0:
            return "—"
        sign = ("+" if amount > 0 else "-") if signed else ("-" if amount < 0 else "")
        return f"{sign}€{abs(amount):,}"

    def _refresh_monthly(self, state: GameState) -> None:
        previous = self.months_table.currentRow()
        self._monthly_list = list(state.monthly_reports)
        self.chart.set_reports(recent_reports(state, 12))
        self.months_table.blockSignals(True)
        self.months_table.setRowCount(len(self._monthly_list))
        for row, rep in enumerate(self._monthly_list):
            vals = [
                f"S{rep.season} · mese {rep.month} (sett. {rep.first_week}-{rep.last_week})",
                self._money(rep.total_income),
                self._money(-rep.total_expenses),
                self._money(rep.net, signed=True),
                f"€{rep.budget_end:,}",
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 3:
                    item.setForeground(QColor("#34d399" if rep.net >= 0 else "#f87171"))
                self.months_table.setItem(row, col, item)
        self.months_table.blockSignals(False)
        if self._monthly_list:
            self.months_table.selectRow(min(max(previous, 0), len(self._monthly_list) - 1))
        self._show_breakdown()

    def _show_breakdown(self) -> None:
        row = self.months_table.currentRow()
        if not (0 <= row < len(self._monthly_list)):
            self.breakdown_table.setRowCount(0)
            return
        rep = self._monthly_list[row]
        categories = sorted(
            set(rep.income) | set(rep.expenses),
            key=lambda c: -(rep.income.get(c, 0) + rep.expenses.get(c, 0)),
        )
        self.breakdown_table.setRowCount(len(categories) + 1)
        rows = [(c, rep.income.get(c, 0), rep.expenses.get(c, 0)) for c in categories]
        rows.append(("TOTALE", rep.total_income, rep.total_expenses))
        for r, (cat, inc, exp) in enumerate(rows):
            for col, text in enumerate([cat, self._money(inc), self._money(-exp)]):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 1 and inc:
                    item.setForeground(QColor("#34d399"))
                elif col == 2 and exp:
                    item.setForeground(QColor("#f87171"))
                if cat == "TOTALE":
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.breakdown_table.setItem(r, col, item)

    def refresh(self, state: GameState) -> None:
        fin = weekly_finances(state)
        net = fin["net"]

        self.balance_val.setText(f"€{state.budget:,}")
        self.balance_val.setStyleSheet("color: #f87171;" if state.budget < 0 else "")
        self.balance_sub.setText(
            f"Fedeltà sponsor {state.fidelity}% (scende con acquisti/cessioni)"
            if state.budget >= 0
            else f"In rosso: 5% interessi/sett · fallimento sotto -€{-BANKRUPTCY_THRESHOLD:,}"
        )

        self.sponsor_val.setText(f"+€{fin['income']:,}")
        self.sponsor_sub.setText(
            f"Società €{fin['sponsor']:,} + Individuali €{fin['individual_sponsors']:,} "
            f"+ Merch €{fin['merchandising']:,} + Quote €{fin['member_fees']:,}"
            + (f" · sponsor −€{fin['sponsor_cut']:,} (stagione scorsa fuori dai primi {SPONSOR_TOP_N})" if fin["sponsor_cut"] else "")
        )

        self.payroll_val.setText(f"-€{fin['expenses']:,}")
        self.payroll_sub.setText(
            f"Atleti €{fin['athlete_wages']:,} + Allenatori €{fin['coach_cost']:,} "
            f"+ Staff €{fin['staff_cost']:,} + Palestra €{fin['gym_upkeep']:,}"
        )

        sign = "+" if net >= 0 else ""
        self.net_val.setText(f"{sign}€{net:,}")
        self.net_val.setStyleSheet("color: #34d399;" if net >= 0 else "color: #f87171;")
        self.net_sub.setText("Esclusi premi, biglietti e trasferte")

        query = self.ledger_search.text().strip().lower() if hasattr(self, "ledger_search") else ""
        transactions = [
            tx
            for tx in state.transactions
            if not query or query in tx.category.lower() or query in tx.description.lower()
        ]
        if self._ledger_sort_active:
            ledger_keys = {
                0: lambda tx: tx.week,
                1: lambda tx: tx.category.lower(),
                2: lambda tx: tx.description.lower(),
                3: lambda tx: tx.amount,
            }
            transactions.sort(
                key=ledger_keys.get(self._ledger_sort_col, ledger_keys[0]), reverse=self._ledger_sort_desc
            )
        self.table.setRowCount(len(transactions))
        for row, tx in enumerate(transactions):
            amt_text = f"+€{tx.amount:,}" if tx.amount >= 0 else f"-€{abs(tx.amount):,}"
            vals = [f"Sett. {tx.week}", tx.category, tx.description, amt_text]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 3:
                    item.setForeground(QColor("#34d399" if tx.amount >= 0 else "#f87171"))
                self.table.setItem(row, col, item)
        self._refresh_monthly(state)

    def _on_ledger_header_clicked(self, col: int) -> None:
        self._ledger_sort_active, self._ledger_sort_col, self._ledger_sort_desc = _toggle_sort(
            self._ledger_sort_active, self._ledger_sort_col, self._ledger_sort_desc, col, desc_cols={0, 3}
        )
        self.refresh(self.controller.state)


class YouthTab(QWidget):
    """Youth academy (vivaio): weekly scouting with points, faster training, promotion at 18."""

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._youth_row_ids: list[int] = []
        self._results_list: list = []
        self._youth_sort_active = False
        self._youth_sort_col = 0
        self._youth_sort_desc = False
        self._results_sort_active = False
        self._results_sort_col = 0
        self._results_sort_desc = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        self.empty_hint = _empty_hint(
            "Il vivaio è vuoto. Usa gli osservatori qui sotto (ogni ricerca costa punti scouting e un po' di denaro) "
            "per trovare i primi ragazzi e inseriscili nel vivaio: crescono più in fretta e a 18 anni passano in Prima Squadra."
        )
        root.addWidget(self.empty_hint)

        squad_panel = QFrame()
        squad_panel.setObjectName("SectionPanel")
        squad_layout = QVBoxLayout(squad_panel)
        squad_layout.setContentsMargins(14, 12, 14, 12)

        head = QHBoxLayout()
        self.squad_title = QLabel("Vivaio")
        self.squad_title.setObjectName("SectionHeader")
        head.addWidget(self.squad_title)
        head.addStretch()
        self.promote_btn = QPushButton("Promuovi in Prima Squadra")
        self.promote_btn.setObjectName("PrimaryButton")
        self.promote_btn.clicked.connect(self._promote_selected)
        head.addWidget(self.promote_btn)
        self.release_btn = QPushButton("Svincola")
        self.release_btn.setObjectName("DangerButton")
        self.release_btn.clicked.connect(self._release_selected)
        head.addWidget(self.release_btn)
        squad_layout.addLayout(head)

        hint = QLabel(
            "I ragazzi del vivaio (14-17 anni) non gareggiano e non prendono rimborsi spese, ma si allenano "
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
        yh.sectionClicked.connect(self._on_youth_header_clicked)
        self.youth_table.itemSelectionChanged.connect(self._update_youth_buttons)
        squad_layout.addWidget(self.youth_table)
        root.addWidget(squad_panel, stretch=1)
        self._update_youth_buttons()

        # Academy a stelle e osservatore capo (E.3)
        advanced_row = QHBoxLayout()
        advanced_row.setSpacing(12)
        academy_card = QFrame()
        academy_card.setObjectName("StatCard")
        academy_layout = QVBoxLayout(academy_card)
        academy_layout.setContentsMargins(14, 12, 14, 12)
        self.academy_label = QLabel("Academy")
        self.academy_label.setObjectName("SectionHeader")
        self.academy_sub = QLabel("")
        self.academy_sub.setObjectName("SubTitle")
        self.academy_sub.setWordWrap(True)
        self.academy_btn = QPushButton("Migliora Academy")
        self.academy_btn.setObjectName("PrimaryButton")
        self.academy_btn.clicked.connect(self.controller.upgrade_academy)
        academy_layout.addWidget(self.academy_label)
        academy_layout.addWidget(self.academy_sub)
        academy_layout.addWidget(self.academy_btn)
        advanced_row.addWidget(academy_card)

        scout_card = QFrame()
        scout_card.setObjectName("StatCard")
        scout_card_layout = QVBoxLayout(scout_card)
        scout_card_layout.setContentsMargins(14, 12, 14, 12)
        self.scout_label = QLabel("Osservatore capo")
        self.scout_label.setObjectName("SectionHeader")
        self.scout_sub = QLabel("")
        self.scout_sub.setObjectName("SubTitle")
        self.scout_sub.setWordWrap(True)
        scout_buttons = QHBoxLayout()
        self.scout_combo = QComboBox()
        for cand in scout_candidates():
            self.scout_combo.addItem(
                f"{cand.name} · potenziale {cand.potenziale}, attuale {cand.attuale} · €{cand.weekly_cost}/sett",
                cand.scout_id,
            )
        scout_buttons.addWidget(self.scout_combo, stretch=1)
        self.scout_hire_btn = QPushButton("Assumi")
        self.scout_hire_btn.setObjectName("PrimaryButton")
        self.scout_hire_btn.clicked.connect(self._hire_scout)
        scout_buttons.addWidget(self.scout_hire_btn)
        self.scout_fire_btn = QPushButton("Licenzia")
        self.scout_fire_btn.setObjectName("DangerButton")
        self.scout_fire_btn.clicked.connect(self.controller.fire_scout)
        scout_buttons.addWidget(self.scout_fire_btn)
        scout_card_layout.addWidget(self.scout_label)
        scout_card_layout.addWidget(self.scout_sub)
        scout_card_layout.addLayout(scout_buttons)
        advanced_row.addWidget(scout_card, stretch=2)
        root.addLayout(advanced_row)

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
        self.region_combo = QComboBox()
        self.region_combo.addItem("Nessuna rete", None)
        for key, (label, spec, _stat, _nat) in SCOUT_REGIONS.items():
            self.region_combo.addItem(
                f"Rete {label}: {spec.value} (+{SCOUT_REGION_EXTRA_POINTS} punto, €{SCOUT_REGION_FEE:,})", key
            )
        self.region_combo.currentIndexChanged.connect(lambda _i: self._update_cost_label())
        controls.addWidget(self.region_combo)
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
        self.results_table.horizontalHeader().sectionClicked.connect(self._on_results_header_clicked)
        self.results_table.verticalHeader().setVisible(False)
        scout_layout.addWidget(self.results_table)

        sign_row = QHBoxLayout()
        sign_row.addStretch()
        self.sign_btn = QPushButton("Inserisci nel Vivaio")
        self.sign_btn.setObjectName("PrimaryButton")
        self.sign_btn.clicked.connect(self._sign_selected)
        sign_row.addWidget(self.sign_btn)
        scout_layout.addLayout(sign_row)

        self.results_table.itemSelectionChanged.connect(self._update_sign_button)
        root.addWidget(scout_panel, stretch=1)
        self._update_sign_button()

    def _update_youth_buttons(self) -> None:
        has_selection = bool(self.youth_table.selectionModel().selectedRows())
        self.promote_btn.setEnabled(has_selection)
        self.release_btn.setEnabled(has_selection)

    def _update_sign_button(self) -> None:
        self.sign_btn.setEnabled(bool(self.results_table.selectionModel().selectedRows()))

    def _filters(self) -> tuple[Optional[Specialty], bool]:
        spec = self.spec_combo.currentData()
        return (spec if isinstance(spec, Specialty) else None), self.high_pot_check.isChecked()

    def _region(self) -> Optional[str]:
        data = self.region_combo.currentData()
        return data if isinstance(data, str) else None

    def _hire_scout(self) -> None:
        sid = self.scout_combo.currentData()
        if isinstance(sid, int):
            self.controller.hire_scout(sid)

    def _update_cost_label(self) -> None:
        state = self.controller.state
        spec, high = self._filters()
        region = self._region()
        extra_points, extra_fee = region_search_extras(region)
        # con una regione la disciplina è quella della regione: il filtro disciplina non si somma (come nel controller)
        filters = (1 if spec is not None and region is None else 0) + (1 if high else 0)
        points, fee = scouting_search_cost(state.scouting_points_used, filters + extra_points)
        fee += extra_fee
        self.spec_combo.setEnabled(region is None)
        enough = points <= state.scouting_points_left
        self.cost_label.setText(f"Costo: {points} punti · €{fee:,}")
        self.search_btn.setEnabled(enough and len(state.youth_squad) < YOUTH_SQUAD_MAX)

    def refresh(self, state: GameState) -> None:
        youth = state.youth_squad
        self.empty_hint.setVisible(not youth)
        self.squad_title.setText(f"Vivaio — {len(youth)}/{YOUTH_SQUAD_MAX} ragazzi")
        self.scout_title.setText(
            f"Osservatori — {state.scouting_points_left}/{WEEKLY_SCOUTING_POINTS} punti disponibili questa settimana"
        )
        stars = state.academy_level
        self.academy_label.setText(f"Academy — {'★' * stars}{'☆' * (ACADEMY_MAX_LEVEL - stars)}")
        self.academy_sub.setText(
            f"+{round((academy_growth_multiplier(stars) - 1) * 100)}% di crescita per i ragazzi del vivaio "
            f"(oltre al +50% di base) · una tantum, nessuna gestione"
        )
        if stars >= ACADEMY_MAX_LEVEL:
            self.academy_btn.setText("Cinque stelle")
            self.academy_btn.setEnabled(False)
        else:
            self.academy_btn.setText(f"Passa a {stars + 1} stelle (€{academy_upgrade_cost(stars):,})")
            self.academy_btn.setEnabled(True)
        scout = state.scout
        if scout is None:
            self.scout_sub.setText(
                "Nessun osservatore: i ragazzi segnalati si vedono con fasce larghe "
                f"(potenziale ±{potential_half_width(None)}, qualità ±{current_half_width(None)}). "
                "Un osservatore bravo le stringe; con 20 la qualità attuale è esatta."
            )
        else:
            self.scout_label.setText(f"Osservatore capo — {scout.name}")
            self.scout_sub.setText(
                f"Giudizio potenziale {scout.potenziale}/20 (fascia ±{potential_half_width(scout)}) · "
                f"Giudizio attuale {scout.attuale}/20 (fascia ±{current_half_width(scout)}) · €{scout.weekly_cost}/sett"
            )
        if scout is None:
            self.scout_label.setText("Osservatore capo")
        self.scout_fire_btn.setEnabled(scout is not None)
        self.scout_hire_btn.setText("Assumi" if scout is None else "Sostituisci")

        # La rete in Nigeria (lanci) non c'è nel Prototipo, che non ha quella disciplina
        region_view = self.region_combo.view()
        for i in range(self.region_combo.count()):
            key = self.region_combo.itemData(i)
            if isinstance(key, str):
                hidden = state.game_mode == "vertical_slice" and region_specialty(key) == Specialty.THROWS
                region_view.setRowHidden(i, hidden)

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

        youth = list(youth)
        if self._youth_sort_active:
            youth_keys = {
                0: lambda a: a.name.lower(),
                1: lambda a: a.age,
                2: lambda a: a.specialty.value,
                3: lambda a: a.personality.value,
                4: lambda a: (a.overall, a.potential),
                5: lambda a: a.speed,
                6: lambda a: a.stamina,
                7: lambda a: a.strength,
                8: lambda a: a.technique,
                9: lambda a: a.fatigue,
            }
            youth.sort(key=youth_keys.get(self._youth_sort_col, youth_keys[0]), reverse=self._youth_sort_desc)

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

        results = list(self.controller.scouting_results)
        if self._results_sort_active:
            results_keys = {
                0: lambda a: a.name.lower(),
                1: lambda a: a.age,
                2: lambda a: a.specialty.value,
                3: lambda a: a.personality.value,
                4: lambda a: a.overall,
                5: lambda a: a.potential,
                6: lambda a: a.resilience,
            }
            results.sort(key=results_keys.get(self._results_sort_col, results_keys[0]), reverse=self._results_sort_desc)
        self._results_list = results
        self.results_table.setRowCount(len(results))
        for row, k in enumerate(results):
            scout = state.scout  # E.3: senza scout la fascia del potenziale è quella di sempre (±8)
            vals = [f"{k.name} ({k.gender})", str(k.age), k.specialty.value, k.personality.value,
                    current_band_text(k, scout), potential_band_text(k, scout), str(k.resilience)]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 5 and k.potential >= 88:
                    item.setForeground(QColor("#fbbf24"))
                self.results_table.setItem(row, col, item)
        if results:
            self.results_table.selectRow(0)

        self._update_cost_label()
        self._update_youth_buttons()
        self._update_sign_button()

    def _on_focus_changed(self, athlete_id: Optional[int], combo: QComboBox) -> None:
        if athlete_id is not None and isinstance(combo.currentData(), TrainingFocus):
            self.controller.set_athlete_training(athlete_id, combo.currentData())

    def _on_youth_header_clicked(self, col: int) -> None:
        if col >= 10:  # combo widget columns, not sortable data
            return
        self._youth_sort_active, self._youth_sort_col, self._youth_sort_desc = _toggle_sort(
            self._youth_sort_active, self._youth_sort_col, self._youth_sort_desc, col, desc_cols={4, 5, 6, 7, 8, 9}
        )
        self.refresh(self.controller.state)

    def _on_results_header_clicked(self, col: int) -> None:
        if col in (4, 5):  # OVR e Potenziale: mostrano solo una fascia, ordinare per il valore vero la svelerebbe
            return
        self._results_sort_active, self._results_sort_col, self._results_sort_desc = _toggle_sort(
            self._results_sort_active, self._results_sort_col, self._results_sort_desc, col, desc_cols={6}
        )
        self.refresh(self.controller.state)

    def _run_search(self) -> None:
        spec, high = self._filters()
        self.controller.run_youth_scouting(specialty=spec, high_potential=high, region=self._region())

    def _sign_selected(self) -> None:
        rows = self.results_table.selectionModel().selectedRows()
        if not rows or not (0 <= rows[0].row() < len(self._results_list)):
            QMessageBox.information(self, "Vivaio", "Seleziona prima un ragazzo segnalato.")
            return
        self.controller.sign_youth(self._results_list[rows[0].row()])

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
        self._change_combos: Dict[str, QComboBox] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        self.empty_hint = _empty_hint(
            "Servono almeno 4 atleti dello stesso sesso per comporre una staffetta. " + EMPTY_SQUAD_TEXT
        )
        root.addWidget(self.empty_hint)

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
            change_line = QHBoxLayout()
            change_lbl = QLabel("Cambio (M e F)")
            change_lbl.setMinimumWidth(150)
            change_line.addWidget(change_lbl)
            change_combo = QComboBox()
            for change in RelayChange:
                change_combo.addItem(change.value, change)
            change_combo.setCurrentIndex(max(0, change_combo.findData(RelayChange.NORMALE)))
            change_combo.setToolTip(
                "Conservativo: −1 punto di squadra e −10 punti percentuali di rischio di squalifica "
                "(serve soprattutto con poco affiatamento). Aggressivo: +2 punti e +10 punti percentuali "
                "(conviene a una squadra che insegue, non a chi è già favorito). Vale per maschile e femminile."
            )
            change_combo.currentIndexChanged.connect(
                lambda _i, n=name, c=change_combo: self.controller.set_relay_change(n, c.currentData())
            )
            change_line.addWidget(change_combo, stretch=1)
            lay.addLayout(change_line)
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
            self._change_combos[name] = change_combo
        root.addLayout(row, stretch=1)

    def refresh(self, state: GameState) -> None:
        self.empty_hint.setVisible(not state.main_squad)
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
            change_combo = self._change_combos[name]
            change_combo.blockSignals(True)
            change_combo.setCurrentIndex(max(0, change_combo.findData(state.change_for(name))))
            change_combo.setEnabled(name in active)
            change_combo.blockSignals(False)

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
        self._rivals_sort_active = False
        self._rivals_sort_col = 1
        self._rivals_sort_desc = True
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
        self.clubs_table.horizontalHeader().sectionClicked.connect(self._on_clubs_header_clicked)
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
            f"Categoria {state.tier.display_name} ({gender}): livello medio rivali {avg:.1f} "
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
        if self._rivals_sort_active:
            rivals_keys = {
                0: lambda c: c.name.lower(),
                1: lambda c: c.level(events),
                2: lambda c: c.trend,
                3: lambda c: c.ambition,
                4: lambda c: state.league_table.get(c.name, 0),
            }
            ordered = sorted(
                clubs, key=rivals_keys.get(self._rivals_sort_col, rivals_keys[1]), reverse=self._rivals_sort_desc
            )
        else:
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

    def _on_clubs_header_clicked(self, col: int) -> None:
        self._rivals_sort_active, self._rivals_sort_col, self._rivals_sort_desc = _toggle_sort(
            self._rivals_sort_active, self._rivals_sort_col, self._rivals_sort_desc, col, desc_cols={1, 2, 3, 4}
        )
        self.refresh(self.controller.state)

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


class RecordsTab(QWidget):
    """Club records (M/F), seasonal honours history, and milestone archive."""

    OUTCOME_COLORS = {
        SeasonOutcome.PROMOTED: "#34d399",
        SeasonOutcome.CHAMPION: "#fbbf24",
        SeasonOutcome.STAYED: "#38bdf8",
        SeasonOutcome.RELEGATED: "#f87171",
    }

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._records_sort = {"m": [False, 0, False], "f": [False, 0, False]}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self.records_m_table = self._make_records_panel(
            top_row, "Record Sociali — Maschile (M)"
        )
        self.records_m_table.horizontalHeader().sectionClicked.connect(
            lambda col: self._on_records_header_clicked("m", col)
        )
        self.records_f_table = self._make_records_panel(
            top_row, "Record Sociali — Femminile (F)"
        )
        self.records_f_table.horizontalHeader().sectionClicked.connect(
            lambda col: self._on_records_header_clicked("f", col)
        )
        root.addLayout(top_row, stretch=3)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        seasons_panel = QFrame()
        seasons_panel.setObjectName("SectionPanel")
        seasons_lay = QVBoxLayout(seasons_panel)
        seasons_lay.setContentsMargins(14, 12, 14, 12)
        seasons_title = QLabel("Storico Stagioni & Piazzamenti")
        seasons_title.setObjectName("SectionHeader")
        seasons_lay.addWidget(seasons_title)
        self.seasons_table = QTableWidget(0, 4)
        self.seasons_table.setHorizontalHeaderLabels(
            ["Stagione", "Categoria", "Posizione", "Verdetto"]
        )
        self.seasons_table.setAlternatingRowColors(True)
        self.seasons_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.seasons_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.seasons_table.verticalHeader().setVisible(False)
        seasons_lay.addWidget(self.seasons_table)
        bottom_row.addWidget(seasons_panel, stretch=3)

        milestones_panel = QFrame()
        milestones_panel.setObjectName("SectionPanel")
        milestones_lay = QVBoxLayout(milestones_panel)
        milestones_lay.setContentsMargins(14, 12, 14, 12)
        milestones_title = QLabel("Albo & Momenti Memorabili")
        milestones_title.setObjectName("SectionHeader")
        milestones_lay.addWidget(milestones_title)
        self.milestones_list = QListWidget()
        self.milestones_list.setWordWrap(True)
        self.milestones_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        milestones_lay.addWidget(self.milestones_list)
        bottom_row.addWidget(milestones_panel, stretch=3)

        retired_panel = QFrame()
        retired_panel.setObjectName("SectionPanel")
        retired_lay = QVBoxLayout(retired_panel)
        retired_lay.setContentsMargins(14, 12, 14, 12)
        retired_title = QLabel("Ex atleti")
        retired_title.setObjectName("SectionHeader")
        retired_lay.addWidget(retired_title)
        self.retired_table = QTableWidget(0, 5)
        self.retired_table.setHorizontalHeaderLabels(["Nome", "Disciplina", "Età", "Stagione", "Stato"])
        self.retired_table.setAlternatingRowColors(True)
        self.retired_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.retired_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.retired_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        header = self.retired_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # il nome prende lo spazio che resta
        self.retired_table.verticalHeader().setVisible(False)
        self.retired_table.itemSelectionChanged.connect(self._update_retired_button)
        retired_lay.addWidget(self.retired_table)
        self.hire_retired_button = QPushButton("Assumi come allenatore")
        self.hire_retired_button.setEnabled(False)
        self.hire_retired_button.clicked.connect(self._hire_selected_retired)
        retired_lay.addWidget(self.hire_retired_button)
        bottom_row.addWidget(retired_panel, stretch=4)

        root.addLayout(bottom_row, stretch=2)

    def _selected_retired_index(self) -> Optional[int]:
        rows = self.retired_table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _update_retired_button(self) -> None:
        """Abilitato solo se l'ex atleta selezionato è disponibile come allenatore (C.3)."""
        idx = self._selected_retired_index()
        retired = self.controller.state.retired
        ok = idx is not None and idx < len(retired) and retired[idx].coach_offer
        self.hire_retired_button.setEnabled(bool(ok))
        if ok:
            ex = retired[idx]
            skills = ", ".join(f"{COACH_STAT_LABELS[k]} {v}" for k, v in ex.coach_skills.items() if v > COACH_BASE_SKILL)
            self.hire_retired_button.setToolTip(
                f"{ex.name}: {skills}. Ingaggio €{RETIRED_COACH_HIRE_COST:,} (ridotto: ex atleta della società)."
            )

    def _hire_selected_retired(self) -> None:
        idx = self._selected_retired_index()
        if idx is not None:
            self.controller.hire_retired_coach(idx)

    @staticmethod
    def _make_records_panel(parent_row: QHBoxLayout, title_text: str) -> QTableWidget:
        panel = QFrame()
        panel.setObjectName("SectionPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        title = QLabel(title_text)
        title.setObjectName("SectionHeader")
        lay.addWidget(title)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Disciplina", "Primato", "Atleta"])
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        lay.addWidget(table)
        parent_row.addWidget(panel, stretch=1)
        return table

    def _on_records_header_clicked(self, which: str, col: int) -> None:
        active, scol, desc = self._records_sort[which]
        self._records_sort[which] = list(_toggle_sort(active, scol, desc, col, desc_cols={1}))
        self.refresh(self.controller.state)

    def _populate_records(
        self,
        which: str,
        table: QTableWidget,
        events: list[str],
        records: dict[str, tuple[float, str, str]],
    ) -> None:
        ordered = [ev for ev in events if ev in records]
        for ev in records:
            if ev not in ordered:
                ordered.append(ev)
        active, col, desc = self._records_sort[which]
        if active:
            rec_keys = {0: lambda ev: ev, 1: lambda ev: records[ev][0], 2: lambda ev: records[ev][2].lower()}
            ordered.sort(key=rec_keys.get(col, rec_keys[0]), reverse=desc)
        table.setRowCount(len(ordered))
        for row, ev in enumerate(ordered):
            _val, disp, athlete = records[ev]
            for col, text in enumerate((ev, disp, athlete)):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 1:
                    item.setForeground(QColor("#19d3c0"))
                table.setItem(row, col, item)

    def refresh(self, state: GameState) -> None:
        self._populate_records("m", self.records_m_table, list(EVENTS), state.club_records)
        self._populate_records("f", self.records_f_table, list(EVENTS), state.club_records_f)

        self.seasons_table.setRowCount(len(state.season_history))
        for row, h in enumerate(state.season_history):
            outcome_txt = h.outcome.value
            if h.new_tier is not None:
                outcome_txt = f"{outcome_txt} → {h.new_tier.display_name}"
            vals = [f"Stagione {h.season}", h.tier.display_name, f"{h.placement}°", outcome_txt]
            color = self.OUTCOME_COLORS.get(h.outcome)
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 3 and color:
                    item.setForeground(QColor(color))
                self.seasons_table.setItem(row, col, item)

        selected = self._selected_retired_index()
        self.retired_table.setRowCount(len(state.retired))
        for row, ex in enumerate(state.retired):
            vals = [ex.name, f"{ex.specialty.value} ({ex.gender})", str(ex.age), f"{ex.season}", ex.status_label]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 4 and ex.coach_offer:
                    item.setForeground(QColor("#19d3c0"))
                self.retired_table.setItem(row, col, item)
        if selected is not None and selected < len(state.retired):
            self.retired_table.selectRow(selected)
        self._update_retired_button()

        self.milestones_list.clear()
        if state.milestones:
            for m in state.milestones:
                self.milestones_list.addItem(f"★ {m}")
        else:
            self.milestones_list.addItem("Nessun traguardo storico ancora registrato.")


class RankingTab(QWidget):
    """Ranking (C.1): classifica mondiale (Top 100), nazionale (Top 50) e delle società della lega, per evento e sesso.

    Gli atleti del club sono evidenziati. Chi sta fuori dalla Top N compare comunque in fondo alla tabella con il
    suo posto vero (per esempio «143°»): il gioco non nasconde dove sei.
    """

    CLUB_COLOR = "#19d3c0"
    RIVAL_COLOR = "#93a0c6"

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(QLabel("Disciplina"))
        self.event_combo = QComboBox()
        self.event_combo.currentIndexChanged.connect(lambda _i: self._refresh_tables())
        bar.addWidget(self.event_combo)
        bar.addWidget(QLabel("Sesso"))
        self.gender_combo = QComboBox()
        self.gender_combo.addItem("Uomini", "M")
        self.gender_combo.addItem("Donne", "F")
        self.gender_combo.currentIndexChanged.connect(lambda _i: self._refresh_tables())
        bar.addWidget(self.gender_combo)
        bar.addStretch(1)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("SubTitle")
        bar.addWidget(self.summary_label)
        root.addLayout(bar)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.world_table, self.world_title = self._panel(row, "Classifica mondiale", 5, ["#", "Atleta", "Naz.", "Società", "Punti"], 3)
        self.national_table, self.national_title = self._panel(row, "Classifica nazionale", 4, ["#", "Atleta", "Società", "Punti"], 3)
        self.club_table, self.club_title = self._panel(row, "Società della lega", 3, ["#", "Società", "Punti"], 2)
        root.addLayout(row, stretch=1)

        self.note_label = QLabel(
            "Punti per piazzamento (1° = 100, 2° = 80, …) per il livello della gara; dimezzano in circa sei meeting. "
            "Gli atleti senza società sono giocatori di fantasia del circuito mondiale. Le staffette non danno punti."
        )
        self.note_label.setObjectName("SubTitle")
        self.note_label.setWordWrap(True)
        root.addWidget(self.note_label)

    @staticmethod
    def _panel(parent_row: QHBoxLayout, title_text: str, columns: int, headers: list[str], stretch: int):
        panel = QFrame()
        panel.setObjectName("SectionPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        title = QLabel(title_text)
        title.setObjectName("SectionHeader")
        lay.addWidget(title)
        table = QTableWidget(0, columns)
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        lay.addWidget(table)
        parent_row.addWidget(panel, stretch=stretch)
        return table, title

    def _fill(self, table: QTableWidget, rows: list[tuple[list[str], bool]]) -> None:
        table.setRowCount(len(rows))
        for r, (cells, is_club) in enumerate(rows):
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_club:
                    item.setForeground(QColor(self.CLUB_COLOR))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                table.setItem(r, c, item)

    @staticmethod
    def _pts(value: float) -> str:
        return f"{value:.0f}" if value >= 10 else f"{value:.1f}"

    def _selection(self) -> tuple[str, str]:
        return self.event_combo.currentText(), self.gender_combo.currentData() or "M"

    def _refresh_tables(self) -> None:
        state = self.controller.state
        event, gender = self._selection()
        if not event:
            return
        world = world_ranking(state, event, gender)
        national = national_ranking(state, event, gender)

        def pick(entries, size):
            shown = entries[:size]
            beyond = [e for e in entries[size:] if e.is_player]  # i miei atleti fuori dalla Top N, col posto vero
            return shown, beyond

        def world_row(e) -> tuple[list[str], bool]:
            nation = f"{NATIONALITIES.get(e.nationality, '')} {e.nationality}".strip()
            return [f"{e.rank}°", e.name, nation, e.club, self._pts(e.points)], e.is_player

        shown, beyond = pick(world, RANKING_WORLD_SIZE)
        self._fill(self.world_table, [world_row(e) for e in (*shown, *beyond)])
        self.world_title.setText(f"Classifica mondiale — Top {RANKING_WORLD_SIZE}")

        shown, beyond = pick(national, RANKING_NATIONAL_SIZE)
        self._fill(
            self.national_table,
            [([f"{e.rank}°", e.name, e.club, self._pts(e.points)], e.is_player) for e in (*shown, *beyond)],
        )
        self.national_title.setText(f"Classifica nazionale — Top {RANKING_NATIONAL_SIZE}")

        clubs = club_ranking(state)
        self._fill(
            self.club_table,
            [([f"{i}°", name, self._pts(points)], is_club) for i, (name, points, is_club) in enumerate(clubs, start=1)],
        )
        mine = next((i for i, (_n, _p, is_club) in enumerate(clubs, start=1) if is_club), 0)
        self.club_title.setText(f"Società della lega — {state.tier.display_name}")
        self.summary_label.setText(f"Punti del club: {self._pts(club_points(state))} · {mine}° tra le società della lega")

    def refresh(self, state: GameState) -> None:
        events = list(state.active_events)
        current = self.event_combo.currentText()
        if [self.event_combo.itemText(i) for i in range(self.event_combo.count())] != events:
            self.event_combo.blockSignals(True)
            self.event_combo.clear()
            self.event_combo.addItems(events)
            if current in events:
                self.event_combo.setCurrentText(current)
            self.event_combo.blockSignals(False)
        self._refresh_tables()
