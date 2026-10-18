import pytest
from unittest.mock import patch, MagicMock
import psutil

from diagnosys.collectors.system.process import ProcessCollector

@patch("psutil.process_iter")
def test_process_collector(mock_process_iter):
    mock_p1 = MagicMock()
    mock_p1.info = {'pid': 1, 'name': 'systemd', 'username': 'root', 'cpu_percent': 0.1, 'memory_percent': 0.5}
    
    mock_p2 = MagicMock()
    mock_p2.info = {'pid': 2, 'name': 'chrome', 'username': 'user', 'cpu_percent': 25.0, 'memory_percent': 15.0}
    
    mock_p3 = MagicMock()
    mock_p3.info = {'pid': 3, 'name': 'python', 'username': 'user', 'cpu_percent': 15.0, 'memory_percent': 25.0}
    
    mock_p4 = MagicMock()
    # Simulating access denied on info access which happens in our try block
    # Actually process_iter yields procs, then we access proc.info
    # Let's make proc.info a property that raises AccessDenied
    type(mock_p4).info = property(lambda self: _raise_access_denied())
    
    def _raise_access_denied():
        raise psutil.AccessDenied(pid=4)
    
    mock_process_iter.return_value = [mock_p1, mock_p2, mock_p3, mock_p4]
    
    collector = ProcessCollector(top_n=2)
    snapshot = collector.collect()
    
    assert snapshot.available is True
    assert snapshot.process_count == 3  # p4 failed
    
    assert len(snapshot.top_cpu) == 2
    assert snapshot.top_cpu[0].name == 'chrome'
    assert snapshot.top_cpu[1].name == 'python'
    
    assert len(snapshot.top_memory) == 2
    assert snapshot.top_memory[0].name == 'python'
    assert snapshot.top_memory[1].name == 'chrome'
