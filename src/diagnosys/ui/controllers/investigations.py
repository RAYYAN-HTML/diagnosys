"""Investigation and verification workflows for the desktop application."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html

from PySide6.QtWidgets import QInputDialog

from diagnosys.diagnostics.investigation import InvestigationEngine, SYMPTOMS
from diagnosys.models.metrics import MetricStatus
from diagnosys.storage.incidents import IncidentRepository
from diagnosys.storage.processes import ProcessRepository
from diagnosys.storage.repositories import AnomalyRepository, MetricRepository


class InvestigationController:
    """Own investigation workflows while delegating application state to MainWindow."""

    def __init__(self, window):
        self.window = window

    def __getattr__(self, name):
        return getattr(self.window, name)

    def __setattr__(self, name, value):
        if name == "window":
            object.__setattr__(self, name, value)
        else:
            setattr(self.window, name, value)


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
        self._sync_verification_controls()


