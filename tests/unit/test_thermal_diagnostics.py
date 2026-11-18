from datetime import datetime, timedelta, timezone

from diagnosys.diagnostics.thermal import ThermalDiagnosticEngine
from diagnosys.models.metrics import MetricSample, MetricStatus


def test_sustained_temperature_uses_sensor_reported_high_limit():
    now = datetime.now(timezone.utc)
    history = [
        {
            "timestamp": (now - timedelta(seconds=seconds)).isoformat(),
            "sensor": "coretemp",
            "label": "CPU Package",
            "temperature_c": 92.0,
            "high_c": 90.0,
            "critical_c": 105.0,
            "reading_kind": "temperature",
        }
        for seconds in (40, 30, 20, 10, 0)
    ]
    metrics = [
        MetricSample(now, "cpu_percent", 88.0, "%", "system", MetricStatus.OK),
        MetricSample(now, "cpu_frequency_mhz", 1800.0, "MHz", "system", MetricStatus.OK),
        MetricSample(now - timedelta(seconds=180), "cpu_frequency_mhz", 2400.0, "MHz", "system", MetricStatus.OK),
    ]

    findings = ThermalDiagnosticEngine().evaluate(history, metrics, now)

    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
    assert findings[0].expected_value == 90.0
    assert "CPU utilization median 88.0 %" in findings[0].explanation
    assert "Current CPU frequency median 1800.0 MHz" in findings[0].explanation
    assert "cpu frequency mhz preceding-window median 2400.0 MHz" in findings[0].explanation
    assert "do not prove performance loss or thermal throttling" in findings[0].explanation


def test_critical_sensor_limit_is_reported_without_waiting_for_sustained_samples():
    now = datetime.now(timezone.utc)
    history = [{
        "timestamp": now.isoformat(),
        "sensor": "coretemp",
        "label": "CPU Package",
        "temperature_c": 106.0,
        "high_c": 90.0,
        "critical_c": 105.0,
        "reading_kind": "temperature",
    }]

    findings = ThermalDiagnosticEngine().evaluate(history, [], now)

    assert len(findings) == 1
    assert findings[0].severity == "CRITICAL"
    assert findings[0].expected_value == 105.0
    assert findings[0].rule_id.startswith("thermal_sensor_limit_critical_")


def test_no_hardware_limits_means_no_universal_temperature_warning():
    now = datetime.now(timezone.utc)
    history = [{
        "timestamp": now.isoformat(),
        "sensor": "unknown_sensor",
        "label": "Unknown",
        "temperature_c": 99.0,
        "high_c": None,
        "critical_c": None,
        "reading_kind": "temperature",
    }]

    assert ThermalDiagnosticEngine().evaluate(history, [], now) == []


def test_sustained_rule_requires_time_span_not_only_many_samples():
    now = datetime.now(timezone.utc)
    history = [
        {
            "timestamp": (now - timedelta(seconds=seconds)).isoformat(),
            "sensor": "coretemp",
            "label": "CPU Package",
            "temperature_c": 95.0,
            "high_c": 90.0,
            "critical_c": 105.0,
            "reading_kind": "temperature",
        }
        for seconds in (4, 2, 0)
    ]

    assert ThermalDiagnosticEngine().evaluate(history, [], now) == []
