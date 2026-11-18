"""Dedicated thermal and drive-health pages."""
from __future__ import annotations

from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)

from diagnosys.collectors.system.disk_health import DiskDiscovery, DiskHealth, DiskDevice
from diagnosys.collectors.system.thermal import ThermalSnapshot


def _page(title: str, subtitle: str) -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet("background: transparent;")
    scroll.viewport().setAutoFillBackground(False)
    root = QWidget()
    root.setObjectName("DashboardPage")
    root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(3, 8, 8, 18)
    layout.setSpacing(14)
    heading = QLabel(title)
    heading.setObjectName("PageTitle")
    description = QLabel(subtitle)
    description.setObjectName("Subtitle")
    description.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(description)
    scroll.setWidget(root)
    return scroll, layout


def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("MetricCard")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    label = QLabel(title)
    label.setObjectName("CardTitle")
    layout.addWidget(label)
    return frame, layout


def _table(columns: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setMinimumHeight(170)
    return table


def _set_row(table: QTableWidget, values: list[str]) -> None:
    row = table.rowCount()
    table.insertRow(row)
    for column, value in enumerate(values):
        item = QTableWidgetItem(value)
        item.setToolTip(value)
        if column > 0 and value.replace(".", "", 1).isdigit():
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row, column, item)


class ThermalPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        scroll, _ = _page(
            "Thermal monitoring",
            "Live sensor and fan readings with their availability and recent history. Sensor values are shown only when the operating system exposes them.",
        )
        root = scroll.widget().layout()
        summary = QHBoxLayout()
        self.cpu_status = QLabel("CPU sensors: checking")
        self.gpu_status = QLabel("GPU temperature: checking")
        self.fan_status = QLabel("Fan sensors: checking")
        self.freshness = QLabel("Last sensor sample: waiting")
        self.freshness.setObjectName("Muted")
        for label in (self.cpu_status, self.gpu_status, self.fan_status):
            label.setObjectName("Muted")
            summary.addWidget(label, 1)
        root.addLayout(summary)
        root.addWidget(self.freshness)

        current_panel, current_layout = _panel("Current sensors")
        self.current_table = _table(["Sensor", "Reading", "Hardware high", "Hardware critical", "Type"])
        current_layout.addWidget(self.current_table)
        root.addWidget(current_panel)

        trend_panel, trend_layout = _panel("Recent thermal history")
        self.history_note = QLabel("History will appear after sensor readings are collected.")
        self.history_note.setObjectName("Muted")
        self.history_note.setWordWrap(True)
        trend_layout.addWidget(self.history_note)
        self.history_table = _table(["Time", "Sensor", "Reading", "Type"])
        trend_layout.addWidget(self.history_table)
        root.addWidget(trend_panel)
        root.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def update_data(self, snapshot: ThermalSnapshot, history: list[dict], gpu_temperature: float | None, sampled_at: datetime | None = None) -> None:
        self.current_table.setRowCount(0)
        stamp = sampled_at.astimezone().strftime("%H:%M:%S") if sampled_at else "unknown"
        self.freshness.setText(f"Last sensor sample: {stamp} · refresh follows the configured monitor interval")
        cpu_sensors = [item for item in snapshot.temperatures if any(
            token in (item.sensor + " " + item.label).casefold()
            for token in ("cpu", "coretemp", "k10temp", "zenpower", "cpu_thermal")
        )]
        if cpu_sensors:
            self.cpu_status.setText(f"CPU sensors: {len(cpu_sensors)} available")
        else:
            self.cpu_status.setText("CPU sensors: unavailable or not identifiable")
        self.gpu_status.setText(
            f"GPU temperature: {gpu_temperature:.1f} °C" if gpu_temperature is not None
            else "GPU temperature: unavailable"
        )
        self.fan_status.setText(
            f"Fan sensors: {len(snapshot.fans)} available" if snapshot.fans
            else "Fan sensors: unavailable"
        )
        for item in snapshot.temperatures:
            _set_row(self.current_table, [
                item.label, f"{item.temperature_c:.1f} °C" if item.temperature_c is not None else "Unavailable",
                f"{item.high_c:.1f} °C" if item.high_c is not None else "Not exposed",
                f"{item.critical_c:.1f} °C" if item.critical_c is not None else "Not exposed",
                "Temperature",
            ])
        if gpu_temperature is not None and not any("gpu" in (item.sensor + item.label).casefold() for item in snapshot.temperatures):
            _set_row(self.current_table, ["GPU telemetry", f"{gpu_temperature:.1f} °C", "Not exposed", "Not exposed", "GPU temperature"])
        for item in snapshot.fans:
            _set_row(self.current_table, [
                item.label, f"{item.speed_rpm:.0f} RPM" if item.speed_rpm is not None else "Unavailable",
                "Not applicable", "Not applicable", "Fan speed",
            ])
        if not snapshot.available and gpu_temperature is None:
            self.history_note.setText(snapshot.reason or "No thermal sensors are available on this device.")
        else:
            self.history_note.setText("Temperature history is device-specific. Hardware-provided high and critical limits are shown only when supplied by the sensor.")
        self.history_table.setRowCount(0)
        for item in history[-100:]:
            is_fan = item.get("reading_kind") == "fan_rpm"
            value = item.get("fan_speed_rpm") if is_fan else item.get("temperature_c")
            unit = "RPM" if is_fan else "°C"
            rendered = f"{value:.1f} {unit}" if isinstance(value, (int, float)) else "Unavailable"
            _set_row(self.history_table, [
                str(item.get("timestamp", ""))[-14:], str(item.get("label") or item.get("sensor") or "Sensor"),
                rendered, str(item.get("reading_kind", "temperature")).replace("_", " ").title(),
            ])


class DiskHealthPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        scroll, _ = _page(
            "Disk health",
            "Read-only SMART and NVMe health information. Missing data is not interpreted as a healthy drive.",
        )
        root = scroll.widget().layout()
        self.status = QLabel("Checking smartctl availability…")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        panel, panel_layout = _panel("Discovered drives")
        self.table = _table([
            "Device", "Protocol", "Health", "Temperature", "Wear", "Available spare", "Power-on hours", "Errors / warnings",
        ])
        panel_layout.addWidget(self.table)
        root.addWidget(panel)
        history_panel, history_layout = _panel("Recent drive-health history")
        self.history_table = _table(["Time", "Device", "State", "Health", "Temperature", "Reason"])
        history_layout.addWidget(self.history_table)
        root.addWidget(history_panel)
        note = QLabel("SMART support depends on the drive, controller, enclosure, operating system, permissions, and optional smartmontools installation. A missing or unsupported SMART result is shown as unknown, never healthy.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def update_data(self, discovery: DiskDiscovery, results: list[tuple[DiskDevice, DiskHealth]], history: list[dict], checked_at: datetime | None = None) -> None:
        self.table.setRowCount(0)
        if not discovery.available:
            self.status.setText(f"{discovery.state.replace('_', ' ').title()}: {discovery.reason or 'Drive health discovery is unavailable.'}")
        else:
            self.status.setText(f"Discovered {len(discovery.devices)} drive(s). Health values reflect only data actually returned by the device.")
        if checked_at:
            self.status.setText(self.status.text() + f" Last checked {checked_at.astimezone().strftime('%H:%M:%S')}.")
        for device, health in results:
            errors = []
            if health.critical_warning not in (None, 0):
                errors.append(f"NVMe critical warning {health.critical_warning}")
            if health.media_errors not in (None, 0):
                errors.append(f"{health.media_errors} media errors")
            if health.reallocated_sectors not in (None, 0):
                errors.append(f"{health.reallocated_sectors} reallocated sectors")
            _set_row(self.table, [
                device.device, device.protocol or "Unknown", health.health_status,
                f"{health.temperature_c:.1f} °C" if health.temperature_c is not None else "Unavailable",
                f"{health.percentage_used:.1f}%" if health.percentage_used is not None else "Unavailable",
                f"{health.available_spare_percent:.1f}%" if health.available_spare_percent is not None else "Unavailable",
                str(health.power_on_hours) if health.power_on_hours is not None else "Unavailable",
                ", ".join(errors) if errors else (health.reason or "No reported indicators"),
            ])
        self.history_table.setRowCount(0)
        for item in history[:100]:
            _set_row(self.history_table, [
                str(item.get("timestamp", ""))[-14:], str(item.get("device", "")),
                str(item.get("state", "unknown")), str(item.get("health_status", "UNKNOWN")),
                f"{item['temperature_c']:.1f} °C" if item.get("temperature_c") is not None else "Unavailable",
                str(item.get("reason") or "No additional detail"),
            ])
