"""Performance overview and resource history page."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)

from diagnosys.ui.components import SummaryCard


class PerformancePage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
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

        title = QLabel("Performance")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Live resource activity and recent measurements. Values are observations, not a universal health rating.")
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(10)
        self.cpu = SummaryCard("CPU", "Checking", "Utilization and clock")
        self.memory = SummaryCard("Memory", "Checking", "Physical memory use")
        self.disk = SummaryCard("Disk activity", "Checking", "Read and write throughput")
        self.gpu = SummaryCard("GPU", "Checking", "Vendor telemetry where supported")
        self.network = SummaryCard("Network", "Checking", "Interface throughput")
        cards.addWidget(self.cpu, 0, 0)
        cards.addWidget(self.memory, 0, 1)
        cards.addWidget(self.disk, 1, 0)
        cards.addWidget(self.gpu, 1, 1)
        cards.addWidget(self.network, 2, 0, 1, 2)
        layout.addLayout(cards)

        history_title = QLabel("Recent performance measurements")
        history_title.setObjectName("CardTitle")
        layout.addWidget(history_title)
        self.history = QTableWidget(0, 5)
        self.history.setHorizontalHeaderLabels(["Time", "Metric", "Value", "Unit", "Source"])
        self.history.setAlternatingRowColors(True)
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history.verticalHeader().setVisible(False)
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history.setMinimumHeight(260)
        layout.addWidget(self.history)

        note = QLabel("Unavailable measurements are omitted or marked unavailable. Disk and network rates require successive samples. A high utilization reading is not by itself a diagnosis.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        scroll.setWidget(root)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def update_data(self, cpu, memory, disk, gpu, network, history: list) -> None:
        self.cpu.set_value(
            f"{cpu.utilization_percent:.1f}%" if cpu.available else "Unavailable",
            f"{_frequency(cpu.frequency_mhz)} · {len(cpu.per_core_utilization_percent)} logical CPU readings"
            if cpu.available else cpu.reason or "CPU telemetry unavailable",
        )
        self.memory.set_value(
            f"{memory.percent_used:.1f}%" if memory.available else "Unavailable",
            f"{_bytes(memory.used_bytes)} used of {_bytes(memory.total_bytes)}"
            if memory.available else memory.reason or "Memory telemetry unavailable",
        )
        self.disk.set_value(
            f"Read {_rate(disk.read_bytes_per_sec)} · Write {_rate(disk.write_bytes_per_sec)}"
            if disk.available else "Unavailable",
            f"{disk.percent_used:.1f}% of primary volume used · {_bytes(disk.free_bytes)} free"
            if disk.available else disk.reason or "Disk telemetry unavailable",
        )
        self.gpu.set_value(
            f"{gpu.utilization_percent:.1f}%" if gpu.available and gpu.utilization_percent is not None
            else "Unavailable",
            f"{gpu.name or 'GPU'} · {gpu.temperature_c:.1f} °C" if gpu.available and gpu.temperature_c is not None
            else gpu.name or gpu.reason or "GPU telemetry unavailable",
        )
        self.network.set_value(
            f"↓ {_rate(network.download_bytes_per_sec)} · ↑ {_rate(network.upload_bytes_per_sec)}"
            if network.available and network.download_bytes_per_sec is not None and network.upload_bytes_per_sec is not None
            else "Waiting for successive samples" if network.available
            else "Unavailable",
            network.reason or "Aggregate interface throughput",
        )

        labels = {
            "cpu_percent": "CPU utilization",
            "cpu_frequency_mhz": "CPU frequency",
            "cpu_temperature_c": "CPU temperature",
            "memory_percent": "Memory utilization",
            "disk_read_bytes_per_sec": "Disk read rate",
            "disk_write_bytes_per_sec": "Disk write rate",
            "gpu_percent": "GPU utilization",
            "gpu_temperature_c": "GPU temperature",
            "network_download_bytes_per_sec": "Network download rate",
            "network_upload_bytes_per_sec": "Network upload rate",
        }
        self.history.setRowCount(0)
        filtered = sorted(
            (item for item in history if item.metric_name in labels),
            key=lambda item: item.timestamp,
        )
        for sample in filtered[-150:]:
            row = self.history.rowCount()
            self.history.insertRow(row)
            if sample.value is None:
                value = "Unavailable"
            elif isinstance(sample.value, (int, float)):
                value = f"{sample.value:.2f}"
            else:
                value = str(sample.value)
            values = [
                sample.timestamp.astimezone().strftime("%H:%M:%S"),
                labels[sample.metric_name], value, sample.unit, sample.source,
            ]
            for column, text in enumerate(values):
                self.history.setItem(row, column, QTableWidgetItem(text))


def _bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"


def _rate(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return _bytes(int(max(0.0, value))) + "/s"


def _frequency(value: float | None) -> str:
    return f"{value / 1000:.2f} GHz" if value is not None else "Clock unavailable"
