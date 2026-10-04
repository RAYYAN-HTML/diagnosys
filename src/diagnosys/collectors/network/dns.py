import socket
import time

from diagnosys.collectors.base import Collector
from diagnosys.models.network import DNSMetrics

class DNSCollector(Collector):
    def __init__(self, target: str = "google.com", timeout_sec: float = 2.0):
        self.target = target
        self.timeout_sec = timeout_sec
        
    def collect(self) -> DNSMetrics:
        start_time = time.time()
        try:
            # We want to measure resolution, not just whatever the system does,
            # but socket.gethostbyname is cached by the OS. It's an MVP limitation.
            socket.setdefaulttimeout(self.timeout_sec)
            socket.gethostbyname(self.target)
            latency_ms = (time.time() - start_time) * 1000.0
            
            return DNSMetrics(
                target=self.target,
                latency_ms=latency_ms,
                success=True,
                timeout=False
            )
        except socket.timeout:
            return DNSMetrics(
                target=self.target,
                latency_ms=None,
                success=False,
                timeout=True,
                reason="DNS query timed out"
            )
        except Exception as e:
            return DNSMetrics(
                target=self.target,
                latency_ms=None,
                success=False,
                timeout=False,
                reason=str(e)
            )
        finally:
            socket.setdefaulttimeout(None)
