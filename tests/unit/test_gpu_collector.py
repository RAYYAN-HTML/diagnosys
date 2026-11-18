from types import SimpleNamespace
from unittest.mock import patch

import pytest

from diagnosys.collectors.system.gpu import GPUCollector


def test_gpu_collector_selects_requested_device_and_parses_values():
    collector = GPUCollector(gpu_index=2)
    result = SimpleNamespace(
        returncode=0,
        stdout="Example GPU, 72, 4096, 8192, 68\n",
        stderr="",
    )
    with patch("diagnosys.collectors.system.gpu.shutil.which", return_value="/usr/bin/nvidia-smi"):
        collector = GPUCollector(gpu_index=2)
    with patch("diagnosys.collectors.system.gpu.subprocess.run", return_value=result) as run:
        metrics = collector.collect()

    assert metrics.available
    assert metrics.gpu_index == 2
    assert metrics.name == "Example GPU"
    assert metrics.utilization_percent == 72
    assert metrics.memory_used_mib == 4096
    assert metrics.memory_total_mib == 8192
    assert metrics.temperature_c == 68
    assert run.call_args.args[0][-1] == "--id=2"


def test_gpu_collector_preserves_unavailable_and_malformed_fields():
    result = SimpleNamespace(
        returncode=0,
        stdout="Example GPU, [N/A], 1024, 8192, [Not Supported]\n",
        stderr="",
    )
    with patch("diagnosys.collectors.system.gpu.shutil.which", return_value="/usr/bin/nvidia-smi"):
        collector = GPUCollector()
    with patch("diagnosys.collectors.system.gpu.subprocess.run", return_value=result):
        metrics = collector.collect()

    assert metrics.available
    assert metrics.name == "Example GPU"
    assert metrics.utilization_percent is None
    assert metrics.memory_used_mib == 1024
    assert metrics.temperature_c is None


def test_gpu_collector_rejects_invalid_index():
    with pytest.raises(ValueError, match="gpu_index"):
        GPUCollector(gpu_index=-1)
    with pytest.raises(ValueError, match="gpu_index"):
        GPUCollector(gpu_index=True)


def test_gpu_collector_reports_missing_tool():
    with patch("diagnosys.collectors.system.gpu.shutil.which", return_value=None):
        metrics = GPUCollector().collect()
    assert not metrics.available
    assert "nvidia-smi" in metrics.reason
