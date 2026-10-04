import urllib.request
import urllib.error
import time

from diagnosys.collectors.base import Collector
from diagnosys.models.network import HTTPMetrics

class HTTPCollector(Collector):
    def __init__(self, target: str = "http://connectivitycheck.gstatic.com/generate_204", timeout_sec: float = 2.0):
        self.target = target
        self.timeout_sec = timeout_sec
        
    def collect(self) -> HTTPMetrics:
        start_time = time.time()
        try:
            req = urllib.request.Request(self.target, headers={'User-Agent': 'Diagnosys/0.1.0'})
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as response:
                status_code = response.getcode()
                # Do not read the body to save bandwidth and memory
                
            latency_ms = (time.time() - start_time) * 1000.0
            
            return HTTPMetrics(
                target=self.target,
                latency_ms=latency_ms,
                status_code=status_code,
                success=True,
                timeout=False
            )
            
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                return HTTPMetrics(
                    target=self.target, latency_ms=None, status_code=None,
                    success=False, timeout=True, reason="HTTP request timed out"
                )
            return HTTPMetrics(
                target=self.target, latency_ms=None, status_code=None,
                success=False, timeout=False, reason=str(e.reason)
            )
        except TimeoutError:
            return HTTPMetrics(
                target=self.target, latency_ms=None, status_code=None,
                success=False, timeout=True, reason="HTTP request timed out"
            )
        except Exception as e:
            return HTTPMetrics(
                target=self.target, latency_ms=None, status_code=None,
                success=False, timeout=False, reason=str(e)
            )
