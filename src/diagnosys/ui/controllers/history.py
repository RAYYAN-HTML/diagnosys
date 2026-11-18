"""History, incident evidence, and capability presentation workflows."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout

from diagnosys.core.capabilities import runtime_info
from diagnosys.storage.incidents import IncidentRepository
from diagnosys.storage.processes import ProcessRepository
from diagnosys.storage.repositories import AnomalyRepository, MetricRepository


class HistoryController:
    """Own history and incident evidence presentation while sharing app state."""

    def __init__(self, window):
        self.window = window

    def __getattr__(self, name):
        return getattr(self.window, name)

    def __setattr__(self, name, value):
        if name == "window":
            object.__setattr__(self, name, value)
        else:
            setattr(self.window, name, value)


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
