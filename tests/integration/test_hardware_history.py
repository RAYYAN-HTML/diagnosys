import sqlite3
from datetime import datetime, timezone

from diagnosys.collectors.system.disk_health import DiskDevice, DiskHealth
from diagnosys.collectors.system.thermal import FanReading, ThermalReading, ThermalSnapshot
from diagnosys.storage.database import init_db
from diagnosys.storage.hardware import HardwareHistoryRepository


def test_hardware_history_persists_temperature_fan_and_disk_observations():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repository = HardwareHistoryRepository(conn)
    timestamp = datetime.now(timezone.utc)

    thermal = ThermalSnapshot(
        True,
        temperatures=(ThermalReading("coretemp", "Package", 67.5, 85.0, 100.0),),
        fans=(FanReading("nct6798", "CPU Fan", 1200.0),),
    )
    repository.save_thermal(thermal, timestamp)

    device = DiskDevice("/dev/nvme0", "NVMe", "Example SSD")
    health = DiskHealth(
        device="/dev/nvme0", available=True, health_status="PASSED",
        temperature_c=42.0, power_on_hours=1200, percentage_used=8.0,
        state="healthy", media_errors=0, critical_warning=0,
        available_spare_percent=100.0, spare_threshold_percent=10.0,
    )
    repository.save_disk_health(device, health, timestamp)

    thermal_rows = repository.query_thermal()
    disk_rows = repository.query_disk_health()
    assert len(thermal_rows) == 2
    assert {row["reading_kind"] for row in thermal_rows} == {"temperature", "fan_rpm"}
    assert thermal_rows[0]["temperature_c"] == 67.5
    assert thermal_rows[1]["temperature_c"] is None
    assert thermal_rows[1]["fan_speed_rpm"] == 1200.0
    assert len(disk_rows) == 1
    assert disk_rows[0]["device"] == "/dev/nvme0"
    assert disk_rows[0]["percentage_used"] == 8.0
    assert disk_rows[0]["state"] == "healthy"
    conn.close()


def test_unavailable_thermal_snapshot_does_not_create_fake_history():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repository = HardwareHistoryRepository(conn)
    repository.save_thermal(ThermalSnapshot(False, reason="No sensors exposed"))
    assert repository.query_thermal() == []
    conn.close()
