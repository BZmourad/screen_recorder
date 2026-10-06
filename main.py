"""Entry point for the Screen Recorder application."""

import logging
import sys

from PySide6.QtWidgets import QApplication

from logger import setup_logging
from ui import MainWindow


def main() -> int:
    setup_logging()
    log = logging.getLogger(__name__)
    log.info("=== Screen Recorder starting ===")

    app = QApplication(sys.argv)

    def _excepthook(exc_type, exc_value, exc_tb):
        log.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())