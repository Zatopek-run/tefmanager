"""Pannello del tabellone live in QML (PIANOLAVORO G.3, scelta C), accanto alla gara in pista.

Disegna soltanto `views.race_live.live_board`. Se QML non parte il pannello resta nascosto: la gara si vede e si gioca come prima
(è una funzione nuova, non c'è una vista di ripiego da mostrare).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from views.qml_host import QmlHost, qml_disabled
from views.race_live import empty_board

PANEL_WIDTH = 310


class RaceBoardViewModel(QObject):
    boardChanged = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._board: dict = empty_board()

    @pyqtProperty("QVariantMap", notify=boardChanged)  # type: ignore[arg-type]
    def board(self) -> dict:
        return self._board

    def set_board(self, board: dict) -> None:
        self._board = board
        self.boardChanged.emit()


class RaceBoardPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.vm = RaceBoardViewModel()
        self.board: dict = empty_board()
        self.qml: Optional[QmlHost] = None
        self.failure = ""
        self.setFixedWidth(PANEL_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if qml_disabled():
            self.failure = "TEF_NO_QML"
            return
        try:
            self.qml = QmlHost("RaceBoard.qml", {"vm": self.vm}, parent=self)
        except Exception as exc:  # noqa: BLE001 - qualunque errore di avvio di QML = pannello nascosto
            self.failure = f"QML non avviato: {exc}"
            self.qml = None
            return
        if self.qml.failed:
            self.failure = self.qml.failure
            return
        self.vm.setParent(self.qml)
        layout.addWidget(self.qml)
        self.qml.failed_signal.connect(lambda why: setattr(self, "failure", why))

    @property
    def failed(self) -> bool:
        return self.qml is None or self.qml.failed or bool(self.failure)

    def set_board(self, board: dict) -> None:
        self.board = board
        self.vm.set_board(board)
