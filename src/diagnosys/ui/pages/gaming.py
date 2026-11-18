"""Dedicated game-session diagnostics page."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)

from diagnosys.collectors.system.gaming import GameSessionSnapshot
from diagnosys.models.metrics import ProcessSnapshot


def _table(columns: list[str], height: int = 190) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setMinimumHeight(height)
    return table


def _add_row(table: QTableWidget, values: list[str]) -> None:
    row = table.rowCount()
    table.insertRow(row)
    for column, value in enumerate(values):
        item = QTableWidgetItem(value)
        item.setToolTip(value)
        table.setItem(row, column, item)


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


class GamingPage(QWidget):
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

        title = QLabel("Gaming diagnostics")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Track user-selected game processes, session history, resource activity, and background load. Diagnosys does not invent FPS or frame-time measurements.")
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.configuration = QLabel("No game processes configured.")
        self.configuration.setObjectName("Muted")
        self.configuration.setWordWrap(True)
        layout.addWidget(self.configuration)

        session_panel, session_layout = _panel("Gaming sessions")
        self.sessions_table = _table([
            "Game process", "Started", "Ended", "Samples", "Peak process CPU",
            "Peak memory", "Average system CPU", "Average GPU",
        ], 210)
        session_layout.addWidget(self.sessions_table)
        layout.addWidget(session_panel)

        self.session_note = QLabel("Session comparisons appear after game processes are sampled.")
        self.session_note.setObjectName("Muted")
        self.session_note.setWordWrap(True)
        layout.addWidget(self.session_note)

        sample_panel, sample_layout = _panel("Recent game process activity")
        self.samples_table = _table([
            "Time", "Process", "CPU", "Memory", "Threads", "Read / sec",
            "Write / sec", "System CPU", "GPU", "GPU temp",
        ], 220)
        sample_layout.addWidget(self.samples_table)
        layout.addWidget(sample_panel)

        background_panel, background_layout = _panel("Other active CPU consumers")
        self.background_table = _table(["Process", "CPU", "Memory"], 160)
        background_layout.addWidget(self.background_table)
        layout.addWidget(background_panel)

        note = QLabel("CPU and GPU utilization are comparative observations, not proof of a bottleneck. FPS and frame-time are unavailable unless a supported telemetry source is added. Process activity alone does not indicate malicious behavior.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        scroll.setWidget(root)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def update_data(
        self,
        configured_names: list[str],
        snapshot: GameSessionSnapshot,
        sessions: list[dict],
        samples: list[dict],
        processes: ProcessSnapshot,
    ) -> None:
        self.configuration.setText(
            "Monitoring configured processes: " + ", ".join(configured_names)
            if configured_names else "No game processes configured. Add executable names in Settings to enable session tracking."
        )
        self.sessions_table.setRowCount(0)
        for item in sessions:
            _add_row(self.sessions_table, [
                str(item.get("process_name", "Unknown")),
                str(item.get("started_at", ""))[-14:],
                str(item.get("ended_at") or "Active")[-14:] if item.get("ended_at") else "Active",
                str(item.get("sample_count") or 0),
                _percent(item.get("peak_process_cpu_percent")),
                _percent(item.get("peak_memory_percent")),
                _percent(item.get("average_system_cpu_percent")),
                _percent(item.get("average_gpu_utilization_percent")),
            ])

        self.samples_table.setRowCount(0)
        for item in reversed(samples[-100:]):
            _add_row(self.samples_table, [
                str(item.get("timestamp", ""))[-14:],
                str(item.get("process_name", "")),
                _percent(item.get("cpu_percent")),
                _percent(item.get("memory_percent")),
                str(item.get("thread_count") if item.get("thread_count") is not None else "Unavailable"),
                _rate(item.get("read_bytes_per_sec")),
                _rate(item.get("write_bytes_per_sec")),
                _percent(item.get("system_cpu_percent")),
                _percent(item.get("gpu_utilization_percent")),
                f"{item['gpu_temperature_c']:.1f} °C" if item.get("gpu_temperature_c") is not None else "Unavailable",
            ])

        if snapshot.available:
            detail = (
                f"{len(snapshot.processes)} configured game process instance(s) are currently visible. "
                "Session start and end times are inferred from observed process presence."
            )
            if snapshot.reason:
                detail += " " + snapshot.reason
            self.session_note.setText(detail)
        else:
            self.session_note.setText(snapshot.reason or "No configured game process is currently running.")

        self.background_table.setRowCount(0)
        game_names = {name.casefold() for name in configured_names}
        if processes.available:
            for process in processes.top_cpu:
                if process.name.casefold() in game_names:
                    continue
                _add_row(self.background_table, [
                    process.name, f"{process.cpu_percent:.1f}%", f"{process.memory_percent:.1f}%",
                ])
        else:
            self.session_note.setToolTip(processes.reason or "System process telemetry unavailable.")

        active = next((item for item in sessions if item.get("ended_at") is None), None)
        if active and active.get("average_system_cpu_percent") is not None and active.get("average_gpu_utilization_percent") is not None:
            cpu = float(active["average_system_cpu_percent"])
            gpu = float(active["average_gpu_utilization_percent"])
            if cpu > gpu:
                comparison = "System CPU utilization averaged above GPU utilization in this session."
            elif gpu > cpu:
                comparison = "GPU utilization averaged above system CPU utilization in this session."
            else:
                comparison = "System CPU and GPU utilization averages were equal in this session."
            self.session_note.setText(
                self.session_note.text() + " " + comparison
                + " This comparison alone cannot establish a bottleneck."
            )


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
