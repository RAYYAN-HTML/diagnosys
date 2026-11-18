"""Incident capture and report export workflows."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QInputDialog,
    QLabel, QMessageBox, QTextBrowser, QVBoxLayout,
)

from diagnosys.collectors.system.events import recent_system_events
from diagnosys.diagnostics.engine import DiagnosticEngine
from diagnosys.models.incidents import Incident
from diagnosys.reports.generator import ReportGenerator
from diagnosys.storage.incidents import IncidentRepository
from diagnosys.storage.processes import ProcessRepository
from diagnosys.storage.repositories import AnomalyRepository, MetricRepository


class ReportController:
    """Own capture/export flows while delegating shared app state to MainWindow."""

    def __init__(self, window):
        self.window = window

    def __getattr__(self, name):
        return getattr(self.window, name)

    def __setattr__(self, name, value):
        if name == "window":
            object.__setattr__(self, name, value)
        else:
            setattr(self.window, name, value)


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


