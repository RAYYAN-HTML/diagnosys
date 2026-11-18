"""Persistence for hardware telemetry histories."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from diagnosys.collectors.system.disk_health import DiskHealth, DiskDevice
from diagnosys.collectors.system.thermal import ThermalSnapshot
from diagnosys.storage.timestamps import serialize_timestamp


class HardwareHistoryRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_thermal(self, snapshot: ThermalSnapshot, timestamp: datetime | None = None) -> None:
        if not snapshot.available:
            return
        stamp = serialize_timestamp(timestamp or datetime.now(timezone.utc))
        rows = [
            (stamp, item.sensor, item.label, item.temperature_c, None, item.high_c, item.critical_c, "temperature")
            for item in snapshot.temperatures
        ]
        rows.extend(
            (stamp, item.sensor, item.label, None, item.speed_rpm, None, None, "fan_rpm")
            for item in snapshot.fans
        )
        if rows:
            self.conn.executemany(
                """INSERT INTO thermal_samples
                (timestamp, sensor, label, temperature_c, fan_speed_rpm, high_c, critical_c, reading_kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            self.conn.commit()

    def query_thermal(self, window_seconds: int = 86400, limit: int = 10000) -> list[dict]:
        cutoff = serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=max(1, window_seconds)))
        rows = self.conn.execute(
            """SELECT timestamp, sensor, label, temperature_c, fan_speed_rpm, high_c, critical_c, reading_kind
            FROM thermal_samples WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?""",
            (cutoff, max(1, min(limit, 100000))),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def save_disk_health(self, device: DiskDevice, health: DiskHealth, timestamp: datetime | None = None) -> None:
        self.conn.execute(
            """INSERT INTO disk_health_samples
            (timestamp, device, protocol, state, health_status, temperature_c, power_on_hours,
             percentage_used, media_errors, critical_warning, available_spare_percent,
             spare_threshold_percent, reallocated_sectors, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                serialize_timestamp(timestamp or datetime.now(timezone.utc)),
                device.device, device.protocol, health.state, health.health_status,
                health.temperature_c, health.power_on_hours, health.percentage_used,
                health.media_errors, health.critical_warning, health.available_spare_percent,
                health.spare_threshold_percent, health.reallocated_sectors, health.reason,
            ),
        )
        self.conn.commit()

    def query_disk_health(self, window_seconds: int = 30 * 86400, limit: int = 10000) -> list[dict]:
        cutoff = serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=max(1, window_seconds)))
        rows = self.conn.execute(
            """SELECT timestamp, device, protocol, state, health_status, temperature_c,
            power_on_hours, percentage_used, media_errors, critical_warning,
            available_spare_percent, spare_threshold_percent, reallocated_sectors, reason
            FROM disk_health_samples WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?""",
            (cutoff, max(1, min(limit, 100000))),
        ).fetchall()
        return [dict(row) for row in rows]
