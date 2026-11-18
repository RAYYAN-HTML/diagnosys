import socket
import ipaddress
import secrets
import struct
import time
import math
import re

from diagnosys.collectors.base import Collector
from diagnosys.models.network import DNSMetrics

class DNSCollector(Collector):
    def __init__(self, target: str = "google.com", timeout_sec: float = 2.0, server: str | None = None):
        if not isinstance(target, str) or not target.strip():
            raise ValueError("target must be a non-empty hostname")
        if not math.isfinite(float(timeout_sec)) or float(timeout_sec) <= 0:
            raise ValueError("timeout_sec must be a finite number greater than zero")
        normalized_target = target.rstrip(".")
        labels = normalized_target.split(".")
        if len(normalized_target) > 253 or any(
            not label or len(label.encode("idna")) > 63
            or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
            for label in labels
        ):
            raise ValueError("The DNS target is not a valid hostname")
        self.target = normalized_target
        self.timeout_sec = float(timeout_sec)
        self.server = server.strip() if server else None
        if self.server:
            try:
                ipaddress.ip_address(self.server)
            except ValueError as exc:
                raise ValueError("server must be an IP address") from exc

    def _query_server(self) -> None:
        server = ipaddress.ip_address(self.server)
        labels = self.target.rstrip(".").split(".")
        if not labels or any(not label or len(label.encode("idna")) > 63 for label in labels):
            raise ValueError("The DNS target is not a valid hostname")
        question = b"".join(bytes((len(label.encode("idna")),)) + label.encode("idna") for label in labels) + b"\x00\x00\x01\x00\x01"
        identifier = secrets.randbelow(65536)
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
        if not flags & 0x8000:
            raise OSError("DNS server response did not contain the response flag")
        if flags & 0x0200:
            raise OSError("DNS server returned a truncated UDP response")
        if flags & 0x000F:
            raise OSError(f"DNS server returned response code {flags & 0x000F}")
        
    def collect(self) -> DNSMetrics:
        start_time = time.perf_counter()
        try:
            if self.server:
                self._query_server()
            else:
                # The system resolver is used without changing process-wide socket
                # defaults. This avoids races with unrelated network operations.
                socket.getaddrinfo(self.target, None, type=socket.SOCK_STREAM)
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
