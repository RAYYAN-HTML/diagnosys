"""Evidence-led investigation summaries for user-reported PC problems."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from diagnosys.models.diagnostics import Anomaly
from diagnosys.models.metrics import MetricSample, MetricStatus


SYMPTOMS: dict[str, dict[str, Any]] = {
    "slow_pc": {
        "title": "My PC feels slow",
        "description": "Look for resource pressure, busy applications, and recent system events.",
        "checks": [
            "Sort the process list by CPU and disk activity, then check whether one application stays near the top.",
            "Compare the capture with the five minutes before the problem began.",
            "If the slowdown followed an update or install, review the related Windows events before changing settings.",
        ],
    },
    "game_stutter": {
        "title": "A game stutters or lags",
        "description": "Compare CPU, GPU, memory, thermal, and network signals during the stutter.",
        "checks": [
            "Check whether CPU or GPU load stays high at the same time as the stutter.",
            "Compare game-session network latency with the local gateway result.",
            "Review temperature readings only when the device exposes a supported sensor.",
        ],
    },
    "internet": {
        "title": "The internet feels slow or unreliable",
        "description": "Separate local Wi-Fi or gateway trouble from destination, DNS, and wider connectivity issues.",
        "checks": [
            "Run the connection check and compare ping, DNS, and HTTP results.",
            "Inspect the gateway and route; missing route hops alone do not prove a fault.",
            "Repeat the check against another destination if only one service seems affected.",
        ],
    },
    "app_crash": {
        "title": "An app crashes or freezes",
        "description": "Capture nearby application and Windows reliability events alongside resource history.",
        "checks": [
            "Check the event timeline for an application error or Windows Error Reporting event near the symptom.",
            "Compare the application's resource activity with the surrounding system load.",
            "If the issue began after an update, note the update time before reinstalling or changing drivers.",
        ],
    },
    "overheating": {
        "title": "My PC seems hot or loud",
        "description": "Review available CPU and GPU temperatures together with sustained load.",
        "checks": [
            "Look for sustained CPU or GPU load that overlaps the temperature rise.",
            "Check that vents are clear and the device has room to move air.",
            "Unavailable temperature readings mean the sensor is not exposed; they do not mean the device is cool.",
        ],
    },
    "other": {
        "title": "Something else is wrong",
        "description": "Capture a broad evidence window and add notes about what you noticed.",
        "checks": [
            "Add a note at the time you notice a change so it appears beside the measurements.",
            "Compare the evidence with the five minutes before the problem began.",
            "Use the timeline to decide which focused check to run next.",
        ],
    },
}


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _number_values(samples: Iterable[MetricSample], name: str) -> list[float]:
    return [
        float(sample.value)
        for sample in samples
        if sample.metric_name == name
        and sample.status == MetricStatus.OK
        and isinstance(sample.value, (int, float))
        and math.isfinite(float(sample.value))
    ]


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))]


def _metric_stats(samples: list[MetricSample]) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for name in sorted({sample.metric_name for sample in samples}):
        values = _number_values(samples, name)
        if values:
            result[name] = {
                "samples": len(values),
                "median": round(statistics.median(values), 2),
                "p95": round(_percentile(values, 0.95) or 0, 2),
                "max": round(max(values), 2),
            }
    return result


class InvestigationEngine:
    """Turn a captured time window into clear findings without claiming causation."""

    def analyze(
        self,
        symptom: str,
        started_at: datetime,
        ended_at: datetime,
        metrics: list[MetricSample],
        anomalies: list[Anomaly],
        processes: list[dict[str, Any]],
        system_events: dict[str, Any],
        baseline_metrics: list[MetricSample] | None = None,
        markers: list[dict[str, Any]] | None = None,
        sensor_availability: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        symptom = symptom if symptom in SYMPTOMS else "other"
        profile = SYMPTOMS[symptom]
        baseline_metrics = baseline_metrics or []
        sensor_availability = sensor_availability or {}
        started_at = _timestamp(started_at) or datetime.now(timezone.utc)
        ended_at = _timestamp(ended_at) or datetime.now(timezone.utc)
        window_seconds = max(1, int((ended_at - started_at).total_seconds()))
        stats = _metric_stats(metrics)
        baseline_stats = _metric_stats(baseline_metrics)
        findings: list[dict[str, str]] = []

        if not metrics:
            findings.append({
                "kind": "coverage",
                "title": "No system samples were saved in this window",
                "detail": "The monitor may have been paused, or the capture window may predate available history.",
                "strength": "limited",
            })
        else:
            for metric, label, threshold, description in (
                ("cpu_percent", "CPU", 80.0, "Sustained processor load may make other work feel slower."),
                ("memory_percent", "Memory", 85.0, "High memory use can increase paging and application delays."),
                ("disk_percent", "System drive", 95.0, "Very little free space can interfere with updates and application work."),
                ("gpu_percent", "GPU", 95.0, "The graphics processor was near full utilization in this window."),
                ("cpu_temperature_c", "CPU temperature", 90.0, "This is a high reading; sensor labels and safe ranges vary by device."),
                ("gpu_temperature_c", "GPU temperature", 85.0, "This is a high reading; sensor labels and safe ranges vary by device."),
            ):
                current = stats.get(metric)
                if current and float(current["p95"]) >= threshold:
                    findings.append({
                        "kind": "measurement",
                        "title": f"{label} was elevated",
                        "detail": f"95th percentile {current['p95']:.1f}; peak {current['max']:.1f}. {description}",
                        "strength": "repeated",
                    })

        anomaly_counts: dict[str, int] = defaultdict(int)
        for anomaly in anomalies:
            anomaly_counts[anomaly.category] += 1
        category_titles = {
            "CPU_PRESSURE": "Repeated CPU pressure was recorded",
            "MEMORY_PRESSURE": "Repeated memory pressure was recorded",
            "DISK_PRESSURE": "Repeated low-space pressure was recorded",
            "NETWORK_LATENCY": "High network latency was recorded",
            "NETWORK_JITTER": "Variable network latency was recorded",
            "PACKET_LOSS": "Packet loss was recorded",
            "DNS_LATENCY": "Slow DNS responses were recorded",
            "HTTP_LATENCY": "Slow HTTP responses were recorded",
        }
        for category, count in sorted(anomaly_counts.items(), key=lambda pair: (-pair[1], pair[0])):
            examples = [item for item in anomalies if item.category == category]
            newest = examples[-1]
            findings.append({
                "kind": "anomaly",
                "title": category_titles.get(category, category.replace("_", " ").title()),
                "detail": f"{count} flagged reading(s); latest was {newest.observed_value:.1f} {newest.metric.replace('_', ' ')} against {newest.expected_value:.1f}.",
                "strength": "rule flagged",
            })

        process_peaks = self._process_peaks(processes)
        if process_peaks:
            lead = process_peaks[0]
            if lead["peak_cpu_percent"] >= 40 or lead["peak_memory_percent"] >= 20:
                findings.append({
                    "kind": "process",
                    "title": f"{lead['process_name']} had the strongest recorded process activity",
                    "detail": f"Peak CPU {lead['peak_cpu_percent']:.1f}% · peak memory {lead['peak_memory_percent']:.1f}% across {lead['samples']} observations.",
                    "strength": "process history",
                })

        events = list(system_events.get("events", [])) if isinstance(system_events, dict) else []
        if events:
            findings.append({
                "kind": "event",
                "title": f"{len(events)} related Windows event(s) were found",
                "detail": "Review the event timeline for an application crash, service failure, restart, or update close to the symptom.",
                "strength": "Windows event log",
            })

        valid_network = [sample for sample in metrics if sample.metric_name in {
            "ping_median_ms", "packet_loss_percent", "ping_jitter_ms", "dns_latency_ms", "http_latency_ms"
        } and sample.status == MetricStatus.OK]
        if symptom == "internet" and not valid_network:
            findings.append({
                "kind": "coverage",
                "title": "No focused network check was recorded yet",
                "detail": "Run the connection check during the capture to compare ping, DNS, and HTTP evidence.",
                "strength": "next step",
            })
        if symptom in {"game_stutter", "overheating"} and not any(sample.metric_name == "gpu_percent" for sample in metrics):
            reason = sensor_availability.get("gpu", "GPU telemetry is unavailable on this device.")
            findings.append({
                "kind": "coverage",
                "title": "GPU telemetry was unavailable",
                "detail": str(reason),
                "strength": "sensor availability",
            })
        if symptom == "overheating" and not any(sample.metric_name in {"cpu_temperature_c", "gpu_temperature_c"} for sample in metrics):
            reasons = "; ".join(filter(None, (
                sensor_availability.get("cpu_temperature"),
                sensor_availability.get("gpu_temperature"),
            ))) or "Temperature sensors are not exposed by the current device or driver."
            findings.append({
                "kind": "coverage",
                "title": "Temperature sensors were not exposed",
                "detail": reasons,
                "strength": "sensor availability",
            })
        if symptom == "app_crash" and not events and isinstance(system_events, dict) and system_events.get("available"):
            findings.append({
                "kind": "coverage",
                "title": "No matching Windows reliability event was found",
                "detail": "That does not rule out an app problem; some applications do not write a Windows event when they freeze.",
                "strength": "event log check",
            })

        comparisons = self._compare_windows(stats, baseline_stats)
        for item in comparisons:
            if abs(item["change_pct"]) >= 25 and abs(item["change"]) >= 5:
                direction = "higher" if item["change"] > 0 else "lower"
                findings.append({
                    "kind": "comparison",
                    "title": f"{item['metric_name'].replace('_', ' ').title()} was {direction} than just before the capture",
                    "detail": f"During median {item['during_median']:.1f} vs prior median {item['before_median']:.1f} ({item['change_pct']:+.0f}%).",
                    "strength": "before/after comparison",
                })

        if not findings:
            findings.append({
                "kind": "coverage",
                "title": "No strong signal stood out in the captured evidence",
                "detail": "That does not rule out the problem. It may not have happened during this window, or the relevant sensor may not be available.",
                "strength": "no clear signal",
            })

        quality = "GOOD" if len(metrics) >= 5 else "LIMITED"
        if len(metrics) >= 5 and not any(item.status == MetricStatus.OK for item in metrics):
            quality = "LIMITED"
        ordered_timeline = self._timeline(metrics, anomalies, events, markers or [])
        summary = self._summary(symptom, findings, quality, window_seconds)
        hypotheses = self._hypotheses(stats, anomaly_counts, events, valid_network)
        return {
            "symptom": symptom,
            "symptom_title": profile["title"],
            "summary": summary,
            "data_quality": quality,
            "window_seconds": window_seconds,
            "metric_count": len(metrics),
            "anomaly_count": len(anomalies),
            "process_sample_count": len(processes),
            "metric_stats": stats,
            "baseline_stats": baseline_stats,
            "before_after": comparisons,
            "findings": findings[:20],
            "hypotheses": hypotheses,
            "process_peaks": process_peaks[:8],
            "system_events": system_events,
            "timeline": ordered_timeline,
            "next_checks": profile["checks"],
            "limitations": [
                "Signals that occur at the same time do not prove one caused the other.",
                "Process names and Windows event details are stored locally and may identify your activity.",
            ],
        }

    @staticmethod
    def _hypotheses(
        stats: dict[str, dict[str, float | int]],
        anomaly_counts: dict[str, int],
        events: list[dict[str, Any]],
        network_samples: list[MetricSample],
    ) -> list[dict[str, str]]:
        candidates: list[tuple[int, dict[str, str]]] = []
        resource_flags = sum((
            float(stats.get("cpu_percent", {}).get("p95", 0)) >= 80,
            float(stats.get("memory_percent", {}).get("p95", 0)) >= 85,
            float(stats.get("disk_percent", {}).get("max", 0)) >= 95,
            any(anomaly_counts.get(key, 0) for key in ("CPU_PRESSURE", "MEMORY_PRESSURE", "DISK_PRESSURE")),
        ))
        if resource_flags:
            candidates.append((resource_flags, {
                "title": "Local resource pressure",
                "strength": "Strong" if resource_flags >= 2 else "Some evidence",
                "basis": "Repeated high CPU, memory, or drive readings" if resource_flags >= 2 else "One resource signal was elevated",
            }))
        thermal = (
            float(stats.get("cpu_temperature_c", {}).get("p95", 0)) >= 90
            or float(stats.get("gpu_temperature_c", {}).get("p95", 0)) >= 85
        )
        if thermal:
            candidates.append((3, {
                "title": "Thermal pressure",
                "strength": "Some evidence",
                "basis": "A temperature reading was high; sensor interpretation varies by hardware",
            }))
        app_events = [item for item in events if str(item.get("Id", item.get("id", ""))) in {"1000", "1001", "1026", "7031"}]
        if app_events:
            candidates.append((4, {
                "title": "Application or service failure",
                "strength": "Some evidence",
                "basis": f"{len(app_events)} related crash, reporting, or service event(s) appeared in the window",
            }))
        change_events = [
            item for item in events
            if str(item.get("Id", item.get("id", ""))) in {"19", "20", "21", "22", "1033", "1034", "11707", "11724"}
        ]
        if change_events:
            candidates.append((2, {
                "title": "A Windows update or software change appears in the timeline",
                "strength": "Timeline clue",
                "basis": f"{len(change_events)} update or installer event(s) were recorded; timing alone does not prove they caused the symptom",
            }))
        network_flags = sum((
            any(anomaly_counts.get(key, 0) for key in ("NETWORK_LATENCY", "NETWORK_JITTER", "PACKET_LOSS", "DNS_LATENCY", "HTTP_LATENCY")),
            any(sample.metric_name == "packet_loss_percent" and float(sample.value or 0) > 0 for sample in network_samples),
            any(sample.metric_name == "ping_median_ms" and float(sample.value or 0) >= 150 for sample in network_samples),
            any(sample.metric_name == "dns_latency_ms" and float(sample.value or 0) >= 1000 for sample in network_samples),
        ))
        if network_flags:
            candidates.append((network_flags, {
                "title": "Network instability",
                "strength": "Strong" if network_flags >= 2 else "Some evidence",
                "basis": "Latency, packet loss, or resolver signals were elevated",
            }))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in candidates[:4]]

    @staticmethod
    def _process_peaks(processes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in processes:
            name = str(row.get("process_name") or "Unknown application")
            item = grouped.setdefault(name, {
                "process_name": name, "peak_cpu_percent": 0.0, "peak_memory_percent": 0.0,
                "peak_read_bytes_per_sec": None, "peak_write_bytes_per_sec": None,
                "peak_network_connections": None, "samples": 0,
            })
            item["peak_cpu_percent"] = max(item["peak_cpu_percent"], float(row.get("cpu_percent") or 0))
            item["peak_memory_percent"] = max(item["peak_memory_percent"], float(row.get("memory_percent") or 0))
            for key in ("read_bytes_per_sec", "write_bytes_per_sec", "network_connection_count"):
                target = "peak_" + key
                value = row.get(key)
                if value is not None:
                    item[target] = max(item[target] or 0, float(value))
            item["samples"] += 1
        return sorted(grouped.values(), key=lambda item: (item["peak_cpu_percent"], item["peak_memory_percent"]), reverse=True)

    @staticmethod
    def _compare_windows(
        current: dict[str, dict[str, float | int]],
        baseline: dict[str, dict[str, float | int]],
    ) -> list[dict[str, float | int | str]]:
        output = []
        for name in sorted(set(current) & set(baseline)):
            before = float(baseline[name]["median"])
            during = float(current[name]["median"])
            change = during - before
            denominator = abs(before) if abs(before) > 0.01 else 1.0
            output.append({
                "metric_name": name,
                "before_median": round(before, 2),
                "during_median": round(during, 2),
                "change": round(change, 2),
                "change_pct": round(change / denominator * 100, 1),
            })
        return output

    @staticmethod
    def _timeline(
        metrics: list[MetricSample],
        anomalies: list[Anomaly],
        events: list[dict[str, Any]],
        markers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in anomalies:
            rows.append({"timestamp": item.timestamp.isoformat(), "kind": "anomaly", "detail": item.explanation})
        for item in events:
            stamp = _timestamp(item.get("time") or item.get("timestamp"))
            if stamp:
                message = str(item.get("message") or item.get("source") or "Windows event")
                rows.append({"timestamp": stamp.isoformat(), "kind": "system event", "detail": message[:240]})
        for item in markers:
            stamp = _timestamp(item.get("timestamp"))
            if stamp:
                rows.append({"timestamp": stamp.isoformat(), "kind": str(item.get("kind") or "note"), "detail": str(item.get("text") or "")[:240]})
        # Keep the timeline readable: downsample routine metrics to one row per minute.
        minute_buckets: dict[tuple[str, str], MetricSample] = {}
        for sample in metrics:
            stamp = _timestamp(sample.timestamp)
            if not stamp or sample.status != MetricStatus.OK or not isinstance(sample.value, (int, float)):
                continue
            key = (stamp.strftime("%Y-%m-%dT%H:%M"), sample.metric_name)
            minute_buckets[key] = sample
        for sample in minute_buckets.values():
            rows.append({
                "timestamp": sample.timestamp.isoformat(),
                "kind": "measurement",
                "detail": f"{sample.metric_name.replace('_', ' ')}: {float(sample.value):.1f} {sample.unit}",
            })
        rows.sort(key=lambda row: row["timestamp"])
        return rows[-300:]

    @staticmethod
    def _summary(symptom: str, findings: list[dict[str, str]], quality: str, window_seconds: int) -> str:
        if quality == "LIMITED":
            return "The capture does not contain enough usable history for a reliable conclusion. Keep the investigation open until the symptom happens again, or run a focused check."
        if findings and findings[0]["kind"] != "coverage":
            return f"Captured {len(findings)} useful clue(s) during this {max(1, window_seconds // 60)} minute window. Start with the strongest clue, then use the suggested check to narrow down the cause."
        return "No strong signal stood out in this capture. Keep it running until the issue happens, then add a note at the moment you notice it."
