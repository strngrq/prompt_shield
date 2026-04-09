"""Application entry point."""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from prompt_shield.core.config import Config
from prompt_shield.core.database import Database
from prompt_shield.ui.main_window import MainWindow

_RESOURCES = Path(__file__).resolve().parent.parent / "resources"


def main():
    config = Config()
    config.save()

    db = Database()

    app = QApplication(sys.argv)

    icon_path = _RESOURCES / "icon_256.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow(db, config)
    window.show()

    exit_code = app.exec()
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
