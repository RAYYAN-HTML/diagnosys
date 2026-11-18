"""Capabilities page construction."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPlainTextEdit, QPushButton
from diagnosys.ui.components import MetricCard


def build(window) -> None:
        _, layout = window._page("Capabilities", "See which measurements this device and operating system expose.")
        result_card = MetricCard("Runtime support")
        window.capabilities_output = QPlainTextEdit()
        window.capabilities_output.setReadOnly(True)
        window.capabilities_output.setMinimumHeight(270)
        result_card.content.addWidget(window.capabilities_output)
        layout.addWidget(result_card)
        refresh = QPushButton("Refresh capabilities")
        refresh.clicked.connect(window.show_capabilities)
        layout.addWidget(refresh, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        window.show_capabilities()

