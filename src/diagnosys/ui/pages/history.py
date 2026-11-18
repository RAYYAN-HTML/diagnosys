"""History page construction."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton
from diagnosys.ui.components import MetricCard


def build(window) -> None:
        _, layout = window._page(
            "History & reports",
            "Review saved measurements and incidents, preview a diagnostic report, or export it for support.",
        )
        actions = QHBoxLayout()
        history = QPushButton("Refresh history")
        history.clicked.connect(window.show_history)
        window.history_window = QComboBox()
        for label, seconds in (("Last hour", 3600), ("Last 24 hours", 86400), ("Last 7 days", 604800)):
            window.history_window.addItem(label, seconds)
        window.history_window.currentIndexChanged.connect(lambda _index: window.show_history())
        window.incident_selector = QComboBox()
        window.incident_selector.setMinimumWidth(190)
        window.incident_selector.setPlaceholderText("Select incident")
        window.incident_selector.currentIndexChanged.connect(window._incident_selection_changed)
        window.view_incident_button = QPushButton("View evidence")
        window.view_incident_button.clicked.connect(window.view_incident_evidence)
        window.report_button = QPushButton("Preview report", objectName="PrimaryButton")
        window.report_button.clicked.connect(window.generate_report)
        window.export_report_button = QPushButton("Export report…")
        window.export_report_button.clicked.connect(window.export_report)
        window.capture_button = QPushButton("Capture incident")
        window.capture_button.clicked.connect(window.capture_incident)
        actions.addWidget(window.history_window)
        actions.addWidget(window.incident_selector)
        actions.addWidget(window.view_incident_button)
        actions.addWidget(history)
        actions.addWidget(window.report_button)
        actions.addWidget(window.export_report_button)
        actions.addWidget(window.capture_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        incident_actions = QHBoxLayout()
        window.export_incident_button = QPushButton("Export selected incident…")
        window.export_incident_button.clicked.connect(window.export_selected_incident)
        window.export_incident_button.setEnabled(False)
        incident_actions.addWidget(window.export_incident_button)
        incident_actions.addWidget(QLabel("Creates a reviewable, redacted support bundle."), 1)
        layout.addLayout(incident_actions)

        result_card = MetricCard("Recent activity")
        result_card.add_badge("LOCAL DATABASE", "PillGood")
        window.history_output = QPlainTextEdit()
        window.history_output.setReadOnly(True)
        window.history_output.setMinimumHeight(330)
        result_card.content.addWidget(window.history_output)
        layout.addWidget(result_card)
        layout.addStretch(1)

