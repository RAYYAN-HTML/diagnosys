import socket
import ipaddress
import random
import struct
import time

from diagnosys.collectors.base import Collector
from diagnosys.models.network import DNSMetrics

class DNSCollector(Collector):
    def __init__(self, target: str = "google.com", timeout_sec: float = 2.0, server: str | None = None):
        self.target = target
        self.timeout_sec = timeout_sec
        self.server = server.strip() if server else None

    def _query_server(self) -> None:
        server = ipaddress.ip_address(self.server)
        labels = self.target.rstrip(".").split(".")
        if not labels or any(not label or len(label.encode("idna")) > 63 for label in labels):
            raise ValueError("The DNS target is not a valid hostname")
        question = b"".join(bytes((len(label.encode("idna")),)) + label.encode("idna") for label in labels) + b"\x00\x00\x01\x00\x01"
        identifier = random.randrange(0, 65536)
        packet = struct.pack("!HHHHHH", identifier, 0x0100, 1, 0, 0, 0) + question
        family = socket.AF_INET6 if server.version == 6 else socket.AF_INET
        with socket.socket(family, socket.SOCK_DGRAM) as client:
            client.settimeout(self.timeout_sec)
            address = (str(server), 53, 0, 0) if family == socket.AF_INET6 else (str(server), 53)
            client.sendto(packet, address)
            response, _ = client.recvfrom(4096)
        if len(response) < 12 or struct.unpack("!H", response[:2])[0] != identifier:
            raise OSError("DNS server returned an invalid response")
        flags = struct.unpack("!H", response[2:4])[0]
        if flags & 0x000F:
            raise OSError(f"DNS server returned response code {flags & 0x000F}")
        
    def collect(self) -> DNSMetrics:
        start_time = time.perf_counter()
        previous_timeout = socket.getdefaulttimeout()
        try:
            if self.server:
                self._query_server()
            else:
                # System resolver access is retained when no explicit resolver is selected.
                socket.setdefaulttimeout(self.timeout_sec)
                socket.gethostbyname(self.target)
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            
            return DNSMetrics(
                target=self.target,
                latency_ms=latency_ms,
                success=True,
                timeout=False,
                server=self.server,
            )
        except socket.timeout:
            return DNSMetrics(
                target=self.target,
                latency_ms=None,
                success=False,
                timeout=True,
                reason="DNS query timed out",
                server=self.server,
            )
        except Exception as e:
            return DNSMetrics(
                target=self.target,
                latency_ms=None,
                success=False,
                timeout=False,
                reason=str(e),
                server=self.server,
            )
        finally:
            if not self.server:
                socket.setdefaulttimeout(previous_timeout)
