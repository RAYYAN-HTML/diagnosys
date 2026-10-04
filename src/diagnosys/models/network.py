from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class PingMetrics:
    target: str
    min_ms: Optional[float]
    median_ms: Optional[float]
    p95_ms: Optional[float]
    max_ms: Optional[float]
    packet_loss_percent: float
    jitter_ms: Optional[float]
    available: bool = True
    reason: Optional[str] = None

@dataclass
class DNSMetrics:
    target: str
    latency_ms: Optional[float]
    success: bool
    timeout: bool
    reason: Optional[str] = None

@dataclass
class HTTPMetrics:
    target: str
    latency_ms: Optional[float]
    status_code: Optional[int]
    success: bool
    timeout: bool
    reason: Optional[str] = None

@dataclass
class NetworkSnapshot:
    timestamp: datetime
    ping: PingMetrics
    dns: DNSMetrics
    http: HTTPMetrics
