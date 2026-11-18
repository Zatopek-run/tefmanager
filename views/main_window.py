"""Main QMainWindow for Track & Field Manager."""

from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from controllers.game_controller import GameController
from models.entities import (
    COACH_COMFORT_LOAD,
    YOUTH_SQUAD_MAX,
    CompetitionSummary,
    EthicalDilemma,
    GameState,
    SeasonEndResult,
)
from views.dialogs import (
    CompetitionResultsDialog,
    EthicalDilemmaDialog,
    NewGameDialog,
    SeasonEndDialog,
)
from views.race_viewer import RaceViewerDialog
from views.start_screen import StartScreen
from views.styles import DARK_STYLESHEET
from views.tabs import (
    CalendarTab,
    DashboardTab,
    FinancesTab,
    RelayTab,
    RivalsTab,
    RosterTab,
    StaffTab,
    YouthTab,
)


class MainWindow(QMainWindow):
    """Primary desktop window hosting StartScreen and the sidebar-driven game shell."""

    def __init__(self, controller: GameController, start_on_menu: bool = False) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Track & Field Manager")
        self.setMinimumSize(1120, 720)
        self.resize(1340, 840)
        self.setStyleSheet(DARK_STYLESHEET)
        self._nav_buttons: List[QPushButton] = []

        self._build_ui()
        self._connect_signals()
        self._refresh_all(self.controller.state)

        if start_on_menu:
            self.show_start_screen()
        else:
            self.show_game()

    def _build_ui(self) -> None:
        self.root_stack = QStackedWidget()
        self.setCentralWidget(self.root_stack)

        self.start_screen = StartScreen(self.controller)
        self.root_stack.addWidget(self.start_screen)

        self.game_page = QWidget()
        main_layout = QVBoxLayout(self.game_page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        header_layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.club_title = QLabel("Track & Field Manager")
        self.club_title.setObjectName("AppTitle")
        self.date_label = QLabel("Settimana 1")
        self.date_label.setObjectName("SubTitle")
        title_box.addWidget(self.club_title)
        title_box.addWidget(self.date_label)
        header_layout.addLayout(title_box)

        self.tier_badge = QLabel("Provinciale")
        self.tier_badge.setObjectName("TierBadge")
        header_layout.addWidget(self.tier_badge)

        self.comp_badge = QLabel("SETTIMANA DI GARA")
        self.comp_badge.setObjectName("CompAlertBadge")
        self.comp_badge.setVisible(False)
        header_layout.addWidget(self.comp_badge)

        header_layout.addStretch()

        self.hud_budget = QLabel("Bilancio: $0")
        self.hud_budget.setObjectName("HudBudgetPill")
        self.hud_prestige = QLabel("Prestigio: 0")
        self.hud_prestige.setObjectName("HudPrestigePill")
        header_layout.addWidget(self.hud_budget)
        header_layout.addWidget(self.hud_prestige)

        self.menu_btn = QPushButton("Partita ▾")
        game_menu = QMenu(self)
        act_save = QAction("Salva Partita", self)
        act_save.triggered.connect(self.controller.save_game)
        act_load = QAction("Ricarica Ultimo Salvataggio", self)
        act_load.triggered.connect(self.controller.load_game)
        act_new = QAction("Nuova Partita...", self)
        act_new.triggered.connect(self._on_new_game)
        act_menu = QAction("Torna al Menu Principale", self)
        act_menu.triggered.connect(self.show_start_screen)
        game_menu.addAction(act_save)
        game_menu.addAction(act_load)
        game_menu.addAction(act_new)
        game_menu.addSeparator()
        game_menu.addAction(act_menu)
        self.menu_btn.setMenu(game_menu)
        header_layout.addWidget(self.menu_btn)

        self.advance_btn = QPushButton("Avanza Settimana")
        self.advance_btn.setObjectName("AdvanceWeekButton")
        self.advance_btn.clicked.connect(self.controller.advance_week)
        header_layout.addWidget(self.advance_btn)

        main_layout.addWidget(header)

        # Body: left sidebar + stacked workspace
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("SideNav")
        sidebar.setFixedWidth(248)
        side_lay = QVBoxLayout(sidebar)
        side_lay.setContentsMargins(0, 10, 0, 12)
        side_lay.setSpacing(2)

        self.tabs = QStackedWidget()
        self.tabs.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.dashboard_tab = DashboardTab(self.controller)
        self.roster_tab = RosterTab(self.controller)
        self.youth_tab = YouthTab(self.controller)
        self.calendar_tab = CalendarTab(self.controller)
        self.relay_tab = RelayTab(self.controller)
        self.rivals_tab = RivalsTab(self.controller)
        self.staff_tab = StaffTab(self.controller)
        self.finances_tab = FinancesTab(self.controller)

        pages = [
            ("GESTIONE", [
                ("Dashboard", self.dashboard_tab),
                ("Rosa && Allenamenti", self.roster_tab),
                ("Vivaio && Osservatori", self.youth_tab),
            ]),
            ("COMPETIZIONI", [
                ("Calendario && Gare", self.calendar_tab),
                ("Staffette", self.relay_tab),
                ("Rivali", self.rivals_tab),
            ]),
            ("SOCIETÀ", [
                ("Staff && Impianto", self.staff_tab),
                ("Finanze", self.finances_tab),
            ]),
        ]

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_base_labels: List[str] = []

        idx = 0
        for section_name, entries in pages:
            sec_lbl = QLabel(section_name)
            sec_lbl.setObjectName("NavSectionLabel")
            side_lay.addWidget(sec_lbl)
            for label, widget in entries:
                self.tabs.addWidget(widget)
                btn = QPushButton(label)
                btn.setObjectName("NavButton")
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                if idx == 0:
                    btn.setChecked(True)
                btn.clicked.connect(lambda _c=False, i=idx: self._navigate_to(i))
                self._nav_group.addButton(btn, idx)
                self._nav_buttons.append(btn)
                self._nav_base_labels.append(label)
                side_lay.addWidget(btn)
                idx += 1

        side_lay.addStretch()

        menu_shortcut = QPushButton("← Menu Principale")
        menu_shortcut.setObjectName("NavButton")
        menu_shortcut.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_shortcut.clicked.connect(self.show_start_screen)
        side_lay.addWidget(menu_shortcut)

        body_layout.addWidget(sidebar)

        content_wrap = QWidget()
        content_lay = QVBoxLayout(content_wrap)
        content_lay.setContentsMargins(6, 6, 6, 6)
        content_lay.addWidget(self.tabs)
        body_layout.addWidget(content_wrap, stretch=1)

        main_layout.addWidget(body, stretch=1)
        self.root_stack.addWidget(self.game_page)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        status_bar.showMessage("Pronto — Pianifica allenamenti, periodizzazione e avanza la settimana.")

    def _connect_signals(self) -> None:
        self.start_screen.game_ready.connect(self.show_game)
        self.start_screen.quit_requested.connect(self.close)
        self.dashboard_tab.navigate_requested.connect(self._navigate_to)

        self.controller.state_changed.connect(self._refresh_all)
        self.controller.competition_completed.connect(self._show_competition_results)
        self.controller.dilemma_triggered.connect(self._show_dilemma)
        self.controller.season_ended.connect(self._show_season_end)
        self.controller.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg, 6000)
        )

    def _navigate_to(self, index: int) -> None:
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)
            if index < len(self._nav_buttons):
                self._nav_buttons[index].setChecked(True)

    def show_start_screen(self) -> None:
        self.start_screen.refresh()
        self.root_stack.setCurrentWidget(self.start_screen)
        self.statusBar().setVisible(False)

    def show_game(self) -> None:
        self._refresh_all(self.controller.state)
        self.root_stack.setCurrentWidget(self.game_page)
        self.statusBar().setVisible(True)
        self._navigate_to(0)

    def _update_nav_badges(self, state: GameState) -> None:
        by_id = {a.id: a for a in state.main_squad}
        missing_lineup = sum(
            1
            for g in ("M", "F")
            for ev in state.active_events
            if (aid := state.lineup_for(g).get(ev)) is None
            or by_id.get(aid) is None
            or by_id[aid].is_injured
        )
        incomplete_relays = sum(
            1
            for g in ("M", "F")
            for rname in state.active_relays
            if (r := state.relays_for(g).get(rname)) is None or not r.is_complete
        )
        tired_count = sum(1 for a in state.main_squad if not a.is_injured and a.fatigue >= 75)
        staff_warn = (
            state.track_condition < 60
            or any(state.coach_load(c) > COACH_COMFORT_LOAD for c in state.coaches)
        )
        youth_pts = state.scouting_points_left if len(state.youth_squad) < YOUTH_SQUAD_MAX else 0

        badges = {
            1: f" ({tired_count} st.)" if tired_count else "",
            2: f" ({youth_pts} pt)" if youth_pts >= 2 else "",
            3: " (!)" if (state.is_competition_week or missing_lineup > 0) else "",
            4: f" ({incomplete_relays}!)" if incomplete_relays else "",
            6: " (!)" if staff_warn else "",
        }
        for i, btn in enumerate(self._nav_buttons):
            btn.setText(self._nav_base_labels[i] + badges.get(i, ""))

    def _refresh_all(self, state: GameState) -> None:
        mode_tag = "Prototipo Outdoor" if state.game_mode == "vertical_slice" else f"Stagione {state.season_number}"
        self.club_title.setText(state.team_name)
        self.date_label.setText(
            f"Settimana {state.week} ({state.current_date:%d %b %Y})  •  {mode_tag} · {state.season_phase.value}"
        )
        self.tier_badge.setText(f"Cat. {state.tier.value}")
        self.comp_badge.setVisible(state.is_competition_week)

        self.hud_budget.setText(f"Bilancio: ${state.budget:,}")
        self.hud_prestige.setText(f"Prestigio: {state.prestige}")

        self.advance_btn.setEnabled(not state.bankrupt)
        if state.bankrupt:
            self.advance_btn.setText("Società Fallita")
        elif state.is_competition_week:
            self.advance_btn.setText("Disputa Gara & Avanza")
        else:
            self.advance_btn.setText("Avanza Settimana")

        self._update_nav_badges(state)

        self.dashboard_tab.refresh(state)
        self.roster_tab.refresh(state)
        self.youth_tab.refresh(state)
        self.calendar_tab.refresh(state)
        self.relay_tab.refresh(state)
        self.rivals_tab.refresh(state)
        self.staff_tab.refresh(state)
        self.finances_tab.refresh(state)

    def _show_competition_results(self, summary: CompetitionSummary) -> None:
        if summary.event_results:
            RaceViewerDialog(summary, parent=self).exec()
        dlg = CompetitionResultsDialog(summary, parent=self)
        dlg.exec()

    def _show_season_end(self, result: SeasonEndResult) -> None:
        dlg = SeasonEndDialog(result, self.controller.state.team_name, parent=self)
        dlg.exec()

    def _show_dilemma(self, dilemma: EthicalDilemma) -> None:
        dlg = EthicalDilemmaDialog(dilemma, parent=self)
        if dlg.exec():
            self.controller.resolve_dilemma(dlg.accepted_shortcut)

    def _on_new_game(self) -> None:
        dlg = NewGameDialog(self.controller.state.team_name, parent=self)
        if dlg.exec():
            self.controller.start_new_game(
                dlg.club_name, game_mode=dlg.game_mode, province=dlg.province
            )
