"""Settings page construction."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QPushButton, QSpinBox
from diagnosys.ui.components import MetricCard


def build(window) -> None:
        _, layout = window._page(
            "Monitoring settings",
            "Tune local sampling, data retention, network probes, and alert behavior. Preferences stay on this device.",
        )
        card = MetricCard("Monitoring and alerts")
        form = QFormLayout()

        window.refresh_interval = QSpinBox()
        window.refresh_interval.setRange(1, 300)
        window.refresh_interval.setSuffix(" seconds")
        window.refresh_interval.setValue(window.settings.refresh_seconds)
        form.addRow("Sampling interval", window.refresh_interval)

        window.retention_period = QSpinBox()
        window.retention_period.setRange(1, 365)
        window.retention_period.setSuffix(" days")
        window.retention_period.setValue(window.settings.retention_days)
        form.addRow("History retention", window.retention_period)

        window.process_history_interval = QSpinBox()
        window.process_history_interval.setRange(1, 3600)
        window.process_history_interval.setSuffix(" seconds")
        window.process_history_interval.setValue(window.settings.process_history_seconds)
        form.addRow("Process history interval", window.process_history_interval)

        window.game_process_names = QLineEdit(window.settings.game_process_names)
        window.game_process_names.setPlaceholderText("e.g. game.exe, another-game.exe")
        form.addRow("Game process names", window.game_process_names)

        window.network_timeout = QDoubleSpinBox()
        window.network_timeout.setRange(0.5, 30)
        window.network_timeout.setDecimals(1)
        window.network_timeout.setSingleStep(0.5)
        window.network_timeout.setSuffix(" seconds")
        window.network_timeout.setValue(window.settings.network_timeout_seconds)
        form.addRow("Network timeout", window.network_timeout)

        window.alerts_enabled = QCheckBox("Show desktop alerts for new resource or network issues")
        window.alerts_enabled.setChecked(window.settings.alerts_enabled)
        form.addRow("Notifications", window.alerts_enabled)

        window.keep_in_tray = QCheckBox("Keep Diagnosys recording when I close the window")
        window.keep_in_tray.setChecked(window.settings.keep_in_tray)
        form.addRow("Background capture", window.keep_in_tray)

        card.content.addLayout(form)
        save = QPushButton("Save settings", objectName="PrimaryButton")
        save.clicked.connect(window.save_settings)
        card.content.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(card)

        note = QLabel("Ping target, DNS name/server, and HTTP endpoint are configured on the Network page.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

