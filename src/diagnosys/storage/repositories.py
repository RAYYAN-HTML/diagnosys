import sqlite3
from typing import List, Optional
from datetime import datetime, timezone

from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.models.diagnostics import Anomaly

class MetricRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        
    def save(self, sample: MetricSample):
        cursor = self.conn.cursor()
        
        # Ensure timestamp is a datetime object, naive or utc is fine, sqlite adapts it
        ts = sample.timestamp
        if ts.tzinfo is None:
             ts = ts.replace(tzinfo=timezone.utc)
             
        cursor.execute("""
            INSERT INTO metrics (timestamp, metric_name, value, unit, source, entity_id, status, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts,
            sample.metric_name,
            float(sample.value) if sample.value is not None else 0.0,
            sample.unit,
            sample.source,
            sample.entity_id,
            sample.status.value,
            sample.reason
        ))
        self.conn.commit()
        
    def query(self, window_seconds: int = 3600, metric_name: Optional[str] = None) -> List[MetricSample]:
        cursor = self.conn.cursor()
        query = "SELECT * FROM metrics WHERE timestamp >= datetime('now', ?)"
        params = [f'-{window_seconds} seconds']
        
        if metric_name:
            query += " AND metric_name = ?"
            params.append(metric_name)
            
        query += " ORDER BY timestamp DESC"
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append(MetricSample(
                timestamp=row['timestamp'],
                metric_name=row['metric_name'],
                value=row['value'],
                unit=row['unit'],
                source=row['source'],
                entity_id=row['entity_id'],
                status=MetricStatus(row['status']),
                reason=row['reason']
            ))
        return results

class AnomalyRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        
    def save(self, anomaly: Anomaly):
        cursor = self.conn.cursor()
        
        ts = anomaly.timestamp
        if ts.tzinfo is None:
             ts = ts.replace(tzinfo=timezone.utc)
             
        cursor.execute("""
            INSERT INTO anomalies (timestamp, category, severity, metric, observed_value, expected_value, rule_id, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts,
            anomaly.category,
            anomaly.severity,
            anomaly.metric,
            anomaly.observed_value,
            anomaly.expected_value,
            anomaly.rule_id,
            anomaly.explanation
        ))
        self.conn.commit()
        
    def query(self, window_seconds: int = 3600) -> List[Anomaly]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM anomalies 
            WHERE timestamp >= datetime('now', ?)
            ORDER BY timestamp DESC
        """, (f'-{window_seconds} seconds',))
        
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append(Anomaly(
                timestamp=row['timestamp'],
                category=row['category'],
                severity=row['severity'],
                metric=row['metric'],
                observed_value=row['observed_value'],
                expected_value=row['expected_value'],
                rule_id=row['rule_id'],
                explanation=row['explanation']
            ))
        return results
