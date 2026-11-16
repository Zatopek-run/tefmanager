"""Gare in diretta: animazione delle corse in pista e tabellone dei tentativi nei concorsi.

L'esito è quello già simulato (`CompetitionSummary`): qui lo si mette in scena, non lo si cambia.
"""

from __future__ import annotations

import math
import random
import zlib
from typing import List, Optional, Sequence

from PyQt6.QtCore import QElapsedTimer, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.entities import EVENTS, CompetitionSummary, EventResult, EventStanding

# Distanza percorsa (m) e durata target dell'animazione (s) a velocità 1x: None = tempo reale
TRACK_DISTANCES = {"100m": 100, "400m": 400, "1500m": 1500, "4x100m": 400, "4x400m": 1600}
TRACK_TARGET_SECONDS = {"100m": None, "400m": 24.0, "1500m": 26.0, "4x100m": 16.0, "4x400m": 28.0}
FIELD_ROUNDS = 4
DNF_PROGRESS = 0.42  # un atleta ritirato si ferma a questo punto della gara
PRE_START_SECONDS = 3.0  # "Ai vostri posti" -> "Pronti" -> sparo
GUN_AT = 2.4  # istante dello sparo nella sequenza di partenza
REACTION_RANGE = (0.12, 0.22)  # tempo di reazione ai blocchi (fa parte del tempo ufficiale)


def is_field_event(event_name: str) -> bool:
    ev = EVENTS.get(event_name)
    return ev is not None and ev.unit == "m"


def _rng(*parts: object) -> random.Random:
    """Generatore deterministico: la stessa gara si rivede sempre uguale."""
    return random.Random(zlib.crc32("|".join(str(p) for p in parts).encode()))


def _velocity(kind: str, u: float) -> float:
    """Velocità relativa (sempre > 0) al tempo normalizzato u in [0, 1] per tipo di gara."""
    if kind == "100m":  # forte accelerazione fino a ~60 m, poi leggero calo
        return (1.0 - math.exp(-u / 0.14)) * (1.0 - 0.07 * max(0.0, (u - 0.6) / 0.4)) + 0.02
    if kind == "400m":  # partenza veloce, calo nella seconda metà
        return (1.0 - math.exp(-u / 0.05)) * (1.0 - 0.16 * u) + 0.02
    if kind == "1500m":  # gruppo compatto, poi volata finale
        return (1.0 - math.exp(-u / 0.02)) * (0.92 + 0.05 * u + 1.3 * max(0.0, u - 0.88) ** 1.4) + 0.02
    # staffette: ogni frazione riparte (cambio al volo), con un po' di calo a fine frazione
    s = (u * 4.0) % 1.0
    return 0.72 + 0.28 * (1.0 - math.exp(-s / 0.2)) - 0.06 * s


_CURVE_STEPS = 600
_G_TABLES: dict = {}


def _g_table(kind: str) -> List[float]:
    """Spazio percorso (normalizzato, 0..1) a passi uniformi di tempo: integrale della velocità."""
    table = _G_TABLES.get(kind)
    if table is None:
        cum = [0.0]
        for i in range(1, _CURVE_STEPS + 1):
            u0, u1 = (i - 1) / _CURVE_STEPS, i / _CURVE_STEPS
            cum.append(cum[-1] + 0.5 * (_velocity(kind, u0) + _velocity(kind, u1)) / _CURVE_STEPS)
        table = [c / cum[-1] for c in cum]
        _G_TABLES[kind] = table
    return table


def curve_kind(event_name: str) -> str:
    return "relay" if event_name.startswith("4x") else event_name


def curve_progress(kind: str, u: float, phase: float = 0.0, amp: float = 0.006) -> float:
    """Frazione di percorso (0..1) al tempo normalizzato `u`: 0 al via, 1 esatto all'arrivo.

    Monotona crescente; `phase`/`amp` aggiungono solo piccoli sorpassi scenici.
    """
    u = max(0.0, min(1.0, u))
    table = _g_table(kind)
    pos = u * _CURVE_STEPS
    i = min(_CURVE_STEPS - 1, int(pos))
    g = table[i] + (table[i + 1] - table[i]) * (pos - i)
    return g + amp * math.sin(phase + 7.0 * u) * u * (1.0 - u)


def reaction_time(seed: object, name: str) -> float:
    return _rng(seed, "reaction", name).uniform(*REACTION_RANGE)


def position_fraction(event_name: str, race_t: float, mark: float, reaction: float, phase: float = 0.0) -> float:
    """Frazione di percorso al tempo di gara `race_t` (dallo sparo) per chi chiude in `mark` secondi.

    Il tempo di reazione è incluso nel tempo ufficiale: corre per (mark - reaction) secondi
    e taglia il traguardo esattamente a `mark`.
    """
    return curve_progress(curve_kind(event_name), (race_t - reaction) / max(1e-6, mark - reaction), phase)


def format_race_time(seconds: float) -> str:
    if seconds >= 60:
        return f"{int(seconds // 60)}:{seconds % 60:05.2f}"
    return f"{seconds:.2f}s"


def generate_attempts(mark: float, rng: random.Random, rounds: int = FIELD_ROUNDS) -> List[Optional[float]]:
    """Tentativi di un concorso: uno uguale al risultato finale, gli altri più bassi o nulli (None)."""
    best_round = rng.randrange(rounds)
    attempts: List[Optional[float]] = []
    for i in range(rounds):
        if i == best_round:
            attempts.append(mark)
        elif rng.random() < 0.15:
            attempts.append(None)
        else:
            attempts.append(round(mark * rng.uniform(0.90, 0.992), 2))
    return attempts


def _short(name: str, limit: int = 22) -> str:
    return name if len(name) <= limit else name[: limit - 1] + "…"


# --------------------------------------------------------------------------- corse
class TrackRaceWidget(QWidget):
    """Corsie con gli atleti che avanzano verso il traguardo."""

    finished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(300)
        self._runners: List[dict] = []
        self._event = "100m"
        self._winner_time = 1.0
        self._scale = 1.0  # secondi di gara per secondo di animazione
        self._t = 0.0  # secondi di animazione dall'inizio (compresa la sequenza di partenza)
        self._done = False

    def set_race(self, event_name: str, result: EventResult, seed: object) -> None:
        self._event = event_name
        self._runners = []
        valid = []
        for s in result.standings:
            is_dnf = s.is_player and result.withdrew_injured
            if not is_dnf:
                valid.append(s.mark_value)
            self._runners.append(
                {
                    "s": s,
                    "dnf": is_dnf,
                    "phase": _rng(seed, s.athlete_name).uniform(0, 6.28),
                    "react": reaction_time(seed, s.athlete_name),
                }
            )
        self._winner_time = max(0.5, min(valid) if valid else 1.0)
        target = TRACK_TARGET_SECONDS.get(event_name)
        self._scale = 1.0 if target is None else max(1.0, self._winner_time / target)
        self._t = 0.0
        self._done = False
        self.update()

    # ---- tempo
    @property
    def race_time(self) -> float:
        """Secondi di gara trascorsi dallo sparo (0 durante la sequenza di partenza)."""
        return max(0.0, self._t - GUN_AT) * self._scale

    @property
    def race_clock(self) -> float:
        return min(self._winner_time, self.race_time)

    @property
    def start_phase(self) -> str:
        if self._t < GUN_AT * 0.5:
            return "AI VOSTRI POSTI"
        if self._t < GUN_AT:
            return "PRONTI"
        if self._t < GUN_AT + 0.7:
            return "VIA!"
        return ""

    def _last_finish(self) -> float:
        return max((r["s"].mark_value for r in self._runners if not r["dnf"]), default=0.0)

    def advance(self, dt: float) -> None:
        if self._done:
            return
        self._t += dt
        end_anim = GUN_AT + self._last_finish() / self._scale + 1.2
        if self._t >= end_anim:
            self._t = end_anim
            self._done = True
            self.finished.emit()
        self.update()

    def skip_to_end(self) -> None:
        if not self._done:
            self._t = 1e6
            self.advance(0.0)

    def fraction(self, runner: dict) -> float:
        """Frazione di pista percorsa dall'atleta in questo istante."""
        t = self.race_time
        if runner["dnf"]:
            f = position_fraction(self._event, t, self._winner_time * 1.25, runner["react"], runner["phase"])
            return min(DNF_PROGRESS, f * 0.9)
        return position_fraction(self._event, t, runner["s"].mark_value, runner["react"], runner["phase"])

    def _has_finished(self, runner: dict) -> bool:
        return (not runner["dnf"]) and self.race_time >= runner["s"].mark_value

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0b1220"))
        n = len(self._runners)
        if n == 0:
            return
        left, right = 190, 120
        x0, x1 = left, self.width() - right
        top, bottom = 10, self.height() - 10
        lane_h = (bottom - top) / n
        font = QFont(self.font())
        font.setPointSize(9)
        p.setFont(font)

        for i, r in enumerate(self._runners):
            y = top + i * lane_h
            p.fillRect(int(x0), int(y + 2), int(x1 - x0), int(lane_h - 4), QColor("#7c2d12" if i % 2 else "#9a3412"))
            p.fillRect(int(x0), int(y + 2), int(x1 - x0), int(lane_h - 4), QColor(0, 0, 0, 60))
            p.setPen(QPen(QColor("#fde68a"), 1))
            p.drawLine(int(x0), int(y), int(x1), int(y))
        p.drawLine(int(x0), int(bottom), int(x1), int(bottom))

        # traguardo a scacchi
        sq = 6
        for j in range(int((bottom - top) // sq) + 1):
            for k in range(2):
                p.fillRect(int(x1 + k * sq), int(top + j * sq), sq, sq,
                           QColor("#f8fafc" if (j + k) % 2 == 0 else "#0f172a"))

        for i, r in enumerate(self._runners):
            s: EventStanding = r["s"]
            y = top + i * lane_h + lane_h / 2
            prog = self.fraction(r)
            finished = self._has_finished(r)
            colour = QColor("#fbbf24" if s.is_player else "#94a3b8")

            # etichetta a sinistra: corsia, nome, squadra
            p.setPen(QColor("#f8fafc" if s.is_player else "#cbd5e1"))
            bold = QFont(font)
            bold.setBold(s.is_player)
            p.setFont(bold)
            p.drawText(8, int(y - 2), f"{i + 1}  {_short(s.athlete_name, 24)}")
            p.setPen(QColor("#64748b"))
            p.setFont(font)
            p.drawText(24, int(y + 12), _short(s.team_name, 26))

            # atleta
            cx = x0 + (x1 - x0) * prog
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colour)
            p.drawEllipse(int(cx - 8), int(y - 8), 16, 16)
            p.setPen(QColor("#0f172a"))
            p.drawText(int(cx - 8), int(y - 8), 16, 16, Qt.AlignmentFlag.AlignCenter, str(i + 1))

            # esito a destra
            if r["dnf"] and self.race_time > self._winner_time * 0.8:
                p.setPen(QColor("#f87171"))
                p.drawText(int(x1 + 18), int(y + 4), "RITIRATO")
            elif finished:
                p.setPen(QColor("#fbbf24" if s.is_player else "#e2e8f0"))
                p.drawText(int(x1 + 18), int(y + 4), f"{s.placement}°  {s.mark_display}")

        phase = self.start_phase
        if phase:
            big = QFont(font)
            big.setPointSize(26)
            big.setBold(True)
            p.setFont(big)
            p.setPen(QColor(0, 0, 0, 150))
            p.drawText(self.rect().adjusted(2, 2, 2, 2), Qt.AlignmentFlag.AlignCenter, phase)
            p.setPen(QColor("#fbbf24" if phase == "VIA!" else "#f8fafc"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, phase)
        p.end()


# --------------------------------------------------------------------------- concorsi
class FieldBoardWidget(QTableWidget):
    """Tabellone dei tentativi: un tentativo per atleta ad ogni round, poi la classifica."""

    finished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(0, FIELD_ROUNDS + 3, parent)
        self.setHorizontalHeaderLabels(
            ["Atleta"] + [f"Prova {i + 1}" for i in range(FIELD_ROUNDS)] + ["Migliore", "Pos"]
        )
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._steps: List[tuple] = []
        self._step = 0
        self._acc = 0.0
        self._step_time = 0.28
        self._done = False
        self._attempts: List[List[Optional[float]]] = []
        self._standings: List[EventStanding] = []
        self._unit = "m"

    def set_race(self, event_name: str, result: EventResult, seed: object) -> None:
        order = list(result.standings)
        _rng(seed, event_name).shuffle(order)  # ordine di gara: non anticipa la classifica
        self._standings = order
        self._unit = EVENTS[event_name].unit
        self._attempts = []
        self.setRowCount(len(order))
        for row, s in enumerate(order):
            if s.is_player and result.withdrew_injured:
                self._attempts.append([None] * FIELD_ROUNDS)
            else:
                self._attempts.append(generate_attempts(s.mark_value, _rng(seed, event_name, s.athlete_name)))
            name = QTableWidgetItem(f"{s.athlete_name}  ·  {s.team_name}")
            if s.is_player:
                name.setForeground(QColor("#fbbf24"))
            self.setItem(row, 0, name)
            for col in range(1, FIELD_ROUNDS + 3):
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, col, item)
        self._steps = [(rnd, row) for rnd in range(FIELD_ROUNDS) for row in range(len(order))]
        self._step = 0
        self._acc = 0.0
        self._done = False

    def advance(self, dt: float) -> None:
        if self._done:
            return
        self._acc += dt
        while self._acc >= self._step_time and self._step < len(self._steps):
            self._acc -= self._step_time
            self._reveal(self._step)
            self._step += 1
        if self._step >= len(self._steps) and self._acc >= 0.6:
            self._finish()

    def skip_to_end(self) -> None:
        while self._step < len(self._steps):
            self._reveal(self._step)
            self._step += 1
        if not self._done:
            self._finish()

    def _reveal(self, idx: int) -> None:
        rnd, row = self._steps[idx]
        value = self._attempts[row][rnd]
        item = self.item(row, 1 + rnd)
        item.setText("X" if value is None else f"{value:.2f}")
        item.setForeground(QColor("#f87171" if value is None else "#e2e8f0"))
        best = max((v for v in self._attempts[row][: rnd + 1] if v is not None), default=None)
        self.item(row, FIELD_ROUNDS + 1).setText("—" if best is None else f"{best:.2f}")
        self.scrollToItem(item)

    def _finish(self) -> None:
        self._done = True
        for row, s in enumerate(self._standings):
            self.item(row, FIELD_ROUNDS + 1).setText(s.mark_display)
            pos = self.item(row, FIELD_ROUNDS + 2)
            pos.setText(f"{s.placement}°")
            if s.placement == 1:
                pos.setForeground(QColor("#fbbf24"))
        self.finished.emit()


# --------------------------------------------------------------------------- dialog
class RaceViewerDialog(QDialog):
    """Mostra una dopo l'altra le gare del meeting. Si può accelerare, saltare o chiudere."""

    SPEEDS = (1.0, 2.0, 4.0)

    def __init__(self, summary: CompetitionSummary, parent=None) -> None:
        super().__init__(parent)
        self.summary = summary
        self.setWindowTitle(f"Gare in diretta — {summary.meet_name}")
        self.resize(900, 560)
        self._index = -1
        self._speed_idx = 0
        self._paused = False
        self._race_done = True

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        self.title = QLabel()
        self.title.setObjectName("AppTitle")
        root.addWidget(self.title)
        self.info = QLabel()
        self.info.setObjectName("SubTitle")
        root.addWidget(self.info)

        self.stack = QStackedWidget()
        self.track = TrackRaceWidget()
        self.field = FieldBoardWidget()
        self.stack.addWidget(self.track)
        self.stack.addWidget(self.field)
        root.addWidget(self.stack, stretch=1)

        self.clock = QLabel("")
        self.clock.setStyleSheet("font-size: 18px; font-weight: 800; color: #f8fafc;")
        root.addWidget(self.clock)
        self.podium = QLabel("")
        self.podium.setObjectName("SectionHeader")
        self.podium.setWordWrap(True)
        root.addWidget(self.podium)

        bar = QHBoxLayout()
        self.btn_pause = QPushButton("⏸ Pausa")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_speed = QPushButton("Velocità 1x")
        self.btn_speed.clicked.connect(self._cycle_speed)
        self.btn_skip = QPushButton("⏩ Salta alla fine")
        self.btn_skip.clicked.connect(self._skip_race)
        self.btn_next = QPushButton("Prossima gara ▶")
        self.btn_next.setObjectName("PrimaryButton")
        self.btn_next.clicked.connect(self._next)
        self.btn_close = QPushButton("Vai ai risultati")
        self.btn_close.clicked.connect(self.accept)
        for b in (self.btn_pause, self.btn_speed, self.btn_skip):
            bar.addWidget(b)
        bar.addStretch()
        bar.addWidget(self.btn_close)
        bar.addWidget(self.btn_next)
        root.addLayout(bar)

        self.track.finished.connect(self._on_race_finished)
        self.field.finished.connect(self._on_race_finished)
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

        self._next()

    # ---- controllo
    def _seed(self) -> str:
        return f"{self.summary.week}-{self.summary.meet_name}"

    def _next(self) -> None:
        if not self._race_done:
            self._skip_race()
            return
        self._index += 1
        results = self.summary.event_results
        if self._index >= len(results):
            self.accept()
            return
        res = results[self._index]
        total = len(results)
        self.title.setText(f"{res.event_name} — gara {self._index + 1} di {total}")
        wind = "" if res.wind_ms is None else f"  |  Vento: {res.wind_ms:+.1f} m/s" + (" (non omologato)" if res.wind_illegal else "")
        self.info.setText(
            f"Meteo: {self.summary.weather.value}  |  Pista: {self.summary.track_surface}{wind}"
            f"  |  Atteggiamento: {res.attitude}"
        )
        self.podium.setText("")
        self.clock.setText("")
        self._race_done = False
        if is_field_event(res.event_name):
            self.field.set_race(res.event_name, res, self._seed())
            self.stack.setCurrentWidget(self.field)
        else:
            self.track.set_race(res.event_name, res, self._seed())
            self.stack.setCurrentWidget(self.track)
        self.btn_next.setEnabled(False)
        self.btn_skip.setEnabled(True)
        self._clock.start()
        self._timer.start()

    def _current_widget(self):
        return self.stack.currentWidget()

    def _tick(self) -> None:
        dt = self._clock.restart() / 1000.0
        if self._paused or self._race_done:
            return
        w = self._current_widget()
        w.advance(dt * self.SPEEDS[self._speed_idx])
        if w is self.track:
            self.clock.setText(f"⏱ {format_race_time(self.track.race_clock)}")

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.btn_pause.setText("▶ Riprendi" if self._paused else "⏸ Pausa")

    def _cycle_speed(self) -> None:
        self._speed_idx = (self._speed_idx + 1) % len(self.SPEEDS)
        self.btn_speed.setText(f"Velocità {int(self.SPEEDS[self._speed_idx])}x")

    def _skip_race(self) -> None:
        if not self._race_done:
            self._current_widget().skip_to_end()

    def _on_race_finished(self) -> None:
        self._race_done = True
        self.btn_skip.setEnabled(False)
        last = self._index >= len(self.summary.event_results) - 1
        self.btn_next.setText("Vai ai risultati ▶" if last else "Prossima gara ▶")
        self.btn_next.setEnabled(True)
        res = self.summary.event_results[self._index]
        top: Sequence[EventStanding] = sorted(res.standings, key=lambda s: s.placement)[:3]
        self.podium.setText("   ".join(f"{s.placement}° {s.athlete_name} {s.mark_display}" for s in top))
        if self.stack.currentWidget() is self.track:
            self.clock.setText(f"⏱ {format_race_time(self.track.race_clock)}")
        note = []
        if res.withdrew_injured:
            note.append(f"{res.player_athlete_name} si è ritirato per infortunio")
        if res.disqualified:
            note.append("squadra squalificata")
        if note:
            self.info.setText(self.info.text() + "  |  " + ", ".join(note))

    def done(self, r: int) -> None:  # chiusura: ferma il timer
        self._timer.stop()
        super().done(r)
