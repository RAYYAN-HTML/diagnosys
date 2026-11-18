from datetime import datetime, timezone

from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.ui import formatters


def test_incident_redaction_removes_identifiers_and_process_names():
    payload = {
        "id": 12,
        "title": "Slowdown on MY-PC",
        "hostname": "MY-PC",
        "evidence": {
            "process_peaks": [{"process_name": "private-game.exe"}],
            "timeline": [{"detail": "private-game.exe on MY-PC"}],
        },
    }
    cleaned = formatters.redact_incident_payload(payload)
    assert cleaned["title"] == "Incident #12"
    assert cleaned["hostname"] == "[redacted]"
    assert cleaned["evidence"]["timeline"][0]["detail"] == "[redacted timeline details]"


def test_incident_markdown_includes_findings_and_limitations():
    payload = {
        "title": "Captured slowdown",
        "symptom": "slow_pc",
        "status": "captured",
        "evidence": {
            "findings": [{"title": "CPU deviation", "detail": "Outside local baseline", "strength": "Repeated"}],
            "limitations": ["Time overlap does not prove causation."],
        },
    }
    rendered = formatters.incident_markdown(payload)
    assert "CPU deviation" in rendered
    assert "Time overlap does not prove causation." in rendered


def test_metric_window_comparison_uses_only_available_numeric_samples():
    now = datetime.now(timezone.utc)
    before = [
        MetricSample(now, "cpu_percent", 20.0, "%", "system", MetricStatus.OK),
        MetricSample(now, "cpu_percent", None, "%", "system", MetricStatus.UNAVAILABLE),
    ]
    during = [MetricSample(now, "cpu_percent", 50.0, "%", "system", MetricStatus.OK)]
    result = formatters.compare_metric_windows(before, during)
    assert result == [{
        "metric_name": "cpu_percent",
        "before_average": 20.0,
        "capture_window_average": 50.0,
        "change": 30.0,
        "unit": "%",
    }]


def test_metric_formatters_handle_unavailable_values():
    assert formatters.rate(None) == "Measuring…"
    assert formatters.history_rate(None) == "not reported"
    assert formatters.frequency(None) == "Unavailable"
    assert formatters.duration(0) == "Unavailable"
