import json
import html
import platform
import socket
import getpass
from dataclasses import asdict
from datetime import datetime, timezone

from diagnosys.models.reports import DiagnosticReport
from diagnosys.storage.repositories import MetricRepository, AnomalyRepository
from diagnosys.diagnostics.engine import DiagnosticEngine
from diagnosys.storage.incidents import IncidentRepository
from diagnosys.storage.processes import ProcessRepository

class ReportGenerator:
    def __init__(
        self,
        metric_repo: MetricRepository,
        anomaly_repo: AnomalyRepository,
        diag_engine: DiagnosticEngine,
        process_repo: ProcessRepository | None = None,
        incident_repo: IncidentRepository | None = None,
    ):
        self.metric_repo = metric_repo
        self.anomaly_repo = anomaly_repo
        self.diag_engine = diag_engine
        self.process_repo = process_repo
        self.incident_repo = incident_repo

    @staticmethod
    def _rate(value: float | None) -> str:
        if value is None:
            return "not reported"
        if value < 1024:
            return f"{value:.0f} B/s"
        if value < 1024 ** 2:
            return f"{value / 1024:.1f} KiB/s"
        return f"{value / (1024 ** 2):.1f} MiB/s"

    def generate_report(self) -> DiagnosticReport:
        baselines_dict = self.metric_repo.get_all_baselines()
        baselines = list(baselines_dict.values())
        
        # Anomalies from last 24 hours
        end_time = datetime.now(timezone.utc)
        anomalies = self.anomaly_repo.query(window_seconds=86400)
        
        # Latest diagnoses
        diag_result = self.diag_engine.diagnose(anomalies, window_seconds=86400)
        
        system_info = {
            "os": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
            "username": getpass.getuser(),
        }
        
        return DiagnosticReport(
            timestamp=end_time,
            system_info=system_info,
            baselines=baselines,
            recent_anomalies=anomalies,
            diagnoses=diag_result,
            process_activity=self.process_repo.top_processes(window_seconds=86400, limit=10) if self.process_repo else [],
            recent_incidents=[incident.to_dict() for incident in self.incident_repo.query(limit=5)] if self.incident_repo else [],
        )

    def format_text(self, report: DiagnosticReport) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append(f" DIAGNOSYS REPORT - {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append("=" * 60)
        
        lines.append("\n[ SYSTEM INFO ]")
        for k, v in report.system_info.items():
            lines.append(f"  {k}: {v}")
            
        lines.append("\n[ BASELINES ]")
        if not report.baselines:
            lines.append("  No baselines available.")
        for b in report.baselines:
            lines.append(f"  {b.metric_name}: p95={b.p95:.2f} median={b.median:.2f} (samples={b.sample_count})")
            
        lines.append("\n[ DIAGNOSES ]")
        if not report.diagnoses.primary_hypothesis:
            lines.append("  System appears healthy. No critical issues detected.")
        else:
            h = report.diagnoses.primary_hypothesis
            lines.append(f"  Primary: {h.category} (Score: {h.score:.2f})")
            lines.append(f"  Confidence: {h.confidence}")
            for evidence in h.evidence:
                lines.append(
                    f"  Evidence: {evidence.metric} = {evidence.observed_value:.1f} "
                    f"(threshold {evidence.expected_value:.1f})"
                )
            if h.recommended_checks:
                lines.append(f"     Recommendations:")
                for rec in h.recommended_checks:
                    lines.append(f"       - {rec}")
            if h.limitations:
                lines.append("     Limitations:")
                for limitation in h.limitations:
                    lines.append(f"       - {limitation}")
            
            for idx, h in enumerate(report.diagnoses.alternatives, 1):
                lines.append(f"  Alternative {idx}: {h.category} (Score: {h.score:.2f})")
                        
        lines.append("\n[ RECENT ANOMALIES ]")
        if not report.recent_anomalies:
            lines.append("  None in the last 24 hours.")
        else:
            for anomaly in report.recent_anomalies:
                lines.append(
                    f"  {anomaly.category} · {anomaly.metric}: {anomaly.observed_value:.1f} "
                    f"(threshold {anomaly.expected_value:.1f}) · {anomaly.explanation}"
                )

        return "\n".join(lines)

    @staticmethod
    def _report_payload(report: DiagnosticReport, redact: bool) -> dict:
        payload = asdict(report)
        if not redact:
            return payload

        sensitive = {
            "hostname", "username", "process_name", "pid", "entity_id", "target", "server",
            "ssid", "bssid", "message", "title", "text", "resolution_note",
        }

        def clean(value, key: str = "", parent_key: str = ""):
            if isinstance(value, dict):
                return {name: clean(item, name, key) for name, item in value.items()}
            if isinstance(value, list):
                return [clean(item, key, parent_key) for item in value]
            if key == "title" and parent_key not in {"recent_incidents", "incidents"}:
                return value
            if key in sensitive:
                if key == "pid":
                    return None
                if key == "process_name":
                    return "Application"
                if key == "message":
                    return "[redacted event details]"
                if key in {"text", "resolution_note"}:
                    return "[redacted note]"
                if key == "title":
                    return "[redacted incident title]"
                return "[redacted]"
            return value

        return clean(payload)

    def format_json(self, report: DiagnosticReport, redact: bool = False) -> str:
        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "value"):
                return obj.value
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            return str(obj)
            
        return json.dumps(self._report_payload(report, redact), default=default_serializer, indent=2)

    def format_markdown(self, report: DiagnosticReport, redact: bool = False) -> str:
        lines = []
        lines.append(f"# Diagnosys Report")
        lines.append(f"Generated at: `{report.timestamp.isoformat()}`\n")
        
        lines.append("## System Information")
        for k, v in report.system_info.items():
            if redact and k in {"hostname", "username"}:
                v = "[redacted]"
            lines.append(f"- **{k}**: {v}")
        lines.append("")
        
        lines.append("## Baselines")
        if not report.baselines:
            lines.append("No baselines available.\n")
        else:
            lines.append("| Metric | p95 | Median | Samples |")
            lines.append("|---|---|---|---|")
            for b in report.baselines:
                lines.append(f"| {b.metric_name} | {b.p95:.2f} | {b.median:.2f} | {b.sample_count} |")
            lines.append("")

        lines.append("## Process activity · last 24 hours")
        if not report.process_activity:
            lines.append("No process history is available yet.\n")
        else:
            lines.append("| Application | Peak CPU | Peak memory | Peak disk read/write | Active connections | Samples |")
            lines.append("|---|---:|---:|---:|---:|---:|")
            for item in report.process_activity:
                name = "Application" if redact else item["process_name"]
                lines.append(
                    f"| {name} | {item['peak_cpu_percent']:.1f}% | "
                    f"{item['peak_memory_percent']:.1f}% | "
                    f"{self._rate(item.get('peak_read_bytes_per_sec'))} / "
                    f"{self._rate(item.get('peak_write_bytes_per_sec'))} | "
                    f"{item.get('peak_network_connections') or 0} | {item['samples']} |"
                )
            lines.append("")
            
        lines.append("## Diagnoses")
        if not report.diagnoses.primary_hypothesis:
            lines.append("System appears healthy. No critical issues detected.")
        else:
            h = report.diagnoses.primary_hypothesis
            lines.append(f"### Primary: {h.category.replace('_', ' ').title()}")
            lines.append(f"Confidence: {h.confidence} · Score: {h.score:.2f}\n")
            if h.evidence:
                lines.append("**Supporting evidence:**")
                for item in h.evidence:
                    lines.append(
                        f"- {item.metric.replace('_', ' ')}: {item.observed_value:.1f} "
                        f"(threshold {item.expected_value:.1f}, {item.time_window // 60} minute window)"
                    )
            if h.recommended_checks:
                lines.append("")
                lines.append("**Recommendations:**")
                for rec in h.recommended_checks:
                    lines.append(f"- {rec}")
            if h.limitations:
                lines.append("")
                lines.append("**Limitations:**")
                for limitation in h.limitations:
                    lines.append(f"- {limitation}")
            lines.append("")
            
            for idx, h in enumerate(report.diagnoses.alternatives, 1):
                lines.append(f"### Alternative {idx}: {h.category.replace('_', ' ').title()} (Score: {h.score:.2f})")
                lines.append("")

        lines.append("## Recent anomalies")
        if not report.recent_anomalies:
            lines.append("No anomalies were recorded in the last 24 hours.")
        else:
            lines.append("| Time (UTC) | Category | Metric | Observed | Threshold |")
            lines.append("|---|---|---|---:|---:|")
            for anomaly in report.recent_anomalies:
                timestamp = anomaly.timestamp
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                lines.append(
                    f"| {timestamp.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} "
                    f"| {anomaly.category.replace('_', ' ').title()} "
                    f"| {anomaly.metric.replace('_', ' ')} "
                    f"| {anomaly.observed_value:.1f} | {anomaly.expected_value:.1f} |"
                )
            lines.append("")

        lines.append("## Recent incidents")
        if not report.recent_incidents:
            lines.append("No incidents have been captured.\n")
        else:
            for incident in report.recent_incidents:
                title = f"Incident #{incident['id']}" if redact else incident["title"]
                lines.append(
                    f"- **{title}** · {incident['started_at']} · "
                    f"{incident['metrics_count']} measurements · {incident['anomalies_count']} anomalies"
                )
                lines.append(f"  {incident['summary']}")
            lines.append("")

        return "\n".join(lines)

    def format_html(self, report: DiagnosticReport, redact: bool = True) -> str:
        """Build a self-contained HTML support report with sensitive fields escaped."""
        payload = self._report_payload(report, redact)
        system_info = payload["system_info"]
        info_rows = "".join(
            f"<tr><th>{html.escape(str(key).replace('_', ' ').title())}</th>"
            f"<td>{html.escape(str(value))}</td></tr>"
            for key, value in system_info.items()
        )
        baseline_rows = "".join(
            "<tr><td>{}</td><td>{:.2f}</td><td>{:.2f}</td><td>{}</td></tr>".format(
                html.escape(str(item["metric_name"])), item["p95"], item["median"], item["sample_count"]
            )
            for item in payload["baselines"]
        ) or '<tr><td colspan="4">No baselines available</td></tr>'
        process_rows = "".join(
            "<tr><td>{}</td><td>{:.1f}%</td><td>{:.1f}%</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(str(item["process_name"])), item["peak_cpu_percent"],
                item["peak_memory_percent"],
                html.escape(f"{self._rate(item.get('peak_read_bytes_per_sec'))} / {self._rate(item.get('peak_write_bytes_per_sec'))}"),
                item.get("peak_network_connections") or 0, item["samples"],
            )
            for item in payload["process_activity"]
        ) or '<tr><td colspan="6">No process history available</td></tr>'
        anomaly_rows = "".join(
            "<tr><td>{}</td><td>{}</td><td>{:.1f}</td><td>{:.1f}</td></tr>".format(
                html.escape(str(item["timestamp"])), html.escape(str(item["category"])),
                item["observed_value"], item["expected_value"],
            )
            for item in payload["recent_anomalies"]
        ) or '<tr><td colspan="4">No recent anomalies</td></tr>'
        hypothesis = payload["diagnoses"].get("primary_hypothesis")
        diagnosis = "No unusual pattern was detected." if not hypothesis else html.escape(
            str(hypothesis["category"]).replace("_", " ").title()
        )
        incident_items = "".join(
            "<li><strong>{}</strong> · {} · {} measurements · {} anomalies</li>".format(
                html.escape(f"Incident #{item['id']}" if redact else str(item["title"])),
                html.escape(str(item["started_at"])), item["metrics_count"], item["anomalies_count"],
            )
            for item in payload["recent_incidents"]
        ) or "<li>No captured incidents</li>"
        privacy_note = "Sensitive identifiers redacted" if redact else "Contains device-specific details"
        return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Diagnosys support report</title><style>
body {{ font: 15px/1.55 Segoe UI, Arial, sans-serif; color: #17212b; background: #f4f7fa; margin: 0; padding: 32px; }}
main {{ max-width: 1000px; margin: auto; }}
header, .card {{ background: #fff; border: 1px solid #dce4ec; border-radius: 12px; padding: 22px; margin: 0 0 16px; }}
h1 {{ margin: 0 0 4px; font-size: 26px; }} h2 {{ font-size: 18px; margin: 0 0 14px; }}
small {{ color: #536474; }} table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 9px 10px; border-bottom: 1px solid #e6ebf0; text-align: left; }}
th {{ color: #536474; font-weight: 600; }} .pill {{ display: inline-block; padding: 5px 10px; border-radius: 20px; background: #e8f2ff; color: #175fa8; }}
</style></head><body><main>
<header><div class="pill">Local diagnostic report</div><h1>Diagnosys support summary</h1>
<small>Generated {html.escape(report.timestamp.isoformat())} · {privacy_note}</small></header>
<section class="card"><h2>Device</h2><table>{info_rows}</table></section>
<section class="card"><h2>Diagnostic summary</h2><p>{diagnosis}</p></section>
<section class="card"><h2>Personal baselines</h2><table><thead><tr><th>Metric</th><th>95th percentile</th><th>Median</th><th>Samples</th></tr></thead><tbody>{baseline_rows}</tbody></table></section>
<section class="card"><h2>Process activity · 24 hours</h2><table><thead><tr><th>Application</th><th>Peak CPU</th><th>Peak memory</th><th>Peak disk read/write</th><th>Active connections</th><th>Samples</th></tr></thead><tbody>{process_rows}</tbody></table></section>
<section class="card"><h2>Recent anomalies</h2><table><thead><tr><th>Time (UTC)</th><th>Category</th><th>Observed</th><th>Expected</th></tr></thead><tbody>{anomaly_rows}</tbody></table></section>
<section class="card"><h2>Recent incidents</h2><ul>{incident_items}</ul></section>
<footer><small>Measurements show evidence and timing, not proof of causation. Generated locally by Diagnosys.</small></footer>
</main></body></html>'''
