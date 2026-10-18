from pathlib import Path
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .tokens import TOKENS


def apply_theme(app: QApplication) -> None:
    app.setFont(QFont("Segoe UI", 10))
    stylesheet = Path(__file__).with_name("theme.qss").read_text(encoding="utf-8")
    for token, value in TOKENS.qss_values().items():
        stylesheet = stylesheet.replace(f"@{token}@", value)
    app.setStyleSheet(stylesheet)
