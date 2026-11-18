"""Pure formatting and export helpers shared by the desktop UI."""
from __future__ import annotations

from diagnosys.models.metrics import MetricSample, MetricStatus


def redact_incident_payload(payload: dict) -> dict:
    evidence = payload.get("evidence") or {}
    process_names = {
        str(item.get("process_name", ""))
        for item in evidence.get("process_peaks", [])
        if item.get("process_name")
    }
    sensitive_fields = {"hostname", "username", "entity_id", "target", "server", "ssid", "bssid", "address"}

    def clean(value, parent: str = ""):
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                if key in sensitive_fields:
                    cleaned[key] = "[redacted]"
                elif key == "pid":
                    cleaned[key] = None
                elif key == "process_name":
                    cleaned[key] = "Application"
                elif key == "message":
                    cleaned[key] = "[redacted event details]"
                elif key == "text":
                    cleaned[key] = "[redacted note]"
                elif parent == "timeline" and key == "detail":
                    cleaned[key] = "[redacted timeline details]"
                elif key == "resolution_note":
                    cleaned[key] = "[redacted note]" if item else ""
                else:
                    cleaned[key] = clean(item, key)
            return cleaned
        if isinstance(value, list):
            return [clean(item, parent) for item in value]
        if isinstance(value, str):
            result = value
            for process_name in sorted(process_names, key=len, reverse=True):
                result = result.replace(process_name, "Application")
            return result
        return value

    cleaned = clean(payload)
    cleaned["title"] = f"Incident #{payload.get('id')}"
    return cleaned


def incident_markdown(payload: dict) -> str:
    evidence = payload.get("evidence") or {}
    lines = [
        f"# {payload.get('title', 'Diagnosys incident')}",
        "",
        f"- **Problem:** {payload.get('symptom', 'other').replace('_', ' ')}",
        f"- **Status:** {payload.get('status', 'captured').replace('_', ' ')}",
        f"- **Captured:** {payload.get('started_at', 'unknown')} to {payload.get('ended_at', 'unknown')}",
        f"- **Measurements:** {payload.get('metrics_count', 0)} · **Rule flags:** {payload.get('anomalies_count', 0)}",
        "",
        "## Summary",
        payload.get("summary", "No summary available."),
        "",
        "## Leading areas to check",
    ]
    hypotheses = evidence.get("hypotheses", [])
    lines.extend(
        f"- **{item.get('title', 'Possible area')}** · {item.get('strength', 'Unrated')} — {item.get('basis', '')}"
        for item in hypotheses
    )
    findings = evidence.get("findings", [])
    if findings:
        lines += ["", "## Findings"]
        lines.extend(
            f"- **{item.get('title', 'Finding')}:** {item.get('detail', '')} ({item.get('strength', '')})"
            for item in findings
        )
    comparisons = evidence.get("before_after", [])
    if comparisons:
        lines += ["", "## Compared with the prior window"]
        lines.extend(
            f"- {item.get('metric_name', 'Metric')}: {item.get('before_median', '—')} → {item.get('during_median', '—')} ({item.get('change_pct', 0):+.0f}%)"
            for item in comparisons
        )
    process_peaks = evidence.get("process_peaks", [])
    if process_peaks:
        lines += ["", "## Process activity"]
        lines.extend(
            f"- {item.get('process_name', 'Application')}: CPU {item.get('peak_cpu_percent', 0):.1f}% · memory {item.get('peak_memory_percent', 0):.1f}% · {item.get('samples', 0)} observations"
            for item in process_peaks[:10]
        )
    verification = evidence.get("verification")
    if verification:
        lines += ["", "## After-change verification", verification.get("summary", "Comparison saved.")]
        lines.extend(
            f"- {item.get('metric_name', 'Metric')}: {item.get('before_median', '—')} → {item.get('after_median', '—')} ({item.get('change_pct', 0):+.0f}%)"
            for item in verification.get("comparisons", [])
        )
    events = evidence.get("system_events", {}).get("events", [])
    lines += ["", "## Windows events"]
    if events:
        lines.extend(
            f"- {item.get('time', 'time unavailable')} · Event {item.get('Id', '—')} · {item.get('source', 'Windows')} · {item.get('message', '')}"
            for item in events[:30]
        )
    else:
        lines.append(evidence.get("system_events", {}).get("reason", "No related events were reported."))
    timeline = evidence.get("timeline", [])
    if timeline:
        lines += ["", "## Timeline"]
        lines.extend(
            f"- {item.get('timestamp', 'time unavailable')} · **{item.get('kind', 'event')}** · {item.get('detail', '')}"
            for item in timeline[-100:]
        )
    checks = evidence.get("next_checks", [])
    if checks:
        lines += ["", "## Suggested next checks"]
        lines.extend(f"- {step}" for step in checks)
    limitations = evidence.get("limitations", [])
    if limitations:
        lines += ["", "## Limits of this result"]
        lines.extend(f"- {item}" for item in limitations)
    lines += ["", "---", "Diagnosys stores this evidence locally. Time overlap is a clue, not proof of cause."]
    return "\n".join(lines)


def compare_metric_windows(before: list[MetricSample], during: list[MetricSample]) -> list[dict]:
    comparisons = []
    metric_names = {item.metric_name for item in before + during}
    for name in sorted(metric_names):
        before_values = [
            float(item.value) for item in before
            if item.metric_name == name and item.status == MetricStatus.OK and isinstance(item.value, (int, float))
        ]
        during_values = [
            float(item.value) for item in during
            if item.metric_name == name and item.status == MetricStatus.OK and isinstance(item.value, (int, float))
        ]
        if before_values and during_values:
            before_average = sum(before_values) / len(before_values)
            during_average = sum(during_values) / len(during_values)
            comparisons.append({
                "metric_name": name,
                "before_average": round(before_average, 2),
                "capture_window_average": round(during_average, 2),
                "change": round(during_average - before_average, 2),
                "unit": next(item.unit for item in during if item.metric_name == name),
            })
    return comparisons


def gib(byte_count: int) -> str:
    return f"{byte_count / (1024 ** 3):.1f} GB"


def rate(bytes_per_second: float | None) -> str:
    if bytes_per_second is None:
        return "Measuring…"
    value = max(0.0, bytes_per_second)
    if value < 1024:
        return f"{value:.0f} B/s"
    if value < 1024 ** 2:
        return f"{value / 1024:.1f} KiB/s"
    return f"{value / (1024 ** 2):.1f} MiB/s"


def history_rate(byte_count: float | None) -> str:
    return "not reported" if byte_count is None else rate(byte_count)


def frequency(mhz: float | None) -> str:
    return f"{mhz / 1000:.2f} GHz" if mhz else "Unavailable"


def duration(seconds: float) -> str:
    if seconds <= 0:
        return "Unavailable"
    total_minutes = int(seconds // 60)
    days, remaining_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining_minutes, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
