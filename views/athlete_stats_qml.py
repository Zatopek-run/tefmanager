"""Parte grafica della scheda atleta in QML (PIANOLAVORO G.2, scelta C): radar, potenziale, condizione, ultime gare, confronto.

`AthleteStatsView` è un widget con un `QQuickWidget` dentro che disegna soltanto `models.athlete_view.athlete_snapshot`. Se QML non parte
(`failed`), la scheda atleta usa le tre colonne QWidget di prima. Una sola vista per dialogo, riusata a ogni `refresh`.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from models.athlete_view import athlete_snapshot, empty_athlete_snapshot
from models.entities import Athlete, GameState
from views.qml_host import QmlHost, qml_disabled


class AthleteViewModel(QObject):
    snapshotChanged = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._snapshot: dict = empty_athlete_snapshot()

    @pyqtProperty("QVariantMap", notify=snapshotChanged)  # type: ignore[arg-type]
    def snapshot(self) -> dict:
        return self._snapshot

    def set_snapshot(self, snapshot: dict) -> None:
        self._snapshot = snapshot
        self.snapshotChanged.emit()


class AthleteStatsView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.vm = AthleteViewModel()
        self.snapshot: dict = empty_athlete_snapshot()
        self.qml: Optional[QmlHost] = None
        self.failure = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if qml_disabled():
            self.failure = "TEF_NO_QML"
            return
        try:
            self.qml = QmlHost("AthleteStats.qml", {"vm": self.vm}, parent=self)
        except Exception as exc:  # noqa: BLE001 - qualunque errore di avvio di QML = ripiego sulle colonne QWidget
            self.failure = f"QML non avviato: {exc}"
            self.qml = None
            return
        if self.qml.failed:
            self.failure = self.qml.failure
            return
        self.vm.setParent(self.qml)  # come la Dashboard: il `vm` muore dopo il contenuto QML
        layout.addWidget(self.qml)
        self.qml.failed_signal.connect(self._on_failed)

    def _on_failed(self, why: str) -> None:
        self.failure = why

    @property
    def failed(self) -> bool:
        return self.qml is None or self.qml.failed or bool(self.failure)

    def set_athlete(self, state: GameState, athlete: Athlete) -> None:
        self.snapshot = athlete_snapshot(state, athlete)
        self.vm.set_snapshot(self.snapshot)
