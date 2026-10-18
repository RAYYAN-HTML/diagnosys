import sqlite3
import statistics
from typing import List, Optional, Dict
from datetime import datetime, timedelta, timezone

from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.models.diagnostics import Anomaly
from diagnosys.models.baselines import MetricBaseline
from diagnosys.storage.timestamps import parse_timestamp, serialize_timestamp

class MetricRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        
    def save(self, sample: MetricSample):
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO metrics (timestamp, metric_name, value, unit, source, entity_id, status, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            serialize_timestamp(sample.timestamp),
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
        query = "SELECT * FROM metrics WHERE timestamp >= ?"
        cutoff = serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=window_seconds))
        params = [cutoff]
        
        if metric_name:
            query += " AND metric_name = ?"
            params.append(metric_name)
            
        query += " ORDER BY timestamp DESC"
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        return [self._from_row(row) for row in rows]

    def query_between(
        self,
        start: datetime,
        end: datetime,
        metric_name: Optional[str] = None,
        limit: int = 50000,
    ) -> List[MetricSample]:
        query = "SELECT * FROM metrics WHERE timestamp >= ? AND timestamp <= ?"
        params: list[object] = [serialize_timestamp(start), serialize_timestamp(end)]
        if metric_name:
            query += " AND metric_name = ?"
            params.append(metric_name)
        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(max(1, min(limit, 100000)))
        rows = self.conn.execute(query, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row) -> MetricSample:
        return MetricSample(
                timestamp=parse_timestamp(row['timestamp']),
                metric_name=row['metric_name'],
                value=row['value'],
                unit=row['unit'],
                source=row['source'],
                entity_id=row['entity_id'],
                status=MetricStatus(row['status']),
                reason=row['reason']
            )

    def get_baseline(self, metric_name: str, window_seconds: int = 86400) -> MetricBaseline:
        """
        Computes a statistical baseline for a specific metric over the given window.
        Uses Python's statistics module to calculate median and 95th percentile.
        Returns a MetricBaseline with available=False if there is insufficient data.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT value FROM metrics
            WHERE metric_name = ?
              AND status = 'ok'
              AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (
            metric_name,
            serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=window_seconds)),
        ))

        rows = cursor.fetchall()
        values = [row['value'] for row in rows]

        if len(values) < 5:
            return MetricBaseline(
                metric_name=metric_name,
                median=0.0, p95=0.0, min_val=0.0, max_val=0.0,
                sample_count=len(values),
                window_seconds=window_seconds,
                available=False,
                reason=f"Insufficient data: only {len(values)} samples (need at least 5)"
            )

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        # Use statistics.quantiles for standard p95 (method='inclusive')
        p95 = statistics.quantiles(sorted_vals, n=100, method='inclusive')[94]

        return MetricBaseline(
            metric_name=metric_name,
            median=statistics.median(sorted_vals),
            p95=p95,
            min_val=sorted_vals[0],
            max_val=sorted_vals[-1],
            sample_count=len(values),
            window_seconds=window_seconds,
            available=True
        )

    def get_all_baselines(self, window_seconds: int = 86400) -> Dict[str, MetricBaseline]:
        """Returns baselines for all known metrics in the database."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT metric_name FROM metrics")
        metric_names = [row['metric_name'] for row in cursor.fetchall()]
        return {name: self.get_baseline(name, window_seconds) for name in metric_names}

class AnomalyRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        
    def save(self, anomaly: Anomaly):
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO anomalies (timestamp, category, severity, metric, observed_value, expected_value, rule_id, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            serialize_timestamp(anomaly.timestamp),
            anomaly.category,
            anomaly.severity,
            anomaly.metric,
            anomaly.observed_value,
            anomaly.expected_value,
            anomaly.rule_id,
            anomaly.explanation
        ))
        self.conn.commit()

    def has_recent(self, rule_id: str, window_seconds: int = 300) -> bool:
        cutoff = serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=window_seconds))
        row = self.conn.execute(
            "SELECT 1 FROM anomalies WHERE rule_id = ? AND timestamp >= ? LIMIT 1",
            (rule_id, cutoff),
        ).fetchone()
        return row is not None
        
    def query(self, window_seconds: int = 3600) -> List[Anomaly]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM anomalies 
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
        """, (serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=window_seconds)),))
        
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append(Anomaly(
                timestamp=parse_timestamp(row['timestamp']),
                category=row['category'],
                severity=row['severity'],
                metric=row['metric'],
                observed_value=row['observed_value'],
                expected_value=row['expected_value'],
                rule_id=row['rule_id'],
                explanation=row['explanation']
            ))
        return results

    def query_between(self, start: datetime, end: datetime, limit: int = 10000) -> List[Anomaly]:
        rows = self.conn.execute(
            """SELECT * FROM anomalies WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC LIMIT ?""",
            (serialize_timestamp(start), serialize_timestamp(end), max(1, min(limit, 50000))),
        ).fetchall()
        return [Anomaly(
            timestamp=parse_timestamp(row['timestamp']),
            category=row['category'], severity=row['severity'], metric=row['metric'],
            observed_value=row['observed_value'], expected_value=row['expected_value'],
            rule_id=row['rule_id'], explanation=row['explanation'],
        ) for row in rows]
