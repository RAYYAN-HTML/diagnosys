"""Process activity and historical resource usage page."""
from __future__ import annotations

from datetime import datetime, timezone
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)

from diagnosys.models.metrics import ProcessSnapshot


def _table(columns: list[str], height: int = 180) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setMinimumHeight(height)
    return table


def _row(table: QTableWidget, values: list[str]) -> None:
    index = table.rowCount()
    table.insertRow(index)
    for column, value in enumerate(values):
        item = QTableWidgetItem(value)
        item.setToolTip(value)
        table.setItem(index, column, item)


def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("MetricCard")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    heading = QLabel(title)
    heading.setObjectName("CardTitle")
    layout.addWidget(heading)
    return frame, layout


class ProcessesPage(QWidget):
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

        title = QLabel("Processes")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Inspect current resource consumers and their sampled history, including process start time, duration, thread count, and disk I/O where the OS permits access.")
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.availability = QLabel("Waiting for process sample…")
        self.availability.setObjectName("Muted")
        self.availability.setWordWrap(True)
        layout.addWidget(self.availability)

        cpu_panel, cpu_layout = _panel("Highest CPU consumers")
        self.cpu_table = _table(["Process", "PID", "CPU", "Memory", "Threads", "Read / sec", "Write / sec", "Started", "Duration"], 210)
        cpu_layout.addWidget(self.cpu_table)
        layout.addWidget(cpu_panel)

        memory_panel, memory_layout = _panel("Highest memory consumers")
        self.memory_table = _table(["Process", "PID", "Memory", "CPU", "Threads", "Started", "Duration"], 190)
        memory_layout.addWidget(self.memory_table)
        layout.addWidget(memory_panel)

        history_panel, history_layout = _panel("Process resource history")
        self.history_table = _table(["Sample time", "Process", "PID", "CPU", "Memory", "Threads", "Started", "Duration at sample", "Read / sec", "Write / sec"], 250)
        history_layout.addWidget(self.history_table)
        layout.addWidget(history_panel)

        note = QLabel("The list is limited to the highest sampled CPU and memory consumers. Operating-system permissions can hide some process details. High resource use is not evidence that a process is malicious or unsafe.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        scroll.setWidget(root)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def update_data(self, snapshot: ProcessSnapshot, history: list[dict]) -> None:
        now = datetime.now(timezone.utc)
        if snapshot.available:
            self.availability.setText(f"{snapshot.process_count} processes detected. Process history is sampled at the configured interval.")
        else:
            self.availability.setText(snapshot.reason or "Process telemetry unavailable.")
        self.cpu_table.setRowCount(0)
        for process in snapshot.top_cpu:
            _row(self.cpu_table, _process_values(process, now, include_io=True))
        self.memory_table.setRowCount(0)
        for process in snapshot.top_memory:
            _row(self.memory_table, [
                process.name, str(process.pid), f"{process.memory_percent:.1f}%",
                f"{process.cpu_percent:.1f}%",
                str(process.thread_count) if process.thread_count is not None else "Unavailable",
                _started(process.create_time), _duration(process.create_time, now),
            ])
        self.history_table.setRowCount(0)
        for item in history[:100]:
            _row(self.history_table, [
                str(item.get("timestamp", ""))[-14:],
                str(item.get("process_name", "Unknown")),
                str(item.get("pid", "")),
                _percent(item.get("cpu_percent")),
                _percent(item.get("memory_percent")),
                str(item.get("thread_count") if item.get("thread_count") is not None else "Unavailable"),
                _started(item.get("create_time")),
                _duration_at_sample(item.get("create_time"), item.get("timestamp")),
                _rate(item.get("read_bytes_per_sec")),
                _rate(item.get("write_bytes_per_sec")),
            ])


def _process_values(process, now: datetime, include_io: bool) -> list[str]:
    values = [
        process.name, str(process.pid), f"{process.cpu_percent:.1f}%",
        f"{process.memory_percent:.1f}%",
        str(process.thread_count) if process.thread_count is not None else "Unavailable",
    ]
    if include_io:
        values.extend((_rate(process.read_bytes_per_sec), _rate(process.write_bytes_per_sec)))
    values.extend((_started(process.create_time), _duration(process.create_time, now)))
    return values


def _started(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    try:
        return datetime.fromtimestamp(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return "Unavailable"


def _duration(value: float | None, now: datetime) -> str:
    if value is None:
        return "Unavailable"
    try:
        seconds = max(0, now.timestamp() - value)
    except (OverflowError, ValueError):
        return "Unavailable"
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"


def _duration_at_sample(started_at: object, sampled_at: object) -> str:
    if not isinstance(started_at, (int, float)) or not isinstance(sampled_at, str):
        return "Unavailable"
    try:
        stamp = datetime.fromisoformat(sampled_at.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        seconds = max(0, int(stamp.timestamp() - float(started_at)))
    except (OverflowError, OSError, TypeError, ValueError):
        return "Unavailable"
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"


def _percent(value: object) -> str:
    return f"{float(value):.1f}%" if isinstance(value, (int, float)) else "Unavailable"


def _rate(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "Unavailable"
    amount = float(value)
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if amount < 1024 or unit == "GB/s":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} GB/s"
