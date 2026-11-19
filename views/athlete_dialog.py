"""Scheda Atleta: dettaglio di un singolo atleta con caratteristiche a colonne e azioni rapide."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from controllers.game_controller import GameController
from models.entities import Athlete, PeriodizationPhase, Specialty, TrainingFocus
from models.simulation import body_fit_score

SPECIALTY_COLORS = {
    Specialty.SPRINTS: "#ef4444",
    Specialty.MIDDLE_DISTANCE: "#38bdf8",
    Specialty.JUMPS: "#a78bfa",
    Specialty.THROWS: "#f59e0b",
}

# Soglie dei badge: (valore minimo, sfondo, testo)
_BADGE_SCALE: List[Tuple[int, str, str]] = [
    (80, "#16a34a", "#ffffff"),
    (65, "#facc15", "#111827"),
    (45, "#fb923c", "#111827"),
    (0, "#ef4444", "#ffffff"),
]


def stat_colors(value: int, invert: bool = False) -> Tuple[str, str]:
    """Colore (sfondo, testo) del badge per un valore 0-100. `invert` per la fatica (meno è meglio)."""
    score = 100 - value if invert else value
    for threshold, bg, fg in _BADGE_SCALE:
        if score >= threshold:
            return bg, fg
    return _BADGE_SCALE[-1][1], _BADGE_SCALE[-1][2]


def potential_stars(potential: int) -> int:
    return max(1, min(5, round(potential / 20)))


def _badge(value: int, invert: bool = False) -> QLabel:
    bg, fg = stat_colors(value, invert)
    lbl = QLabel(str(value))
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedSize(44, 24)
    lbl.setStyleSheet(
        f"background-color: {bg}; color: {fg}; border-radius: 4px; font-weight: 800; font-size: 13px;"
    )
    return lbl


class _StatColumn(QFrame):
    """Pannello con titolo colorato e righe 'nome ... badge'."""

    def __init__(self, title: str, rows: List[Tuple[str, int, bool]], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SectionPanel")
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(0)
        head = QLabel(title.upper())
        head.setStyleSheet("color: #0de0cc; font-weight: 800; font-size: 12px; letter-spacing: 0.7px; padding-bottom: 8px;")
        box.addWidget(head)
        for name, value, invert in rows:
            row = QFrame()
            row.setStyleSheet("QFrame { border-bottom: 1px solid #26354d; }")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 6, 0, 6)
            label = QLabel(name)
            label.setStyleSheet("color: #cbd5e1; border: none;")
            hl.addWidget(label)
            hl.addStretch()
            hl.addWidget(_badge(value, invert))
            box.addWidget(row)
        box.addStretch()


class AthleteDetailDialog(QDialog):
    """Scheda atleta: header, tab (Panoramica / Allenamento / Competizioni) e barra azioni."""

    def __init__(self, controller: GameController, athlete_id: int, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.athlete_id = athlete_id
        self.released = False
        self.setMinimumSize(860, 640)

        athlete = self._athlete()
        self.setWindowTitle(f"Scheda Atleta — {athlete.name if athlete else ''}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(0)

        self.header = QFrame()
        self.header.setObjectName("HeaderBar")
        self._header_layout = QHBoxLayout(self.header)
        self._header_layout.setContentsMargins(18, 12, 18, 12)
        root.addWidget(self.header)

        self.tabs = QTabWidget()
        self.overview_page = QWidget()
        self.training_page = QWidget()
        self.results_page = QWidget()
        self.tabs.addTab(self.overview_page, "PANORAMICA")
        self.tabs.addTab(self.training_page, "ALLENAMENTO")
        self.tabs.addTab(self.results_page, "COMPETIZIONI")
        root.addWidget(self.tabs, stretch=1)

        actions = QHBoxLayout()
        actions.setContentsMargins(18, 8, 18, 0)
        actions.addStretch()
        btn_release = QPushButton("✕ SVINCOLA")
        btn_release.setObjectName("DangerButton")
        btn_release.clicked.connect(self._release)
        self.btn_no_renew = QPushButton("NON RINNOVARE")
        self.btn_no_renew.setToolTip(
            "A fine contratto l'atleta lascia la società senza penali. Con lo svincolo subito si perde fedeltà."
        )
        self.btn_no_renew.clicked.connect(self._toggle_no_renew)
        btn_recover = QPushButton("RECUPERO (€250)")
        btn_recover.setStyleSheet(
            "background-color: #0e7490; color: #f8fafc; border: 1px solid #0de0cc; font-weight: 700;"
        )
        btn_recover.clicked.connect(self._recover)
        btn_close = QPushButton("✓ CHIUDI")
        btn_close.setObjectName("PrimaryButton")
        btn_close.clicked.connect(self.accept)
        for b in (btn_release, self.btn_no_renew, btn_recover, btn_close):
            actions.addWidget(b)
        actions.addStretch()
        root.addLayout(actions)

        self.refresh()

    # ------------------------------------------------------------------ dati
    def _athlete(self) -> Optional[Athlete]:
        return next((a for a in self.controller.state.athletes if a.id == self.athlete_id), None)

    def refresh(self) -> None:
        athlete = self._athlete()
        if athlete is None:
            return
        self._build_header(athlete)
        self._update_no_renew_button(athlete)
        self._rebuild(self.overview_page, self._build_overview(athlete))
        self._rebuild(self.training_page, self._build_training(athlete))
        self._rebuild(self.results_page, self._build_results(athlete))

    @staticmethod
    def _rebuild(page: QWidget, content: QWidget) -> None:
        old = page.layout()
        if old is None:
            old = QVBoxLayout(page)
            old.setContentsMargins(18, 14, 18, 6)
        while old.count():
            item = old.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        old.addWidget(content)

    # ------------------------------------------------------------------ header
    def _contract_text(self, a: Athlete) -> str:
        """Scadenza del contratto (Q22): rinnovo automatico a fine stagione, a meno di svincolare l'atleta."""
        if a.in_youth_squad or a.contract_end_season <= 0:
            return "—"
        text = f"fino alla stagione {a.contract_end_season}"
        if a.contract_no_renew:
            text += " (non verrà rinnovato)"
        elif a.contract_end_season <= self.controller.state.season_number:
            text += " (rinnovo automatico)"
        return text

    @staticmethod
    def _initials(name: str) -> str:
        parts = [p for p in name.replace("-", " ").split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    def _avatar(self, athlete: Athlete, size: int) -> QLabel:
        color = SPECIALTY_COLORS.get(athlete.specialty, "#38bdf8")
        lbl = QLabel(self._initials(athlete.name))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedSize(size, size)
        lbl.setStyleSheet(
            f"background-color: #1e3a8a; color: #f8fafc; border: 3px solid {color};"
            f"border-radius: {size // 2}px; font-weight: 800; font-size: {size // 3}px;"
        )
        return lbl

    @staticmethod
    def _pill(text: str, bg: str, fg: str = "#f8fafc") -> QLabel:
        pill = QLabel(text)
        pill.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 10px; padding: 3px 10px;"
            "font-weight: 700; font-size: 11px;"
        )
        return pill

    def _build_header(self, athlete: Athlete) -> None:
        lay = self._header_layout
        while lay.count():
            item = lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        lay.addWidget(self._avatar(athlete, 52))
        names = QVBoxLayout()
        title = QLabel(f"{athlete.name} {athlete.flag}" + (" *" if athlete.is_youth_prospect else ""))
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #f8fafc;")
        team = QLabel(f"{self.controller.state.team_name}  ·  {athlete.flag} {athlete.nationality}")
        team.setObjectName("SubTitle")
        names.addWidget(title)
        names.addWidget(team)
        lay.addLayout(names)
        gender_bg = "#831843" if athlete.gender == "F" else "#1e40af"
        lay.addWidget(self._pill(athlete.gender_label, gender_bg), alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._pill(athlete.specialty.value, "#7f1d4a"), alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._pill(athlete.status_label, "#4b3f1d", "#fcd34d"), alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch()
        lay.addWidget(self._pill(f"Settimana {self.controller.state.week}", "#1e293b", "#cbd5e1"), alignment=Qt.AlignmentFlag.AlignVCenter)

    # ------------------------------------------------------------------ panoramica
    def _build_overview(self, a: Athlete) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        title = QLabel("CARATTERISTICHE")
        title.setStyleSheet(
            "font-size: 15px; font-weight: 800; color: #f8fafc; padding-bottom: 6px;"
            "border-bottom: 2px solid #0de0cc;"
        )
        outer.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(12)
        outer.addLayout(body, stretch=1)

        # colonna sinistra: avatar, OVR + stelle, scheda anagrafica
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignmentFlag.AlignTop)
        left.addWidget(self._avatar(a, 110), alignment=Qt.AlignmentFlag.AlignHCenter)
        badges = QHBoxLayout()
        badges.addStretch()
        ovr = QLabel(str(a.overall))
        ovr.setStyleSheet(
            "background-color: #0de0cc; color: #060e26; border-radius: 4px; padding: 3px 10px;"
            "font-weight: 800; font-size: 15px;"
        )
        stars = QLabel(f"★ {potential_stars(a.potential)}")
        stars.setStyleSheet("color: #f59e0b; font-weight: 800; font-size: 18px;")
        stars.setToolTip(f"Potenziale: {a.potential}")
        badges.addWidget(ovr)
        badges.addWidget(stars)
        badges.addStretch()
        left.addLayout(badges)

        coach = self.controller.state.coach_of(a)
        info_rows = [
            ("Categoria", a.gender_label),
            ("Età", f"{a.age} anni"),
            ("Fascia d'età", a.age_category),
            ("Nazionalità", f"{a.flag} {a.nationality}"),
            ("Altezza", a.height_display),
            ("Peso", a.weight_display),
            ("Disciplina", a.specialty.value),
            ("Carattere", a.personality.value),
            ("Potenziale", str(a.potential)),
            ("Rimborso spese", f"€{a.weekly_wage:,}/sett."),
            ("Contratto", self._contract_text(a)),
            ("Fan", f"{a.fans:,}"),
            ("Primato", a.personal_best_display or "—"),
            ("Allenatore", coach.name if coach else "Nessuno"),
        ]
        info = QFrame()
        info.setObjectName("SectionPanel")
        form = QFormLayout(info)
        form.setContentsMargins(14, 10, 14, 10)
        form.setHorizontalSpacing(18)
        for k, v in info_rows:
            key = QLabel(k)
            key.setStyleSheet("color: #94a3b8;")
            val = QLabel(v)
            val.setStyleSheet("font-weight: 700; color: #f8fafc;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            form.addRow(key, val)
        left.addWidget(info)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(250)
        body.addWidget(left_w)

        # tre colonne di caratteristiche
        body.addWidget(
            _StatColumn(
                "Fisico",
                [
                    ("Velocità", a.speed, False),
                    ("Resistenza", a.stamina, False),
                    ("Forza", a.strength, False),
                    ("Potenza", a.power, False),
                    ("Resilienza", a.resilience, False),
                ],
            ),
            stretch=1,
        )
        body.addWidget(
            _StatColumn(
                "Tecnica",
                [
                    ("Tecnica", a.technique, False),
                    ("Struttura fisica", body_fit_score(a), False),
                    ("Valutazione (OVR)", a.overall, False),
                    ("Potenziale", a.potential, False),
                ],
            ),
            stretch=1,
        )
        body.addWidget(
            _StatColumn(
                "Condizione",
                [
                    ("Forma", a.form, False),
                    ("Fatica", a.fatigue, True),
                    ("Sonno", a.sleep_quality, False),
                    ("Alimentazione", a.nutrition, False),
                ],
            ),
            stretch=1,
        )
        return page

    # ------------------------------------------------------------------ allenamento
    def _build_training(self, a: Athlete) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionPanel")
        form = QFormLayout(page)
        form.setContentsMargins(18, 16, 18, 16)
        form.setVerticalSpacing(12)

        focus = QComboBox()
        for f in TrainingFocus:
            focus.addItem(f.value, f)
        focus.setCurrentIndex(max(0, focus.findData(a.training_focus)))
        focus.setEnabled(not a.is_injured)
        focus.activated.connect(
            lambda _i: self.controller.set_athlete_training(self.athlete_id, focus.currentData())
        )
        form.addRow("Allenamento", focus)

        period = QComboBox()
        for p in PeriodizationPhase:
            period.addItem(p.value, p)
        period.setCurrentIndex(max(0, period.findData(a.periodization)))
        period.setEnabled(not a.is_injured)
        period.activated.connect(
            lambda _i: self.controller.set_athlete_periodization(self.athlete_id, period.currentData())
        )
        form.addRow("Periodizzazione", period)

        state = self.controller.state
        coach_combo = QComboBox()
        coach_combo.addItem("— Nessuno —", None)
        for c in state.coaches:
            if c.can_train(a):
                coach_combo.addItem(f"{c.name} ({state.coach_load(c)} atl.)", c.id)
        current = state.coach_of(a)
        coach_combo.setCurrentIndex(max(0, coach_combo.findData(current.id if current else None)))
        coach_combo.activated.connect(
            lambda _i: self.controller.assign_coach(self.athlete_id, coach_combo.currentData())
        )
        form.addRow("Allenatore", coach_combo)

        if a.is_injured:
            note = QLabel(f"Infortunato per altre {a.injured_weeks} settimane: allenamento bloccato.")
            note.setStyleSheet("color: #f87171;")
            form.addRow(note)
        return page

    # ------------------------------------------------------------------ competizioni
    def _build_results(self, a: Athlete) -> QWidget:
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Sett.", "Meeting", "Gara", "Piazzamento", "Risultato", "Note"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        rows = []
        for summary in reversed(self.controller.state.competition_history):
            for res in summary.event_results:
                if res.player_athlete_name == a.name:
                    rows.append((summary, res))
        table.setRowCount(len(rows))
        for r, (summary, res) in enumerate(rows):
            notes = []
            if res.is_pb:
                notes.append("PB")
            if res.is_club_record:
                notes.append("Record club")
            if res.withdrew_injured:
                notes.append("Ritirato")
            if res.disqualified:
                notes.append("Squalificato")
            cells = [
                str(summary.week),
                summary.meet_name,
                res.event_name,
                f"{res.placement}°/{res.total_competitors}",
                res.player_mark,
                ", ".join(notes),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(r, c, item)
        if not rows:
            holder = QFrame()
            holder.setObjectName("SectionPanel")
            lay = QVBoxLayout(holder)
            empty = QLabel("Nessuna gara disputata finora.")
            empty.setObjectName("SubTitle")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(empty)
            return holder
        return table

    # ------------------------------------------------------------------ azioni
    def _recover(self) -> None:
        self.controller.apply_recovery_session(self.athlete_id)
        self.refresh()

    def _update_no_renew_button(self, athlete: Athlete) -> None:
        self.btn_no_renew.setVisible(not athlete.in_youth_squad)
        self.btn_no_renew.setText("ANNULLA NON RINNOVO" if athlete.contract_no_renew else "NON RINNOVARE")

    def _toggle_no_renew(self) -> None:
        athlete = self._athlete()
        if athlete is None:
            return
        self.controller.set_contract_no_renew(self.athlete_id, not athlete.contract_no_renew)
        self.refresh()

    def _release(self) -> None:
        athlete = self._athlete()
        if athlete is None:
            return
        answer = QMessageBox.question(self, "Conferma", f"Svincolare {athlete.name}?")
        if answer == QMessageBox.StandardButton.Yes and self.controller.release_athlete(self.athlete_id):
            self.released = True
            self.accept()
