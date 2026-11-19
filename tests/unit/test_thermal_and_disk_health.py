import json
from types import SimpleNamespace
from unittest.mock import patch

from diagnosys.collectors.system.thermal import ThermalCollector
from diagnosys.collectors.system.disk_health import DiskHealthCollector, DiskDevice


def test_thermal_collector_reports_unavailable_when_no_sensor_api():
    with patch("diagnosys.collectors.system.thermal.psutil.sensors_temperatures", None, create=True):
        with patch("diagnosys.collectors.system.thermal.psutil.sensors_fans", return_value={}, create=True):
            result = ThermalCollector().collect()
    assert not result.available
    assert result.reason


def test_smartctl_missing_is_explicit():
    with patch("diagnosys.collectors.system.disk_health.shutil.which", return_value=None):
        result = DiskHealthCollector().collect("/dev/sda")
    assert not result.available
    assert result.state == "tool_missing"
    assert "smartctl" in result.reason


def test_smartctl_discovers_devices_from_json():
    payload = {"devices": [{"name": "/dev/nvme0", "protocol": "NVMe", "info_name": "Example SSD"}]}
    completed = SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)
    collector = DiskHealthCollector(executable="smartctl")
    with patch("diagnosys.collectors.system.disk_health.subprocess.run", return_value=completed) as run:
        result = collector.discover()
    assert result.available
    assert result.devices == (DiskDevice("/dev/nvme0", "NVMe", "Example SSD", None),)
    assert run.call_args.args[0] == ["smartctl", "--scan-open", "-j"]


def test_smartctl_nvme_health_data_is_parsed_without_invented_values():
    payload = {
        "smart_status": {"passed": True},
        "temperature": {"current": 42},
        "power_on_time": {"hours": 1234},
        "nvme_smart_health_information_log": {
            "percentage_used": 7,
            "media_errors": 0,
            "critical_warning": 0,
            "available_spare": 100,
            "available_spare_threshold": 10,
        },
    }
    completed = SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)
    collector = DiskHealthCollector(executable="smartctl")
    with patch("diagnosys.collectors.system.disk_health.subprocess.run", return_value=completed):
        result = collector.collect("/dev/nvme0")
    assert result.available
    assert result.state == "healthy"
    assert result.health_status == "PASSED"
    assert result.temperature_c == 42
    assert result.power_on_hours == 1234
    assert result.percentage_used == 7
    assert result.media_errors == 0
    assert result.critical_warning == 0


def test_smartctl_nvme_critical_warning_is_not_reported_as_healthy():
    payload = {
        "smart_status": {"passed": True},
        "nvme_smart_health_information_log": {"critical_warning": 2},
    }
    completed = SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)
    collector = DiskHealthCollector(executable="smartctl")
    with patch("diagnosys.collectors.system.disk_health.subprocess.run", return_value=completed):
        result = collector.collect("/dev/nvme0")
    assert result.state == "warning"
    assert result.reason
    assert result.temperature_c is None


def test_smartctl_permission_error_is_classified():
    completed = SimpleNamespace(stdout="", stderr="Permission denied", returncode=2)
    collector = DiskHealthCollector(executable="smartctl")
    with patch("diagnosys.collectors.system.disk_health.subprocess.run", return_value=completed):
        result = collector.collect("/dev/sda")
    assert not result.available
    assert result.state == "permission_denied"


def test_smartctl_timeout_is_explicit():
    import subprocess

    collector = DiskHealthCollector(executable="smartctl", timeout_seconds=2)
    with patch("diagnosys.collectors.system.disk_health.subprocess.run", side_effect=subprocess.TimeoutExpired("smartctl", 2)):
        result = collector.collect("/dev/sda")
    assert not result.available
    assert result.state == "timeout"


def test_smartctl_discovery_reports_missing_optional_tool_state():
    with patch("diagnosys.collectors.system.disk_health.shutil.which", return_value=None):
        result = DiskHealthCollector().discover()
    assert not result.available
    assert result.state == "tool_missing"


def test_nvme_health_can_be_passed_without_ata_smart_status_field():
    import json
    from types import SimpleNamespace

    payload = {
        "nvme_smart_health_information_log": {
            "critical_warning": 0,
            "percentage_used": 12,
            "media_errors": 0,
        }
    }
    completed = SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)
    collector = DiskHealthCollector(executable="smartctl")
    with patch("diagnosys.collectors.system.disk_health.subprocess.run", return_value=completed):
        result = collector.collect("/dev/nvme0")
    assert result.state == "healthy"
    assert result.health_status == "PASSED"
    assert result.percentage_used == 12



def test_smartctl_nonzero_nvme_media_errors_are_a_warning_even_when_smart_passes():
    payload = {
        "smart_status": {"passed": True},
        "nvme_smart_health_information_log": {
            "critical_warning": 0,
            "media_errors": 3,
            "percentage_used": 12,
        },
    }
    completed = SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)
    collector = DiskHealthCollector(executable="smartctl")
    with patch("diagnosys.collectors.system.disk_health.subprocess.run", return_value=completed):
        result = collector.collect("/dev/nvme0")

    assert result.available
    assert result.state == "warning"
    assert result.health_status == "WARNING"
    assert result.media_errors == 3
    assert "3 NVMe media error" in result.reason


def test_thermal_collector_keeps_valid_sensors_when_one_sensor_is_malformed():
    valid = SimpleNamespace(label="CPU Package", current=67.5, high=90.0, critical=105.0)
    malformed = SimpleNamespace(label="Broken", current=float("nan"), high=None, critical=None)
    with patch(
        "diagnosys.collectors.system.thermal.psutil.sensors_temperatures",
        return_value={"coretemp": [valid], "broken": [malformed]},
        create=True,
    ):
        with patch(
            "diagnosys.collectors.system.thermal.psutil.sensors_fans",
            return_value={},
            create=True,
        ):
            result = ThermalCollector().collect()
    assert result.available
    assert len(result.temperatures) == 1
    assert result.temperatures[0].temperature_c == 67.5
    assert result.temperatures[0].high_c == 90.0


def test_thermal_collector_reports_fans_when_temperature_api_is_empty():
    fan = SimpleNamespace(label="CPU Fan", current=1200)
    with patch(
        "diagnosys.collectors.system.thermal.psutil.sensors_temperatures",
        return_value={},
        create=True,
    ):
        with patch(
            "diagnosys.collectors.system.thermal.psutil.sensors_fans",
            return_value={"nct": [fan]},
            create=True,
        ):
            result = ThermalCollector().collect()
    assert result.available
    assert not result.temperatures
    assert result.fans[0].speed_rpm == 1200.0


def test_thermal_collector_keeps_fan_data_when_temperature_api_is_missing():
    fan = SimpleNamespace(label="Chassis Fan", current=900)
    with patch("diagnosys.collectors.system.thermal.psutil.sensors_temperatures", None, create=True):
        with patch(
            "diagnosys.collectors.system.thermal.psutil.sensors_fans",
            return_value={"board": [fan]},
            create=True,
        ):
            result = ThermalCollector().collect()
    assert result.available
    assert result.fans[0].speed_rpm == 900.0
    assert "Temperature sensors are not exposed" in result.reason


def test_thermal_collector_preserves_valid_subzero_temperatures():
    reading = SimpleNamespace(label="Ambient", current=-5.5, high=45.0, critical=60.0)
    with patch(
        "diagnosys.collectors.system.thermal.psutil.sensors_temperatures",
        return_value={"ambient": [reading]},
        create=True,
    ):
        with patch(
            "diagnosys.collectors.system.thermal.psutil.sensors_fans",
            return_value={},
            create=True,
        ):
            result = ThermalCollector().collect()
    assert result.available
    assert result.temperatures[0].temperature_c == -5.5
