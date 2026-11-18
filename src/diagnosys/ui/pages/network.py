"""Network page construction."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton
from diagnosys.ui.components import MetricCard, SummaryCard


def build(window) -> None:
        _, layout = window._page(
            "Network health",
            "Compare ping, DNS, and HTTP from this device, then inspect the route and local Wi-Fi link. "
            "All checks are read-only and run only when you start them.",
        )
        controls = QHBoxLayout()
        window.target = QLineEdit(window.settings.ping_target)
        window.target.setPlaceholderText("Ping host or IP address")
        window.target.setClearButtonEnabled(True)
        window.network_check_button = QPushButton("Run network check", objectName="PrimaryButton")
        window.network_check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        window.network_check_button.clicked.connect(window.network_check)
        controls.addWidget(window.target, 1)
        controls.addWidget(window.network_check_button)
        layout.addLayout(controls)

        resolver_row = QHBoxLayout()
        window.dns_target = QLineEdit(window.settings.dns_target)
        window.dns_target.setPlaceholderText("DNS name to resolve")
        window.dns_server = QLineEdit(window.settings.dns_server)
        window.dns_server.setPlaceholderText("System resolver or DNS server IP")
        resolver_row.addWidget(QLabel("DNS name"))
        resolver_row.addWidget(window.dns_target, 1)
        resolver_row.addWidget(QLabel("Resolver"))
        resolver_row.addWidget(window.dns_server, 1)
        layout.addLayout(resolver_row)

        http_row = QHBoxLayout()
        window.http_target = QLineEdit(window.settings.http_target)
        window.http_target.setPlaceholderText("HTTP or HTTPS test URL")
        http_row.addWidget(QLabel("HTTP endpoint"))
        http_row.addWidget(window.http_target, 1)
        window.route_check_button = QPushButton("Inspect route")
        window.route_check_button.clicked.connect(window.inspect_network_path)
        http_row.addWidget(window.route_check_button)
        layout.addLayout(http_row)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        window.network_latency_card = SummaryCard("Median latency", "—", "Run a check to measure")
        window.packet_loss_card = SummaryCard("Packet loss", "—", "From the latest ping test")
        window.jitter_card = SummaryCard("Jitter", "—", "Variation between replies")
        for card in (window.network_latency_card, window.packet_loss_card, window.jitter_card):
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        results = MetricCard("Connectivity results")
        results.add_badge("LATEST CHECK", "PillGood")
        window.network_output = QPlainTextEdit()
        window.network_output.setReadOnly(True)
        window.network_output.setMinimumHeight(220)
        window.network_output.setMaximumHeight(320)
        window.network_output.setPlaceholderText("Run a network check to see ping, packet loss, DNS, and HTTP results.")
        results.content.addWidget(window.network_output)
        layout.addWidget(results)

        route_card = MetricCard("Gateway, route & Wi-Fi")
        window.route_output = QPlainTextEdit()
        window.route_output.setReadOnly(True)
        window.route_output.setMinimumHeight(160)
        window.route_output.setPlaceholderText("Inspect the network path to see the default gateway, route hops, and Wi-Fi link details.")
        route_card.content.addWidget(window.route_output)
        layout.addWidget(route_card)
        layout.addStretch(1)

