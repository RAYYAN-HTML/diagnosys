"""Network diagnostic workflows for the desktop application."""
from __future__ import annotations

from datetime import datetime, timezone

from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.collectors.network.dns import DNSCollector
from diagnosys.collectors.network.http import HTTPCollector
from diagnosys.collectors.network.investigation import NetworkInvestigator
from diagnosys.collectors.network.ping import PingCollector


class NetworkController:
    """Own network checks while delegating shared UI state to MainWindow."""

    def __init__(self, window):
        self.window = window

    def __getattr__(self, name):
        return getattr(self.window, name)

    def __setattr__(self, name, value):
        if name == "window":
            object.__setattr__(self, name, value)
        else:
            setattr(self.window, name, value)


    @staticmethod
    def _network_work(target: str, dns_target: str, dns_server: str | None, http_target: str, timeout: float):
        return (
            PingCollector(target=target, count=3, timeout_sec=timeout).collect(),
            DNSCollector(target=dns_target, timeout_sec=timeout, server=dns_server).collect(),
            HTTPCollector(target=http_target, timeout_sec=timeout).collect(),
        )

    def network_check(self) -> None:
        target = self.target.text().strip() or self.settings.ping_target
        dns_target = self.dns_target.text().strip() or self.settings.dns_target
        dns_server = self.dns_server.text().strip() or None
        http_target = self.http_target.text().strip() or self.settings.http_target
        timeout = self.settings.network_timeout_seconds
        self.network_output.setPlainText("Checking ping, DNS, and HTTP connectivity…")
        self._run_async(
            "network",
            lambda: self._network_work(target, dns_target, dns_server, http_target, timeout),
            self._apply_network,
        )

    def inspect_network_path(self) -> None:
        target = self.target.text().strip() or self.settings.ping_target
        timeout = self.settings.network_timeout_seconds
        self.route_output.setPlainText("Checking the default gateway and tracing up to eight network hops…")
        self._run_async(
            "route",
            lambda: NetworkInvestigator().collect(target, timeout),
            self._apply_network_path,
        )

    def _apply_network_path(self, result: dict) -> None:
        gateway = result.get("gateway", {})
        gateway_ping = result.get("gateway_ping")
        route = result.get("route", {})
        wifi = result.get("wifi", {})
        if gateway_ping:
            timestamp = datetime.now(timezone.utc)
            gateway_id = f"gateway:{gateway.get('address', 'default')}"
            self._store_sample(MetricSample(
                timestamp, "ping_median_ms", gateway_ping.median_ms, "ms", "network",
                MetricStatus.OK if gateway_ping.median_ms is not None else MetricStatus.UNAVAILABLE,
                entity_id=gateway_id, reason=gateway_ping.reason,
            ))
            self._store_sample(MetricSample(
                timestamp, "packet_loss_percent", gateway_ping.packet_loss_percent, "%", "network",
                MetricStatus.OK, entity_id=gateway_id,
            ))
        lines = [f"Target: {result.get('target', '—')}", "", "DEFAULT GATEWAY"]
        lines.append(gateway.get("address", gateway.get("reason", "Unavailable")))
        lines += ["", "GATEWAY CONNECTIVITY"]
        if gateway_ping and gateway_ping.median_ms is not None:
            lines.append(
                f"Median {gateway_ping.median_ms:.1f} ms · "
                f"packet loss {gateway_ping.packet_loss_percent:.0f}%"
            )
        elif gateway_ping:
            lines.append(gateway_ping.reason or "The gateway did not reply to the local ping check.")
        else:
            lines.append("Gateway connectivity could not be measured.")
        lines += ["", "ROUTE TRACE"]
        if route.get("available"):
            lines.extend(route.get("lines", []))
        else:
            lines.append(route.get("reason", "No route trace available."))
        lines += ["", "WI-FI LINK"]
        if wifi.get("available"):
            lines.extend(f"{key.replace('_', ' ').title()}: {value}" for key, value in wifi.items() if key != "available")
        else:
            lines.append(wifi.get("reason", "Wi-Fi details unavailable."))
        lines += ["", "HOW TO READ THIS"]
        lines.append("A gateway reply confirms local router reachability, not access to every internet service.")
        lines.append("Some routers suppress route-trace replies; missing hops alone do not prove a connection failure.")
        self.route_output.setPlainText("\n".join(lines))
        if self._active_investigation is not None:
            wifi_signal = wifi.get("signal", "not reported") if wifi.get("available") else "not available"
            route_count = len(route.get("lines", [])) if route.get("available") else 0
            gateway_result = (
                f"gateway {gateway.get('address', 'unavailable')} replied at {gateway_ping.median_ms:.1f} ms"
                if gateway_ping and gateway_ping.median_ms is not None
                else "gateway reply unavailable"
            )
            marker = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": "network path check",
                "text": f"{gateway_result}; Wi-Fi signal {wifi_signal}; route trace returned {route_count} hop line(s).",
            }
            self.incident_repo.add_marker(self._active_investigation.id, marker)
            self._active_investigation.evidence.setdefault("markers", []).append(marker)

    def _apply_network(self, results) -> None:
        ping, dns, http = results
        timestamp = datetime.now(timezone.utc)
        if ping.available:
            if ping.median_ms is not None:
                self._store_sample(MetricSample(
                    timestamp, "ping_median_ms", ping.median_ms, "ms", "network",
                    MetricStatus.OK, entity_id=ping.target,
                ))
            else:
                self._store_sample(MetricSample(
                    timestamp, "ping_median_ms", None, "ms", "network",
                    MetricStatus.UNAVAILABLE, entity_id=ping.target,
                    reason=ping.reason or "No ping replies were received.",
                ))
            self._store_sample(MetricSample(
                timestamp, "packet_loss_percent", ping.packet_loss_percent, "%", "network",
                MetricStatus.OK, entity_id=ping.target,
            ))
            if ping.jitter_ms is not None:
                self._store_sample(MetricSample(
                    timestamp, "ping_jitter_ms", ping.jitter_ms, "ms", "network",
                    MetricStatus.OK, entity_id=ping.target,
                ))
        else:
            self._store_sample(MetricSample(
                timestamp, "ping_median_ms", None, "ms", "network",
                MetricStatus.UNAVAILABLE, entity_id=ping.target,
                reason=ping.reason or "Ping is unavailable.",
            ))
        if dns.success and dns.latency_ms is not None:
            self._store_sample(MetricSample(
                timestamp, "dns_latency_ms", dns.latency_ms, "ms", "network",
                MetricStatus.OK, entity_id=f"{dns.target} via {dns.server or 'system'}",
            ))
        else:
            self._store_sample(MetricSample(
                timestamp, "dns_latency_ms", None, "ms", "network",
                MetricStatus.UNAVAILABLE, entity_id=f"{dns.target} via {dns.server or 'system'}",
                reason=dns.reason or "DNS lookup failed.",
            ))
        if http.success and http.latency_ms is not None:
            self._store_sample(MetricSample(
                timestamp, "http_latency_ms", http.latency_ms, "ms", "network",
                MetricStatus.OK, entity_id=http.target,
            ))
        else:
            self._store_sample(MetricSample(
                timestamp, "http_latency_ms", None, "ms", "network",
                MetricStatus.UNAVAILABLE, entity_id=http.target,
                reason=http.reason or "HTTP request failed.",
            ))
        if ping.median_ms is not None:
            self.network_latency_card.set_value(f"{ping.median_ms:.1f} ms", f"Median ping to {ping.target}")
            self.network_latency_value = f"{ping.median_ms:.1f} ms"
        else:
            self.network_latency_card.set_value("Timeout", ping.reason or "No ping replies")
            self.network_latency_value = "Timeout"
        if ping.available:
            self.packet_loss_card.set_value(f"{ping.packet_loss_percent:.0f}%", f"To {ping.target}")
            self.jitter_card.set_value(f"{ping.jitter_ms:.1f} ms" if ping.jitter_ms is not None else "—", "Mean reply variation")
            self.ping_summary.setText(
                f"Latency {self.network_latency_value}  ·  Packet loss {ping.packet_loss_percent:.0f}%"
            )
        else:
            self.packet_loss_card.set_value("Unavailable", ping.reason or "Ping probe failed")
            self.jitter_card.set_value("Unavailable", "Ping probe failed")
            self.ping_summary.setText(f"Ping unavailable · {ping.reason or 'probe failed'}")
        lines = ["PING", f"Target: {ping.target}"]
        if not ping.available:
            lines.append(f"Unavailable: {ping.reason or 'probe failed'}")
            lines.append("Packet loss: unavailable")
        elif ping.median_ms is not None and ping.min_ms is not None and ping.max_ms is not None:
            lines.append(f"Median: {ping.median_ms:.1f} ms  ·  Min: {ping.min_ms:.1f} ms  ·  Max: {ping.max_ms:.1f} ms")
        else:
            lines.append(f"No reply  ·  Packet loss: {ping.packet_loss_percent:.0f}% ({ping.reason or 'no response'})")
        lines.append(f"Jitter: {ping.jitter_ms:.1f} ms" if ping.jitter_ms is not None else "Jitter: unavailable")
        resolver = f" via {dns.server}" if dns.server else " via system resolver"
        lines += ["", "DNS", f"{dns.target}{resolver}: {dns.latency_ms:.1f} ms" if dns.success and dns.latency_ms is not None else f"Unavailable: {dns.reason or 'request failed'}", "", "HTTP", f"{http.target}: {http.latency_ms:.1f} ms · status {http.status_code}" if http.success and http.latency_ms is not None else f"Unavailable: {http.reason or 'request failed'}"]
        self.network_output.setPlainText("\n".join(lines))
        self._update_insight()


