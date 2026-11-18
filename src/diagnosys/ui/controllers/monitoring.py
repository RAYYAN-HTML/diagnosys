"""Background telemetry application and deterministic diagnosis workflows."""
from __future__ import annotations

import platform
import psutil
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from diagnosys.collectors.system.gpu import GPUMetrics
from diagnosys.collectors.system.thermal import ThermalReading, ThermalSnapshot
from diagnosys.diagnostics.engine import DiagnosticEngine
from diagnosys.models.diagnostics import DiagnosisResult
from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.storage.database import get_connection, init_db, prune_db
from diagnosys.storage.repositories import AnomalyRepository, MetricRepository


class MonitoringController:
    """Own telemetry refresh, persistence, and evidence-based diagnosis."""

    def __init__(self, window):
        self.window = window

    def __getattr__(self, name):
        return getattr(self.window, name)

    def __setattr__(self, name, value):
        if name == "window":
            object.__setattr__(self, name, value)
        else:
            setattr(self.window, name, value)


    def refresh(self) -> None:
        self._run_async("refresh", self._collect_snapshot, self._apply_snapshot)
    
    def _collect_snapshot(self):
        cpu = self.cpu.collect()
        memory = self.memory.collect()
        disk = self.disk.collect()
        processes = self.processes.collect()
        gpu = self.gpu.collect()
        network = self.network_rates.collect()
        uptime = self.uptime.collect()
        thermal = self.thermal.collect()
        game_names = [name.strip() for name in self.settings.game_process_names.split(",") if name.strip()]
        gaming = self.gaming.collect(game_names)
        temperature = next((
            reading.temperature_c for reading in thermal.temperatures
            if reading.temperature_c is not None
            and any(token in (reading.sensor + " " + reading.label).casefold()
                    for token in ("cpu", "coretemp", "k10temp", "zenpower", "cpu_thermal"))
        ), None)
        now = datetime.now(timezone.utc)
        disk_refreshed = False
        if now - self._last_disk_health_refresh >= timedelta(seconds=60):
            discovery = self.disk_health.discover()
            disk_results = [(device, self.disk_health.collect(device.device)) for device in discovery.devices]
            self._disk_discovery = discovery
            self._disk_health_results = disk_results
            self._last_disk_health_refresh = now
            disk_refreshed = True
        return cpu, memory, disk, processes, gpu, network, uptime, temperature, thermal, self._disk_discovery, list(self._disk_health_results), disk_refreshed, gaming
    
    def _apply_snapshot(self, result) -> None:
        cpu, memory, disk, processes, gpu, network, uptime, temperature, thermal, disk_discovery, disk_results, disk_refreshed, gaming = result
        timestamp = datetime.now(timezone.utc)
        samples = (
            MetricSample(timestamp, "cpu_percent", cpu.utilization_percent if cpu.available else None, "%", "system", MetricStatus.OK if cpu.available else MetricStatus.UNAVAILABLE, reason=cpu.reason),
            MetricSample(timestamp, "memory_percent", memory.percent_used if memory.available else None, "%", "system", MetricStatus.OK if memory.available else MetricStatus.UNAVAILABLE, reason=memory.reason),
            MetricSample(timestamp, "disk_percent", disk.percent_used if disk.available else None, "%", "system", MetricStatus.OK if disk.available else MetricStatus.UNAVAILABLE, reason=disk.reason),
        )
        for sample in samples:
            self._store_sample(sample)
        thermal_for_history = thermal
        has_gpu_sensor = any("gpu" in (item.sensor + " " + item.label).casefold() for item in thermal.temperatures)
        if gpu.temperature_c is not None and not has_gpu_sensor:
            thermal_for_history = ThermalSnapshot(
                available=True,
                temperatures=thermal.temperatures + (ThermalReading("gpu", gpu.name or "GPU", gpu.temperature_c),),
                fans=thermal.fans,
                reason=thermal.reason,
            )
        if timestamp - self._last_thermal_persist_at >= timedelta(seconds=10):
            self.hardware_repo.save_thermal(thermal_for_history, timestamp)
            self._last_thermal_persist_at = timestamp
        if disk_refreshed:
            for device, health in disk_results:
                self.hardware_repo.save_disk_health(device, health, timestamp)
        thermal_history = self.hardware_repo.query_thermal(window_seconds=24 * 3600, limit=5000)
        recent_metrics = self.metric_repo.query(window_seconds=300)
        for anomaly in self.thermal_diagnostics.evaluate(thermal_history, recent_metrics, timestamp):
            if not self.anomaly_repo.has_recent(anomaly.rule_id, window_seconds=300):
                self.anomaly_repo.save(anomaly)
                self._notify_anomaly(anomaly)
        disk_history = self.hardware_repo.query_disk_health(window_seconds=30 * 86400, limit=5000)
        self.thermal_page.update_data(thermal_for_history, thermal_history, gpu.temperature_c, timestamp)
        self.disk_health_page.update_data(disk_discovery, disk_results, disk_history, self._last_disk_health_refresh)
    
        thermal_values = []
        if temperature is not None:
            thermal_values.append(f"CPU {temperature:.0f} °C")
        if gpu.temperature_c is not None:
            thermal_values.append(f"GPU {gpu.temperature_c:.0f} °C")
        if thermal_values:
            self.thermal_overview.set_value(" · ".join(thermal_values), f"{len(thermal.temperatures)} sensor temperature(s), {len(thermal.fans)} fan reading(s)")
        elif thermal.temperatures:
            self.thermal_overview.set_value("Readings available", ", ".join(item.label for item in thermal.temperatures[:3]))
        else:
            self.thermal_overview.set_value("Unavailable", thermal.reason or "No supported temperature sensor is exposed")
    
        warning_drives = [(device.device, health) for device, health in disk_results if health.state == "warning"]
        if warning_drives:
            self.disk_health_overview.set_value("Warning", ", ".join(name for name, _ in warning_drives))
        elif disk_results and all(health.state == "healthy" for _, health in disk_results):
            self.disk_health_overview.set_value("Reported passed", f"{len(disk_results)} drive(s) returned a clean health status")
        elif disk_results:
            self.disk_health_overview.set_value("Unknown", "One or more drives returned inconclusive SMART data")
        else:
            self.disk_health_overview.set_value("Unavailable", disk_discovery.reason or "No queryable SMART devices were found")
    
        game_names = [name.strip() for name in self.settings.game_process_names.split(",") if name.strip()]
        if not game_names:
            self.gaming_overview.set_value("Not configured", "Add executable names in Settings")
        elif gaming.available:
            self.gaming_overview.set_value(f"{len(gaming.processes)} active", ", ".join(sorted({item.name for item in gaming.processes})))
        else:
            self.gaming_overview.set_value("Not running", gaming.reason or "No configured game process was detected")
    
        recent_findings = self.anomaly_repo.query(window_seconds=3600)
        if recent_findings:
            latest = recent_findings[0]
            detail = f"{latest.category}: {latest.explanation}"
            self.recent_events_overview.set_value(f"{len(recent_findings)} finding(s)", detail[:180] + ("…" if len(detail) > 180 else ""))
        else:
            self.recent_events_overview.set_value("No findings in last hour", "No saved baseline-relative or hardware-limit findings")
    
        optional_readings = (
            ("cpu_temperature_c", temperature, "°C", "CPU sensor"),
            ("cpu_frequency_mhz", cpu.frequency_mhz if cpu.available else None, "MHz", "CPU"),
            ("gpu_percent", gpu.utilization_percent, "%", "GPU 0"),
            ("gpu_temperature_c", gpu.temperature_c, "°C", "GPU 0"),
            ("disk_read_bytes_per_sec", disk.read_bytes_per_sec if disk.available else None, "B/s", "system disk"),
            ("disk_write_bytes_per_sec", disk.write_bytes_per_sec if disk.available else None, "B/s", "system disk"),
            ("network_download_bytes_per_sec", network.download_bytes_per_sec, "B/s", "all interfaces"),
            ("network_upload_bytes_per_sec", network.upload_bytes_per_sec, "B/s", "all interfaces"),
        )
        self._latest_sensor_availability = {
            "cpu_temperature": "available" if temperature is not None else "not exposed by this device",
            "gpu": "available" if gpu.available else (gpu.reason or "not available"),
            "gpu_temperature": "available" if gpu.temperature_c is not None else "not exposed by this device",
        }
        for name, value, unit, entity in optional_readings:
            if value is not None:
                self._store_sample(MetricSample(
                    timestamp, name, value, unit, "system", MetricStatus.OK, entity_id=entity,
                ))
        if timestamp - self._last_process_persist_at >= timedelta(seconds=self.settings.process_history_seconds):
            self.process_repo.save_snapshot(processes)
            self._last_process_persist_at = timestamp
        self.process_page.update_data(processes, self.process_repo.query(window_seconds=6 * 3600, limit=1000))
        self.performance_page.update_data(
            cpu, memory, disk, gpu, network,
            self.metric_repo.query(window_seconds=3600, limit=1000),
        )
        game_names = [name.strip() for name in self.settings.game_process_names.split(",") if name.strip()]
        self.gaming_repo.save_snapshot(
            gaming, timestamp,
            system_cpu_percent=cpu.utilization_percent if cpu.available else None,
            gpu_utilization_percent=gpu.utilization_percent,
            gpu_temperature_c=gpu.temperature_c,
        )
        self.gaming_page.update_data(
            game_names, gaming,
            self.gaming_repo.query_sessions(window_seconds=30 * 86400, limit=100),
            self.gaming_repo.latest_samples(limit=100), processes,
        )
    
        if timestamp - self._last_prune_at >= timedelta(hours=1):
            prune_db(self.db, self.settings.retention_days)
            self._last_prune_at = timestamp
    
        if timestamp - self._last_baseline_refresh >= timedelta(minutes=5):
            self.detector.baselines = self.metric_repo.get_all_baselines(window_seconds=86400)
            self._last_baseline_refresh = timestamp
    
        self._snapshot_count += 1
        self.cpu_gauge.set_value(cpu.utilization_percent if cpu.available else None)
        self.cpu_frequency.setText(self._frequency(cpu.frequency_mhz) if cpu.available else "Unavailable")
        self.cpu_temperature.setText(f"{temperature:.0f} °C" if temperature is not None else "Unavailable")
        self.cpu_cores.setText(f"{psutil.cpu_count(logical=True) or '—'} logical processors")
    
        self.memory_value.setText(
            f"{self._gib(memory.used_bytes)} / {self._gib(memory.total_bytes)}"
            if memory.available else "Unavailable"
        )
        self.memory_progress.set_metric(
            memory.percent_used if memory.available else None,
            f"{memory.percent_used:.0f}%" if memory.available else "Unavailable",
            f"{self._gib(memory.used_bytes)} used of {self._gib(memory.total_bytes)}" if memory.available else (memory.reason or "Memory metrics unavailable"),
        )
        self.memory_available.setText(
            f"{self._gib(memory.available_bytes)} available" if memory.available else (memory.reason or "Memory metrics unavailable")
        )
    
        self.disk_value.setText(
            f"{self._gib(disk.total_bytes - disk.free_bytes)} / {self._gib(disk.total_bytes)}"
            if disk.available else "Unavailable"
        )
        self.disk_progress.set_metric(
            disk.percent_used if disk.available else None,
            f"{disk.percent_used:.0f}%" if disk.available else "Unavailable",
            f"{self._gib(disk.free_bytes)} free" if disk.available else (disk.reason or "Storage metrics unavailable"),
        )
        rates_ready = self._snapshot_count > 1
        self.disk_read.setText(self._rate(disk.read_bytes_per_sec) if disk.available and rates_ready else "Measuring…")
        self.disk_write.setText(self._rate(disk.write_bytes_per_sec) if disk.available and rates_ready else "Measuring…")
    
        if network.available:
            self.download_value.setText(self._rate(network.download_bytes_per_sec))
            self.upload_value.setText(self._rate(network.upload_bytes_per_sec))
        else:
            self.download_value.setText("Unavailable")
            self.upload_value.setText("Unavailable")
            self.download_value.setToolTip(network.reason or "Network counters unavailable")
            self.upload_value.setToolTip(network.reason or "Network counters unavailable")
    
        self._apply_gpu(gpu)
        self.host_summary.set_value(platform.node() or "This device", "Hostname")
        self.uptime_summary.set_value(self._duration(uptime), "Since last boot" if uptime > 0 else "Uptime unavailable")
        self.os_summary.set_value(platform.system() or "Unknown", f"{platform.release()} · {platform.machine()}")
    
        for key, value, available in (
            ("CPU", cpu.utilization_percent, cpu.available),
            ("Memory", memory.percent_used, memory.available),
            ("Disk", disk.percent_used, disk.available),
        ):
            if available:
                self.history[key].append(value)
                self.chart.set_series(key, list(self.history[key]))
        self._update_processes(processes)
        self._update_insight()
        self.monitoring_badge.setText("MONITORING")
        self.monitoring_badge.setObjectName("PillGood")
        self.monitoring_badge.style().unpolish(self.monitoring_badge)
        self.monitoring_badge.style().polish(self.monitoring_badge)
        self.updated_label.setText(f"Updated {datetime.now().astimezone().strftime('%H:%M:%S')}")
    
    def _apply_gpu(self, gpu: GPUMetrics) -> None:
        self.gpu_badge.setText("AVAILABLE" if gpu.available else "UNAVAILABLE")
        self.gpu_badge.setObjectName("PillGood" if gpu.available else "PillNeutral")
        self.gpu_badge.style().unpolish(self.gpu_badge)
        self.gpu_badge.style().polish(self.gpu_badge)
        self.gpu_name.setText(
            gpu.name if gpu.available and gpu.name else (gpu.reason or "GPU telemetry unavailable")
        )
        self.gpu_progress.set_metric(
            gpu.utilization_percent,
            f"{gpu.utilization_percent:.0f}%" if gpu.utilization_percent is not None else "Unavailable",
            "GPU 0 utilization" if gpu.available else "No supported GPU sensor detected",
        )
        if gpu.memory_used_mib is not None and gpu.memory_total_mib is not None:
            self.gpu_memory.setText(f"{gpu.memory_used_mib / 1024:.1f} / {gpu.memory_total_mib / 1024:.1f} GB")
        else:
            self.gpu_memory.setText("Unavailable")
        self.gpu_temperature.setText(f"{gpu.temperature_c:.0f} °C" if gpu.temperature_c is not None else "Unavailable")
        if not gpu.available:
            self.gpu_name.setToolTip(gpu.reason or "GPU telemetry is not supported")
    
    def _update_processes(self, processes) -> None:
        self.process_table.clearContents()
        for row in range(6):
            cpu = processes.top_cpu[row] if row < len(processes.top_cpu) else None
            memory = processes.top_memory[row] if row < len(processes.top_memory) else None
            values = (
                cpu.name if cpu else "—",
                f"{cpu.cpu_percent:.1f}%" if cpu else "—",
                memory.name if memory else "—",
                f"{memory.memory_percent:.1f}%" if memory else "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column in (1, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.process_table.setItem(row, column, item)
        self.process_table.setToolTip(
            f"{processes.process_count} active processes" if processes.available else (processes.reason or "Process data unavailable")
        )
    
    def _update_insight(self) -> None:
        try:
            samples = [
                item for item in self.metric_repo.query(window_seconds=3600)
                if item.status == MetricStatus.OK
            ]
            if len(samples) < 5:
                self.insight_title.setText("Collecting enough evidence")
                self.insight_body.setText("Diagnosys needs a few more readings before it can say whether the recent pattern looks normal.")
                self.insight_evidence.setText(f"{len(samples)} usable reading(s) available so far.")
                return
            baselines = self.metric_repo.get_all_baselines(window_seconds=86400)
            ready = [item for item in baselines.values() if item.available]
            if not ready:
                count = max((item.sample_count for item in baselines.values()), default=0)
                self.insight_title.setText("Learning this device's baseline")
                self.insight_body.setText("Diagnosys needs at least 30 valid samples for a metric before it can flag unusual behaviour. No generic cutoff is substituted.")
                self.insight_evidence.setText(f"Most-developed metric baseline: {count}/30 samples.")
                return
            anomalies = self.anomaly_repo.query(window_seconds=3600)
            result = DiagnosticEngine().diagnose(anomalies, window_seconds=3600)
            self._render_insight(result)
        except Exception as exc:
            self.insight_title.setText("Insight temporarily unavailable")
            self.insight_body.setText(str(exc))
            self.insight_evidence.clear()
    
    def _render_insight(self, result: DiagnosisResult) -> None:
        hypothesis = result.primary_hypothesis
        if result.status == "INSUFFICIENT_DATA":
            self.insight_title.setText("Collecting enough evidence")
            self.insight_body.setText("The recent window has too few usable measurements for a health conclusion.")
            self.insight_evidence.setText("Keep monitoring or capture the issue while it is happening.")
            return
        if result.status == "INSUFFICIENT_BASELINE":
            self.insight_title.setText("Learning this device's baseline")
            self.insight_body.setText("At least 30 valid samples are needed for a metric before Diagnosys can identify deviations.")
            self.insight_evidence.setText("No global performance cutoff is substituted while history is incomplete.")
            return
        if result.status == "NO_ANOMALY" or not hypothesis:
            self.insight_title.setText("No baseline deviation detected")
            self.insight_body.setText("No monitored metric crossed its learned variation band. This does not prove every component is healthy.")
            self.insight_evidence.setText("Personal baselines require sufficient local history for each metric.")
            return
    
        self.insight_title.setText(hypothesis.category.replace("_", " ").title())
        explanations = {
            "LOCAL_RESOURCE_CONTENTION": "Sustained pressure on a local resource may affect responsiveness.",
            "NETWORK_INSTABILITY": "Elevated latency or packet loss may interrupt online activity.",
            "UNKNOWN_ANOMALY": "An unusual signal was recorded, but evidence is not yet conclusive.",
        }
        recommendation = hypothesis.recommended_checks[0] if hypothesis.recommended_checks else "Continue monitoring and review the detailed analysis."
        self.insight_body.setText(f"{explanations.get(hypothesis.category, 'Recent measurements show an unusual pattern.')} Next: {recommendation}")
        evidence = hypothesis.evidence[:2]
        self.insight_evidence.setText(
            "Evidence: " + " · ".join(
                f"{item.metric.replace('_', ' ')} {item.observed_value:.1f} vs {item.expected_value:.1f} expected"
                for item in evidence
            ) if evidence else "Review the diagnosis page for supporting evidence and limitations."
        )
    
    def _store_sample(self, sample: MetricSample) -> None:
        self.metric_repo.save(sample)
        if sample.status == MetricStatus.OK:
            for anomaly in self.detector.evaluate_sample(sample):
                if not self.anomaly_repo.has_recent(anomaly.rule_id, window_seconds=300):
                    self.anomaly_repo.save(anomaly)
                    self._notify_anomaly(anomaly)
    
    def _connection(self):
        connection = get_connection()
        init_db(connection)
        return connection
    
    def diagnose(self) -> None:
        self.diagnosis_output.setPlainText("Analyzing saved evidence…")
        self._run_async("diagnosis", self._diagnose_data, self._apply_diagnosis)
    
    def _diagnose_data(self):
        connection = self._connection()
        try:
            samples = [item for item in MetricRepository(connection).query(window_seconds=3600) if item.status == MetricStatus.OK]
            if len(samples) < 5:
                return DiagnosisResult(
                    status="INSUFFICIENT_DATA", primary_hypothesis=None,
                    time_window=3600, data_quality="LIMITED",
                )
            baselines = MetricRepository(connection).get_all_baselines(window_seconds=86400)
            if not any(item.available for item in baselines.values()):
                return DiagnosisResult(status="INSUFFICIENT_BASELINE", primary_hypothesis=None,
                    time_window=3600, data_quality="INSUFFICIENT_BASELINE")
            return DiagnosticEngine().diagnose(AnomalyRepository(connection).query(window_seconds=3600), window_seconds=3600)
        finally:
            connection.close()
    
    def _apply_diagnosis(self, result: DiagnosisResult) -> None:
        lines: list[str] = []
        if result.status == "INSUFFICIENT_DATA":
            lines += ["Not enough evidence yet", "", "Diagnosys has fewer than five usable readings in the last hour. Keep monitoring or capture the problem while it is happening."]
        elif result.status == "INSUFFICIENT_BASELINE":
            lines += ["Learning personal baselines", "", "Diagnosys needs at least 30 valid samples for a metric before it can flag deviations. Keep monitoring. No generic performance cutoff is used."]
        elif result.status == "NO_ANOMALY":
            lines += ["No unusual deviation detected", "", "No monitored metric crossed its learned personal variation band. This does not prove every component is healthy.", "", "Keep monitoring if the issue returns."]
        else:
            lines += [f"Status: {result.status}", ""]
        hypothesis = result.primary_hypothesis
        if hypothesis:
            category = hypothesis.category
            explanations = {
                "LOCAL_RESOURCE_CONTENTION": "One or more local resources are under sustained pressure. This can make applications feel slow, cause stuttering, or delay background tasks.",
                "NETWORK_INSTABILITY": "The network is showing elevated latency or packet loss. This can cause slow pages, voice/video interruptions, and game lag.",
                "UNKNOWN_ANOMALY": "The system recorded an unusual signal, but there is not enough evidence to identify a specific cause yet.",
            }
            lines += [f"Observed pattern: {category.replace('_', ' ').title()}", "", explanations.get(category, "The diagnostic engine found an unusual pattern in recent measurements."), ""]
            if hypothesis.evidence:
                lines += ["Evidence:"]
                lines += [f"• {e.metric.replace('_', ' ').title()}: {e.observed_value:.1f} (expected around {e.expected_value:.1f})" for e in hypothesis.evidence]
                lines.append("")
            lines.append("What to do next:")
            lines += [f"• {check}" for check in hypothesis.recommended_checks]
            if hypothesis.limitations:
                lines += ["", "Limits of this result:"]
                lines += [f"• {limit}" for limit in hypothesis.limitations]
        self.diagnosis_output.setPlainText("\n".join(lines))
        self._render_insight(result)
    