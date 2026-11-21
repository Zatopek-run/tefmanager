"""Dashboard in QML (PIANOLAVORO G, scelta C): `DashboardTab` = vista QML + **ripiego** sulla versione QWidget.

La vista QML disegna soltanto `models.dashboard.dashboard_snapshot` (testi e soglie sono decisi in Python, testati senza Qt).
Se QML non si carica, il grafo di scena non parte (nessuna GPU) o c'è `TEF_NO_QML=1`, si usa `WidgetDashboardTab`.
Stessa interfaccia di prima per `MainWindow`: `refresh(state)` e il segnale `navigate_requested(int)`.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QStackedLayout, QWidget

from controllers.game_controller import GameController
from models.dashboard import dashboard_snapshot, empty_dashboard_snapshot
from models.entities import GameState
from views.athlete_dialog import AthleteDetailDialog
from views.qml_host import QmlHost, qml_disabled
from views.tabs import WidgetDashboardTab


class DashboardViewModel(QObject):
    """Ponte tra Python e QML: espone l'istantanea (sola lettura) e raccoglie i clic (navigazione, Scheda Atleta)."""

    snapshotChanged = pyqtSignal()
    navigateRequested = pyqtSignal(int)
    athleteRequested = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._snapshot: dict = empty_dashboard_snapshot()

    @pyqtProperty("QVariantMap", notify=snapshotChanged)  # type: ignore[arg-type]
    def snapshot(self) -> dict:
        return self._snapshot

    def set_snapshot(self, snapshot: dict) -> None:
        self._snapshot = snapshot
        self.snapshotChanged.emit()

    @pyqtSlot(int)
    def navigate(self, index: int) -> None:
        self.navigateRequested.emit(index)

    @pyqtSlot(int)
    def openAthlete(self, athlete_id: int) -> None:
        self.athleteRequested.emit(athlete_id)


class DashboardTab(QWidget):
    navigate_requested = pyqtSignal(int)

    def __init__(self, controller: GameController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.snapshot: dict = empty_dashboard_snapshot()
        self.vm = DashboardViewModel()  # senza parent Qt: lo tiene vivo Python, così non muore prima della vista QML
        self.vm.navigateRequested.connect(self.navigate_requested)
        self.vm.athleteRequested.connect(self._open_athlete)
        self._last_state: Optional[GameState] = None
        self._fallback: Optional[WidgetDashboardTab] = None
        self._stack = QStackedLayout(self)
        self.qml: Optional[QmlHost] = None
        if not qml_disabled():
            try:
                self.qml = QmlHost("Dashboard.qml", {"vm": self.vm}, parent=self)
            except Exception as exc:  # noqa: BLE001 - qualunque errore di avvio di QML = ripiego, mai un'eccezione verso Qt
                self.qml = None
                self.qml_failure = f"QML non avviato: {exc}"
        if self.qml is None or self.qml.failed:
            self._use_fallback()
        else:
            self.vm.setParent(self.qml)  # il QQuickWidget distrugge prima il contenuto QML e poi i figli: nessun binding su un `vm` già morto
            self._stack.addWidget(self.qml)
            self.qml.failed_signal.connect(lambda _why: self._use_fallback())

    @property
    def uses_qml(self) -> bool:
        return self._fallback is None

    def _use_fallback(self) -> None:
        if self._fallback is not None:
            return
        self._fallback = WidgetDashboardTab(self.controller, self)
        self._fallback.navigate_requested.connect(self.navigate_requested)
        self._stack.addWidget(self._fallback)
        self._stack.setCurrentWidget(self._fallback)
        if self._last_state is not None:
            self._fallback.refresh(self._last_state)

    def _open_athlete(self, athlete_id: int) -> None:
        if athlete_id >= 0:  # fuori dal gestore di QML: il dialogo è modale
            QTimer.singleShot(0, lambda: AthleteDetailDialog(self.controller, athlete_id, parent=self).exec())

    def refresh(self, state: GameState) -> None:
        self._last_state = state
        if self._fallback is not None:
            self._fallback.refresh(state)
            return
        self.snapshot = dashboard_snapshot(state, self.controller.free_agent_pool)
        self.vm.set_snapshot(self.snapshot)
