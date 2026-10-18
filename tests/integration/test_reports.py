import pytest
from datetime import datetime, timedelta, timezone
from diagnosys.models.incidents import Incident
from diagnosys.models.metrics import ProcessInfo, ProcessSnapshot
from diagnosys.storage.database import get_connection, init_db
from diagnosys.storage.repositories import MetricRepository, AnomalyRepository
from diagnosys.diagnostics.engine import DiagnosticEngine
from diagnosys.reports.generator import ReportGenerator
from diagnosys.storage.incidents import IncidentRepository
from diagnosys.storage.processes import ProcessRepository

@pytest.fixture
def db_conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn

def test_report_generator(db_conn):
    metric_repo = MetricRepository(db_conn)
    anomaly_repo = AnomalyRepository(db_conn)
    diag_engine = DiagnosticEngine()
    
    generator = ReportGenerator(metric_repo, anomaly_repo, diag_engine)
    report = generator.generate_report()
    
    assert report is not None
    assert "os" in report.system_info
    assert len(report.baselines) == 0
    
    text_out = generator.format_text(report)
    assert "DIAGNOSYS REPORT" in text_out
    
    json_out = generator.format_json(report)
    assert "system_info" in json_out
    
    md_out = generator.format_markdown(report)
    assert "# Diagnosys Report" in md_out
    html_out = generator.format_html(report)
    assert "<html lang=\"en\">" in html_out
    assert "Sensitive identifiers redacted" in html_out


def test_support_report_redacts_process_and_incident_identifiers(db_conn):
    now = datetime.now(timezone.utc)
    ProcessRepository(db_conn).save_snapshot(ProcessSnapshot(
        now, 1,
        [ProcessInfo(42, "private-app-name", "private-user", 72.0, 22.0, 8192, 4096, 4)],
        [],
    ))
    IncidentRepository(db_conn).save(Incident(
        None, now - timedelta(minutes=5), now, "private-incident-title", "Local resource contention",
        3, 1, "LOCAL_RESOURCE_CONTENTION",
        evidence={"target": "private.example", "message": "private event details"},
    ))
    generator = ReportGenerator(
        MetricRepository(db_conn), AnomalyRepository(db_conn), DiagnosticEngine(),
        ProcessRepository(db_conn), IncidentRepository(db_conn),
    )

    redacted_json = generator.format_json(generator.generate_report(), redact=True)
    redacted_html = generator.format_html(generator.generate_report(), redact=True)

    for secret in ("private-app-name", "private-user", "private-incident-title", "private.example", "private event details"):
        assert secret not in redacted_json
        assert secret not in redacted_html
    assert "Application" in redacted_html
