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
    # Insert 10 known values to make percentile math predictable
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    _insert_samples(repo, "cpu_percent", values)

    b = repo.get_baseline("cpu_percent", window_seconds=86400)
    assert b.available is True
    assert b.sample_count == 10
    assert b.median == 55.0  # median of sorted 10 values
    assert b.min_val == 10.0
    assert b.max_val == 100.0
    # p95 using statistics.quantiles inclusive method on 10 uniform values
    # 95th percentile of [10..100] in steps of 10 ≈ 95.5 (interpolated)
    assert b.p95 >= 90.0

def test_get_all_baselines(db_conn):
    repo = MetricRepository(db_conn)
    _insert_samples(repo, "cpu_percent", [40.0, 50.0, 60.0, 70.0, 80.0])
    _insert_samples(repo, "memory_percent", [60.0, 65.0, 70.0, 75.0, 80.0])

    baselines = repo.get_all_baselines(window_seconds=86400)
    assert "cpu_percent" in baselines
    assert "memory_percent" in baselines

def test_anomaly_detector_uses_baseline(db_conn):
    """If a baseline exists with low p95, a moderate reading should trigger an anomaly."""
    repo = MetricRepository(db_conn)
    # Simulate a quiet machine where CPU p95 is only 40%
    _insert_samples(repo, "cpu_percent", [10.0, 20.0, 30.0, 35.0, 40.0, 40.0, 38.0, 36.0, 35.0, 34.0])

    baselines = repo.get_all_baselines(window_seconds=86400)
    detector = AnomalyDetector(baselines=baselines)

    # p95 of our data ≈ 40. Threshold = 40 + 20 = 60. Current CPU of 62 should trigger.
    now = datetime.now(timezone.utc)
    sample = MetricSample(
        timestamp=now, metric_name="cpu_percent", value=62.0,
        unit="%", source="test", status=MetricStatus.OK
    )
    anomalies = detector.evaluate_sample(sample)
    assert len(anomalies) == 1
    assert anomalies[0].category == "CPU_PRESSURE"
    assert "baseline" in anomalies[0].rule_id

def test_anomaly_detector_no_anomaly_within_baseline(db_conn):
    """If value is within baseline p95 + margin, no anomaly should be raised."""
    repo = MetricRepository(db_conn)
    _insert_samples(repo, "cpu_percent", [10.0, 20.0, 30.0, 35.0, 40.0, 40.0, 38.0, 36.0, 35.0, 34.0])

    baselines = repo.get_all_baselines(window_seconds=86400)
    detector = AnomalyDetector(baselines=baselines)

    now = datetime.now(timezone.utc)
    sample = MetricSample(
        timestamp=now, metric_name="cpu_percent", value=50.0,  # below threshold of 60
        unit="%", source="test", status=MetricStatus.OK
    )
    anomalies = detector.evaluate_sample(sample)
    assert len(anomalies) == 0
