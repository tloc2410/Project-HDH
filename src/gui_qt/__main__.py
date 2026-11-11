"""Mở giao diện PySide6 bằng ``python -m src.gui_qt``."""

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        if exc.name != "PySide6":
            raise
        print("Cài PySide6 bằng lệnh: python -m pip install -r requirements-qt.txt", file=sys.stderr)
        return 1

    from .controller import SimulatorController
    from .main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    controller = SimulatorController(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
