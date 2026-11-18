import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:
    pytest.skip(f"Qt runtime libraries are unavailable: {exc}", allow_module_level=True)

from diagnosys.collectors.system.disk_health import DiskDiscovery
from diagnosys.collectors.system.gaming import GameSessionSnapshot
from diagnosys.collectors.system.thermal import ThermalSnapshot
from diagnosys.models.metrics import ProcessSnapshot
from diagnosys.ui.pages.hardware import DiskHealthPage, ThermalPage
from diagnosys.ui.pages.gaming import GamingPage
from diagnosys.ui.pages.processes import ProcessesPage
from diagnosys.ui.pages.performance import PerformancePage
from diagnosys.ui.pages import overview, network, diagnostics, history, capabilities, settings
from diagnosys.ui.main_window import MainWindow
from diagnosys.config.settings import Settings
from diagnosys.ui.controllers.investigations import InvestigationController
from diagnosys.ui.controllers.network import NetworkController
from diagnosys.ui.controllers.reports import ReportController
from diagnosys.ui.controllers.monitoring import MonitoringController
from diagnosys.ui.controllers.history import HistoryController


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_page_builder_modules_import():
    assert MainWindow is not None
    assert callable(MonitoringController.refresh)
    assert callable(MonitoringController._apply_snapshot)
    assert callable(MonitoringController._diagnose_data)
    assert callable(HistoryController.show_history)
    assert callable(HistoryController.view_incident_evidence)
    assert all(callable(module.build) for module in (
        overview, network, diagnostics, history, capabilities, settings,
    ))


def test_hardware_and_activity_pages_render_unavailable_states(qt_app):
    thermal = ThermalPage()
    thermal.update_data(
        ThermalSnapshot(False, reason="No temperature sensors exposed."),
        [], None, datetime.now(timezone.utc),
    )
    assert "unavailable" in thermal.cpu_status.text().casefold()

    disk = DiskHealthPage()
    disk.update_data(
        DiskDiscovery(False, reason="smartctl is missing.", state="tool_missing"),
        [], [], datetime.now(timezone.utc),
    )
    assert "tool missing" in disk.status.text().casefold()

    gaming = GamingPage()
    gaming.update_data(
        [], GameSessionSnapshot(False, reason="No game processes configured."),
        [], [], ProcessSnapshot(datetime.now(timezone.utc), 0, [], [], available=False, reason="Process data unavailable."),
    )
    assert "no game processes configured" in gaming.session_note.text().casefold()

    performance = PerformancePage()
    from diagnosys.collectors.system.gpu import GPUMetrics
    from diagnosys.collectors.network.rates import NetworkRateMetrics
    from diagnosys.models.metrics import CPUMetrics, MemoryMetrics, DiskMetrics
    performance.update_data(
        CPUMetrics(0.0, [], None, None, available=False, reason="CPU unavailable"),
        MemoryMetrics(0, 0, 0, 0.0, None, available=False, reason="Memory unavailable"),
        DiskMetrics(0, 0, 0.0, 0.0, 0.0, None, available=False, reason="Disk unavailable"),
        GPUMetrics(available=False, reason="GPU unavailable"),
        NetworkRateMetrics(None, None, available=False, reason="Network unavailable"),
        [],
    )

    processes = ProcessesPage()
    processes.update_data(
        ProcessSnapshot(datetime.now(timezone.utc), 0, [], [], available=False, reason="Permission denied."),
        [],
    )
    assert "permission denied" in processes.availability.text().casefold()


def test_ui_controllers_delegate_state_to_main_window():
    window = SimpleNamespace(shared_state="before")
    for controller_type in (InvestigationController, NetworkController, ReportController):
        controller = controller_type(window)
        controller.shared_state = "after"
        assert window.shared_state == "after"
        assert controller.shared_state == "after"



def test_process_page_displays_historical_lifetime_without_fabricating_values(qt_app):
    from diagnosys.models.metrics import ProcessInfo

    page = ProcessesPage()
    sampled_at = datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc).isoformat()
    process = ProcessInfo(
        pid=4321,
        name="example-game",
        username=None,
        cpu_percent=22.5,
        memory_percent=8.0,
        read_bytes_per_sec=None,
        write_bytes_per_sec=4096.0,
        thread_count=24,
        create_time=datetime(2026, 11, 18, 23, 0, tzinfo=timezone.utc).timestamp(),
    )
    page.update_data(
        ProcessSnapshot(datetime.now(timezone.utc), 1, [process], [process]),
        [{
            "timestamp": sampled_at,
            "pid": 4321,
            "process_name": "example-game",
            "cpu_percent": 22.5,
            "memory_percent": 8.0,
            "thread_count": 24,
            "create_time": process.create_time,
            "read_bytes_per_sec": None,
            "write_bytes_per_sec": 4096.0,
        }],
    )

    assert page.cpu_table.rowCount() == 1
    assert page.cpu_table.item(0, 4).text() == "24"
    assert page.cpu_table.item(0, 5).text() == "Unavailable"
    assert page.history_table.rowCount() == 1
    assert page.history_table.item(0, 5).text() == "24"
    assert page.history_table.item(0, 6).text() != "Unavailable"
    assert page.history_table.item(0, 7).text() == "1h 0m"
    assert page.history_table.item(0, 8).text() == "Unavailable"
    assert page.history_table.item(0, 9).text() == "4.0 KB/s"



def test_main_window_initializes_and_navigates_all_pages(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        Settings,
        "from_env",
        classmethod(lambda cls: Settings(data_dir=tmp_path)),
    )
    monkeypatch.setattr(MonitoringController, "refresh", lambda self: None)

    window = MainWindow()

    assert window.pages.count() == 11
    assert len(window.nav_buttons) == 11
    assert not hasattr(window, "investigation_question")
    assert not hasattr(window, "ask_investigation_button")
    for index in range(window.pages.count()):
        window._navigate(index)
        assert window.pages.currentIndex() == index

    window.close()
