"""Modal dialogs for Competition Results, Scouting, Ethical Dilemmas, and New Career."""

from __future__ import annotations

import random
import zlib
from typing import Dict, List, Optional

from PyQt6.QtCore import QPropertyAnimation, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from views import theme
from models.entities import (
    COACH_BASE_SKILL,
    COACH_COMFORT_LOAD,
    COACH_MAX_TIER,
    COACH_STAT_LABELS,
    COACH_STATS,
    GAME_MODE_OPTIONS,
    MIN_NEGOTIATED_FEE,
    BOARD_MAX_FAILED_STREAK,
    BOARD_OBJECTIVES_TO_PASS,
    Agent,
    Athlete,
    CompetitionSummary,
    PROMOTION_SPOTS,
    RELEGATION_SPOTS,
    EthicalDilemma,
    SeasonEndResult,
    SeasonObjective,
    SeasonOutcome,
    Specialty,
    coach_hire_cost,
    coach_hire_skills,
    coach_weekly_wage,
)
from models.agents import negotiated_fee
from models.generator import LAZIO_PROVINCES
from models.market import Negotiation, NegotiationState, Terms
from models.glory import GloryMoment
from models.press import PressConference


def potential_band_display(prospect: Athlete, half_width: int = 8) -> str:
    """Fascia d'incertezza sul potenziale di un prospetto non ancora tesserato.

    Il valore esatto resta nel modello (usato dalla simulazione); qui si mostra solo una
    fascia che lo contiene, con un piccolo scarto deterministico (per prospetto) così il
    centro della fascia non coincide sempre col valore vero.
    """
    # crc32 e non `hash()`: quello è salato per processo e la fascia cambierebbe a ogni avvio (A.3 / PLAN 2.2)
    key = f"{prospect.name}|{prospect.age}|{prospect.specialty.value}|{prospect.gender}"
    seed = zlib.crc32(key.encode())
    offset = random.Random(seed).randint(-3, 3)
    lo = max(1, prospect.potential - half_width + offset)
    hi = min(99, prospect.potential + half_width + offset)
    return f"{lo}-{hi}"


class GloryMomentDialog(QDialog):
    """Popup celebrativo (F.4): un momento di gloria con dissolvenza d'ingresso. Solo messa in scena, nessun effetto sul gioco."""

    FADE_MS = 600

    def __init__(self, moment: GloryMoment, parent=None) -> None:
        super().__init__(parent)
        self.moment = moment
        self.setWindowTitle(moment.title)
        self.resize(520, 300)
        self.setStyleSheet(f"QDialog {{ background: {theme.BG}; border: 3px solid {theme.WARN}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)
        star = QLabel("★  ★  ★")
        star.setAlignment(Qt.AlignmentFlag.AlignCenter)
        star.setStyleSheet(f"color: {theme.WARN}; font-size: 22px; letter-spacing: 6px;")
        layout.addWidget(star)
        title = QLabel(moment.title)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {theme.WARN}; font-size: 28px; font-weight: 900;")
        layout.addWidget(title)
        text = QLabel(moment.text)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {theme.TEXT}; font-size: 15px;")
        layout.addWidget(text, stretch=1)
        self.close_btn = QPushButton("Che emozione!")
        self.close_btn.setObjectName("PrimaryButton")
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)
        self.setWindowOpacity(0.0)
        self.fade = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade.setDuration(self.FADE_MS)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)

    def showEvent(self, event) -> None:  # noqa: N802 (nome Qt)
        super().showEvent(event)
        self.fade.start()


class PressConferenceDialog(QDialog):
    """Conferenza stampa dopo la gara (F.2): una domanda per volta con le risposte possibili.

    `answers` (domanda → chiave della risposta) è valido solo se `answered` è vero, cioè se si è premuto «Rispondi».
    Chiudere la finestra o «Nessun commento» non ha effetti sul gioco.
    """

    def __init__(self, conference: PressConference, parent=None) -> None:
        super().__init__(parent)
        self.conference = conference
        self.answered = False
        self.answers: dict[str, str] = {}
        self._groups: dict[str, dict[str, QRadioButton]] = {}
        self._button_groups: list[QButtonGroup] = []
        self.setWindowTitle(f"Conferenza stampa — {conference.meet_name}")
        self.resize(560, 420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Il giornalista alza la mano…")
        title.setStyleSheet(f"color: {theme.WARN}; font-size: 18px; font-weight: 800;")
        layout.addWidget(title)
        for question in self.conference.questions:
            text = QLabel(question.text)
            text.setWordWrap(True)
            text.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {theme.TEXT};")
            layout.addWidget(text)
            buttons: dict[str, QRadioButton] = {}
            group = QButtonGroup(self)  # un gruppo per domanda: senza, le radio dello stesso genitore si escluderebbero tra loro
            for key, label in question.options.items():
                radio = QRadioButton(label)
                group.addButton(radio)
                layout.addWidget(radio)
                buttons[key] = radio
            self._button_groups.append(group)
            self._groups[question.key] = buttons
        layout.addStretch()
        hint = QLabel(
            "Le risposte cambiano la reputazione (a seconda del risultato) e la relazione con l'agente dell'atleta citato. "
            "Senza risposta non succede nulla."
        )
        hint.setObjectName("SubTitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch()
        self.skip_btn = QPushButton("Nessun commento")
        self.skip_btn.clicked.connect(self.reject)
        row.addWidget(self.skip_btn)
        self.answer_btn = QPushButton("Rispondi")
        self.answer_btn.setObjectName("PrimaryButton")
        self.answer_btn.clicked.connect(self._answer)
        row.addWidget(self.answer_btn)
        layout.addLayout(row)

    def _answer(self) -> None:
        """Raccoglie le risposte date (anche solo una); senza alcuna risposta equivale a «Nessun commento»."""
        self.answers = {
            qkey: okey for qkey, group in self._groups.items() for okey, radio in group.items() if radio.isChecked()
        }
        if not self.answers:
            self.reject()
            return
        self.answered = True
        self.accept()


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
            f"Biglietti: +€{self.summary.ticket_income:,}"
            if self.summary.is_home
            else f"Trasferta Pullman: -€{self.summary.travel_cost:,}"
        )
        team_place = self.summary.team_placement
        team_txt = (
            f"Società: {team_place}ª su {len(self.summary.team_standings)}   |   "
            if team_place
            else ""
        )
        totals = QLabel(
            f"{team_txt}Premi Totali: €{self.summary.total_prize_money:,}   |   "
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
            promo_label.setStyleSheet(f"color: {theme.GOOD}; font-weight: 800; font-size: 14px;")
            promo_layout.addWidget(promo_label)
            layout.addWidget(promo)

        summary_label = QLabel("Piazzamenti della squadra (seleziona una gara per la classifica completa):")
        summary_label.setObjectName("SubTitle")
        layout.addWidget(summary_label)

        self.events_table = QTableWidget(len(self.summary.event_results), 8)
        self.events_table.setHorizontalHeaderLabels(
            ["Gara", "Atleta / Frazionisti", "Atteggiamento", "Misura / Tempo", "Vento", "Posizione", "Premio", "Note"]
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
            if res.disqualified:
                notes.append("Squalificata (cambio fuori zona)")
            if res.is_club_record:
                notes.append("RECORD SOCIALE!")
            elif res.is_pb:
                notes.append("PB")
            if res.wind_illegal:
                notes.append("Vento > 2.0 (non omol.)")
            note_str = " · ".join(notes) if notes else "—"

            items = [
                QTableWidgetItem(res.display_event_name),
                QTableWidgetItem(res.player_athlete_name),
                QTableWidgetItem(res.attitude),
                QTableWidgetItem(res.player_mark),
                QTableWidgetItem(wind_str),
                QTableWidgetItem(
                    "RIT." if res.withdrew_injured
                    else ("SQ." if res.disqualified else f"#{res.placement} / {res.total_competitors}")
                ),
                QTableWidgetItem(f"€{res.prize_money:,}"),
                QTableWidgetItem(note_str),
            ]
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if res.withdrew_injured or res.disqualified:
                    item.setForeground(QColor(theme.BAD))
                elif col == 4 and res.wind_illegal:
                    item.setForeground(QColor(theme.WARN))
                elif res.placement == 1:
                    item.setForeground(QColor(theme.WARN))
                elif res.placement <= 3:
                    item.setForeground(QColor(theme.GOOD))
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
                    item.setForeground(QColor(theme.INFO))
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
                    item.setForeground(QColor(theme.INFO))
                self.standings_table.setItem(row, col, item)


class RecruitAthleteDialog(QDialog):
    """Scouting dialog featuring Campionati Studenteschi youth talents & free agents."""

    def __init__(
        self,
        prospects: List[Athlete],
        budget: int,
        roster: Optional[List[Athlete]] = None,
        parent=None,
        agents: Optional[List[Agent]] = None,
    ) -> None:
        super().__init__(parent)
        self.prospects = prospects
        self.budget = budget
        self.roster: List[Athlete] = list(roster) if roster is not None else []
        self.agents: Dict[int, Agent] = {a.id: a for a in (agents or [])}  # D.1: senza agenti vale l'ingaggio standard
        self.selected_prospect: Optional[Athlete] = None
        self.selected_terms: Optional[Terms] = None  # condizioni concordate in trattativa (D.2); None = richiesta standard
        self.setWindowTitle("Scouting & Mercato Svincolati")
        self.resize(1240, 470)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        header = QLabel(f"Mercato Settimanale (Budget Disponibile: €{self.budget:,})")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        sub = QLabel(
            "I ragazzi dei Campionati Studenteschi (15-17 anni) hanno alto Potenziale ma vanno fatti maturare con pazienza. "
            "Il pool si aggiorna ogni settimana."
        )
        sub.setObjectName("SubTitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self.table = QTableWidget(len(self.prospects), 12)
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
                "Agente",
                "Costo",
                "Note",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        for stretch_col in (0, 9):  # nome e agente prendono lo spazio che resta: sono i testi lunghi
            header_view.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)

        for row, a in enumerate(self.prospects):
            fee = self._fee(a)
            agent = self._agent(a)
            origin = "Camp. Studenteschi" if a.is_youth_prospect else "Svincolato"
            note = f"Vel {a.speed} · Res {a.stamina} · Tec {a.technique}"
            vals = [
                f"{a.name} ({a.gender})",
                str(a.age),
                origin,
                a.specialty.value,
                str(a.overall),
                potential_band_display(a),
                str(a.resilience),
                a.personality.value,
                f"€{a.weekly_wage}",
                self._agent_text(agent),
                f"€{fee:,}",
                note,
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 5 and a.potential >= 85:
                    item.setForeground(QColor(theme.GOOD))
                elif col == 10 and fee > self.budget:
                    item.setForeground(QColor(theme.BAD))
                if col == 9 and agent is not None:
                    item.setToolTip(self._agent_tooltip(a, agent))
                self.table.setItem(row, col, item)

        self.table.itemSelectionChanged.connect(self._update_comparison)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._on_sign())
        layout.addWidget(self.table)

        self.compare_label = QLabel("")
        self.compare_label.setObjectName("SubTitle")
        self.compare_label.setWordWrap(True)
        layout.addWidget(self.compare_label)

        if self.prospects:
            self.table.selectRow(0)
            self._update_comparison()

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

    def _agent(self, prospect: Athlete) -> Optional[Agent]:
        return self.agents.get(prospect.agent_id) if prospect.agent_id is not None else None

    def _fee(self, prospect: Athlete) -> int:
        return negotiated_fee(prospect, self._agent(prospect))

    @staticmethod
    def _agent_text(agent: Optional[Agent]) -> str:
        if agent is None:
            return "—"
        return f"{agent.name} · {agent.personality.value} ({agent.relation})"

    @staticmethod
    def _agent_tooltip(prospect: Athlete, agent: Agent) -> str:
        pct = round(agent.fee_modifier * 100)
        return (
            f"Agente {agent.name}: {agent.personality.value}, relazione {agent.relation}/100 ({agent.relation_label}).\n"
            f"Chiede il {pct:+d}% sull'ingaggio standard di {prospect.name}."
        )

    def _update_comparison(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows or not (0 <= rows[0].row() < len(self.prospects)):
            self.compare_label.setText("")
            return
        prospect = self.prospects[rows[0].row()]
        fee = self._fee(prospect)
        after = self.budget - fee
        peers = [
            a
            for a in self.roster
            if a.specialty == prospect.specialty and a.gender == prospect.gender
        ]
        if peers:
            best = max(peers, key=lambda a: a.overall)
            diff = prospect.overall - best.overall
            comp = (
                f"Confronto in rosa ({prospect.specialty.value} {prospect.gender}): "
                f"migliore attuale {best.name} (OVR {best.overall}/Pot {best.potential}) · Δ OVR {diff:+d}"
            )
        elif self.roster:
            comp = f"Nessun atleta in rosa per {prospect.specialty.value} ({prospect.gender})."
        else:
            comp = (
                f"{prospect.specialty.value} ({prospect.gender}) · OVR {prospect.overall}/"
                f"Pot {potential_band_display(prospect)}"
            )
        budget_txt = (
            f"Budget dopo tesseramento: €{after:,}"
            if after >= 0
            else f"Fondi insufficienti (mancano €{-after:,})"
        )
        self.compare_label.setText(f"{comp}   |   {budget_txt}")

    def _on_sign(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        prospect = self.prospects[rows[0].row()]
        agent = self._agent(prospect)
        if agent is not None:  # D.2: con un agente si tratta (richiesta, offerta, controfferta)
            terms = self._negotiate(prospect, agent)
            if terms is None:
                return
            self.selected_terms = terms
            self.selected_prospect = prospect
            self.accept()
            return
        fee = self._fee(prospect)
        if fee > self.budget:
            QMessageBox.warning(
                self,
                "Budget Insufficiente",
                f"Servono €{fee:,} per tesserare {prospect.name}, ma hai €{self.budget:,}.",
            )
            return
        self.selected_prospect = prospect
        self.accept()

    def _negotiate(self, prospect: Athlete, agent: Agent) -> Optional[Terms]:
        """Apre la finestra di trattativa; restituisce le condizioni concordate o None se si rinuncia."""
        dlg = NegotiationDialog(prospect, agent, self.budget, parent=self)
        return dlg.selected_terms if dlg.exec() else None


def release_question_text(athlete: Athlete, budget: int) -> str:
    """Testo della conferma di svincolo (D.2): per un atleta di Prima Squadra ricorda la clausola rescissoria da pagare."""
    text = f"Svincolare {athlete.name}?"
    clause = athlete.release_clause_cost
    if clause > 0:
        text += f"\n\nClausola rescissoria: €{clause:,} (budget €{budget:,})."
        text += "\nLasciarlo andare gratis: «Non rinnovare» (esce alla scadenza del contratto)."
    return text


class NegotiationDialog(QDialog):
    """Trattativa con l'agente di un atleta del mercato (D.2): richiesta → offerta → controfferta → accetto/rifiuto.

    Tutta la logica è in `models.market.Negotiation` (senza RNG); qui ci sono solo i controlli. A trattativa accettata
    `selected_terms` ha ingaggio e bonus concordati.
    """

    def __init__(self, athlete: Athlete, agent: Agent, budget: int, parent=None) -> None:
        super().__init__(parent)
        self.athlete = athlete
        self.agent = agent
        self.budget = budget
        self.negotiation = Negotiation(athlete, agent)
        self.selected_terms: Optional[Terms] = None
        self.setWindowTitle(f"Trattativa — {athlete.name}")
        self.resize(560, 380)
        self._build_ui()
        self.offer_spin.setValue(self.negotiation.ask.fee)  # si parte dalla richiesta dell'agente
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 18, 18, 18)

        title = QLabel(f"Trattativa per {self.athlete.name}")
        title.setObjectName("SectionHeader")
        layout.addWidget(title)
        info = QLabel(
            f"{self.athlete.specialty.value} · {self.athlete.age} anni · OVR {self.athlete.overall} · "
            f"Potenziale {potential_band_display(self.athlete)}"
        )
        info.setObjectName("SubTitle")
        layout.addWidget(info)
        agent_label = QLabel(
            f"Agente: {self.agent.name} — {self.agent.personality.value}, relazione {self.agent.relation}/100 "
            f"({self.agent.relation_label})"
        )
        agent_label.setWordWrap(True)
        layout.addWidget(agent_label)

        form = QFormLayout()
        self.bonus_combo = QComboBox()
        for b in self.negotiation.bonus_choices:
            label = "Nessun bonus" if b == 0 else f"€{b:,} a ogni record sociale (ingaggio −€{b:,})"
            self.bonus_combo.addItem(label, b)
        self.bonus_combo.setToolTip(
            "Bonus pagato a ogni record sociale individuale dell'atleta finché dura il contratto. "
            "L'agente abbassa l'ingaggio dello stesso importo: si paga dopo, e solo se il record arriva."
        )
        self.bonus_combo.currentIndexChanged.connect(self._on_bonus_changed)
        form.addRow("Bonus per risultati", self.bonus_combo)
        self.ask_label = QLabel("")
        self.ask_label.setStyleSheet("font-weight: 700;")
        form.addRow("Richiesta dell'agente", self.ask_label)
        self.offer_spin = QSpinBox()
        self.offer_spin.setPrefix("€")
        self.offer_spin.setRange(MIN_NEGOTIATED_FEE, 1_000_000)
        form.addRow("La tua offerta (ingaggio)", self.offer_spin)
        layout.addLayout(form)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("SubTitle")
        layout.addWidget(self.status_label)
        layout.addStretch()

        row = QHBoxLayout()
        row.addStretch()
        self.btn_refuse = QPushButton("Rifiuta")
        self.btn_refuse.clicked.connect(self._refuse)
        self.btn_accept_ask = QPushButton("Accetta la richiesta")
        self.btn_accept_ask.clicked.connect(self._accept_ask)
        self.btn_offer = QPushButton("Proponi offerta")
        self.btn_offer.clicked.connect(self._propose)
        self.btn_accept_counter = QPushButton("Accetta la controfferta")
        self.btn_accept_counter.setObjectName("PrimaryButton")
        self.btn_accept_counter.clicked.connect(self._accept_counter)
        for b in (self.btn_refuse, self.btn_accept_ask, self.btn_offer, self.btn_accept_counter):
            row.addWidget(b)
        layout.addLayout(row)

    # ------------------------------------------------------------------ stato della finestra
    def _afford(self, fee: int) -> bool:
        return fee <= self.budget

    def _refresh(self) -> None:
        neg = self.negotiation
        ask = neg.ask
        self.ask_label.setText(f"€{ask.fee:,}" + (f" + bonus €{ask.bonus:,} a record" if ask.bonus else ""))
        countered = neg.state is NegotiationState.COUNTERED
        self.bonus_combo.setEnabled(not countered)
        self.offer_spin.setEnabled(not countered)
        self.btn_accept_ask.setVisible(not countered)
        self.btn_offer.setVisible(not countered)
        self.btn_accept_counter.setVisible(countered)
        if countered:
            assert neg.counter is not None
            self.btn_accept_counter.setEnabled(self._afford(neg.counter.fee))
            text = (
                f"L'agente rilancia: ingaggio €{neg.counter.fee:,}"
                + (f" + bonus €{neg.counter.bonus:,} a record" if neg.counter.bonus else "")
                + ". Puoi accettare o rifiutare: non si rilancia di nuovo."
            )
            if not self._afford(neg.counter.fee):
                text += f"\nFondi insufficienti (hai €{self.budget:,})."
            self.status_label.setText(text)
            return
        self.offer_spin.setMaximum(ask.fee)
        self.offer_spin.setValue(min(max(self.offer_spin.value(), MIN_NEGOTIATED_FEE), ask.fee))
        self.btn_accept_ask.setEnabled(self._afford(ask.fee))
        self.status_label.setText(
            f"Budget disponibile: €{self.budget:,}. Un'offerta bassa può essere accettata subito, rilanciata una volta "
            "o respinta: dipende dall'agente."
            + ("" if self._afford(ask.fee) else "\nLa richiesta supera il budget: prova con un'offerta più bassa.")
        )

    def _on_bonus_changed(self, index: int) -> None:
        bonus = self.bonus_combo.itemData(index)
        if bonus is None or self.negotiation.state is not NegotiationState.OPEN:
            return
        self.negotiation.set_bonus(int(bonus))
        self.offer_spin.setMaximum(1_000_000)  # `_refresh` lo riporta alla nuova richiesta
        self.offer_spin.setValue(self.negotiation.ask.fee)
        self._refresh()

    # ------------------------------------------------------------------ mosse
    def _conclude(self, terms: Terms) -> None:
        self.selected_terms = terms
        self.accept()

    def _accept_ask(self) -> None:
        if not self._afford(self.negotiation.ask.fee):
            return
        self._conclude(self.negotiation.accept_ask())

    def _propose(self) -> None:
        fee = self.offer_spin.value()
        if not self._afford(fee):
            self.status_label.setText(f"Fondi insufficienti per un'offerta di €{fee:,} (hai €{self.budget:,}).")
            return
        state = self.negotiation.offer(fee)
        if state is NegotiationState.ACCEPTED:
            assert self.negotiation.terms is not None
            self._conclude(self.negotiation.terms)
        else:
            self._refresh()

    def _accept_counter(self) -> None:
        counter = self.negotiation.counter
        if counter is None or not self._afford(counter.fee):
            return
        self._conclude(self.negotiation.accept_counter())

    def _refuse(self) -> None:
        if not self.negotiation.is_closed:
            self.negotiation.refuse()
        self.reject()


class EthicalDilemmaDialog(QDialog):
    """Modal presenting an ethical choice with sporting vs moral trade-offs."""

    def __init__(self, dilemma: EthicalDilemma, parent=None) -> None:
        super().__init__(parent)
        self.dilemma = dilemma
        self.accepted_shortcut: bool = False
        # Falso solo se il giocatore preme «Accetta» o «Rifiuta»: chiudere la finestra (X, Esc) o «Ignora» = ignorato.
        self.chose: bool = False
        self.setWindowTitle(f"Dilemma Etico — {dilemma.title}")
        self.resize(540, 280)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(self.dilemma.title)
        title.setObjectName("AppTitle")
        title.setStyleSheet(f"color: {theme.WARN}; font-size: 18px; font-weight: 800;")
        layout.addWidget(title)

        desc = QLabel(self.dilemma.description)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 13px; color: {theme.TEXT};")
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

        ignore_btn = QPushButton("Ignora (l'occasione sfuma, nessun effetto)")
        ignore_btn.setObjectName("IgnoreDilemmaButton")
        ignore_btn.clicked.connect(self.reject)
        self.ignore_btn = ignore_btn

        btn_col.addWidget(accept_btn)
        btn_col.addWidget(reject_btn)
        btn_col.addWidget(ignore_btn)
        layout.addLayout(btn_col)

    def _choose_accept(self) -> None:
        self.accepted_shortcut = True
        self.chose = True
        self.accept()

    def _choose_reject(self) -> None:
        self.accepted_shortcut = False
        self.chose = True
        self.accept()


class NewGameDialog(QDialog):
    """Dialog to choose club name, game mode, and Lazio province."""

    def __init__(self, default_name: str = "Atletica Aurora", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nuova Partita — Track & Field Manager")
        self.resize(460, 280)

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
        for mode, label in GAME_MODE_OPTIONS:
            self.mode_combo.addItem(label, mode)
        layout.addWidget(self.mode_combo)

        prov_label = QLabel("Provincia di Partenza (Lazio):")
        prov_label.setObjectName("SectionHeader")
        layout.addWidget(prov_label)

        self.province_combo = QComboBox()
        self.province_combo.addItem("Standard (Selezione Lazio)", None)
        for prov in LAZIO_PROVINCES:
            self.province_combo.addItem(f"{prov} (società reali dal CSV)", prov)
        layout.addWidget(self.province_combo)

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

    @property
    def province(self) -> Optional[str]:
        val = self.province_combo.currentData()
        return str(val) if val else None


class HireCoachDialog(QDialog):
    """Choose a coach's type, the skills they are hired for and the recruitment level."""

    def __init__(self, budget: int, allowed_specialties: List[Specialty], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Assumi Allenatore")
        self.resize(520, 300)
        self.budget = budget

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 18, 18, 18)

        title = QLabel("Nuovo Allenatore")
        title.setObjectName("SectionHeader")
        layout.addWidget(title)
        hint = QLabel(
            "Un allenatore specializzato segue solo gli atleti della sua disciplina; quello del "
            "vivaio segue solo i ragazzi del vivaio, di qualsiasi disciplina. Le abilità non scelte "
            f"restano basse ({COACH_BASE_SKILL}). Oltre {COACH_COMFORT_LOAD} atleti seguiti, ognuno "
            "riceve meno attenzione."
        )
        hint.setObjectName("SubTitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.kind_combo = QComboBox()
        for spec in allowed_specialties:
            self.kind_combo.addItem(f"Specializzato — {spec.value}", spec)
        self.kind_combo.addItem("Vivaio (solo ragazzi 14-17)", None)
        form.addRow("Tipo:", self.kind_combo)

        self.primary_combo = QComboBox()
        self.secondary_combo = QComboBox()
        self.secondary_combo.addItem("Nessuna (stipendio più basso)", None)
        for stat in COACH_STATS:
            self.primary_combo.addItem(COACH_STAT_LABELS[stat], stat)
            self.secondary_combo.addItem(COACH_STAT_LABELS[stat], stat)
        self.secondary_combo.setCurrentIndex(4)  # Tecnica
        form.addRow("Abilità principale:", self.primary_combo)
        form.addRow("Abilità secondaria:", self.secondary_combo)

        self.tier_combo = QComboBox()
        for tier in range(1, COACH_MAX_TIER + 1):
            prim, sec = coach_hire_skills(tier)
            self.tier_combo.addItem(
                f"Livello {tier} — principale {prim}, secondaria {sec} — €{coach_hire_cost(tier):,}",
                tier,
            )
        form.addRow("Ingaggio:", self.tier_combo)
        layout.addLayout(form)

        self.preview = QLabel("")
        self.preview.setObjectName("SubTitle")
        layout.addWidget(self.preview)

        for combo in (self.kind_combo, self.primary_combo, self.secondary_combo, self.tier_combo):
            combo.currentIndexChanged.connect(lambda _i: self._update_preview())

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        self.hire_btn = QPushButton("Assumi")
        self.hire_btn.setObjectName("PrimaryButton")
        self.hire_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.hire_btn)
        layout.addLayout(btn_row)
        self._update_preview()

    @property
    def specialty(self) -> Optional[Specialty]:
        data = self.kind_combo.currentData()
        return data if isinstance(data, Specialty) else None

    @property
    def primary(self) -> str:
        return str(self.primary_combo.currentData())

    @property
    def secondary(self) -> Optional[str]:
        data = self.secondary_combo.currentData()
        return None if data is None or data == self.primary else str(data)

    @property
    def tier(self) -> int:
        return int(self.tier_combo.currentData())

    def _update_preview(self) -> None:
        prim, sec = coach_hire_skills(self.tier)
        skills = {stat: COACH_BASE_SKILL for stat in COACH_STATS}
        skills[self.primary] = prim
        if self.secondary is not None:
            skills[self.secondary] = sec
        cost = coach_hire_cost(self.tier)
        self.preview.setText(
            f"Costo ingaggio €{cost:,} · stipendio €{coach_weekly_wage(skills):,}/sett "
            f"(budget €{self.budget:,})"
        )
        self.hire_btn.setEnabled(cost <= self.budget)


class SeasonEndDialog(QDialog):
    """Final league table of the season with promotion / relegation outcome."""

    OUTCOME_COLORS = {
        SeasonOutcome.PROMOTED: theme.GOOD,
        SeasonOutcome.CHAMPION: theme.WARN,
        SeasonOutcome.STAYED: theme.INFO,
        SeasonOutcome.RELEGATED: theme.BAD,
    }

    def __init__(self, result: SeasonEndResult, team_name: str, parent=None) -> None:
        super().__init__(parent)
        self.result = result
        self.setWindowTitle(f"Fine Stagione {result.season}")
        self.resize(520, 480)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        title = QLabel(f"Stagione {result.season} — Lega {result.tier.display_name}")
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        if result.outcome == SeasonOutcome.PROMOTED and result.new_tier is not None:
            text = f"{result.placement}° posto: PROMOSSI in categoria {result.new_tier.display_name}!"
        elif result.outcome == SeasonOutcome.RELEGATED and result.new_tier is not None:
            text = f"Ultimo posto: RETROCESSI in categoria {result.new_tier.display_name}."
        elif result.outcome == SeasonOutcome.CHAMPION:
            text = f"1° posto: CAMPIONI della lega {result.tier.display_name}!"
        else:
            text = f"{result.placement}° posto: categoria {result.tier.display_name} confermata."
        outcome = QLabel(text)
        outcome.setStyleSheet(
            f"color: {self.OUTCOME_COLORS[result.outcome]}; font-weight: 800; font-size: 15px;"
        )
        layout.addWidget(outcome)

        rules = QLabel(
            f"Le prime {PROMOTION_SPOTS} salgono di categoria, l'ultima scende. "
            "I punti di lega ripartono da zero."
        )
        rules.setObjectName("SubTitle")
        layout.addWidget(rules)

        n = len(result.final_table)
        self.table = QTableWidget(n, 3)
        self.table.setHorizontalHeaderLabels(["Pos", "Società", "Punti"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        for row, (team, pts) in enumerate(result.final_table):
            if team == team_name:
                color = theme.INFO
            elif row < PROMOTION_SPOTS:
                color = theme.GOOD
            elif row >= n - RELEGATION_SPOTS:
                color = theme.BAD
            else:
                color = None
            for col, value in enumerate((str(row + 1), team, str(pts))):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if color:
                    item.setForeground(QColor(color))
                self.table.setItem(row, col, item)
        layout.addWidget(self.table, stretch=1)

        self.board_label: Optional[QLabel] = None
        if result.board_failed is not None:  # verdetto del Board (C.2); None = stagione senza obiettivi del Board
            lines = [f"{'✔' if ok else '✘'} {title}" for title, ok in result.board_results]
            if result.fired:
                verdict, color = f"ESONERATO: {result.board_streak} stagioni fallite di fila.", theme.BAD
            elif result.board_foundation:  # stagione di fondazione (Q32): solo informativa
                verdict, color = (
                    "Stagione di fondazione: nessuna conseguenza. Da ora il Board guarda i risultati.", theme.INFO
                )
            elif result.board_failed:
                verdict = f"Stagione FALLITA per il Board. Fallite di fila: {result.board_streak}. Alla {BOARD_MAX_FAILED_STREAK}ª arriva l'esonero."
                color = theme.WARN
            else:
                verdict, color = "Il Board è soddisfatto della stagione.", theme.GOOD
            self.board_label = QLabel("OBIETTIVI DEL BOARD\n" + "\n".join(lines) + "\n" + verdict)
            self.board_label.setWordWrap(True)
            self.board_label.setStyleSheet(f"color: {color}; font-weight: 700;")
            layout.addWidget(self.board_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("Chiudi" if result.fired else "Inizia la nuova stagione")
        ok.setObjectName("PrimaryButton")
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)


class BoardObjectivesDialog(QDialog):
    """Gli obiettivi che il Board assegna a inizio stagione (C.2)."""

    def __init__(self, objectives: List[SeasonObjective], season: int, team_name: str, failed_streak: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Il Board — Stagione {season}")
        self.resize(520, 300)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)
        title = QLabel(f"{team_name}: obiettivi della stagione {season}")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        intro = QLabel(
            f"Il Board si aspetta che tu ne centri almeno {BOARD_OBJECTIVES_TO_PASS} su {len(objectives)}. "
            f"{BOARD_MAX_FAILED_STREAK} stagioni fallite di fila portano all'esonero."
        )
        intro.setObjectName("SubTitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.objectives_label = QLabel("\n".join(f"• {o.title}" for o in objectives))
        self.objectives_label.setWordWrap(True)
        layout.addWidget(self.objectives_label)
        if failed_streak:
            warn = QLabel(f"Attenzione: la stagione scorsa è stata fallita ({failed_streak} di fila).")
            warn.setStyleSheet(f"color: {theme.WARN}; font-weight: 700;")
            layout.addWidget(warn)
        layout.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("Capito")
        ok.setObjectName("PrimaryButton")
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)
