import pytest
from unittest.mock import patch, MagicMock
import socket
import urllib.error
import subprocess

from diagnosys.collectors.network.ping import PingCollector
from diagnosys.collectors.network.dns import DNSCollector
from diagnosys.collectors.network.http import HTTPCollector

@patch("subprocess.run")
def test_ping_collector_success(mock_run):
    # Mocking a successful ping response
    mock_result = MagicMock()
    mock_result.stdout = "Reply from 8.8.8.8: bytes=32 time=14ms TTL=57\nReply from 8.8.8.8: bytes=32 time=16ms TTL=57"
    mock_result.stderr = ""
    mock_run.return_value = mock_result
    
    collector = PingCollector(count=2)
    metrics = collector.collect()
    
    assert metrics.available is True
    assert metrics.packet_loss_percent == 0.0
    assert metrics.min_ms == 14.0
    assert metrics.max_ms == 16.0
    assert metrics.median_ms == 15.0
    assert metrics.jitter_ms == 2.0

@patch("subprocess.run")
def test_ping_collector_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="ping", timeout=10)
    
    collector = PingCollector(count=2)
    metrics = collector.collect()
    
    assert metrics.available is True
    assert metrics.packet_loss_percent == 100.0
    assert metrics.reason == "Command timed out"

@patch("socket.gethostbyname")
def test_dns_collector_success(mock_gethostbyname):
    mock_gethostbyname.return_value = "8.8.8.8"
    
    collector = DNSCollector()
    metrics = collector.collect()
    
    assert metrics.success is True
    assert metrics.timeout is False
    assert metrics.latency_ms is not None

@patch("socket.gethostbyname")
def test_dns_collector_timeout(mock_gethostbyname):
    mock_gethostbyname.side_effect = socket.timeout("timed out")
    
    collector = DNSCollector()
    metrics = collector.collect()
    
    assert metrics.success is False
    assert metrics.timeout is True

@patch("urllib.request.urlopen")
def test_http_collector_success(mock_urlopen):
    mock_response = MagicMock()
    mock_response.getcode.return_value = 204
    
    # Context manager mock
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    collector = HTTPCollector()
    metrics = collector.collect()
    
    assert metrics.success is True
    assert metrics.status_code == 204
    assert metrics.latency_ms is not None

@patch("urllib.request.urlopen")
def test_http_collector_timeout(mock_urlopen):
    # Simulate urllib timeout
    mock_urlopen.side_effect = urllib.error.URLError(TimeoutError("timed out"))
    
    collector = HTTPCollector()
    metrics = collector.collect()
    
    assert metrics.success is False
    assert metrics.timeout is True
