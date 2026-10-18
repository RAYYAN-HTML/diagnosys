from pathlib import Path
from tempfile import TemporaryDirectory

from diagnosys.config.settings import Settings


def test_settings_are_saved_and_loaded_from_local_app_data(monkeypatch):
    with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
        data_dir = Path(temporary_directory)
        settings = Settings(
            data_dir=data_dir,
            refresh_seconds=15,
            retention_days=30,
            network_timeout_seconds=4.5,
            ping_target="router.local",
            dns_target="example.net",
            dns_server="1.1.1.1",
            http_target="https://example.net/health",
            alerts_enabled=False,
        )
        settings.save()
        monkeypatch.setenv("DIAGNOSYS_DATA_DIR", str(data_dir))

        loaded = Settings.from_env()

        assert loaded.refresh_seconds == 15
        assert loaded.retention_days == 30
        assert loaded.network_timeout_seconds == 4.5
        assert loaded.ping_target == "router.local"
        assert loaded.dns_server == "1.1.1.1"
        assert loaded.alerts_enabled is False


def test_settings_reject_invalid_network_targets():
    import pytest
    with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
        data_dir = Path(temporary_directory)
        with pytest.raises(ValueError, match="dns_server"):
            Settings(data_dir=data_dir, dns_server="not-an-ip")
        with pytest.raises(ValueError, match="http_target"):
            Settings(data_dir=data_dir, http_target="file:///etc/passwd")
