import pytest
from unittest.mock import patch, MagicMock

from diagnosys.collectors.system.cpu import CPUCollector
from diagnosys.collectors.system.memory import MemoryCollector
from diagnosys.collectors.system.disk import DiskCollector
from diagnosys.collectors.system.uptime import UptimeCollector

@patch("psutil.cpu_percent")
@patch("psutil.cpu_freq")
@patch("psutil.getloadavg", create=True)
def test_cpu_collector(mock_getloadavg, mock_cpu_freq, mock_cpu_percent):
    mock_cpu_percent.side_effect = [35.5, [30.0, 40.0]]
    
    mock_freq = MagicMock()
    mock_freq.current = 2400.0
    mock_cpu_freq.return_value = mock_freq
    
    mock_getloadavg.return_value = (1.5, 1.2, 1.0)
    
    collector = CPUCollector()
    metrics = collector.collect()
    
    assert metrics.available is True
    assert metrics.utilization_percent == 35.5
    assert metrics.per_core_utilization_percent == [30.0, 40.0]
    assert metrics.frequency_mhz == 2400.0
    assert metrics.load_average == [1.5, 1.2, 1.0]

@patch("psutil.virtual_memory")
@patch("psutil.swap_memory")
def test_memory_collector(mock_swap_memory, mock_virtual_memory):
    mock_vmem = MagicMock()
    mock_vmem.total = 16000000000
    mock_vmem.used = 8000000000
    mock_vmem.available = 8000000000
    mock_vmem.percent = 50.0
    mock_virtual_memory.return_value = mock_vmem
    
    mock_smem = MagicMock()
    mock_smem.percent = 10.0
    mock_swap_memory.return_value = mock_smem
    
    collector = MemoryCollector()
    metrics = collector.collect()
    
    assert metrics.available is True
    assert metrics.total_bytes == 16000000000
    assert metrics.used_bytes == 8000000000
    assert metrics.percent_used == 50.0
    assert metrics.swap_percent == 10.0

@patch("psutil.disk_partitions")
@patch("psutil.disk_usage")
@patch("psutil.disk_io_counters")
def test_disk_collector(mock_io_counters, mock_disk_usage, mock_disk_partitions):
    mock_part = MagicMock()
    mock_part.mountpoint = "/"
    mock_disk_partitions.return_value = [mock_part]
    
    mock_usage = MagicMock()
    mock_usage.total = 500000000000
    mock_usage.free = 250000000000
    mock_usage.percent = 50.0
    mock_disk_usage.return_value = mock_usage
    
    mock_io = MagicMock()
    mock_io.read_bytes = 1000
    mock_io.write_bytes = 2000
    mock_io.busy_time = 100
    mock_io_counters.return_value = mock_io
    
    collector = DiskCollector()
    
    # First collection initializes the IO counters
    metrics1 = collector.collect()
    assert metrics1.available is True
    assert metrics1.total_bytes == 500000000000
    assert metrics1.read_bytes_per_sec == 0.0
    
    # Need a time diff for IO
    with patch("time.time", return_value=100.0):
        collector._last_time = 99.0 # 1 second ago
        
        mock_io2 = MagicMock()
        mock_io2.read_bytes = 2000
        mock_io2.write_bytes = 4000
        mock_io2.busy_time = 150 # 50ms busy
        mock_io_counters.return_value = mock_io2
        
        metrics2 = collector.collect()
        assert metrics2.read_bytes_per_sec == 1000.0
        assert metrics2.write_bytes_per_sec == 2000.0
        assert metrics2.busy_percent == 5.0 # (50ms / 1000ms) * 100

@patch("psutil.boot_time")
@patch("time.time")
def test_uptime_collector(mock_time, mock_boot_time):
    mock_boot_time.return_value = 1000.0
    mock_time.return_value = 1050.0
    
    collector = UptimeCollector()
    uptime = collector.collect()
    
    assert uptime == 50.0
