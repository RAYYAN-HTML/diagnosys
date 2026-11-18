from unittest.mock import patch
from diagnosys.collectors.system.thermal import ThermalCollector
from diagnosys.collectors.system.disk_health import DiskHealthCollector

def test_thermal_collector_reports_unavailable_when_no_sensor_api():
    with patch("diagnosys.collectors.system.thermal.psutil.sensors_temperatures", None):
        result = ThermalCollector().collect()
    assert not result.available
    assert result.reason

def test_smartctl_missing_is_explicit():
    with patch("diagnosys.collectors.system.disk_health.shutil.which", return_value=None):
        result = DiskHealthCollector().collect("/dev/sda")
    assert not result.available
    assert "smartctl" in result.reason
