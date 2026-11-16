"""Entry point for Track & Field Manager desktop application."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.database import DatabaseManager
from views.main_window import MainWindow


def main() -> int:
    """Initialize Qt application, MVC layers, and run event loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("Track & Field Manager")
    app.setOrganizationName("TrackFieldManager")

    db_manager = DatabaseManager()
    controller = GameController(db_manager=db_manager)
    window = MainWindow(controller=controller)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
