import pytest
import sqlite3
from datetime import datetime, timezone

from diagnosys.storage.database import init_db
from diagnosys.storage.repositories import MetricRepository, AnomalyRepository
from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.models.diagnostics import Anomaly

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()

def test_metric_repository(db_conn):
    repo = MetricRepository(db_conn)
    
    sample = MetricSample(
        timestamp=datetime.now(timezone.utc),
        metric_name="cpu_percent",
        value=55.5,
        unit="%",
        source="system",
        status=MetricStatus.OK
    )
    
    repo.save(sample)
    
    results = repo.query(window_seconds=3600)
    assert len(results) == 1
    
    # Query specific metric
    results = repo.query(window_seconds=3600, metric_name="cpu_percent")
    assert len(results) == 1
    assert results[0].value == 55.5
    
    results = repo.query(window_seconds=3600, metric_name="memory_percent")
    assert len(results) == 0

def test_anomaly_repository(db_conn):
    repo = AnomalyRepository(db_conn)
    
    anomaly = Anomaly(
        timestamp=datetime.now(timezone.utc),
        category="CPU_PRESSURE",
        severity="WARNING",
        metric="cpu_percent",
        observed_value=95.0,
        expected_value=80.0,
        rule_id="cpu_usage_high",
        explanation="CPU usage exceeded 80%"
    )
    
    repo.save(anomaly)
    
    results = repo.query(window_seconds=3600)
    assert len(results) == 1
    assert results[0].category == "CPU_PRESSURE"
    assert results[0].observed_value == 95.0
