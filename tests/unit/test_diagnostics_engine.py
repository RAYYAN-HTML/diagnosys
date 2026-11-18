from datetime import datetime, timezone
from diagnosys.diagnostics.engine import DiagnosticEngine
from diagnosys.diagnostics.rules import AnomalyDetector
from diagnosys.models.baselines import MetricBaseline
from diagnosys.models.diagnostics import Anomaly
from diagnosys.models.metrics import MetricSample, MetricStatus

def test_no_anomaly_is_not_reported_as_proven_healthy():
    result = DiagnosticEngine().diagnose([], 300)
    assert result.status == "NO_ANOMALY"
    assert result.primary_hypothesis is None

def test_hypothesis_has_evidence_not_arbitrary_probability():
    now = datetime.now(timezone.utc)
    anomalies = [
        Anomaly(now, "CPU_PRESSURE", "WARNING", "cpu_percent", 98.0, 70.0, "cpu_percent_personal_baseline_deviation", "CPU deviation"),
        Anomaly(now, "CPU_PRESSURE", "WARNING", "cpu_percent", 96.0, 70.0, "cpu_percent_personal_baseline_deviation", "CPU deviation"),
    ]
    result = DiagnosticEngine().diagnose(anomalies, 60)
    assert result.status == "INVESTIGATE"
    assert result.primary_hypothesis.category == "LOCAL_RESOURCE_CONTENTION"
    assert len(result.primary_hypothesis.evidence) == 2
    assert not hasattr(result.primary_hypothesis, "score")
    assert not hasattr(result.primary_hypothesis, "confidence")

def test_rule_waits_for_sufficient_personal_history():
    baseline = MetricBaseline("cpu_percent", 25.0, 40.0, 5.0, 60.0, 29, 86400, True, mad=5.0)
    sample = MetricSample(datetime.now(timezone.utc), "cpu_percent", 99.0, "%", "system", MetricStatus.OK)
    assert AnomalyDetector({"cpu_percent": baseline}).evaluate_sample(sample) == []

def test_rule_uses_learned_variation_band():
    baseline = MetricBaseline("cpu_percent", 25.0, 40.0, 5.0, 60.0, 100, 86400, True, mad=5.0)
    sample = MetricSample(datetime.now(timezone.utc), "cpu_percent", 99.0, "%", "system", MetricStatus.OK)
    anomalies = AnomalyDetector({"cpu_percent": baseline}).evaluate_sample(sample)
    assert len(anomalies) == 1
    assert anomalies[0].expected_value > 40.0
    assert "personal" in anomalies[0].explanation


def test_hardware_reported_thermal_limit_is_included_in_diagnosis():
    now = datetime.now(timezone.utc)
    anomaly = Anomaly(
        now, "THERMAL_LIMIT", "WARNING", "thermal_temperature_c", 94.0, 90.0,
        "thermal_sensor_limit_sustained_coretemp", "CPU package remained above its reported high limit.",
    )
    result = DiagnosticEngine().diagnose([anomaly], 60)
    assert result.status == "INVESTIGATE"
    assert result.primary_hypothesis.category == "OBSERVED_THERMAL_LIMIT"
    assert result.primary_hypothesis.evidence[0].observed_value == 94.0
    assert any("hardware" in item.lower() for item in result.primary_hypothesis.recommended_checks)
