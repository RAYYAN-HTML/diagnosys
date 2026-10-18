import pytest
import sqlite3
from datetime import datetime, timedelta, timezone

from diagnosys.storage.database import init_db
from diagnosys.storage.repositories import MetricRepository, AnomalyRepository
from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.models.diagnostics import Anomaly
from diagnosys.models.incidents import Incident
from diagnosys.models.metrics import ProcessInfo, ProcessSnapshot
from diagnosys.storage.incidents import IncidentRepository
from diagnosys.storage.processes import ProcessRepository

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
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


def test_process_repository_keeps_resource_and_connection_history(db_conn):
    repo = ProcessRepository(db_conn)
    process = ProcessInfo(
        pid=123, name="example-app", username="private-user", cpu_percent=42.0,
        memory_percent=12.0, read_bytes_per_sec=2048.0,
        write_bytes_per_sec=1024.0, network_connection_count=3,
    )
    repo.save_snapshot(ProcessSnapshot(datetime.now(timezone.utc), 1, [process], [process]))

    rows = repo.query(window_seconds=3600)
    peaks = repo.top_processes(window_seconds=3600)
    assert len(rows) == 1
    assert rows[0]["read_bytes_per_sec"] == 2048.0
    assert rows[0]["network_connection_count"] == 3
    assert peaks[0]["process_name"] == "example-app"
    assert peaks[0]["peak_write_bytes_per_sec"] == 1024.0


def test_incident_repository_round_trips_full_evidence(db_conn):
    repository = IncidentRepository(db_conn)
    now = datetime.now(timezone.utc)
    evidence = {
        "before_after": [{"metric_name": "cpu_percent", "before_average": 20, "capture_window_average": 90}],
        "processes": [{"process_name": "example-app", "cpu_percent": 80}],
        "system_events": {"available": False, "events": []},
    }
    incident_id = repository.save(
        Incident(None, now - timedelta(minutes=5), now, "Slowdown", "CPU pressure", 1, 1, "CPU_PRESSURE", evidence)
    )

    saved = repository.query()[0]
    assert saved.id == incident_id
    assert saved.evidence == evidence


def test_legacy_schema_adds_incident_evidence_and_process_counters():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE incidents (
            id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT NOT NULL,
            title TEXT NOT NULL, summary TEXT NOT NULL, metrics_count INTEGER NOT NULL,
            anomalies_count INTEGER NOT NULL, diagnosis_category TEXT
        );
        CREATE TABLE process_samples (
            id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, pid INTEGER NOT NULL,
            process_name TEXT NOT NULL, cpu_percent REAL NOT NULL, memory_percent REAL NOT NULL
        );
        PRAGMA user_version = 1;
    """)

    init_db(conn)

    incident_columns = {row[1] for row in conn.execute("PRAGMA table_info(incidents)")}
    process_columns = {row[1] for row in conn.execute("PRAGMA table_info(process_samples)")}
    assert "evidence_json" in incident_columns
    assert {"read_bytes_per_sec", "write_bytes_per_sec", "network_connection_count"} <= process_columns
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    conn.close()
