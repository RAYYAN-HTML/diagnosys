"""Application entry point for the native Diagnosys desktop application."""

from PySide6.QtWidgets import QApplication

from diagnosys.ui.main_window import MainWindow
from diagnosys.ui.theme.apply_theme import apply_theme


def run_gui(refresh_seconds: int | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    window = MainWindow(refresh_seconds)
    window.show()
    return app.exec()
