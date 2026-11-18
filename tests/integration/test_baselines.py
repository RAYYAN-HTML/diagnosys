import pytest
import sqlite3
from datetime import datetime, timezone, timedelta

from diagnosys.storage.database import init_db
from diagnosys.storage.repositories import MetricRepository
from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.diagnostics.rules import AnomalyDetector

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()

def _insert_samples(repo, metric_name, values):
    """Helper to insert a list of float values as MetricSamples."""
    now = datetime.now(timezone.utc)
    for i, v in enumerate(values):
        ts = now - timedelta(seconds=len(values) - i)
        repo.save(MetricSample(
            timestamp=ts, metric_name=metric_name, value=v,
            unit="%", source="test", status=MetricStatus.OK
        ))

def test_baseline_insufficient_data(db_conn):
    repo = MetricRepository(db_conn)
    _insert_samples(repo, "cpu_percent", [40.0, 50.0])  # Only 2 samples — below threshold

    b = repo.get_baseline("cpu_percent", window_seconds=86400)
    assert b.available is False
    assert b.sample_count == 2

def test_baseline_computes_correctly(db_conn):
    repo = MetricRepository(db_conn)
    # 30 observations are required before a personal baseline is considered usable.
    values = [float(value) for value in range(10, 40)]
    _insert_samples(repo, "cpu_percent", values)

    b = repo.get_baseline("cpu_percent", window_seconds=86400)
    assert b.available is True
    assert b.sample_count == 30
    assert b.median == 24.5
    assert b.min_val == 10.0
    assert b.max_val == 39.0
    assert b.p95 >= 37.0
    assert b.mad > 0

def test_get_all_baselines(db_conn):
    repo = MetricRepository(db_conn)
    _insert_samples(repo, "cpu_percent", [float(20 + (i % 5)) for i in range(30)])
    _insert_samples(repo, "memory_percent", [float(50 + (i % 5)) for i in range(30)])

    baselines = repo.get_all_baselines(window_seconds=86400)
    assert "cpu_percent" in baselines
    assert "memory_percent" in baselines

def test_anomaly_detector_uses_baseline(db_conn):
    """If a baseline exists with low p95, a moderate reading should trigger an anomaly."""
    repo = MetricRepository(db_conn)
    # Simulate a quiet machine where CPU p95 is only 40%
    _insert_samples(repo, "cpu_percent", [float(30 + (i % 3)) for i in range(30)])

    baselines = repo.get_all_baselines(window_seconds=86400)
    detector = AnomalyDetector(baselines=baselines)

    # A reading far beyond the personal robust variation band should trigger.
    now = datetime.now(timezone.utc)
    sample = MetricSample(
        timestamp=now, metric_name="cpu_percent", value=99.0,
        unit="%", source="test", status=MetricStatus.OK
    )
    anomalies = detector.evaluate_sample(sample)
    assert len(anomalies) == 1
    assert anomalies[0].category == "CPU_PRESSURE"
    assert "personal_baseline" in anomalies[0].rule_id

def test_anomaly_detector_no_anomaly_within_baseline(db_conn):
    """If value is within baseline p95 + margin, no anomaly should be raised."""
    repo = MetricRepository(db_conn)
    _insert_samples(repo, "cpu_percent", [float(30 + (i % 3)) for i in range(30)])

    baselines = repo.get_all_baselines(window_seconds=86400)
    detector = AnomalyDetector(baselines=baselines)

    now = datetime.now(timezone.utc)
    sample = MetricSample(
        timestamp=now, metric_name="cpu_percent", value=32.0,  # within the personal variation band
        unit="%", source="test", status=MetricStatus.OK
    )
    anomalies = detector.evaluate_sample(sample)
    assert len(anomalies) == 0
