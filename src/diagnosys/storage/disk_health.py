"""Read-only history for discovered SMART/NVMe devices."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from diagnosys.collectors.system.disk_health import DiskHealth
from diagnosys.storage.timestamps import parse_timestamp, serialize_timestamp


class DiskHealthRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, reading: DiskHealth, observed_at: datetime | None = None) -> None:
        timestamp = serialize_timestamp(observed_at or datetime.now(timezone.utc))
        self.conn.execute(
            """INSERT INTO disk_health_samples
            (timestamp, device, available, state, health_status, temperature_c,
             power_on_hours, percentage_used, media_errors, critical_warning,
             available_spare_percent, spare_threshold_percent, reallocated_sectors, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp, reading.device, int(reading.available), reading.state,
                reading.health_status, reading.temperature_c, reading.power_on_hours,
                reading.percentage_used, reading.media_errors, reading.critical_warning,
                reading.available_spare_percent, reading.spare_threshold_percent,
                reading.reallocated_sectors, reading.reason,
            ),
        )
        self.conn.commit()

    def latest(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            """SELECT sample.* FROM disk_health_samples AS sample
            JOIN (SELECT device, MAX(timestamp) AS latest_at
                  FROM disk_health_samples GROUP BY device) AS latest
            ON sample.device = latest.device AND sample.timestamp = latest.latest_at
            ORDER BY sample.device LIMIT ?""",
            (max(1, min(limit, 500)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def history(self, device: str, window_seconds: int = 30 * 86400, limit: int = 5000) -> list[dict]:
        cutoff = serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=max(1, window_seconds)))
        rows = self.conn.execute(
            """SELECT * FROM disk_health_samples
            WHERE device = ? AND timestamp >= ?
            ORDER BY timestamp ASC LIMIT ?""",
            (device, cutoff, max(1, min(limit, 50000))),
        ).fetchall()
        return [dict(row) for row in rows]
