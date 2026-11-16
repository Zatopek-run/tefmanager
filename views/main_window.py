"""Main QMainWindow for Track & Field Manager."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from controllers.game_controller import GameController
from models.entities import CompetitionSummary, EthicalDilemma, GameState
from views.dialogs import (
    CompetitionResultsDialog,
    EthicalDilemmaDialog,
    NewGameDialog,
)
from views.styles import DARK_STYLESHEET
from views.tabs import (
    CalendarTab,
    DashboardTab,
    FinancesTab,
    RelayTab,
    RosterTab,
    StaffTab,
    YouthTab,
)


class MainWindow(QMainWindow):
    """Primary desktop window hosting the Track & Field Manager dashboard."""

    def __init__(self, controller: GameController) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Track & Field Manager")
        self.resize(1300, 820)
        self.setStyleSheet(DARK_STYLESHEET)

        self._build_ui()
        self._connect_signals()
        self._refresh_all(self.controller.state)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
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

        self.hud_budget = QLabel("Budget: $0")
        self.hud_budget.setStyleSheet("font-weight: 700; color: #34d399; font-size: 14px;")
        self.hud_prestige = QLabel("Prestigio: 0")
        self.hud_prestige.setStyleSheet("font-weight: 700; color: #fbbf24; font-size: 14px;")
        header_layout.addWidget(self.hud_budget)
        header_layout.addWidget(self.hud_prestige)

        save_btn = QPushButton("Salva")
        save_btn.clicked.connect(self.controller.save_game)
        load_btn = QPushButton("Carica")
        load_btn.clicked.connect(self.controller.load_game)
        new_btn = QPushButton("Nuova Stagione")
        new_btn.clicked.connect(self._on_new_game)
        header_layout.addWidget(save_btn)
        header_layout.addWidget(load_btn)
        header_layout.addWidget(new_btn)

        self.advance_btn = QPushButton("Avanza Settimana")
        self.advance_btn.setObjectName("AdvanceWeekButton")
        self.advance_btn.clicked.connect(self.controller.advance_week)
        header_layout.addWidget(self.advance_btn)

        main_layout.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 12)

        self.tabs = QTabWidget()
        self.dashboard_tab = DashboardTab(self.controller)
        self.roster_tab = RosterTab(self.controller)
        self.youth_tab = YouthTab(self.controller)
        self.calendar_tab = CalendarTab(self.controller)
        self.relay_tab = RelayTab(self.controller)
        self.staff_tab = StaffTab(self.controller)
        self.finances_tab = FinancesTab(self.controller)

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.roster_tab, "Rosa && Allenamenti")
        self.tabs.addTab(self.youth_tab, "Vivaio && Osservatori")
        self.tabs.addTab(self.calendar_tab, "Calendario && Gare")
        self.tabs.addTab(self.relay_tab, "Staffette")
        self.tabs.addTab(self.staff_tab, "Staff && Impianto")
        self.tabs.addTab(self.finances_tab, "Finanze")

        body_layout.addWidget(self.tabs)
        main_layout.addWidget(body, stretch=1)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        status_bar.showMessage("Pronto — Pianifica allenamenti, periodizzazione e avanza la settimana.")

    def _connect_signals(self) -> None:
        self.controller.state_changed.connect(self._refresh_all)
        self.controller.competition_completed.connect(self._show_competition_results)
        self.controller.dilemma_triggered.connect(self._show_dilemma)
        self.controller.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg, 6000)
        )

    def _refresh_all(self, state: GameState) -> None:
        mode_tag = "Prototipo Outdoor" if state.game_mode == "vertical_slice" else f"Stagione {state.season_number}"
        self.club_title.setText(f"{state.team_name} — Track & Field Manager")
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

        self.dashboard_tab.refresh(state)
        self.roster_tab.refresh(state)
        self.youth_tab.refresh(state)
        self.calendar_tab.refresh(state)
        self.relay_tab.refresh(state)
        self.staff_tab.refresh(state)
        self.finances_tab.refresh(state)

    def _show_competition_results(self, summary: CompetitionSummary) -> None:
        dlg = CompetitionResultsDialog(summary, parent=self)
        dlg.exec()

    def _show_dilemma(self, dilemma: EthicalDilemma) -> None:
        dlg = EthicalDilemmaDialog(dilemma, parent=self)
        if dlg.exec():
            self.controller.resolve_dilemma(dlg.accepted_shortcut)

    def _on_new_game(self) -> None:
        dlg = NewGameDialog(self.controller.state.team_name, parent=self)
        if dlg.exec():
            self.controller.start_new_game(dlg.club_name, game_mode=dlg.game_mode)
