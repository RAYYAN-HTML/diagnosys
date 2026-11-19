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

@patch("socket.getaddrinfo")
def test_dns_collector_success(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]
    
    collector = DNSCollector()
    metrics = collector.collect()
    
    assert metrics.success is True
    assert metrics.timeout is False
    assert metrics.latency_ms is not None

@patch("socket.getaddrinfo")
def test_dns_collector_timeout(mock_getaddrinfo):
    mock_getaddrinfo.side_effect = socket.timeout("timed out")
    
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


def test_ping_parser_does_not_double_count_less_than_one_ms():
    collector = PingCollector(count=2)
    assert collector._parse_time("Reply time<1ms\nReply time=2.5ms") == [0.5, 2.5]


def test_dns_collector_rejects_invalid_hostname_and_timeout():
    import pytest
    with pytest.raises(ValueError, match="hostname"):
        DNSCollector(target="invalid host name")
    with pytest.raises(ValueError, match="timeout_sec"):
        DNSCollector(timeout_sec=0)


def test_dns_explicit_server_uses_bounded_socket_timeout_and_validates_response():
    import struct

    fake_socket = MagicMock()
    fake_socket.__enter__.return_value = fake_socket

    def respond(_size):
        query = fake_socket.sendto.call_args.args[0]
        query_id = struct.unpack("!H", query[:2])[0]
        return struct.pack("!HHHHHH", query_id, 0x8180, 1, 1, 0, 0), ("1.1.1.1", 53)

    fake_socket.recvfrom.side_effect = respond
    with patch("diagnosys.collectors.network.dns.socket.socket", return_value=fake_socket):
        metrics = DNSCollector(target="example.com", server="1.1.1.1", timeout_sec=1.25).collect()

    assert metrics.success
    assert metrics.server == "1.1.1.1"
    fake_socket.settimeout.assert_called_once_with(1.25)


def test_dns_explicit_server_rejects_truncated_udp_response():
    import struct

    fake_socket = MagicMock()
    fake_socket.__enter__.return_value = fake_socket

    def respond(_size):
        query = fake_socket.sendto.call_args.args[0]
        query_id = struct.unpack("!H", query[:2])[0]
        return struct.pack("!HHHHHH", query_id, 0x8380, 1, 0, 0, 0), ("1.1.1.1", 53)

    fake_socket.recvfrom.side_effect = respond
    with patch("diagnosys.collectors.network.dns.socket.socket", return_value=fake_socket):
        metrics = DNSCollector(target="example.com", server="1.1.1.1").collect()

    assert not metrics.success
    assert "truncated" in metrics.reason
