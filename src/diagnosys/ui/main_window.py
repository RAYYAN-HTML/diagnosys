from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QPoint, QRectF, QSize, QThread, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from diagnosys.collectors.network.rates import NetworkRateCollector
from diagnosys.collectors.system.cpu import CPUCollector
from diagnosys.collectors.system.disk import DiskCollector
from diagnosys.collectors.system.disk_health import DiskHealthCollector, DiskDiscovery, DiskDevice, DiskHealth
from diagnosys.collectors.system.gpu import GPUCollector, GPUMetrics
from diagnosys.collectors.system.gaming import GameSessionCollector
from diagnosys.collectors.system.memory import MemoryCollector
from diagnosys.collectors.system.process import ProcessCollector
from diagnosys.collectors.system.thermal import ThermalCollector
from diagnosys.collectors.system.uptime import UptimeCollector
from diagnosys.config.settings import Settings
from diagnosys.diagnostics.rules import AnomalyDetector
from diagnosys.diagnostics.thermal import ThermalDiagnosticEngine
from diagnosys.models.diagnostics import DiagnosisResult
from diagnosys.models.metrics import MetricSample
from diagnosys.storage.database import get_connection, init_db, prune_db
from diagnosys.storage.incidents import IncidentRepository
from diagnosys.storage.processes import ProcessRepository
from diagnosys.storage.hardware import HardwareHistoryRepository
from diagnosys.storage.gaming import GamingRepository
from diagnosys.storage.repositories import AnomalyRepository, MetricRepository

from .theme.tokens import TOKENS
from .pages.hardware import ThermalPage, DiskHealthPage
from .pages.gaming import GamingPage
from .pages.processes import ProcessesPage
from .pages.performance import PerformancePage
from .pages.overview import build as build_overview
from .pages.network import build as build_network
from .pages.diagnostics import build as build_diagnostics
from .pages.history import build as build_history
from .pages.capabilities import build as build_capabilities
from .pages.settings import build as build_settings
from .tasks import TaskRouter, TaskWorker
from .controllers.investigations import InvestigationController
from .controllers.network import NetworkController
from .controllers.reports import ReportController
from .controllers.monitoring import MonitoringController
from .controllers.history import HistoryController
from . import formatters


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
        self._last_thermal_persist_at = datetime.min.replace(tzinfo=timezone.utc)
        self._last_disk_health_refresh = datetime.min.replace(tzinfo=timezone.utc)
        self._disk_discovery = DiskDiscovery(False, reason="Drive health has not been checked yet.")
        self._disk_health_results: list[tuple[DiskDevice, DiskHealth]] = []
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
        self.thermal = ThermalCollector()
        self.disk_health = DiskHealthCollector()
        self.gaming = GameSessionCollector()

        self.db = get_connection()
        init_db(self.db)
        prune_db(self.db, self.settings.retention_days)
        self.metric_repo = MetricRepository(self.db)
        self.anomaly_repo = AnomalyRepository(self.db)
        self.process_repo = ProcessRepository(self.db)
        self.hardware_repo = HardwareHistoryRepository(self.db)
        self.gaming_repo = GamingRepository(self.db)
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
        self.thermal_diagnostics = ThermalDiagnosticEngine()
        self.investigation_controller = InvestigationController(self)
        self.network_controller = NetworkController(self)
        self.report_controller = ReportController(self)
        self.monitoring_controller = MonitoringController(self)
        self.history_controller = HistoryController(self)
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
        self.nav_icons = ("overview", "network", "diagnosis", "history", "settings", "settings", "thermal", "disk", "gaming", "processes", "performance")
        nav = (
            ("Home", 0),
            ("Network", 1),
            ("Diagnostics", 2),
            ("History & reports", 3),
            ("Capabilities", 4),
            ("Settings", 5),
            ("Thermal", 6),
            ("Disk Health", 7),
            ("Gaming", 8),
            ("Processes", 9),
            ("Performance", 10),
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

        build_overview(self)
        build_network(self)
        build_diagnostics(self)
        build_history(self)
        build_capabilities(self)
        build_settings(self)
        self.thermal_page = ThermalPage()
        self.pages.addWidget(self.thermal_page)
        self.disk_health_page = DiskHealthPage()
        self.pages.addWidget(self.disk_health_page)
        self.gaming_page = GamingPage()
        self.pages.addWidget(self.gaming_page)
        self.process_page = ProcessesPage()
        self.pages.addWidget(self.process_page)
        self.performance_page = PerformancePage()
        self.pages.addWidget(self.performance_page)

    def _navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        labels = ("HOME", "NETWORK HEALTH", "DIAGNOSTICS", "HISTORY & REPORTS", "CAPABILITIES", "SETTINGS", "THERMAL MONITORING", "DISK HEALTH", "GAMING DIAGNOSTICS", "PROCESS ACTIVITY", "PERFORMANCE")
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
        elif name == "thermal":
            painter.drawRoundedRect(QRectF(9, 3, 6, 13), 3, 3)
            painter.drawEllipse(QRectF(7, 14, 10, 10))
            painter.drawLine(QPoint(12, 7), QPoint(12, 17))
        elif name == "disk":
            painter.drawRoundedRect(QRectF(3, 4, 18, 16), 3, 3)
            painter.drawEllipse(QRectF(14, 13, 4, 4))
            painter.drawLine(QPoint(6, 9), QPoint(12, 9))
        elif name == "gaming":
            painter.drawRoundedRect(QRectF(3, 7, 18, 12), 5, 5)
            painter.drawLine(QPoint(7, 13), QPoint(12, 13))
            painter.drawLine(QPoint(9, 10), QPoint(9, 16))
            painter.drawEllipse(QRectF(15, 10, 2, 2))
            painter.drawEllipse(QRectF(18, 13, 2, 2))
        elif name == "processes":
            for y in (4, 10, 16):
                painter.drawRoundedRect(QRectF(4, y, 5, 5), 1, 1)
                painter.drawLine(QPoint(12, y + 2), QPoint(20, y + 2))
        elif name == "performance":
            painter.drawLine(QPoint(3, 20), QPoint(3, 4))
            painter.drawLine(QPoint(3, 20), QPoint(21, 20))
            path = QPainterPath(QPoint(5, 16))
            for point in ((9, 12), (12, 14), (16, 7), (20, 5)):
                path.lineTo(*point)
            painter.drawPath(path)
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








    @staticmethod
    def _network_work(target: str, dns_target: str, dns_server: str | None, http_target: str, timeout: float):
        return NetworkController._network_work(target, dns_target, dns_server, http_target, timeout)

    def network_check(self) -> None:
        return self.network_controller.network_check()

    def inspect_network_path(self) -> None:
        return self.network_controller.inspect_network_path()

    def _apply_network_path(self, result: dict) -> None:
        return self.network_controller._apply_network_path(result)

    def _apply_network(self, results) -> None:
        return self.network_controller._apply_network(results)

    def _open_investigation(self, symptom: str) -> None:
        return self.investigation_controller._open_investigation(symptom)

    def _select_symptom(self, symptom: str) -> None:
        return self.investigation_controller._select_symptom(symptom)

    def _sync_investigation_controls(self) -> None:
        return self.investigation_controller._sync_investigation_controls()

    def _sync_verification_controls(self) -> None:
        return self.investigation_controller._sync_verification_controls()

    def _update_verification_status(self) -> None:
        return self.investigation_controller._update_verification_status()

    def _update_capture_elapsed(self) -> None:
        return self.investigation_controller._update_capture_elapsed()

    def start_investigation(self) -> None:
        return self.investigation_controller.start_investigation()

    def add_investigation_note(self) -> None:
        return self.investigation_controller.add_investigation_note()

    def stop_investigation(self) -> None:
        return self.investigation_controller.stop_investigation()

    def _finish_investigation_data(self, incident, markers: list[dict], sensor_availability: dict[str, str]) -> dict:
        return self.investigation_controller._finish_investigation_data(incident, markers, sensor_availability)

    def _investigation_finished(self, result: dict) -> None:
        return self.investigation_controller._investigation_finished(result)

    def _investigation_html(self, result: dict) -> str:
        return self.investigation_controller._investigation_html(result)

    def set_investigation_resolution(self, status: str) -> None:
        return self.investigation_controller.set_investigation_resolution(status)

    def start_verification(self) -> None:
        return self.investigation_controller.start_verification()

    def compare_verification(self) -> None:
        return self.investigation_controller.compare_verification()

    def _verification_data(self, incident_id: int, started: datetime, before_stats: dict) -> dict:
        return self.investigation_controller._verification_data(incident_id, started, before_stats)

    def _verification_finished(self, verification: dict) -> None:
        return self.investigation_controller._verification_finished(verification)

    @staticmethod
    def _redact_incident_payload(payload: dict) -> dict:
        return formatters.redact_incident_payload(payload)

    @staticmethod
    def _incident_markdown(payload: dict) -> str:
        return formatters.incident_markdown(payload)

    @staticmethod
    def _compare_metric_windows(before: list[MetricSample], during: list[MetricSample]) -> list[dict]:
        return formatters.compare_metric_windows(before, during)

    @staticmethod
    def _gib(byte_count: int) -> str:
        return formatters.gib(byte_count)

    @staticmethod
    def _history_rate(byte_count: float | None) -> str:
        return formatters.history_rate(byte_count)

    @staticmethod
    def _rate(bytes_per_second: float | None) -> str:
        return formatters.rate(bytes_per_second)

    @staticmethod
    def _frequency(mhz: float | None) -> str:
        return formatters.frequency(mhz)

    @staticmethod
    def _duration(seconds: float) -> str:
        return formatters.duration(seconds)

    def _make_detector(self) -> AnomalyDetector:
        # No universal cutoffs: the detector uses sufficiently populated local baselines.
        return AnomalyDetector(baselines=self.metric_repo.get_all_baselines())

    def save_settings(self) -> None:
        try:
            updated = Settings(
                data_dir=self.settings.data_dir,
                refresh_seconds=self.refresh_interval.value(),
                process_history_seconds=self.process_history_interval.value(),
                game_process_names=self.game_process_names.text().strip(),
                retention_days=self.retention_period.value(),
                network_timeout_seconds=self.network_timeout.value(),
                ping_target=self.target.text().strip(),
                dns_target=self.dns_target.text().strip(),
                dns_server=self.dns_server.text().strip(),
                http_target=self.http_target.text().strip(),
                alerts_enabled=self.alerts_enabled.isChecked(),
                keep_in_tray=self.keep_in_tray.isChecked(),
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
        return self.monitoring_controller.refresh()

    def _collect_snapshot(self):
        return self.monitoring_controller._collect_snapshot()

    def _apply_snapshot(self, result) -> None:
        return self.monitoring_controller._apply_snapshot(result)

    def _apply_gpu(self, gpu: GPUMetrics) -> None:
        return self.monitoring_controller._apply_gpu(gpu)

    def _update_processes(self, processes) -> None:
        return self.monitoring_controller._update_processes(processes)

    def _update_insight(self) -> None:
        return self.monitoring_controller._update_insight()

    def _render_insight(self, result: DiagnosisResult) -> None:
        return self.monitoring_controller._render_insight(result)

    def _store_sample(self, sample: MetricSample) -> None:
        return self.monitoring_controller._store_sample(sample)

    def _connection(self):
        return self.monitoring_controller._connection()

    def diagnose(self) -> None:
        return self.monitoring_controller.diagnose()

    def _diagnose_data(self):
        return self.monitoring_controller._diagnose_data()

    def _apply_diagnosis(self, result: DiagnosisResult) -> None:
        return self.monitoring_controller._apply_diagnosis(result)

    def show_capabilities(self) -> None:
        return self.history_controller.show_capabilities()

    def show_history(self) -> None:
        return self.history_controller.show_history()

    def _incident_selection_changed(self, *_args) -> None:
        return self.history_controller._incident_selection_changed(*_args)

    def _refresh_cached_incident(self) -> None:
        return self.history_controller._refresh_cached_incident()

    def view_incident_evidence(self) -> None:
        return self.history_controller.view_incident_evidence()

    def generate_report(self) -> None:
        return self.report_controller.generate_report()

    def export_selected_incident(self) -> None:
        return self.report_controller.export_selected_incident()

    def _incident_export_previews(self, incident) -> dict[str, str]:
        return self.report_controller._incident_export_previews(incident)

    def _report_preview_data(self) -> str:
        return self.report_controller._report_preview_data()

    def _apply_report_preview(self, content: str) -> None:
        return self.report_controller._apply_report_preview(content)

    def export_report(self) -> None:
        return self.report_controller.export_report()

    def _export_preview_data(self) -> dict[str, str]:
        return self.report_controller._export_preview_data()

    def _review_export(self, previews: dict[str, str]) -> None:
        return self.report_controller._review_export(previews)

    def _report_exported(self, path: str) -> None:
        return self.report_controller._report_exported(path)

    def capture_incident(self) -> None:
        return self.report_controller.capture_incident()

    def _capture_incident_data(self, title: str) -> dict:
        return self.report_controller._capture_incident_data(title)

    def _incident_captured(self, result: dict) -> None:
        return self.report_controller._incident_captured(result)

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
