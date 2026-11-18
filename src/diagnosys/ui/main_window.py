from __future__ import annotations

import platform
import html
import json
import statistics
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QPoint, QRectF, QSize, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QLayout,
    QMainWindow,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QStyle,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from diagnosys.collectors.network.dns import DNSCollector
from diagnosys.collectors.network.http import HTTPCollector
from diagnosys.collectors.network.investigation import NetworkInvestigator
from diagnosys.collectors.network.ping import PingCollector
from diagnosys.collectors.network.rates import NetworkRateCollector
from diagnosys.collectors.system.cpu import CPUCollector
from diagnosys.collectors.system.disk import DiskCollector
from diagnosys.collectors.system.events import recent_system_events
from diagnosys.collectors.system.gpu import GPUCollector, GPUMetrics
from diagnosys.collectors.system.memory import MemoryCollector
from diagnosys.collectors.system.process import ProcessCollector
from diagnosys.collectors.system.uptime import UptimeCollector
from diagnosys.config.settings import Settings
from diagnosys.core.capabilities import runtime_info
from diagnosys.diagnostics.engine import DiagnosticEngine
from diagnosys.diagnostics.investigation import InvestigationEngine, SYMPTOMS
from diagnosys.diagnostics.rules import AnomalyDetector
from diagnosys.models.diagnostics import DiagnosisResult
from diagnosys.models.incidents import Incident
from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.reports.generator import ReportGenerator
from diagnosys.storage.database import get_connection, init_db, prune_db
from diagnosys.storage.incidents import IncidentRepository
from diagnosys.storage.processes import ProcessRepository
from diagnosys.storage.repositories import AnomalyRepository, MetricRepository

from .components import CircularGauge, MetricCard, ProgressMetric, SummaryCard, TrendChart
from .theme.tokens import TOKENS


class TaskWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, function):
        super().__init__()
        self.function = function

    @Slot()
    def run(self):
        try:
            self.finished.emit(self.function())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class TaskRouter(QObject):
    """Deliver worker results to the GUI thread before running widget callbacks."""

    def __init__(self, window: "MainWindow", key: str, callback, thread: QThread, worker: TaskWorker):
        super().__init__(window)
        self.window = window
        self.key = key
        self.callback = callback
        self.thread = thread
        self.worker = worker

    @Slot(object)
    def complete(self, result) -> None:
        try:
            self.callback(result)
        except Exception as exc:
            self.window._show_error(f"{type(exc).__name__}: {exc}")
        finally:
            self.window._finish_task(self.key)

    @Slot(str)
    def fail(self, error: str) -> None:
        self.window._finish_task(self.key)
        if self.key == "refresh":
            self.window.monitoring_badge.setText("MONITOR ISSUE")
            self.window.monitoring_badge.setObjectName("PillError")
            self.window.monitoring_badge.style().unpolish(self.window.monitoring_badge)
            self.window.monitoring_badge.style().polish(self.window.monitoring_badge)
        self.window._show_error(error)

    @Slot()
    def thread_finished(self) -> None:
        self.window._release_thread(self.thread)
        self.window._release_worker(self.worker)
        self.deleteLater()


class MainWindow(QMainWindow):
    """Local diagnostics UI; collection, persistence, and diagnosis use existing services."""

    def __init__(self, refresh_seconds: int | None = None):
        super().__init__()
        self.setWindowTitle("Diagnosys · PC investigations")
        self.setMinimumSize(980, 680)
        self.resize(1320, 880)
        self.settings = Settings.from_env()
        self.refresh_ms = max(1, refresh_seconds or self.settings.refresh_seconds) * 1000
        self.history = {key: deque(maxlen=60) for key in ("CPU", "Memory", "Disk")}
        self._threads: list[QThread] = []
        self._workers: list[TaskWorker] = []
        self._active_tasks: set[str] = set()
        self._snapshot_count = 0
        self._last_prune_at = datetime.now(timezone.utc)
        self._last_process_persist_at = datetime.min.replace(tzinfo=timezone.utc)
        self._last_baseline_refresh = datetime.min.replace(tzinfo=timezone.utc)
        self._alert_cooldowns: dict[str, datetime] = {}
        self._selected_symptom = "other"
        self._active_investigation = None
        self._latest_sensor_availability: dict[str, str] = {}
        self._explicit_quit = False

        self.cpu = CPUCollector()
        self.memory = MemoryCollector()
        self.disk = DiskCollector()
        self.gpu = GPUCollector()
        self.uptime = UptimeCollector()
        self.network_rates = NetworkRateCollector()
        self.processes = ProcessCollector(top_n=6)

        self.db = get_connection()
        init_db(self.db)
        prune_db(self.db, self.settings.retention_days)
        self.metric_repo = MetricRepository(self.db)
        self.anomaly_repo = AnomalyRepository(self.db)
        self.process_repo = ProcessRepository(self.db)
        self.incident_repo = IncidentRepository(self.db)
        self._active_investigation = self.incident_repo.active_investigation()
        if self._active_investigation:
            resumed_marker = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": "capture resumed",
                "text": "Diagnosys reopened while this investigation was active; there may be a gap while the app was closed.",
            }
            self.incident_repo.add_marker(self._active_investigation.id, resumed_marker)
            self._active_investigation.evidence.setdefault("markers", []).append(resumed_marker)
        previous_incidents = self.incident_repo.query(limit=1)
        self._last_incident = previous_incidents[0] if previous_incidents else None
        if self._last_incident and self._last_incident.evidence.get("verification_started_at") and not self._last_incident.evidence.get("verification"):
            note = self._last_incident.evidence.get("verification_note", "")
            restarted_at = self.incident_repo.begin_verification(self._last_incident.id, note)
            self._last_incident.evidence["verification_started_at"] = restarted_at.isoformat()
            self._last_incident.evidence.pop("verification", None)
            self._last_incident.evidence.setdefault("markers", []).append({
                "timestamp": restarted_at.isoformat(),
                "kind": "after-change check resumed",
                "text": "A new one-minute measurement window began after Diagnosys reopened.",
            })
        self.detector = self._make_detector()
        self.pages = QStackedWidget()
        self._build()
        self._setup_tray()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(self.refresh_ms)
        self.refresh()

    def _build(self) -> None:
        shell = QWidget(objectName="AppShell")
        root = QHBoxLayout(shell)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        sidebar = QFrame(objectName="Sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(15, 20, 15, 16)
        side.setSpacing(8)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        mark = QLabel("D")
        mark.setObjectName("BrandMark")
        brand = QLabel("Diagnosys")
        brand.setObjectName("Brand")
        brand_row.addWidget(mark)
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        side.addLayout(brand_row)
        tagline = QLabel("Find what changed. Check what helped.")
        tagline.setObjectName("Muted")
        side.addWidget(tagline)
        side.addSpacing(22)

        self.nav_buttons: list[QPushButton] = []
        self.nav_icons = ("overview", "network", "diagnosis", "history", "settings", "settings")
        nav = (
            ("Home", 0),
            ("Network", 1),
            ("Investigate", 2),
            ("History & reports", 3),
            ("Capabilities", 4),
            ("Settings", 5),
        )
        for text, index in nav:
            button = QPushButton(text, objectName="NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(42)
            button.setIconSize(QSize(18, 18))
            button.setIcon(self._nav_icon(self.nav_icons[index], TOKENS.accent if index == 0 else TOKENS.secondary))
            button.clicked.connect(lambda checked=False, i=index: self._navigate(i))
            side.addWidget(button)
            button.setChecked(index == 0)
            self.nav_buttons.append(button)

        side.addStretch(1)
        privacy = QFrame(objectName="InsetPanel")
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(12, 12, 12, 12)
        privacy_layout.setSpacing(5)
        local = QLabel("LOCAL MONITORING")
        local.setObjectName("AccentText")
        local.setStyleSheet("font-size: 10px;")
        privacy_layout.addWidget(local)
        privacy_text = QLabel("Your measurements stay on this device.")
        privacy_text.setWordWrap(True)
        privacy_layout.addWidget(privacy_text)
        side.addWidget(privacy)
        root.addWidget(sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(12)
        topbar = QHBoxLayout()
        self.section_label = QLabel("SYSTEM OVERVIEW")
        self.section_label.setObjectName("TinyLabel")
        self.monitoring_badge = QLabel("STARTING")
        self.monitoring_badge.setObjectName("PillNeutral")
        self.updated_label = QLabel("Starting monitor…")
        self.updated_label.setObjectName("Muted")
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)
        topbar.addWidget(self.section_label)
        topbar.addStretch(1)
        topbar.addWidget(self.monitoring_badge)
        topbar.addSpacing(8)
        topbar.addWidget(self.updated_label)
        topbar.addSpacing(8)
        topbar.addWidget(self.refresh_button)
        content.addLayout(topbar)

        root.addLayout(content, 1)
        content.addWidget(self.pages, 1)
        self.setCentralWidget(shell)

        self._build_overview()
        self._build_network()
        self._build_diagnosis()
        self._build_history()
        self._build_capabilities()
        self._build_settings()

    def _navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        labels = ("HOME", "NETWORK HEALTH", "INVESTIGATE", "HISTORY & REPORTS", "CAPABILITIES", "SETTINGS")
        self.section_label.setText(labels[index])
        for current, button in enumerate(self.nav_buttons):
            selected = current == index
            button.setChecked(selected)
            button.setIcon(self._nav_icon(self.nav_icons[current], TOKENS.accent if selected else TOKENS.secondary))

    @staticmethod
    def _nav_icon(name: str, color: str) -> QIcon:
        """Draw a compact matching set of 18 px outline icons without dependencies."""
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

        if name == "overview":
            for x, y in ((3, 3), (14, 3), (3, 14), (14, 14)):
                painter.drawRoundedRect(QRectF(x, y, 7, 7), 1.5, 1.5)
        elif name == "network":
            painter.drawEllipse(QRectF(3, 3, 18, 18))
            painter.drawEllipse(QRectF(8, 3, 8, 18))
            painter.drawLine(QPoint(4, 9), QPoint(20, 9))
            painter.drawLine(QPoint(4, 15), QPoint(20, 15))
        elif name == "diagnosis":
            painter.drawEllipse(QRectF(3, 3, 18, 18))
            path = QPainterPath(QPoint(5, 12))
            for point in ((8, 12), (10, 8), (13, 16), (15, 11), (19, 11)):
                path.lineTo(*point)
            painter.drawPath(path)
        elif name == "history":
            painter.drawEllipse(QRectF(3, 3, 18, 18))
            painter.drawLine(QPoint(12, 6), QPoint(12, 12))
            painter.drawLine(QPoint(12, 12), QPoint(16, 14))
        else:
            painter.drawEllipse(QRectF(7, 7, 10, 10))
            painter.drawEllipse(QRectF(10, 10, 4, 4))
            for start, end in ((QPoint(12, 2), QPoint(12, 6)), (QPoint(12, 18), QPoint(12, 22)), (QPoint(2, 12), QPoint(6, 12)), (QPoint(18, 12), QPoint(22, 12)), (QPoint(5, 5), QPoint(8, 8)), (QPoint(16, 16), QPoint(19, 19)), (QPoint(5, 19), QPoint(8, 16)), (QPoint(16, 8), QPoint(19, 5))):
                painter.drawLine(start, end)

        painter.end()
        return QIcon(pixmap)

    def _page(self, title: str, subtitle: str) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")
        scroll.viewport().setAutoFillBackground(False)
        page = QWidget()
        page.setObjectName("DashboardPage")
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(3, 8, 8, 18)
        layout.setSpacing(15)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("Subtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)
        return scroll, layout

    @staticmethod
    def _pair(title: str, value: str = "—") -> tuple[QWidget, QLabel]:
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        name = QLabel(title)
        name.setObjectName("TinyLabel")
        result = QLabel(value)
        result.setObjectName("SummaryValue")
        layout.addWidget(name)
        layout.addWidget(result)
        return row, result

    @staticmethod
    def _muted_label(text: str = "") -> QLabel:
        label = QLabel(text)
        label.setObjectName("MetricDetail")
        label.setWordWrap(True)
        return label

    def _build_overview(self) -> None:
        _, layout = self._page("Your PC, at a glance", "Start with the problem you noticed. Diagnosys will collect evidence while it happens.")

        hero = MetricCard("What are you trying to fix?")
        hero_text = QLabel("Choose a problem to start a focused investigation. Your measurements stay on this device.")
        hero_text.setObjectName("MetricDetail")
        hero_text.setWordWrap(True)
        hero.content.addWidget(hero_text)
        choices = QGridLayout()
        choices.setHorizontalSpacing(8)
        choices.setVerticalSpacing(8)
        for index, symptom in enumerate(("slow_pc", "game_stutter", "internet", "app_crash", "overheating", "other")):
            button = QPushButton(SYMPTOMS[symptom]["title"])
            button.setObjectName("SymptomChoice")
            button.setMinimumHeight(42)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleDescription(SYMPTOMS[symptom]["description"])
            button.clicked.connect(lambda checked=False, item=symptom: self._open_investigation(item))
            choices.addWidget(button, index // 3, index % 3)
        hero.content.addLayout(choices)
        self.active_capture_label = QLabel("No active investigation")
        self.active_capture_label.setObjectName("Muted")
        hero.content.addWidget(self.active_capture_label)
        layout.addWidget(hero)

        summaries = QHBoxLayout()
        summaries.setSpacing(12)
        self.host_summary = SummaryCard("Device", "—", "Hostname")
        self.uptime_summary = SummaryCard("Uptime", "—", "Since last boot")
        self.os_summary = SummaryCard("Operating system", "—", "Platform details")
        for card in (self.host_summary, self.uptime_summary, self.os_summary):
            summaries.addWidget(card, 1)
        layout.addLayout(summaries)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)

        self.cpu_card = MetricCard("Processor")
        cpu_row = QHBoxLayout()
        cpu_row.setSpacing(14)
        self.cpu_gauge = CircularGauge("CPU LOAD")
        cpu_row.addWidget(self.cpu_gauge, 0, Qt.AlignmentFlag.AlignVCenter)
        cpu_info = QVBoxLayout()
        cpu_info.setSpacing(12)
        cpu_info.addStretch(1)
        pair, self.cpu_frequency = self._pair("CURRENT FREQUENCY")
        cpu_info.addWidget(pair)
        pair, self.cpu_temperature = self._pair("TEMPERATURE")
        cpu_info.addWidget(pair)
        self.cpu_cores = self._muted_label("Logical processors —")
        cpu_info.addWidget(self.cpu_cores)
        cpu_info.addStretch(1)
        cpu_row.addLayout(cpu_info, 1)
        self.cpu_card.content.addLayout(cpu_row, 1)
        metrics.addWidget(self.cpu_card, 0, 0)

        self.memory_card = MetricCard("Memory")
        self.memory_value = QLabel("— / —")
        self.memory_value.setObjectName("MetricValue")
        self.memory_card.content.addWidget(self.memory_value)
        self.memory_progress = ProgressMetric("In use")
        self.memory_card.content.addWidget(self.memory_progress)
        self.memory_available = self._muted_label("Available memory —")
        self.memory_card.content.addStretch(1)
        self.memory_card.content.addWidget(self.memory_available)
        metrics.addWidget(self.memory_card, 0, 1)

        self.disk_card = MetricCard("Storage & disk activity")
        self.disk_card.add_badge("SYSTEM VOLUME", "PillGood")
        self.disk_value = QLabel("— / —")
        self.disk_value.setObjectName("MetricValue")
        self.disk_card.content.addWidget(self.disk_value)
        self.disk_progress = ProgressMetric("Space used")
        self.disk_card.content.addWidget(self.disk_progress)
        io_row = QHBoxLayout()
        io_row.setSpacing(16)
        pair, self.disk_read = self._pair("READ")
        io_row.addWidget(pair)
        pair, self.disk_write = self._pair("WRITE")
        io_row.addWidget(pair)
        self.disk_card.content.addLayout(io_row)
        metrics.addWidget(self.disk_card, 1, 0)

        self.network_card = MetricCard("Network")
        self.network_card.add_badge("INTERFACE ACTIVITY", "PillGood")
        rates = QHBoxLayout()
        rates.setSpacing(12)
        down = QVBoxLayout()
        down.setSpacing(3)
        down.addWidget(QLabel("DOWNLOAD", objectName="TinyLabel"))
        self.download_value = QLabel("—")
        self.download_value.setObjectName("MetricValue")
        down.addWidget(self.download_value)
        rates.addLayout(down, 1)
        up = QVBoxLayout()
        up.setSpacing(3)
        up.addWidget(QLabel("UPLOAD", objectName="TinyLabel"))
        self.upload_value = QLabel("—")
        self.upload_value.setObjectName("MetricValue")
        up.addWidget(self.upload_value)
        rates.addLayout(up, 1)
        self.network_card.content.addLayout(rates)
        network_bottom = QHBoxLayout()
        self.ping_summary = self._muted_label("Latency — · Packet loss —")
        network_bottom.addWidget(self.ping_summary, 1)
        check_network = QPushButton("Test connection")
        check_network.setCursor(Qt.CursorShape.PointingHandCursor)
        check_network.clicked.connect(self.network_check)
        network_bottom.addWidget(check_network)
        self.network_card.content.addLayout(network_bottom)
        metrics.addWidget(self.network_card, 1, 1)

        self.gpu_card = MetricCard("Graphics processor")
        self.gpu_badge = self.gpu_card.add_badge("UNAVAILABLE", "PillNeutral")
        self.gpu_name = self._muted_label("GPU telemetry is not available on this device.")
        self.gpu_card.content.addWidget(self.gpu_name)
        self.gpu_progress = ProgressMetric("Utilization")
        self.gpu_card.content.addWidget(self.gpu_progress)
        gpu_detail = QHBoxLayout()
        pair, self.gpu_memory = self._pair("VIDEO MEMORY")
        gpu_detail.addWidget(pair)
        pair, self.gpu_temperature = self._pair("TEMPERATURE")
        gpu_detail.addWidget(pair)
        self.gpu_card.content.addLayout(gpu_detail)
        metrics.addWidget(self.gpu_card, 2, 0)

        self.insight_card = MetricCard("Diagnostic insights")
        self.insight_card.add_badge("LOCAL · RULE BASED", "PillGood")
        self.insight_title = QLabel("Gathering recent evidence")
        self.insight_title.setObjectName("SummaryValue")
        self.insight_body = self._muted_label("Recommendations are based on measurements collected by Diagnosys.")
        self.insight_evidence = self._muted_label("")
        insight_actions = QHBoxLayout()
        view_diagnosis = QPushButton("View evidence", objectName="PrimaryButton")
        view_diagnosis.setCursor(Qt.CursorShape.PointingHandCursor)
        view_diagnosis.clicked.connect(lambda: self._navigate(2))
        insight_actions.addStretch(1)
        insight_actions.addWidget(view_diagnosis)
        self.insight_card.content.addWidget(self.insight_title)
        self.insight_card.content.addWidget(self.insight_body)
        self.insight_card.content.addWidget(self.insight_evidence)
        self.insight_card.content.addStretch(1)
        self.insight_card.content.addLayout(insight_actions)
        metrics.addWidget(self.insight_card, 2, 1)
        metrics.setColumnStretch(0, 1)
        metrics.setColumnStretch(1, 1)
        layout.addLayout(metrics)

        chart_card = MetricCard("Resource history")
        chart_card.add_badge("LAST 60 SAMPLES", "PillGood")
        self.chart = TrendChart()
        chart_card.content.addWidget(self.chart)
        layout.addWidget(chart_card)

        process_card = MetricCard("Top processes")
        process_card.add_badge("LIVE SNAPSHOT", "PillGood")
        self.process_table = QTableWidget(6, 4)
        self.process_table.setHorizontalHeaderLabels(("Highest CPU", "CPU", "Highest memory", "Memory"))
        self.process_table.verticalHeader().setVisible(False)
        self.process_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.process_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.process_table.setAlternatingRowColors(True)
        self.process_table.setShowGrid(False)
        self.process_table.setMinimumHeight(230)
        self.process_table.setMaximumHeight(260)
        header = self.process_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        process_card.content.addWidget(self.process_table)
        layout.addWidget(process_card)
        layout.addStretch(1)

    def _build_network(self) -> None:
        _, layout = self._page(
            "Network health",
            "Compare ping, DNS, and HTTP from this device, then inspect the route and local Wi-Fi link. "
            "All checks are read-only and run only when you start them.",
        )
        controls = QHBoxLayout()
        self.target = QLineEdit(self.settings.ping_target)
        self.target.setPlaceholderText("Ping host or IP address")
        self.target.setClearButtonEnabled(True)
        self.network_check_button = QPushButton("Run network check", objectName="PrimaryButton")
        self.network_check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.network_check_button.clicked.connect(self.network_check)
        controls.addWidget(self.target, 1)
        controls.addWidget(self.network_check_button)
        layout.addLayout(controls)

        resolver_row = QHBoxLayout()
        self.dns_target = QLineEdit(self.settings.dns_target)
        self.dns_target.setPlaceholderText("DNS name to resolve")
        self.dns_server = QLineEdit(self.settings.dns_server)
        self.dns_server.setPlaceholderText("System resolver or DNS server IP")
        resolver_row.addWidget(QLabel("DNS name"))
        resolver_row.addWidget(self.dns_target, 1)
        resolver_row.addWidget(QLabel("Resolver"))
        resolver_row.addWidget(self.dns_server, 1)
        layout.addLayout(resolver_row)

        http_row = QHBoxLayout()
        self.http_target = QLineEdit(self.settings.http_target)
        self.http_target.setPlaceholderText("HTTP or HTTPS test URL")
        http_row.addWidget(QLabel("HTTP endpoint"))
        http_row.addWidget(self.http_target, 1)
        self.route_check_button = QPushButton("Inspect route")
        self.route_check_button.clicked.connect(self.inspect_network_path)
        http_row.addWidget(self.route_check_button)
        layout.addLayout(http_row)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.network_latency_card = SummaryCard("Median latency", "—", "Run a check to measure")
        self.packet_loss_card = SummaryCard("Packet loss", "—", "From the latest ping test")
        self.jitter_card = SummaryCard("Jitter", "—", "Variation between replies")
        for card in (self.network_latency_card, self.packet_loss_card, self.jitter_card):
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        results = MetricCard("Connectivity results")
        results.add_badge("LATEST CHECK", "PillGood")
        self.network_output = QPlainTextEdit()
        self.network_output.setReadOnly(True)
        self.network_output.setMinimumHeight(220)
        self.network_output.setMaximumHeight(320)
        self.network_output.setPlaceholderText("Run a network check to see ping, packet loss, DNS, and HTTP results.")
        results.content.addWidget(self.network_output)
        layout.addWidget(results)

        route_card = MetricCard("Gateway, route & Wi-Fi")
        self.route_output = QPlainTextEdit()
        self.route_output.setReadOnly(True)
        self.route_output.setMinimumHeight(160)
        self.route_output.setPlaceholderText("Inspect the network path to see the default gateway, route hops, and Wi-Fi link details.")
        route_card.content.addWidget(self.route_output)
        layout.addWidget(route_card)
        layout.addStretch(1)

    def _build_diagnosis(self) -> None:
        _, layout = self._page(
            "Investigate a problem",
            "Capture what happened, review the evidence, then record whether the problem is fixed.",
        )
        symptom_card = MetricCard("1 · Choose the problem")
        symptom_grid = QGridLayout()
        symptom_grid.setHorizontalSpacing(8)
        symptom_grid.setVerticalSpacing(8)
        self.symptom_buttons: dict[str, QPushButton] = {}
        for index, symptom in enumerate(("slow_pc", "game_stutter", "internet", "app_crash", "overheating", "other")):
            button = QPushButton(SYMPTOMS[symptom]["title"])
            button.setObjectName("SymptomChoice")
            button.setCheckable(True)
            button.setMinimumHeight(44)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleDescription(SYMPTOMS[symptom]["description"])
            button.clicked.connect(lambda checked=False, item=symptom: self._select_symptom(item))
            self.symptom_buttons[symptom] = button
            symptom_grid.addWidget(button, index // 3, index % 3)
        symptom_card.content.addLayout(symptom_grid)
        self.symptom_description = QLabel(SYMPTOMS["other"]["description"])
        self.symptom_description.setObjectName("Muted")
        self.symptom_description.setWordWrap(True)
        symptom_card.content.addWidget(self.symptom_description)
        layout.addWidget(symptom_card)

        capture_card = MetricCard("2 · Capture the problem")
        capture_actions = QHBoxLayout()
        self.start_investigation_button = QPushButton("Start capturing", objectName="PrimaryButton")
        self.start_investigation_button.clicked.connect(self.start_investigation)
        self.stop_investigation_button = QPushButton("Stop & analyze")
        self.stop_investigation_button.clicked.connect(self.stop_investigation)
        self.stop_investigation_button.setEnabled(False)
        self.add_note_button = QPushButton("Add a note")
        self.add_note_button.clicked.connect(self.add_investigation_note)
        capture_actions.addWidget(self.start_investigation_button)
        capture_actions.addWidget(self.stop_investigation_button)
        capture_actions.addWidget(self.add_note_button)
        capture_actions.addStretch(1)
        capture_card.content.addLayout(capture_actions)
        network_actions = QHBoxLayout()
        self.investigation_network_hint = QLabel("For connection issues, run these focused checks while the capture is active.")
        self.investigation_network_hint.setObjectName("Muted")
        self.investigation_network_hint.setWordWrap(True)
        network_actions.addWidget(self.investigation_network_hint, 1)
        self.run_focused_check_button = QPushButton("Run connection check")
        self.run_focused_check_button.clicked.connect(self.network_check)
        self.inspect_route_button = QPushButton("Inspect route")
        self.inspect_route_button.clicked.connect(self.inspect_network_path)
        network_actions.addWidget(self.run_focused_check_button)
        network_actions.addWidget(self.inspect_route_button)
        capture_card.content.addLayout(network_actions)
        self.investigation_status = QLabel("Choose a problem, then start a capture. Diagnosys will keep collecting evidence in the background.")
        self.investigation_status.setObjectName("MetricDetail")
        self.investigation_status.setWordWrap(True)
        capture_card.content.addWidget(self.investigation_status)
        layout.addWidget(capture_card)

        result_card = MetricCard("3 · Review the findings")
        result_card.add_badge("LOCAL EVIDENCE", "PillGood")
        self.investigation_result_title = QLabel("Your findings will appear here")
        self.investigation_result_title.setObjectName("SummaryValue")
        self.investigation_result_summary = QLabel("Stop the capture after the problem occurs to compare system, process, network, and Windows event evidence.")
        self.investigation_result_summary.setObjectName("MetricDetail")
        self.investigation_result_summary.setWordWrap(True)
        self.investigation_chart = TrendChart()
        self.investigation_chart.setMinimumHeight(190)
        self.investigation_result = QTextBrowser()
        self.investigation_result.setOpenExternalLinks(False)
        self.investigation_result.setMinimumHeight(300)
        result_card.content.addWidget(self.investigation_result_title)
        result_card.content.addWidget(self.investigation_result_summary)
        result_card.content.addWidget(self.investigation_chart)
        result_card.content.addWidget(self.investigation_result, 1)
        resolution_actions = QHBoxLayout()
        self.resolve_button = QPushButton("Mark as fixed")
        self.resolve_button.clicked.connect(lambda: self.set_investigation_resolution("resolved"))
        self.unresolved_button = QPushButton("Still happening")
        self.unresolved_button.clicked.connect(lambda: self.set_investigation_resolution("still_happening"))
        self.resolution_status = QLabel("")
        self.resolution_status.setObjectName("Muted")
        self.diagnose_button = QPushButton("Analyze last hour")
        self.diagnose_button.clicked.connect(self.diagnose)
        resolution_actions.addWidget(self.diagnose_button)
        resolution_actions.addWidget(self.resolve_button)
        resolution_actions.addWidget(self.unresolved_button)
        resolution_actions.addWidget(self.resolution_status, 1)
        result_card.content.addLayout(resolution_actions)
        verification_row = QHBoxLayout()
        self.resolution_note_input = QLineEdit()
        self.resolution_note_input.setPlaceholderText("What did you change or try? (optional)")
        self.start_verification_button = QPushButton("Start 1-minute check")
        self.start_verification_button.clicked.connect(self.start_verification)
        self.compare_verification_button = QPushButton("Compare after 1 minute")
        self.compare_verification_button.clicked.connect(self.compare_verification)
        self.compare_verification_button.setEnabled(False)
        verification_row.addWidget(self.resolution_note_input, 1)
        verification_row.addWidget(self.start_verification_button)
        verification_row.addWidget(self.compare_verification_button)
        result_card.content.addLayout(verification_row)
        self.verification_status = QLabel("After trying a change, measure another minute and compare the readings with this capture.")
        self.verification_status.setObjectName("Muted")
        self.verification_status.setWordWrap(True)
        result_card.content.addWidget(self.verification_status)
        ask_row = QHBoxLayout()
        self.investigation_question = QLineEdit()
        self.investigation_question.setPlaceholderText("Ask about this evidence: what changed, or which app was busiest?")
        self.investigation_question.returnPressed.connect(self.ask_investigation)
        self.ask_investigation_button = QPushButton("Ask this capture")
        self.ask_investigation_button.clicked.connect(self.ask_investigation)
        ask_row.addWidget(self.investigation_question, 1)
        ask_row.addWidget(self.ask_investigation_button)
        result_card.content.addLayout(ask_row)
        self.investigation_answer = QLabel("Answers are based only on the selected local capture.")
        self.investigation_answer.setObjectName("Muted")
        self.investigation_answer.setWordWrap(True)
        result_card.content.addWidget(self.investigation_answer)
        layout.addWidget(result_card)
        layout.addStretch(1)
        self.diagnosis_output = self.investigation_result
        self.capture_elapsed_timer = QTimer(self)
        self.capture_elapsed_timer.timeout.connect(self._update_capture_elapsed)
        self.verification_timer = QTimer(self)
        self.verification_timer.timeout.connect(self._update_verification_status)
        self._sync_investigation_controls()

    def _build_history(self) -> None:
        _, layout = self._page(
            "History & reports",
            "Review saved measurements and incidents, preview a diagnostic report, or export it for support.",
        )
        actions = QHBoxLayout()
        history = QPushButton("Refresh history")
        history.clicked.connect(self.show_history)
        self.history_window = QComboBox()
        for label, seconds in (("Last hour", 3600), ("Last 24 hours", 86400), ("Last 7 days", 604800)):
            self.history_window.addItem(label, seconds)
        self.history_window.currentIndexChanged.connect(lambda _index: self.show_history())
        self.incident_selector = QComboBox()
        self.incident_selector.setMinimumWidth(190)
        self.incident_selector.setPlaceholderText("Select incident")
        self.incident_selector.currentIndexChanged.connect(self._incident_selection_changed)
        self.view_incident_button = QPushButton("View evidence")
        self.view_incident_button.clicked.connect(self.view_incident_evidence)
        self.report_button = QPushButton("Preview report", objectName="PrimaryButton")
        self.report_button.clicked.connect(self.generate_report)
        self.export_report_button = QPushButton("Export report…")
        self.export_report_button.clicked.connect(self.export_report)
        self.capture_button = QPushButton("Capture incident")
        self.capture_button.clicked.connect(self.capture_incident)
        actions.addWidget(self.history_window)
        actions.addWidget(self.incident_selector)
        actions.addWidget(self.view_incident_button)
        actions.addWidget(history)
        actions.addWidget(self.report_button)
        actions.addWidget(self.export_report_button)
        actions.addWidget(self.capture_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        incident_actions = QHBoxLayout()
        self.export_incident_button = QPushButton("Export selected incident…")
        self.export_incident_button.clicked.connect(self.export_selected_incident)
        self.export_incident_button.setEnabled(False)
        incident_actions.addWidget(self.export_incident_button)
        incident_actions.addWidget(QLabel("Creates a reviewable, redacted support bundle."), 1)
        layout.addLayout(incident_actions)

        result_card = MetricCard("Recent activity")
        result_card.add_badge("LOCAL DATABASE", "PillGood")
        self.history_output = QPlainTextEdit()
        self.history_output.setReadOnly(True)
        self.history_output.setMinimumHeight(330)
        result_card.content.addWidget(self.history_output)
        layout.addWidget(result_card)
        layout.addStretch(1)

    def _build_capabilities(self) -> None:
        _, layout = self._page("Capabilities", "See which measurements this device and operating system expose.")
        result_card = MetricCard("Runtime support")
        self.capabilities_output = QPlainTextEdit()
        self.capabilities_output.setReadOnly(True)
        self.capabilities_output.setMinimumHeight(270)
        result_card.content.addWidget(self.capabilities_output)
        layout.addWidget(result_card)
        refresh = QPushButton("Refresh capabilities")
        refresh.clicked.connect(self.show_capabilities)
        layout.addWidget(refresh, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        self.show_capabilities()

    def _build_settings(self) -> None:
        _, layout = self._page(
            "Monitoring settings",
            "Tune local sampling, data retention, network probes, and alert behavior. Preferences stay on this device.",
        )
        card = MetricCard("Monitoring and alerts")
        form = QFormLayout()

        self.refresh_interval = QSpinBox()
        self.refresh_interval.setRange(1, 300)
        self.refresh_interval.setSuffix(" seconds")
        self.refresh_interval.setValue(self.settings.refresh_seconds)
        form.addRow("Sampling interval", self.refresh_interval)

        self.retention_period = QSpinBox()
        self.retention_period.setRange(1, 365)
        self.retention_period.setSuffix(" days")
        self.retention_period.setValue(self.settings.retention_days)
        form.addRow("History retention", self.retention_period)

        self.process_history_interval = QSpinBox()
        self.process_history_interval.setRange(1, 3600)
        self.process_history_interval.setSuffix(" seconds")
        self.process_history_interval.setValue(self.settings.process_history_seconds)
        form.addRow("Process history interval", self.process_history_interval)

        self.network_timeout = QDoubleSpinBox()
        self.network_timeout.setRange(0.5, 30)
        self.network_timeout.setDecimals(1)
        self.network_timeout.setSingleStep(0.5)
        self.network_timeout.setSuffix(" seconds")
        self.network_timeout.setValue(self.settings.network_timeout_seconds)
        form.addRow("Network timeout", self.network_timeout)

        self.baseline_enabled = QCheckBox("Use this device’s recent history as a personal baseline")
        self.baseline_enabled.setChecked(self.settings.baseline_enabled)
        form.addRow("Adaptive baseline", self.baseline_enabled)

        self.alerts_enabled = QCheckBox("Show desktop alerts for new resource or network issues")
        self.alerts_enabled.setChecked(self.settings.alerts_enabled)
        form.addRow("Notifications", self.alerts_enabled)

        self.keep_in_tray = QCheckBox("Keep Diagnosys recording when I close the window")
        self.keep_in_tray.setChecked(self.settings.keep_in_tray)
        form.addRow("Background capture", self.keep_in_tray)

        card.content.addLayout(form)
        save = QPushButton("Save settings", objectName="PrimaryButton")
        save.clicked.connect(self.save_settings)
        card.content.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(card)

        note = QLabel("Ping target, DNS name/server, and HTTP endpoint are configured on the Network page.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

    def _make_detector(self) -> AnomalyDetector:
        # No universal cutoffs: the detector uses sufficiently populated local baselines.
        baselines = self.metric_repo.get_all_baselines() if self.settings.baseline_enabled else {}
        return AnomalyDetector(baselines=baselines)

    def save_settings(self) -> None:
        try:
            updated = Settings(
                data_dir=self.settings.data_dir,
                refresh_seconds=self.refresh_interval.value(),
                process_history_seconds=self.process_history_interval.value(),
                retention_days=self.retention_period.value(),
                network_timeout_seconds=self.network_timeout.value(),
                ping_target=self.target.text().strip(),
                dns_target=self.dns_target.text().strip(),
                dns_server=self.dns_server.text().strip(),
                http_target=self.http_target.text().strip(),
                alerts_enabled=self.alerts_enabled.isChecked(),
                keep_in_tray=self.keep_in_tray.isChecked(),
                baseline_enabled=self.baseline_enabled.isChecked(),
            )
            updated.save()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Settings were not saved", str(exc))
            return
        self.settings = updated
        self.refresh_ms = updated.refresh_seconds * 1000
        self.refresh_timer.setInterval(self.refresh_ms)
        self.detector = self._make_detector()
        self.statusBar().showMessage("Settings saved on this device.", 5000)

    def _setup_tray(self) -> None:
        self.tray_icon = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.keep_in_tray.setEnabled(False)
            self.keep_in_tray.setToolTip("A system tray is not available on this desktop.")
            return
        self.tray_icon = QSystemTrayIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self)
        self.tray_icon.setToolTip("Diagnosys · local system health")
        menu = QMenu(self)
        open_action = QAction("Open Diagnosys", self)
        open_action.triggered.connect(self.showNormal)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(open_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_activated(self, reason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def quit_application(self) -> None:
        self._explicit_quit = True
        self.close()

    def _notify_anomaly(self, anomaly) -> None:
        if not self.settings.alerts_enabled or self.tray_icon is None:
            return
        now = datetime.now(timezone.utc)
        previous = self._alert_cooldowns.get(anomaly.category)
        if previous and now - previous < timedelta(minutes=10):
            return
        self._alert_cooldowns[anomaly.category] = now
        self.tray_icon.showMessage(
            "Diagnosys detected an unusual reading",
            anomaly.explanation,
            QSystemTrayIcon.MessageIcon.Warning,
            7000,
        )

    def _run_async(self, key: str, function, callback) -> bool:
        if key in self._active_tasks:
            return False
        self._active_tasks.add(key)
        thread = QThread(self)
        worker = TaskWorker(function)
        router = TaskRouter(self, key, callback, thread, worker)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(router.complete)
        worker.failed.connect(router.fail)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(router.thread_finished)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.start()
        self._set_task_controls(key, True)
        return True

    def _finish_task(self, key: str) -> None:
        self._active_tasks.discard(key)
        self._set_task_controls(key, False)

    def _release_thread(self, thread: QThread) -> None:
        if thread in self._threads:
            self._threads.remove(thread)

    def _release_worker(self, worker: TaskWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def _set_task_controls(self, key: str, active: bool) -> None:
        controls = {
            "refresh": (self.refresh_button,),
            "network": (self.network_check_button,),
            "route": (self.route_check_button,),
            "diagnosis": (self.diagnose_button,),
            "report": (self.report_button,),
            "export": (self.export_report_button,),
            "capture": (self.capture_button,),
            "investigation_finish": (self.stop_investigation_button,),
            "incident_export": (self.export_incident_button,),
            "verification_compare": (self.compare_verification_button,),
        }.get(key, ())
        for control in controls:
            control.setEnabled(not active)
        if key == "network":
            self.network_check_button.setText("Checking…" if active else "Run network check")
            self.run_focused_check_button.setText("Checking…" if active else "Run connection check")
            self.run_focused_check_button.setEnabled(not active and self._active_investigation is not None)
        elif key == "route":
            self.route_check_button.setText("Inspecting…" if active else "Inspect route")
            self.inspect_route_button.setText("Inspecting…" if active else "Inspect route")
            self.inspect_route_button.setEnabled(not active and self._active_investigation is not None)
        elif key == "diagnosis":
            self.diagnose_button.setText("Analyzing…" if active else "Analyze recent evidence")
        elif key == "report":
            self.report_button.setText("Building preview…" if active else "Preview report")
        elif key == "export":
            self.export_report_button.setText("Exporting…" if active else "Export report…")
        elif key == "capture":
            self.capture_button.setText("Capturing…" if active else "Capture incident")
        elif key == "investigation_finish":
            self.stop_investigation_button.setText("Analyzing…" if active else "Stop & analyze")
            if active:
                self.stop_investigation_button.setEnabled(False)
            else:
                self._sync_investigation_controls()
        elif key == "verification_compare":
            if active:
                self.compare_verification_button.setEnabled(False)
            else:
                self._sync_verification_controls()

    def _show_error(self, error: str) -> None:
        QMessageBox.warning(self, "Diagnosys", error)

    def refresh(self) -> None:
        self._run_async("refresh", self._collect_snapshot, self._apply_snapshot)

    def _collect_snapshot(self):
        cpu = self.cpu.collect()
        memory = self.memory.collect()
        disk = self.disk.collect()
        processes = self.processes.collect()
        gpu = self.gpu.collect()
        network = self.network_rates.collect()
        uptime = self.uptime.collect()
        temperature = self._cpu_temperature()
        return cpu, memory, disk, processes, gpu, network, uptime, temperature

    @staticmethod
    def _cpu_temperature() -> float | None:
        """Return a CPU-labelled thermal reading only when the OS exposes one."""
        sensors = getattr(psutil, "sensors_temperatures", None)
        if sensors is None:
            return None
        try:
            available = sensors(fahrenheit=False)
        except Exception:
            return None
        for name, readings in available.items():
            key = name.casefold()
            if not any(token in key for token in ("cpu", "coretemp", "k10temp", "zenpower", "cpu_thermal")):
                continue
            for reading in readings:
                if reading.current is not None:
                    return float(reading.current)
        return None

    def _apply_snapshot(self, result) -> None:
        cpu, memory, disk, processes, gpu, network, uptime, temperature = result
        timestamp = datetime.now(timezone.utc)
        samples = (
            MetricSample(timestamp, "cpu_percent", cpu.utilization_percent, "%", "system", MetricStatus.OK if cpu.available else MetricStatus.UNAVAILABLE, reason=cpu.reason),
            MetricSample(timestamp, "memory_percent", memory.percent_used, "%", "system", MetricStatus.OK if memory.available else MetricStatus.UNAVAILABLE, reason=memory.reason),
            MetricSample(timestamp, "disk_percent", disk.percent_used, "%", "system", MetricStatus.OK if disk.available else MetricStatus.UNAVAILABLE, reason=disk.reason),
        )
        for sample in samples:
            self._store_sample(sample)
        optional_readings = (
            ("cpu_temperature_c", temperature, "°C", "CPU sensor"),
            ("gpu_percent", gpu.utilization_percent, "%", "GPU 0"),
            ("gpu_temperature_c", gpu.temperature_c, "°C", "GPU 0"),
            ("disk_read_bytes_per_sec", disk.read_bytes_per_sec if disk.available else None, "B/s", "system disk"),
            ("disk_write_bytes_per_sec", disk.write_bytes_per_sec if disk.available else None, "B/s", "system disk"),
            ("network_download_bytes_per_sec", network.download_bytes_per_sec, "B/s", "all interfaces"),
            ("network_upload_bytes_per_sec", network.upload_bytes_per_sec, "B/s", "all interfaces"),
        )
        self._latest_sensor_availability = {
            "cpu_temperature": "available" if temperature is not None else "not exposed by this device",
            "gpu": "available" if gpu.available else (gpu.reason or "not available"),
            "gpu_temperature": "available" if gpu.temperature_c is not None else "not exposed by this device",
        }
        for name, value, unit, entity in optional_readings:
            if value is not None:
                self._store_sample(MetricSample(
                    timestamp, name, value, unit, "system", MetricStatus.OK, entity_id=entity,
                ))
        if timestamp - self._last_process_persist_at >= timedelta(seconds=self.settings.process_history_seconds):
            self.process_repo.save_snapshot(processes)
            self._last_process_persist_at = timestamp

        if timestamp - self._last_prune_at >= timedelta(hours=1):
            prune_db(self.db, self.settings.retention_days)
            self._last_prune_at = timestamp

        if self.settings.baseline_enabled and timestamp - self._last_baseline_refresh >= timedelta(minutes=5):
            self.detector.baselines = self.metric_repo.get_all_baselines(window_seconds=86400)
            self._last_baseline_refresh = timestamp

        self._snapshot_count += 1
        self.cpu_gauge.set_value(cpu.utilization_percent if cpu.available else None)
        self.cpu_frequency.setText(self._frequency(cpu.frequency_mhz) if cpu.available else "Unavailable")
        self.cpu_temperature.setText(f"{temperature:.0f} °C" if temperature is not None else "Unavailable")
        self.cpu_cores.setText(f"{psutil.cpu_count(logical=True) or '—'} logical processors")

        self.memory_value.setText(
            f"{self._gib(memory.used_bytes)} / {self._gib(memory.total_bytes)}"
            if memory.available else "Unavailable"
        )
        self.memory_progress.set_metric(
            memory.percent_used if memory.available else None,
            f"{memory.percent_used:.0f}%" if memory.available else "Unavailable",
            f"{self._gib(memory.used_bytes)} used of {self._gib(memory.total_bytes)}" if memory.available else (memory.reason or "Memory metrics unavailable"),
        )
        self.memory_available.setText(
            f"{self._gib(memory.available_bytes)} available" if memory.available else (memory.reason or "Memory metrics unavailable")
        )

        self.disk_value.setText(
            f"{self._gib(disk.total_bytes - disk.free_bytes)} / {self._gib(disk.total_bytes)}"
            if disk.available else "Unavailable"
        )
        self.disk_progress.set_metric(
            disk.percent_used if disk.available else None,
            f"{disk.percent_used:.0f}%" if disk.available else "Unavailable",
            f"{self._gib(disk.free_bytes)} free" if disk.available else (disk.reason or "Storage metrics unavailable"),
        )
        rates_ready = self._snapshot_count > 1
        self.disk_read.setText(self._rate(disk.read_bytes_per_sec) if disk.available and rates_ready else "Measuring…")
        self.disk_write.setText(self._rate(disk.write_bytes_per_sec) if disk.available and rates_ready else "Measuring…")

        if network.available:
            self.download_value.setText(self._rate(network.download_bytes_per_sec))
            self.upload_value.setText(self._rate(network.upload_bytes_per_sec))
        else:
            self.download_value.setText("Unavailable")
            self.upload_value.setText("Unavailable")
            self.download_value.setToolTip(network.reason or "Network counters unavailable")
            self.upload_value.setToolTip(network.reason or "Network counters unavailable")

        self._apply_gpu(gpu)
        self.host_summary.set_value(platform.node() or "This device", "Hostname")
        self.uptime_summary.set_value(self._duration(uptime), "Since last boot" if uptime > 0 else "Uptime unavailable")
        self.os_summary.set_value(platform.system() or "Unknown", f"{platform.release()} · {platform.machine()}")

        for key, value, available in (
            ("CPU", cpu.utilization_percent, cpu.available),
            ("Memory", memory.percent_used, memory.available),
            ("Disk", disk.percent_used, disk.available),
        ):
            if available:
                self.history[key].append(value)
                self.chart.set_series(key, list(self.history[key]))
        self._update_processes(processes)
        self._update_insight()
        self.monitoring_badge.setText("MONITORING")
        self.monitoring_badge.setObjectName("PillGood")
        self.monitoring_badge.style().unpolish(self.monitoring_badge)
        self.monitoring_badge.style().polish(self.monitoring_badge)
        self.updated_label.setText(f"Updated {datetime.now().astimezone().strftime('%H:%M:%S')}")

    def _apply_gpu(self, gpu: GPUMetrics) -> None:
        self.gpu_badge.setText("AVAILABLE" if gpu.available else "UNAVAILABLE")
        self.gpu_badge.setObjectName("PillGood" if gpu.available else "PillNeutral")
        self.gpu_badge.style().unpolish(self.gpu_badge)
        self.gpu_badge.style().polish(self.gpu_badge)
        self.gpu_name.setText(
            gpu.name if gpu.available and gpu.name else (gpu.reason or "GPU telemetry unavailable")
        )
        self.gpu_progress.set_metric(
            gpu.utilization_percent,
            f"{gpu.utilization_percent:.0f}%" if gpu.utilization_percent is not None else "Unavailable",
            "GPU 0 utilization" if gpu.available else "No supported GPU sensor detected",
        )
        if gpu.memory_used_mib is not None and gpu.memory_total_mib is not None:
            self.gpu_memory.setText(f"{gpu.memory_used_mib / 1024:.1f} / {gpu.memory_total_mib / 1024:.1f} GB")
        else:
            self.gpu_memory.setText("Unavailable")
        self.gpu_temperature.setText(f"{gpu.temperature_c:.0f} °C" if gpu.temperature_c is not None else "Unavailable")
        if not gpu.available:
            self.gpu_name.setToolTip(gpu.reason or "GPU telemetry is not supported")

    def _update_processes(self, processes) -> None:
        self.process_table.clearContents()
        for row in range(6):
            cpu = processes.top_cpu[row] if row < len(processes.top_cpu) else None
            memory = processes.top_memory[row] if row < len(processes.top_memory) else None
            values = (
                cpu.name if cpu else "—",
                f"{cpu.cpu_percent:.1f}%" if cpu else "—",
                memory.name if memory else "—",
                f"{memory.memory_percent:.1f}%" if memory else "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column in (1, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.process_table.setItem(row, column, item)
        self.process_table.setToolTip(
            f"{processes.process_count} active processes" if processes.available else (processes.reason or "Process data unavailable")
        )

    def _update_insight(self) -> None:
        try:
            samples = [
                item for item in self.metric_repo.query(window_seconds=3600)
                if item.status == MetricStatus.OK
            ]
            if len(samples) < 5:
                self.insight_title.setText("Collecting enough evidence")
                self.insight_body.setText("Diagnosys needs a few more readings before it can say whether the recent pattern looks normal.")
                self.insight_evidence.setText(f"{len(samples)} usable reading(s) available so far.")
                return
            anomalies = self.anomaly_repo.query(window_seconds=3600)
            result = DiagnosticEngine().diagnose(anomalies, window_seconds=3600)
            self._render_insight(result)
        except Exception as exc:
            self.insight_title.setText("Insight temporarily unavailable")
            self.insight_body.setText(str(exc))
            self.insight_evidence.clear()

    def _render_insight(self, result: DiagnosisResult) -> None:
        hypothesis = result.primary_hypothesis
        if result.status == "INSUFFICIENT_DATA":
            self.insight_title.setText("Collecting enough evidence")
            self.insight_body.setText("The recent window has too few usable measurements for a health conclusion.")
            self.insight_evidence.setText("Keep monitoring or capture the issue while it is happening.")
            return
        if result.status == "NO_ANOMALY" or not hypothesis:
            self.insight_title.setText("No baseline deviation detected")
            self.insight_body.setText("No monitored metric crossed its learned variation band. This does not prove every component is healthy.")
            self.insight_evidence.setText("Personal baselines require sufficient local history for each metric.")
            return

        self.insight_title.setText(hypothesis.category.replace("_", " ").title())
        explanations = {
            "LOCAL_RESOURCE_CONTENTION": "Sustained pressure on a local resource may affect responsiveness.",
            "NETWORK_INSTABILITY": "Elevated latency or packet loss may interrupt online activity.",
            "UNKNOWN_ANOMALY": "An unusual signal was recorded, but evidence is not yet conclusive.",
        }
        recommendation = hypothesis.recommended_checks[0] if hypothesis.recommended_checks else "Continue monitoring and review the detailed analysis."
        self.insight_body.setText(f"{explanations.get(hypothesis.category, 'Recent measurements show an unusual pattern.')} Next: {recommendation}")
        evidence = hypothesis.evidence[:2]
        self.insight_evidence.setText(
            "Evidence: " + " · ".join(
                f"{item.metric.replace('_', ' ')} {item.observed_value:.1f} vs {item.expected_value:.1f} expected"
                for item in evidence
            ) if evidence else "Review the diagnosis page for supporting evidence and limitations."
        )

    def _open_investigation(self, symptom: str) -> None:
        self._select_symptom(symptom)
        self._navigate(2)

    def _select_symptom(self, symptom: str) -> None:
        self._selected_symptom = symptom if symptom in SYMPTOMS else "other"
        for key, button in getattr(self, "symptom_buttons", {}).items():
            button.setChecked(key == self._selected_symptom)
        if hasattr(self, "symptom_description"):
            self.symptom_description.setText(SYMPTOMS[self._selected_symptom]["description"])
        if hasattr(self, "investigation_network_hint"):
            is_network = self._selected_symptom in {"internet", "game_stutter"}
            self.investigation_network_hint.setText(
                "Run these checks during the capture to compare the gateway, internet, DNS, and HTTP."
                if is_network else
                "Connection checks are available here whenever they are relevant to the problem."
            )

    def _sync_investigation_controls(self) -> None:
        if not hasattr(self, "start_investigation_button"):
            return
        active = self._active_investigation is not None
        last_evidence = (self._last_incident.evidence or {}) if self._last_incident else {}
        verification_pending = bool(last_evidence.get("verification_started_at") and not last_evidence.get("verification"))
        self.start_investigation_button.setEnabled(not active and not verification_pending)
        self.stop_investigation_button.setEnabled(active)
        self.add_note_button.setEnabled(active)
        self.run_focused_check_button.setEnabled(active)
        self.inspect_route_button.setEnabled(active)
        self.resolve_button.setEnabled(not active and self._last_incident is not None)
        self.unresolved_button.setEnabled(not active and self._last_incident is not None)
        self.start_verification_button.setEnabled(not active and self._last_incident is not None)
        if active:
            self._selected_symptom = self._active_investigation.symptom
            self._select_symptom(self._selected_symptom)
            self.capture_elapsed_timer.start(1000)
            resumed = any(marker.get("kind") == "capture resumed" for marker in (self._active_investigation.evidence or {}).get("markers", []))
            capture_note = "The capture resumed after Diagnosys reopened; there may be a gap while it was closed." if resumed else "The capture includes five minutes of recent history before you started."
            self.investigation_status.setText(
                f"Capturing {SYMPTOMS.get(self._selected_symptom, SYMPTOMS['other'])['title'].lower()} since "
                f"{self._active_investigation.started_at.astimezone().strftime('%H:%M:%S')}. "
                f"{capture_note}"
            )
            self.active_capture_label.setText("Investigation in progress · " + self._active_investigation.title)
        else:
            self.capture_elapsed_timer.stop()
            self.investigation_status.setText("Choose a problem, then start a capture. Diagnosys will keep collecting evidence in the background.")
            self.active_capture_label.setText(
                f"Last investigation · {self._last_incident.title} · {self._last_incident.status.replace('_', ' ')}"
                if self._last_incident else "No active investigation"
            )
            if self._last_incident:
                self.resolution_note_input.setText(self._last_incident.resolution_note)
                statuses = {
                    "resolved": "Marked fixed · your confirmation",
                    "still_happening": "Still happening · keep monitoring",
                    "captured": "Not marked fixed yet",
                }
                self.resolution_status.setText(statuses.get(self._last_incident.status, ""))
        self._sync_verification_controls()

    def _sync_verification_controls(self) -> None:
        if not hasattr(self, "verification_timer"):
            return
        incident = self._last_incident
        if not incident or incident.status == "investigating" or self._active_investigation:
            self.verification_timer.stop()
            self.compare_verification_button.setEnabled(False)
            self.verification_status.setText("After trying a change, measure another minute and compare the readings with this capture.")
            return
        evidence = incident.evidence or {}
        verification = evidence.get("verification")
        if verification:
            self.start_verification_button.setEnabled(True)
            self.verification_timer.stop()
            self.compare_verification_button.setEnabled(False)
            self.verification_status.setText(verification.get("summary", "After-change comparison saved."))
            return
        started_value = evidence.get("verification_started_at")
        if not started_value:
            self.start_verification_button.setEnabled(True)
            self.verification_timer.stop()
            self.compare_verification_button.setEnabled(False)
            return
        try:
            started = datetime.fromisoformat(str(started_value).replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
        except ValueError:
            self.compare_verification_button.setEnabled(False)
            return
        self._verification_started_at = started
        self.start_verification_button.setEnabled(False)
        self.verification_timer.start(1000)
        self._update_verification_status()

    def _update_verification_status(self) -> None:
        started = getattr(self, "_verification_started_at", None)
        if not started:
            return
        elapsed = int((datetime.now(timezone.utc) - started).total_seconds())
        remaining = max(0, 60 - elapsed)
        if remaining:
            self.compare_verification_button.setEnabled(False)
            self.verification_status.setText(f"After-change check running · compare will be ready in {remaining} seconds.")
        else:
            self.verification_timer.stop()
            self.compare_verification_button.setEnabled(True)
            self.verification_status.setText("One minute of after-change readings is ready to compare.")

    def _update_capture_elapsed(self) -> None:
        incident = self._active_investigation
        if not incident:
            self.capture_elapsed_timer.stop()
            return
        elapsed = max(0, int((datetime.now(timezone.utc) - incident.started_at).total_seconds()))
        self.investigation_status.setText(
            f"Capturing {SYMPTOMS.get(incident.symptom, SYMPTOMS['other'])['title'].lower()} · "
            f"{self._duration(elapsed)} elapsed. Add a note when the issue occurs; five minutes of earlier history will also be reviewed."
        )

    def start_investigation(self) -> None:
        if self._active_investigation is not None:
            return
        profile = SYMPTOMS[self._selected_symptom]
        incident_id = self.incident_repo.start_investigation(self._selected_symptom, profile["title"])
        self._active_investigation = self.incident_repo.active_investigation()
        if self._active_investigation:
            self.incident_repo.add_marker(incident_id, {
                "timestamp": self._active_investigation.started_at.isoformat(),
                "kind": "capture started",
                "text": "Five minutes of pre-capture history will be included when available.",
            })
            self._active_investigation.evidence.setdefault("markers", []).append({
                "timestamp": self._active_investigation.started_at.isoformat(),
                "kind": "capture started",
                "text": "Five minutes of pre-capture history will be included when available.",
            })
        self.investigation_result_title.setText("Capture is running")
        self.investigation_result_summary.setText("Use your PC as usual. Add a note when the symptom occurs, then stop the capture to review evidence.")
        self._sync_investigation_controls()

    def add_investigation_note(self) -> None:
        incident = self._active_investigation
        if not incident:
            return
        note, accepted = QInputDialog.getMultiLineText(
            self, "Add an investigation note", "What did you notice just now?"
        )
        if not accepted or not note.strip():
            return
        marker = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": "user note",
            "text": note.strip()[:1000],
        }
        self.incident_repo.add_marker(incident.id, marker)
        incident.evidence.setdefault("markers", []).append(marker)
        self.statusBar().showMessage("Note added to this local investigation.", 4000)

    def stop_investigation(self) -> None:
        incident = self._active_investigation
        if not incident:
            return
        markers = list((incident.evidence or {}).get("markers", []))
        sensor_availability = dict(self._latest_sensor_availability)
        self.investigation_status.setText("Reviewing the capture, comparing it with the prior window, and checking Windows events…")
        self._run_async(
            "investigation_finish",
            lambda: self._finish_investigation_data(incident, markers, sensor_availability),
            self._investigation_finished,
        )

    def _finish_investigation_data(self, incident, markers: list[dict], sensor_availability: dict[str, str]) -> dict:
        connection = self._connection()
        try:
            now = datetime.now(timezone.utc)
            requested_start = incident.started_at - timedelta(minutes=5)
            capture_start = max(requested_start, now - timedelta(hours=24))
            window_limited = capture_start > requested_start
            baseline_start = capture_start - timedelta(minutes=5)
            metric_repo = MetricRepository(connection)
            metrics = metric_repo.query_between(capture_start, now, limit=100000)
            baseline_metrics = metric_repo.query_between(baseline_start, capture_start, limit=30000)
            anomalies = AnomalyRepository(connection).query_between(capture_start, now)
            processes = ProcessRepository(connection).query_between(capture_start, now, limit=100000)
            duration_minutes = max(1, int((now - capture_start).total_seconds() / 60) + 1)
            events = recent_system_events(minutes=min(1440, duration_minutes), limit=100)
            result = InvestigationEngine().analyze(
                incident.symptom, capture_start, now, metrics, anomalies,
                processes, events, baseline_metrics, markers, sensor_availability,
            )
            result["capture_started_at"] = incident.started_at.isoformat()
            result["capture_window_start"] = capture_start.isoformat()
            result["capture_ended_at"] = now.isoformat()
            result["window_limited_to_24_hours"] = window_limited
            if window_limited:
                result["limitations"].append("This investigation lasted longer than 24 hours; the analysis uses the most recent 24 hours of measurements.")
            result["sensor_availability"] = sensor_availability
            result["symptom_start_marker"] = incident.started_at.isoformat()
            result["chart_series"] = {
                key: [float(item.value) for item in metrics if item.metric_name == name and item.status == MetricStatus.OK and isinstance(item.value, (int, float))][-60:]
                for key, name in (("CPU", "cpu_percent"), ("Memory", "memory_percent"), ("Disk", "disk_percent"))
            }
            category_counts: dict[str, int] = {}
            for anomaly in anomalies:
                category_counts[anomaly.category] = category_counts.get(anomaly.category, 0) + 1
            diagnosis_category = max(category_counts, key=category_counts.get) if category_counts else None
            if not diagnosis_category:
                diagnostic_kinds = {"cpu_percent": "CPU_PRESSURE", "memory_percent": "MEMORY_PRESSURE", "disk_percent": "DISK_PRESSURE", "ping_median_ms": "NETWORK_LATENCY"}
                for finding in result["findings"]:
                    metric_name = finding.get("metric_name")
                    if metric_name in diagnostic_kinds:
                        diagnosis_category = diagnostic_kinds[metric_name]
                        break
            IncidentRepository(connection).finish_investigation(
                incident.id, now, result["summary"], len(metrics), len(anomalies),
                diagnosis_category, result,
            )
            result["incident_id"] = incident.id
            result["incident_title"] = incident.title
            result["status"] = "captured"
            return result
        finally:
            connection.close()

    def _investigation_finished(self, result: dict) -> None:
        self._active_investigation = None
        self._latest_investigation_data = result
        cached = IncidentRepository(self.db).query(limit=1)
        self._last_incident = cached[0] if cached else None
        self._select_symptom(result["symptom"])
        self.investigation_result_title.setText(result["symptom_title"])
        self.investigation_result_summary.setText(result["summary"])
        series = result.get("chart_series", {})
        for key in ("CPU", "Memory", "Disk"):
            self.investigation_chart.set_series(key, series.get(key, []))
        self.investigation_result.setHtml(self._investigation_html(result))
        self.resolution_status.setText("Not marked fixed yet")
        self.investigation_status.setText(
            f"Capture saved as incident #{result['incident_id']}. You can mark it fixed after trying a check, or leave it open as still happening."
        )
        self._sync_investigation_controls()
        self.show_history()
        self._navigate(2)

    def ask_investigation(self) -> None:
        question = self.investigation_question.text().strip()
        if not question:
            self.investigation_answer.setText("Enter a question about this capture.")
            return
        result = getattr(self, "_latest_investigation_data", None)
        if result is None and self._last_incident:
            result = self._last_incident.evidence
        if not result:
            self.investigation_answer.setText("Capture a problem first. Diagnosys answers from saved incident evidence only.")
            return
        question_key = question.casefold()
        findings = result.get("findings", [])
        processes = result.get("process_peaks", [])
        stats = result.get("metric_stats", {})
        if any(term in question_key for term in ("fix", "improve", "after", "better", "resolved")):
            verification = result.get("verification")
            if verification and verification.get("comparisons"):
                answer = verification.get("summary", "After-change comparison saved.") + " " + "; ".join(
                    f"{item['metric_name'].replace('_', ' ')} {item['change_pct']:+.0f}%"
                    for item in verification["comparisons"][:5]
                )
            elif verification:
                answer = verification.get("summary", "The after-change check was saved.")
            else:
                answer = "No after-change comparison has been recorded. Start a one-minute check after trying a change."
        elif any(term in question_key for term in ("changed", "change", "before", "different", "worse", "update")):
            comparisons = result.get("before_after", [])
            events = result.get("system_events", {}).get("events", [])
            if comparisons:
                answer = "Compared with the previous five minutes: " + "; ".join(
                    f"{item['metric_name'].replace('_', ' ')} {item['change_pct']:+.0f}%"
                    for item in comparisons[:5]
                )
            else:
                answer = "There are not enough matching readings for a before-and-during comparison."
            if events:
                answer += " Nearby Windows events: " + "; ".join(
                    str(item.get("source") or item.get("message") or "Windows event")[:100]
                    for item in events[:3]
                ) + ". Timing overlap is a clue, not proof of cause."
        elif any(term in question_key for term in ("internet", "network", "wifi", "ping", "dns", "connection")):
            network_stats = {
                name: item for name, item in stats.items()
                if any(term in name for term in ("ping", "packet_loss", "dns", "http"))
            }
            network_findings = [item["title"] for item in findings if "network" in item.get("title", "").casefold() or "ping" in item.get("detail", "").casefold()]
            answer = (
                "Network readings: " + "; ".join(f"{name.replace('_', ' ')} median {item['median']:.1f}" for name, item in network_stats.items())
                if network_stats else "No focused network measurements were saved in this capture. Run the connection check while the problem is happening."
            )
            if network_findings:
                answer += " Clues: " + "; ".join(network_findings[:3]) + "."
        elif any(term in question_key for term in ("app", "process", "cpu", "memory", "busy", "using")):
            requested = [item for item in processes if item["process_name"].casefold() in question_key]
            chosen = requested or processes[:4]
            answer = (
                "Recorded process peaks: " + "; ".join(
                    f"{item['process_name']} CPU {item['peak_cpu_percent']:.1f}%, memory {item['peak_memory_percent']:.1f}%"
                    for item in chosen
                ) if chosen else "No process observations were saved in this capture."
            )
        elif any(term in question_key for term in ("hot", "heat", "temperature", "fan")):
            temperature = {name: item for name, item in stats.items() if "temperature" in name}
            answer = (
                "Temperature readings: " + "; ".join(f"{name.replace('_', ' ')} peak {item['max']:.1f} °C" for name, item in temperature.items())
                if temperature else "No temperature sensor readings were available. Check the sensor availability notes in the findings."
            )
        elif any(term in question_key for term in ("crash", "error", "event", "freeze")):
            events = result.get("system_events", {}).get("events", [])
            answer = (
                "Nearby events: " + "; ".join(
                    f"{item.get('time', 'time unavailable')} · {str(item.get('message') or item.get('source') or 'Windows event')[:140]}"
                    for item in events[:4]
                ) if events else "No matching Windows event was found. Some application freezes are not written to the event log."
            )
        else:
            lead = result.get("hypotheses", [])
            clue_text = "; ".join(item["title"] for item in findings[:3]) or "No strong measurement signal stood out."
            likely_text = " Leading areas: " + "; ".join(item["title"] for item in lead[:3]) + "." if lead else ""
            answer = result.get("summary", "No summary was saved.") + " Clues: " + clue_text + "." + likely_text
        self.investigation_answer.setText(answer)

    def _investigation_html(self, result: dict) -> str:
        escape = html.escape
        lines: list[str] = []
        hypotheses = result.get("hypotheses", [])
        if hypotheses:
            lines.extend(["<h3>Leading areas to check</h3><ul>"])
            for item in hypotheses:
                lines.append(
                    f"<li><b>{escape(item['title'])}</b> · {escape(item['strength'])}<br>{escape(item['basis'])}</li>"
                )
            lines.append("</ul>")
        lines.extend([
            "<h3>What the evidence shows</h3>",
            f"<p><b>Data coverage:</b> {escape(result['data_quality'])} · "
            f"{int(result['metric_count']):,} measurements · {int(result['process_sample_count']):,} process observations · "
            f"{int(result['anomaly_count']):,} rule flags.</p>",
            "<h3>Strongest clues</h3><ul>",
        ])
        for finding in result.get("findings", []):
            lines.append(f"<li><b>{escape(finding['title'])}</b><br>{escape(finding['detail'])} <i>({escape(finding['strength'])})</i></li>")
        lines.append("</ul>")
        comparisons = result.get("before_after", [])
        lines.append("<h3>Compared with the five minutes before capture</h3>")
        if comparisons:
            lines.append("<ul>")
            for item in comparisons:
                lines.append(
                    f"<li>{escape(item['metric_name'].replace('_', ' '))}: "
                    f"{item['before_median']:.1f} → {item['during_median']:.1f} "
                    f"({item['change_pct']:+.0f}%)</li>"
                )
            lines.append("</ul>")
        else:
            lines.append("<p>Not enough matching measurements for a comparison.</p>")
        process_peaks = result.get("process_peaks", [])
        lines.append("<h3>Applications with the highest recorded activity</h3>")
        if process_peaks:
            lines.append("<ul>")
            for item in process_peaks[:6]:
                lines.append(
                    f"<li>{escape(item['process_name'])}: CPU {item['peak_cpu_percent']:.1f}% · "
                    f"memory {item['peak_memory_percent']:.1f}% · {item['samples']} observations</li>"
                )
            lines.append("</ul>")
        else:
            lines.append("<p>No process observations were recorded in this window.</p>")
        events = result.get("system_events", {}).get("events", [])
        lines.append("<h3>Windows events</h3>")
        if events:
            lines.append("<ul>")
            for event in events[:12]:
                stamp = event.get("time") or "Time unavailable"
                detail = event.get("message") or event.get("source") or "Windows event"
                lines.append(f"<li>{escape(str(stamp))} · {escape(str(detail)[:300])}</li>")
            lines.append("</ul>")
        else:
            reason = result.get("system_events", {}).get("reason", "No related Windows events were reported.")
            lines.append(f"<p>{escape(str(reason))}</p>")
        lines.append("<h3>Try these checks</h3><ol>")
        lines.extend(f"<li>{escape(step)}</li>" for step in result.get("next_checks", []))
        lines.append("</ol><h3>Timeline</h3>")
        timeline = result.get("timeline", [])
        if timeline:
            lines.append("<ul>")
            for item in timeline[-30:]:
                lines.append(f"<li>{escape(item['timestamp'])} · <b>{escape(item['kind'])}</b> · {escape(item['detail'])}</li>")
            lines.append("</ul>")
        else:
            lines.append("<p>No notable timeline entries were saved.</p>")
        limitations = result.get("limitations", [])
        if limitations:
            lines.append("<h3>Limits of this result</h3><ul>")
            lines.extend(f"<li>{escape(item)}</li>" for item in limitations)
            lines.append("</ul>")
        lines.append("<p><i>Event details and process names remain on this device.</i></p>")
        return "".join(lines)

    def set_investigation_resolution(self, status: str) -> None:
        incident = self._last_incident
        if not incident or incident.status == "investigating":
            return
        note = self.resolution_note_input.text().strip()
        self.incident_repo.set_resolution(incident.id, status, note)
        incident.status = status
        incident.resolution_note = note
        self._refresh_cached_incident()
        self.resolution_status.setText("Marked fixed · your confirmation" if status == "resolved" else "Still happening · keep monitoring")
        self.active_capture_label.setText(f"Last investigation · {incident.title} · {status.replace('_', ' ')}")
        self.statusBar().showMessage("Investigation outcome saved locally.", 4000)

    def start_verification(self) -> None:
        incident = self._last_incident
        if not incident or incident.status == "investigating" or self._active_investigation:
            return
        note = self.resolution_note_input.text().strip()
        started = self.incident_repo.begin_verification(incident.id, note)
        incident.evidence["verification_started_at"] = started.isoformat()
        incident.evidence["verification_note"] = note
        incident.evidence.pop("verification", None)
        incident.evidence.setdefault("markers", []).append({
            "timestamp": started.isoformat(),
            "kind": "after-change check started",
            "text": note or "User started a one-minute after-change check.",
        })
        incident.status = "captured"
        incident.resolution_note = note
        self._refresh_cached_incident()
        self._verification_started_at = started
        self.verification_timer.start(1000)
        self.resolution_status.setText("After-change check in progress")
        self.start_verification_button.setEnabled(False)
        self._update_verification_status()

    def compare_verification(self) -> None:
        incident = self._last_incident
        if not incident or not getattr(self, "_verification_started_at", None):
            return
        if (datetime.now(timezone.utc) - self._verification_started_at).total_seconds() < 60:
            self._update_verification_status()
            return
        started = self._verification_started_at
        before_stats = dict((incident.evidence or {}).get("metric_stats", {}))
        self.verification_status.setText("Comparing the after-change readings with the original capture…")
        self._run_async(
            "verification_compare",
            lambda: self._verification_data(incident.id, started, before_stats),
            self._verification_finished,
        )

    def _verification_data(self, incident_id: int, started: datetime, before_stats: dict) -> dict:
        connection = self._connection()
        try:
            now = datetime.now(timezone.utc)
            samples = MetricRepository(connection).query_between(started, now, limit=30000)
            after_stats: dict[str, dict[str, float | int]] = {}
            for name in sorted({sample.metric_name for sample in samples}):
                values = [
                    float(sample.value) for sample in samples
                    if sample.metric_name == name and sample.status == MetricStatus.OK
                    and isinstance(sample.value, (int, float))
                ]
                if values:
                    after_stats[name] = {
                        "samples": len(values),
                        "median": round(statistics.median(values), 2),
                        "max": round(max(values), 2),
                    }
            comparisons = []
            for name in sorted(set(before_stats) & set(after_stats)):
                before = float(before_stats[name].get("median", 0))
                after = float(after_stats[name]["median"])
                delta = after - before
                denominator = abs(before) if abs(before) > 0.01 else 1.0
                comparisons.append({
                    "metric_name": name,
                    "before_median": round(before, 2),
                    "after_median": round(after, 2),
                    "change_pct": round(delta / denominator * 100, 1),
                    "samples": after_stats[name]["samples"],
                })
            if len(samples) < 5:
                summary = "The after-change window has too few usable measurements. Keep Diagnosys open for another minute and compare again."
            elif comparisons:
                summary = f"Compared {len(comparisons)} metric(s) using {len(samples)} after-change samples. A lower reading can be encouraging, but it does not by itself prove the issue is fixed."
            else:
                summary = "The after-change window has readings, but no metrics overlap with the original capture."
            verification = {
                "started_at": started.isoformat(),
                "ended_at": now.isoformat(),
                "sample_count": len(samples),
                "comparisons": comparisons,
                "summary": summary,
                "after_stats": after_stats,
            }
            IncidentRepository(connection).save_verification(incident_id, verification)
            verification["incident_id"] = incident_id
            return verification
        finally:
            connection.close()

    def _verification_finished(self, verification: dict) -> None:
        incident = self._last_incident
        if incident and incident.id == verification.get("incident_id"):
            incident.evidence["verification"] = verification
            self._refresh_cached_incident()
        self._verification_started_at = None
        self.verification_timer.stop()
        self.compare_verification_button.setEnabled(False)
        self.verification_status.setText(verification["summary"])
        lines = ["<h3>After-change comparison</h3>", f"<p>{html.escape(verification['summary'])}</p>"]
        if verification.get("comparisons"):
            lines.append("<ul>")
            for item in verification["comparisons"]:
                lines.append(
                    f"<li>{html.escape(item['metric_name'].replace('_', ' '))}: "
                    f"{item['before_median']:.1f} → {item['after_median']:.1f} "
                    f"({item['change_pct']:+.0f}%)</li>"
                )
            lines.append("</ul>")
        self.investigation_result.append("".join(lines))
        self.ask_investigation_button.setEnabled(True)
        self._sync_verification_controls()

    @staticmethod
    def _network_work(target: str, dns_target: str, dns_server: str | None, http_target: str, timeout: float):
        return (
            PingCollector(target=target, count=3, timeout_sec=timeout).collect(),
            DNSCollector(target=dns_target, timeout_sec=timeout, server=dns_server).collect(),
            HTTPCollector(target=http_target, timeout_sec=timeout).collect(),
        )

    def network_check(self) -> None:
        target = self.target.text().strip() or self.settings.ping_target
        dns_target = self.dns_target.text().strip() or self.settings.dns_target
        dns_server = self.dns_server.text().strip() or None
        http_target = self.http_target.text().strip() or self.settings.http_target
        timeout = self.settings.network_timeout_seconds
        self.network_output.setPlainText("Checking ping, DNS, and HTTP connectivity…")
        self._run_async(
            "network",
            lambda: self._network_work(target, dns_target, dns_server, http_target, timeout),
            self._apply_network,
        )

    def inspect_network_path(self) -> None:
        target = self.target.text().strip() or self.settings.ping_target
        timeout = self.settings.network_timeout_seconds
        self.route_output.setPlainText("Checking the default gateway and tracing up to eight network hops…")
        self._run_async(
            "route",
            lambda: NetworkInvestigator().collect(target, timeout),
            self._apply_network_path,
        )

    def _apply_network_path(self, result: dict) -> None:
        gateway = result.get("gateway", {})
        gateway_ping = result.get("gateway_ping")
        route = result.get("route", {})
        wifi = result.get("wifi", {})
        if gateway_ping:
            timestamp = datetime.now(timezone.utc)
            gateway_id = f"gateway:{gateway.get('address', 'default')}"
            self._store_sample(MetricSample(
                timestamp, "ping_median_ms", gateway_ping.median_ms, "ms", "network",
                MetricStatus.OK if gateway_ping.median_ms is not None else MetricStatus.UNAVAILABLE,
                entity_id=gateway_id, reason=gateway_ping.reason,
            ))
            self._store_sample(MetricSample(
                timestamp, "packet_loss_percent", gateway_ping.packet_loss_percent, "%", "network",
                MetricStatus.OK, entity_id=gateway_id,
            ))
        lines = [f"Target: {result.get('target', '—')}", "", "DEFAULT GATEWAY"]
        lines.append(gateway.get("address", gateway.get("reason", "Unavailable")))
        lines += ["", "GATEWAY CONNECTIVITY"]
        if gateway_ping and gateway_ping.median_ms is not None:
            lines.append(
                f"Median {gateway_ping.median_ms:.1f} ms · "
                f"packet loss {gateway_ping.packet_loss_percent:.0f}%"
            )
        elif gateway_ping:
            lines.append(gateway_ping.reason or "The gateway did not reply to the local ping check.")
        else:
            lines.append("Gateway connectivity could not be measured.")
        lines += ["", "ROUTE TRACE"]
        if route.get("available"):
            lines.extend(route.get("lines", []))
        else:
            lines.append(route.get("reason", "No route trace available."))
        lines += ["", "WI-FI LINK"]
        if wifi.get("available"):
            lines.extend(f"{key.replace('_', ' ').title()}: {value}" for key, value in wifi.items() if key != "available")
        else:
            lines.append(wifi.get("reason", "Wi-Fi details unavailable."))
        lines += ["", "HOW TO READ THIS"]
        lines.append("A gateway reply confirms local router reachability, not access to every internet service.")
        lines.append("Some routers suppress route-trace replies; missing hops alone do not prove a connection failure.")
        self.route_output.setPlainText("\n".join(lines))
        if self._active_investigation is not None:
            wifi_signal = wifi.get("signal", "not reported") if wifi.get("available") else "not available"
            route_count = len(route.get("lines", [])) if route.get("available") else 0
            gateway_result = (
                f"gateway {gateway.get('address', 'unavailable')} replied at {gateway_ping.median_ms:.1f} ms"
                if gateway_ping and gateway_ping.median_ms is not None
                else "gateway reply unavailable"
            )
            marker = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": "network path check",
                "text": f"{gateway_result}; Wi-Fi signal {wifi_signal}; route trace returned {route_count} hop line(s).",
            }
            self.incident_repo.add_marker(self._active_investigation.id, marker)
            self._active_investigation.evidence.setdefault("markers", []).append(marker)

    def _apply_network(self, results) -> None:
        ping, dns, http = results
        timestamp = datetime.now(timezone.utc)
        if ping.available:
            if ping.median_ms is not None:
                self._store_sample(MetricSample(
                    timestamp, "ping_median_ms", ping.median_ms, "ms", "network",
                    MetricStatus.OK, entity_id=ping.target,
                ))
            else:
                self._store_sample(MetricSample(
                    timestamp, "ping_median_ms", None, "ms", "network",
                    MetricStatus.UNAVAILABLE, entity_id=ping.target,
                    reason=ping.reason or "No ping replies were received.",
                ))
            self._store_sample(MetricSample(
                timestamp, "packet_loss_percent", ping.packet_loss_percent, "%", "network",
                MetricStatus.OK, entity_id=ping.target,
            ))
            if ping.jitter_ms is not None:
                self._store_sample(MetricSample(
                    timestamp, "ping_jitter_ms", ping.jitter_ms, "ms", "network",
                    MetricStatus.OK, entity_id=ping.target,
                ))
        else:
            self._store_sample(MetricSample(
                timestamp, "ping_median_ms", None, "ms", "network",
                MetricStatus.UNAVAILABLE, entity_id=ping.target,
                reason=ping.reason or "Ping is unavailable.",
            ))
        if dns.success and dns.latency_ms is not None:
            self._store_sample(MetricSample(
                timestamp, "dns_latency_ms", dns.latency_ms, "ms", "network",
                MetricStatus.OK, entity_id=f"{dns.target} via {dns.server or 'system'}",
            ))
        else:
            self._store_sample(MetricSample(
                timestamp, "dns_latency_ms", None, "ms", "network",
                MetricStatus.UNAVAILABLE, entity_id=f"{dns.target} via {dns.server or 'system'}",
                reason=dns.reason or "DNS lookup failed.",
            ))
        if http.success and http.latency_ms is not None:
            self._store_sample(MetricSample(
                timestamp, "http_latency_ms", http.latency_ms, "ms", "network",
                MetricStatus.OK, entity_id=http.target,
            ))
        else:
            self._store_sample(MetricSample(
                timestamp, "http_latency_ms", None, "ms", "network",
                MetricStatus.UNAVAILABLE, entity_id=http.target,
                reason=http.reason or "HTTP request failed.",
            ))
        if ping.median_ms is not None:
            self.network_latency_card.set_value(f"{ping.median_ms:.1f} ms", f"Median ping to {ping.target}")
            self.network_latency_value = f"{ping.median_ms:.1f} ms"
        else:
            self.network_latency_card.set_value("Timeout", ping.reason or "No ping replies")
            self.network_latency_value = "Timeout"
        if ping.available:
            self.packet_loss_card.set_value(f"{ping.packet_loss_percent:.0f}%", f"To {ping.target}")
            self.jitter_card.set_value(f"{ping.jitter_ms:.1f} ms" if ping.jitter_ms is not None else "—", "Mean reply variation")
            self.ping_summary.setText(
                f"Latency {self.network_latency_value}  ·  Packet loss {ping.packet_loss_percent:.0f}%"
            )
        else:
            self.packet_loss_card.set_value("Unavailable", ping.reason or "Ping probe failed")
            self.jitter_card.set_value("Unavailable", "Ping probe failed")
            self.ping_summary.setText(f"Ping unavailable · {ping.reason or 'probe failed'}")
        lines = ["PING", f"Target: {ping.target}"]
        if not ping.available:
            lines.append(f"Unavailable: {ping.reason or 'probe failed'}")
            lines.append("Packet loss: unavailable")
        elif ping.median_ms is not None and ping.min_ms is not None and ping.max_ms is not None:
            lines.append(f"Median: {ping.median_ms:.1f} ms  ·  Min: {ping.min_ms:.1f} ms  ·  Max: {ping.max_ms:.1f} ms")
        else:
            lines.append(f"No reply  ·  Packet loss: {ping.packet_loss_percent:.0f}% ({ping.reason or 'no response'})")
        lines.append(f"Jitter: {ping.jitter_ms:.1f} ms" if ping.jitter_ms is not None else "Jitter: unavailable")
        resolver = f" via {dns.server}" if dns.server else " via system resolver"
        lines += ["", "DNS", f"{dns.target}{resolver}: {dns.latency_ms:.1f} ms" if dns.success and dns.latency_ms is not None else f"Unavailable: {dns.reason or 'request failed'}", "", "HTTP", f"{http.target}: {http.latency_ms:.1f} ms · status {http.status_code}" if http.success and http.latency_ms is not None else f"Unavailable: {http.reason or 'request failed'}"]
        self.network_output.setPlainText("\n".join(lines))
        self._update_insight()

    def _store_sample(self, sample: MetricSample) -> None:
        self.metric_repo.save(sample)
        if sample.status == MetricStatus.OK:
            for anomaly in self.detector.evaluate_sample(sample):
                if not self.anomaly_repo.has_recent(anomaly.rule_id, window_seconds=300):
                    self.anomaly_repo.save(anomaly)
                    self._notify_anomaly(anomaly)

    def _connection(self):
        connection = get_connection()
        init_db(connection)
        return connection

    def diagnose(self) -> None:
        self.diagnosis_output.setPlainText("Analyzing saved evidence…")
        self._run_async("diagnosis", self._diagnose_data, self._apply_diagnosis)

    def _diagnose_data(self):
        connection = self._connection()
        try:
            samples = [item for item in MetricRepository(connection).query(window_seconds=3600) if item.status == MetricStatus.OK]
            if len(samples) < 5:
                return DiagnosisResult(
                    status="INSUFFICIENT_DATA", primary_hypothesis=None,
                    time_window=3600, data_quality="LIMITED",
                )
            return DiagnosticEngine().diagnose(AnomalyRepository(connection).query(window_seconds=3600), window_seconds=3600)
        finally:
            connection.close()

    def _apply_diagnosis(self, result: DiagnosisResult) -> None:
        lines: list[str] = []
        if result.status == "INSUFFICIENT_DATA":
            lines += ["Not enough evidence yet", "", "Diagnosys has fewer than five usable readings in the last hour. Keep monitoring or capture the problem while it is happening."]
        elif result.status == "NO_ANOMALY":
            lines += ["No unusual deviation detected", "", "No monitored metric crossed its learned personal variation band. This does not prove every component is healthy.", "", "Keep monitoring if the issue returns."]
        else:
            lines += [f"Status: {result.status}", ""]
        hypothesis = result.primary_hypothesis
        if hypothesis:
            category = hypothesis.category
            explanations = {
                "LOCAL_RESOURCE_CONTENTION": "One or more local resources are under sustained pressure. This can make applications feel slow, cause stuttering, or delay background tasks.",
                "NETWORK_INSTABILITY": "The network is showing elevated latency or packet loss. This can cause slow pages, voice/video interruptions, and game lag.",
                "UNKNOWN_ANOMALY": "The system recorded an unusual signal, but there is not enough evidence to identify a specific cause yet.",
            }
            lines += [f"Observed pattern: {category.replace('_', ' ').title()}", "", explanations.get(category, "The diagnostic engine found an unusual pattern in recent measurements."), ""]
            if hypothesis.evidence:
                lines += ["Evidence:"]
                lines += [f"• {e.metric.replace('_', ' ').title()}: {e.observed_value:.1f} (expected around {e.expected_value:.1f})" for e in hypothesis.evidence]
                lines.append("")
            lines.append("What to do next:")
            lines += [f"• {check}" for check in hypothesis.recommended_checks]
            if hypothesis.limitations:
                lines += ["", "Limits of this result:"]
                lines += [f"• {limit}" for limit in hypothesis.limitations]
        self.diagnosis_output.setPlainText("\n".join(lines))
        self._render_insight(result)

    def show_capabilities(self) -> None:
        info = runtime_info()
        lines = [f"{info['os']} {info['os_release']} · {info['architecture']}", f"Python {info['python_version']} · psutil {info['psutil_version']}", "", "SYSTEM CAPABILITIES"]
        lines += [f"{capability['name']}: {'Available' if capability['available'] else 'Unavailable — ' + str(capability['reason'])}" for capability in info["capabilities"]]
        lines += ["", "OPTIONAL DEVICE TELEMETRY", "GPU: NVIDIA nvidia-smi is used when present; other GPU vendors may not expose readings.", "CPU temperature: shown only when the operating system reports a CPU-labelled sensor."]
        self.capabilities_output.setPlainText("\n".join(lines))

    def show_history(self) -> None:
        window_seconds = self.history_window.currentData() or 3600
        connection = self._connection()
        try:
            metrics = MetricRepository(connection).query(window_seconds=window_seconds)
            anomalies = AnomalyRepository(connection).query(window_seconds=window_seconds)
            incidents = IncidentRepository(connection).query(limit=10)
            process_peaks = ProcessRepository(connection).top_processes(window_seconds=window_seconds, limit=8)
        finally:
            connection.close()
        self._incident_cache = incidents
        self.incident_selector.blockSignals(True)
        self.incident_selector.clear()
        for incident in incidents:
            self.incident_selector.addItem(f"#{incident.id} · {incident.title}", incident.id)
        self.incident_selector.blockSignals(False)
        self.view_incident_button.setEnabled(bool(incidents))
        self._incident_selection_changed()
        lines = [
            f"Measurements in the selected period: {len(metrics)}",
            f"Anomalies in the selected period: {len(anomalies)}",
            "",
            "PROCESS HISTORY · PEAKS",
        ]
        if process_peaks:
            lines += [
                f"• {item['process_name']}: CPU peak {item['peak_cpu_percent']:.1f}% · "
                f"memory peak {item['peak_memory_percent']:.1f}% · "
                f"disk read/write peak {self._history_rate(item['peak_read_bytes_per_sec'])} / "
                f"{self._history_rate(item['peak_write_bytes_per_sec'])} · "
                f"{item['peak_network_connections'] if item['peak_network_connections'] is not None else 'unavailable'} active connections · "
                f"{item['samples']} observations"
                for item in process_peaks
            ]
        else:
            lines.append("No process snapshots are available for this period yet.")
        lines += [
            "",
            "RECENT ANOMALIES",
        ]
        lines += [f"• {anomaly.category}: {anomaly.explanation}" for anomaly in anomalies[:12]]
        if not anomalies:
            lines.append("No anomalies were recorded in the last hour.")
        lines += ["", "CAPTURED INCIDENTS"]
        if incidents:
            for incident in incidents:
                timestamp = incident.started_at.strftime("%Y-%m-%d %H:%M UTC")
                lines.append(
                    f"• #{incident.id} · {timestamp} · {incident.title} · {incident.status.replace('_', ' ')} · "
                    f"{incident.metrics_count} measurements · {incident.anomalies_count} anomalies"
                )
                lines.append(f"  {incident.summary}")
                evidence = incident.evidence or {}
                saved_processes = evidence.get("process_peaks", [])
                if saved_processes:
                    lines.append("  Leading process activity: " + ", ".join(
                        f"{item.get('process_name', 'Application')} CPU {item.get('peak_cpu_percent', 0):.1f}%"
                        for item in saved_processes[:3]
                    ))
                else:
                    saved_processes = evidence.get("processes", [])
                if saved_processes and not evidence.get("process_peaks"):
                    top = sorted(saved_processes, key=lambda item: item.get("cpu_percent", 0), reverse=True)[:3]
                    lines.append("  Highest CPU at capture: " + ", ".join(
                        f"{item.get('process_name', 'Application')} {item.get('cpu_percent', 0):.1f}%"
                        for item in top
                    ))
                events = evidence.get("system_events", {}).get("events", [])
                if events:
                    lines.append(f"  Related Windows reliability events: {len(events)}")
        else:
            lines.append("No incidents captured yet. Capture one while a slowdown is happening.")
        self.history_output.setPlainText("\n".join(lines))
        self._navigate(3)

    def _incident_selection_changed(self, *_args) -> None:
        if not hasattr(self, "export_incident_button"):
            return
        incident_id = self.incident_selector.currentData()
        incident = next((item for item in getattr(self, "_incident_cache", []) if item.id == incident_id), None)
        self.export_incident_button.setEnabled(bool(incident and incident.status != "investigating"))

    def _refresh_cached_incident(self) -> None:
        if not self._last_incident:
            return
        for cached in getattr(self, "_incident_cache", []):
            if cached.id == self._last_incident.id:
                cached.status = self._last_incident.status
                cached.resolution_note = self._last_incident.resolution_note
                cached.evidence = self._last_incident.evidence

    def view_incident_evidence(self) -> None:
        incident_id = self.incident_selector.currentData()
        incident = next(
            (item for item in getattr(self, "_incident_cache", []) if item.id == incident_id),
            None,
        )
        if incident is None:
            return
        evidence = incident.evidence or {}
        lines = [
            f"{incident.title}",
            f"Problem: {incident.symptom.replace('_', ' ')} · Status: {incident.status.replace('_', ' ')}",
            f"Captured {incident.started_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} to "
            f"{incident.ended_at.astimezone().strftime('%H:%M:%S %Z')}",
            f"Diagnosis: {incident.diagnosis_category or 'No confirmed anomaly'}",
            "",
            "BEFORE / CAPTURE-WINDOW COMPARISON",
        ]
        comparisons = evidence.get("before_after", [])
        if comparisons:
            lines.extend(
                f"• {item['metric_name']}: "
                f"{item.get('before_median', item.get('before_average', 0)):.2f} → "
                f"{item.get('during_median', item.get('capture_window_average', 0)):.2f} "
                f"{item.get('unit', '')} "
                f"({item.get('change_pct', item.get('change', 0)):+.2f}{'%' if 'change_pct' in item else ''})"
                for item in comparisons
            )
        else:
            lines.append("Not enough saved samples for a before-and-during comparison.")
        lines += ["", "HIGHEST PROCESS ACTIVITY AT CAPTURE"]
        process_peaks = evidence.get("process_peaks", [])
        processes = sorted(evidence.get("processes", []), key=lambda item: item.get("cpu_percent", 0), reverse=True)[:12]
        if process_peaks:
            lines.extend(
                f"• {item['process_name']}: peak CPU {item['peak_cpu_percent']:.1f}% · "
                f"peak memory {item['peak_memory_percent']:.1f}% · {item['samples']} observations"
                for item in process_peaks[:12]
            )
        elif processes:
            lines.extend(
                f"• {item['process_name']} (PID {item['pid']}): CPU {item['cpu_percent']:.1f}% · "
                f"memory {item['memory_percent']:.1f}% · read {self._rate(item.get('read_bytes_per_sec'))} · "
                f"write {self._rate(item.get('write_bytes_per_sec'))} · "
                f"{item.get('network_connection_count') if item.get('network_connection_count') is not None else 'network count unavailable'} active connections"
                for item in processes
            )
        else:
            lines.append("No process observations were saved.")
        lines += ["", "RELATED SYSTEM EVENTS"]
        event_data = evidence.get("system_events", {})
        if event_data.get("events"):
            lines.extend(
                f"• {item.get('time', 'Unknown time')} · Event {item.get('Id', '—')} · "
                f"{item.get('source', 'Windows')} · {item.get('message', '')}"
                for item in event_data["events"]
            )
        else:
            lines.append(event_data.get("reason", "No relevant events were reported."))
        lines += ["", "SAVED ANOMALIES"]
        anomalies = evidence.get("anomalies", [])
        if anomalies:
            lines.extend(f"• {item['category']} · {item['explanation']}" for item in anomalies)
        else:
            lines.append("No baseline-relative deviation was recorded during the capture window.")
        findings = evidence.get("findings", [])
        if findings:
            lines += ["", "INVESTIGATION FINDINGS"]
            lines.extend(f"• {item.get('title', 'Finding')} · {item.get('detail', '')}" for item in findings)
        timeline = evidence.get("timeline", [])
        if timeline:
            lines += ["", "TIMELINE"]
            lines.extend(
                f"• {item.get('timestamp', 'Unknown time')} · {item.get('kind', 'event')} · {item.get('detail', '')}"
                for item in timeline[-50:]
            )

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Incident #{incident.id} evidence")
        dialog.resize(760, 600)
        layout = QVBoxLayout(dialog)
        detail = QPlainTextEdit()
        detail.setReadOnly(True)
        detail.setPlainText("\n".join(lines))
        layout.addWidget(detail, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def generate_report(self) -> None:
        self._run_async("report", self._report_preview_data, self._apply_report_preview)

    def export_selected_incident(self) -> None:
        incident_id = self.incident_selector.currentData()
        incident = next((item for item in getattr(self, "_incident_cache", []) if item.id == incident_id), None)
        if incident is None or incident.status == "investigating":
            return
        default_name = f"Diagnosys-incident-{incident.id}.md"
        selected_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export an incident support bundle",
            default_name,
            "Markdown bundle (*.md);;JSON evidence (*.json)",
        )
        if not selected_path:
            return
        path = Path(selected_path)
        suffix = path.suffix.lower()
        if suffix not in {".md", ".json"}:
            suffix = ".json" if selected_filter.startswith("JSON") else ".md"
            path = path.with_suffix(suffix)
        self._pending_export_path = path
        self._pending_export_format = "json" if suffix == ".json" else "markdown"
        self._pending_export_kind = "incident"
        self._run_async("incident_export", lambda: self._incident_export_previews(incident), self._review_export)

    def _incident_export_previews(self, incident) -> dict[str, str]:
        full = incident.to_dict()
        redacted = self._redact_incident_payload(full)
        return {
            "json_full": json.dumps(full, ensure_ascii=False, indent=2, default=str),
            "json_redacted": json.dumps(redacted, ensure_ascii=False, indent=2, default=str),
            "markdown_full": self._incident_markdown(full),
            "markdown_redacted": self._incident_markdown(redacted),
        }

    @staticmethod
    def _redact_incident_payload(payload: dict) -> dict:
        evidence = payload.get("evidence") or {}
        process_names = {
            str(item.get("process_name", ""))
            for item in evidence.get("process_peaks", [])
            if item.get("process_name")
        }
        sensitive_fields = {"hostname", "username", "entity_id", "target", "server", "ssid", "bssid", "address"}

        def clean(value, parent: str = ""):
            if isinstance(value, dict):
                cleaned = {}
                for key, item in value.items():
                    if key in sensitive_fields:
                        cleaned[key] = "[redacted]"
                    elif key == "pid":
                        cleaned[key] = None
                    elif key == "process_name":
                        cleaned[key] = "Application"
                    elif key == "message":
                        cleaned[key] = "[redacted event details]"
                    elif key == "text":
                        cleaned[key] = "[redacted note]"
                    elif parent == "timeline" and key == "detail":
                        cleaned[key] = "[redacted timeline details]"
                    elif key == "resolution_note":
                        cleaned[key] = "[redacted note]" if item else ""
                    else:
                        cleaned[key] = clean(item, key)
                return cleaned
            if isinstance(value, list):
                return [clean(item, parent) for item in value]
            if isinstance(value, str):
                result = value
                for process_name in sorted(process_names, key=len, reverse=True):
                    result = result.replace(process_name, "Application")
                return result
            return value

        cleaned = clean(payload)
        cleaned["title"] = f"Incident #{payload.get('id')}"
        return cleaned

    @staticmethod
    def _incident_markdown(payload: dict) -> str:
        evidence = payload.get("evidence") or {}
        lines = [
            f"# {payload.get('title', 'Diagnosys incident')}",
            "",
            f"- **Problem:** {payload.get('symptom', 'other').replace('_', ' ')}",
            f"- **Status:** {payload.get('status', 'captured').replace('_', ' ')}",
            f"- **Captured:** {payload.get('started_at', 'unknown')} to {payload.get('ended_at', 'unknown')}",
            f"- **Measurements:** {payload.get('metrics_count', 0)} · **Rule flags:** {payload.get('anomalies_count', 0)}",
            "",
            "## Summary",
            payload.get("summary", "No summary available."),
            "",
            "## Leading areas to check",
        ]
        hypotheses = evidence.get("hypotheses", [])
        lines.extend(
            f"- **{item.get('title', 'Possible area')}** · {item.get('strength', 'Unrated')} — {item.get('basis', '')}"
            for item in hypotheses
        )
        findings = evidence.get("findings", [])
        if findings:
            lines += ["", "## Findings"]
            lines.extend(f"- **{item.get('title', 'Finding')}:** {item.get('detail', '')} ({item.get('strength', '')})" for item in findings)
        comparisons = evidence.get("before_after", [])
        if comparisons:
            lines += ["", "## Compared with the prior window"]
            lines.extend(
                f"- {item.get('metric_name', 'Metric')}: {item.get('before_median', '—')} → {item.get('during_median', '—')} ({item.get('change_pct', 0):+.0f}%)"
                for item in comparisons
            )
        process_peaks = evidence.get("process_peaks", [])
        if process_peaks:
            lines += ["", "## Process activity"]
            lines.extend(
                f"- {item.get('process_name', 'Application')}: CPU {item.get('peak_cpu_percent', 0):.1f}% · memory {item.get('peak_memory_percent', 0):.1f}% · {item.get('samples', 0)} observations"
                for item in process_peaks[:10]
            )
        verification = evidence.get("verification")
        if verification:
            lines += ["", "## After-change verification", verification.get("summary", "Comparison saved.")]
            lines.extend(
                f"- {item.get('metric_name', 'Metric')}: {item.get('before_median', '—')} → {item.get('after_median', '—')} ({item.get('change_pct', 0):+.0f}%)"
                for item in verification.get("comparisons", [])
            )
        events = evidence.get("system_events", {}).get("events", [])
        lines += ["", "## Windows events"]
        if events:
            lines.extend(
                f"- {item.get('time', 'time unavailable')} · Event {item.get('Id', '—')} · {item.get('source', 'Windows')} · {item.get('message', '')}"
                for item in events[:30]
            )
        else:
            lines.append(evidence.get("system_events", {}).get("reason", "No related events were reported."))
        timeline = evidence.get("timeline", [])
        if timeline:
            lines += ["", "## Timeline"]
            lines.extend(f"- {item.get('timestamp', 'time unavailable')} · **{item.get('kind', 'event')}** · {item.get('detail', '')}" for item in timeline[-100:])
        checks = evidence.get("next_checks", [])
        if checks:
            lines += ["", "## Suggested next checks"]
            lines.extend(f"- {step}" for step in checks)
        limitations = evidence.get("limitations", [])
        if limitations:
            lines += ["", "## Limits of this result"]
            lines.extend(f"- {item}" for item in limitations)
        lines += ["", "---", "Diagnosys stores this evidence locally. Time overlap is a clue, not proof of cause."]
        return "\n".join(lines)

    def _report_preview_data(self) -> str:
        connection = self._connection()
        try:
            generator = ReportGenerator(
                MetricRepository(connection), AnomalyRepository(connection), DiagnosticEngine(),
                ProcessRepository(connection), IncidentRepository(connection),
            )
            return generator.format_text(generator.generate_report())
        finally:
            connection.close()

    def _apply_report_preview(self, content: str) -> None:
        self.history_output.setPlainText(content)
        self._navigate(3)

    def export_report(self) -> None:
        default_name = f"Diagnosys-support-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
        selected_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Create a shareable support report",
            default_name,
            "HTML support report (*.html);;Markdown report (*.md);;JSON data (*.json)",
        )
        if not selected_path:
            return

        path = Path(selected_path)
        suffix = path.suffix.lower()
        if suffix not in {".md", ".json", ".html"}:
            suffix = ".json" if selected_filter.startswith("JSON") else ".md" if selected_filter.startswith("Markdown") else ".html"
            path = path.with_suffix(suffix)
        format_name = {".json": "json", ".md": "markdown", ".html": "html"}[suffix]
        self._pending_export_path = path
        self._pending_export_format = format_name
        self._pending_export_kind = "report"
        self._run_async("export", self._export_preview_data, self._review_export)

    def _export_preview_data(self) -> dict[str, str]:
        connection = self._connection()
        try:
            generator = ReportGenerator(
                MetricRepository(connection), AnomalyRepository(connection), DiagnosticEngine(),
                ProcessRepository(connection), IncidentRepository(connection),
            )
            report = generator.generate_report()
            return {
                "html_redacted": generator.format_html(report, redact=True),
                "html_full": generator.format_html(report, redact=False),
                "markdown_redacted": generator.format_markdown(report, redact=True),
                "markdown_full": generator.format_markdown(report, redact=False),
                "json_redacted": generator.format_json(report, redact=True),
                "json_full": generator.format_json(report, redact=False),
            }
        finally:
            connection.close()

    def _review_export(self, previews: dict[str, str]) -> None:
        dialog = QDialog(self)
        is_incident = getattr(self, "_pending_export_kind", "report") == "incident"
        dialog.setWindowTitle("Review incident support bundle" if is_incident else "Review support report")
        dialog.resize(800, 620)
        layout = QVBoxLayout(dialog)
        explanation = QLabel(
            "Review the incident bundle before saving. Sensitive identifiers and notes are removed by default; turn off redaction only if you intend to share device-specific details."
            if is_incident else
            "Review the report before saving. Sensitive identifiers are removed by default; turn off redaction only if you intend to share device-specific details."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        redact = QCheckBox("Redact device, process, event, network identifiers, and notes")
        redact.setChecked(True)
        layout.addWidget(redact)
        preview = QTextBrowser()
        preview.setOpenExternalLinks(False)
        layout.addWidget(preview, 1)

        def render_preview(should_redact: bool) -> None:
            suffix = "redacted" if should_redact else "full"
            content = previews[f"{self._pending_export_format}_{suffix}"]
            if self._pending_export_format == "html":
                preview.setHtml(content)
            else:
                preview.setHtml(f"<pre style='white-space:pre-wrap'>{html.escape(content)}</pre>")

        redact.toggled.connect(render_preview)
        render_preview(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        suffix = "redacted" if redact.isChecked() else "full"
        content = previews[f"{self._pending_export_format}_{suffix}"]
        try:
            self._pending_export_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Report was not saved", str(exc))
            return
        self._report_exported(str(self._pending_export_path))

    def _report_exported(self, path: str) -> None:
        title = "Incident bundle exported" if getattr(self, "_pending_export_kind", "report") == "incident" else "Report exported"
        QMessageBox.information(self, title, f"Your file was saved to:\n{path}")

    def capture_incident(self) -> None:
        title, accepted = QInputDialog.getText(self, "Capture incident", "Incident title:", text="Captured slowdown")
        if not accepted:
            return
        title = title.strip() or "Captured incident"
        self._run_async("capture", lambda: self._capture_incident_data(title), self._incident_captured)

    def _capture_incident_data(self, title: str) -> dict:
        connection = self._connection()
        try:
            metric_repo = MetricRepository(connection)
            all_metrics = metric_repo.query(window_seconds=600)
            now = datetime.now(timezone.utc)
            start = now - timedelta(minutes=5)
            metrics = [item for item in all_metrics if item.timestamp >= start]
            previous_metrics = [item for item in all_metrics if item.timestamp < start]
            anomalies = AnomalyRepository(connection).query(window_seconds=300)
            processes = ProcessRepository(connection).query(window_seconds=300, limit=1000)
            events = recent_system_events(minutes=5)
            diagnosis = DiagnosticEngine().diagnose(anomalies, window_seconds=300)
            category = diagnosis.primary_hypothesis.category if diagnosis.primary_hypothesis else None
            comparison = self._compare_metric_windows(previous_metrics, metrics)
            evidence = {
                "captured_at": now.isoformat(),
                "metrics": [
                    {
                        "timestamp": item.timestamp.isoformat(),
                        "metric_name": item.metric_name,
                        "value": item.value,
                        "unit": item.unit,
                        "source": item.source,
                        "entity_id": item.entity_id,
                        "status": item.status.value,
                        "reason": item.reason,
                    }
                    for item in metrics
                ],
                "anomalies": [
                    {
                        "timestamp": item.timestamp.isoformat(),
                        "category": item.category,
                        "severity": item.severity,
                        "metric": item.metric,
                        "observed_value": item.observed_value,
                        "expected_value": item.expected_value,
                        "explanation": item.explanation,
                    }
                    for item in anomalies
                ],
                "processes": processes,
                "before_after": comparison,
                "system_events": events,
                "diagnosis": {
                    "status": diagnosis.status,
                    "primary_category": category,
                     "recommended_checks": diagnosis.primary_hypothesis.recommended_checks if diagnosis.primary_hypothesis else [],
                },
            }
            incident_id = IncidentRepository(connection).save(
                Incident(
                    None, now - timedelta(minutes=5), now, title,
                    category or "No confirmed anomaly", len(metrics), len(anomalies), category,
                    evidence=evidence,
                )
            )
            return {"id": incident_id, "evidence": evidence}
        finally:
            connection.close()

    def _incident_captured(self, result: dict) -> None:
        evidence = result["evidence"]
        QMessageBox.information(
            self,
            "Incident captured",
            f"Incident #{result['id']} saved with {len(evidence['metrics'])} measurements, "
            f"{len(evidence['processes'])} process observations, and "
            f"{len(evidence['system_events'].get('events', []))} related system events.",
        )
        self.show_history()

    @staticmethod
    def _compare_metric_windows(before: list[MetricSample], during: list[MetricSample]) -> list[dict]:
        comparisons = []
        metric_names = {item.metric_name for item in before + during}
        for name in sorted(metric_names):
            before_values = [
                float(item.value) for item in before
                if item.metric_name == name and item.status == MetricStatus.OK and isinstance(item.value, (int, float))
            ]
            during_values = [
                float(item.value) for item in during
                if item.metric_name == name and item.status == MetricStatus.OK and isinstance(item.value, (int, float))
            ]
            if before_values and during_values:
                before_average = sum(before_values) / len(before_values)
                during_average = sum(during_values) / len(during_values)
                comparisons.append({
                    "metric_name": name,
                    "before_average": round(before_average, 2),
                    "capture_window_average": round(during_average, 2),
                    "change": round(during_average - before_average, 2),
                    "unit": next(item.unit for item in during if item.metric_name == name),
                })
        return comparisons

    @staticmethod
    def _gib(byte_count: int) -> str:
        return f"{byte_count / (1024 ** 3):.1f} GB"

    @classmethod
    def _history_rate(cls, byte_count: float | None) -> str:
        return "not reported" if byte_count is None else cls._rate(byte_count)

    @staticmethod
    def _rate(bytes_per_second: float | None) -> str:
        if bytes_per_second is None:
            return "Measuring…"
        value = max(0.0, bytes_per_second)
        if value < 1024:
            return f"{value:.0f} B/s"
        if value < 1024 ** 2:
            return f"{value / 1024:.1f} KiB/s"
        return f"{value / (1024 ** 2):.1f} MiB/s"

    @staticmethod
    def _frequency(mhz: float | None) -> str:
        return f"{mhz / 1000:.2f} GHz" if mhz else "Unavailable"

    @staticmethod
    def _duration(seconds: float) -> str:
        if seconds <= 0:
            return "Unavailable"
        total_minutes = int(seconds // 60)
        days, remaining_minutes = divmod(total_minutes, 24 * 60)
        hours, minutes = divmod(remaining_minutes, 60)
        if days:
            return f"{days}d {hours}h"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def closeEvent(self, event) -> None:
        if self.settings.keep_in_tray and self.tray_icon is not None and not self._explicit_quit:
            self.hide()
            self.tray_icon.showMessage(
                "Diagnosys is still recording",
                "Open it from the system tray or choose Quit to stop local monitoring.",
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
            event.ignore()
            return
        self.refresh_timer.stop()
        if self._active_investigation is not None:
            marker = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": "capture paused",
                "text": "Diagnosys stopped recording when the app closed.",
            }
            self.incident_repo.add_marker(self._active_investigation.id, marker)
        if self.tray_icon is not None:
            self.tray_icon.hide()
        for thread in tuple(self._threads):
            thread.quit()
        for thread in tuple(self._threads):
            thread.wait(6000)
        self.db.close()
        super().closeEvent(event)
