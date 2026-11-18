"""Hardware-limit thermal rules with explicit time overlap and no generic cutoffs."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from diagnosys.models.diagnostics import Anomaly
from diagnosys.models.metrics import MetricSample, MetricStatus


class ThermalDiagnosticEngine:
    """Flag only sensor-provided limits and include contemporaneous system evidence."""

    WINDOW_SECONDS = 60
    MIN_SUSTAINED_SAMPLES = 3
    MIN_SUSTAINED_SPAN_SECONDS = 20

    def evaluate(
        self,
        history: list[dict[str, Any]],
        metrics: list[MetricSample],
        now: datetime | None = None,
    ) -> list[Anomaly]:
        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(seconds=self.WINDOW_SECONDS)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in history:
            if item.get("reading_kind") != "temperature":
                continue
            stamp = self._parse_timestamp(item.get("timestamp"))
            value = item.get("temperature_c")
            if stamp is None or stamp < cutoff or not isinstance(value, (int, float)):
                continue
            grouped[str(item.get("sensor") or item.get("label") or "unknown")].append(item)

        results: list[Anomaly] = []
        for sensor, readings in grouped.items():
            readings.sort(key=lambda item: self._parse_timestamp(item.get("timestamp")) or current)
            latest = readings[-1]
            values = [self._number(item.get("temperature_c")) for item in readings]
            valid = [value for value in values if value is not None]
            if not valid:
                continue

            critical_pairs = [
                (self._number(item.get("temperature_c")), self._number(item.get("critical_c")))
                for item in readings
                if self._number(item.get("critical_c")) is not None
                and self._number(item.get("temperature_c")) is not None
                and self._number(item.get("temperature_c")) >= self._number(item.get("critical_c"))
            ]
            sustained_pairs = [
                item for item in readings
                if self._number(item.get("high_c")) is not None
                and self._number(item.get("temperature_c")) is not None
                and self._number(item.get("temperature_c")) >= self._number(item.get("high_c"))
            ]
            is_critical = bool(critical_pairs)
            if is_critical:
                observed, expected = max(critical_pairs, key=lambda pair: pair[0] or 0)
                severity = "CRITICAL"
                detail = "A sensor reading reached or exceeded the hardware-reported critical limit."
            elif (
                len(sustained_pairs) >= self.MIN_SUSTAINED_SAMPLES
                and self._span_seconds(sustained_pairs) >= self.MIN_SUSTAINED_SPAN_SECONDS
            ):
                observed, expected = max(
                    ((self._number(item.get("temperature_c")), self._number(item.get("high_c"))) for item in sustained_pairs),
                    key=lambda pair: pair[0] or 0,
                )
                severity = "WARNING"
                detail = (
                    f"The sensor remained at or above its hardware-reported high limit "
                    f"for {self._span_seconds(sustained_pairs):.0f} seconds across {len(sustained_pairs)} samples."
                )
            else:
                continue

            label = str(latest.get("label") or sensor)
            context = self._correlated_context(metrics, label, cutoff)
            explanation = f"{label}: {detail} Observed {observed:.1f} °C; hardware limit {expected:.1f} °C. {context} Time overlap is not proof of thermal throttling."
            results.append(Anomaly(
                timestamp=current,
                category="THERMAL_LIMIT",
                severity=severity,
                metric="thermal_temperature_c",
                observed_value=observed,
                expected_value=expected,
                rule_id=(
                    f"thermal_sensor_limit_{'critical' if is_critical else 'sustained'}_"
                    f"{sensor.casefold().replace(' ', '_').replace('/', '_')}"
                ),
                explanation=explanation,
            ))
        return results

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _span_seconds(cls, readings: list[dict[str, Any]]) -> float:
        stamps = [cls._parse_timestamp(item.get("timestamp")) for item in readings]
        valid = [stamp for stamp in stamps if stamp is not None]
        return (max(valid) - min(valid)).total_seconds() if len(valid) >= 2 else 0.0

    @staticmethod
    def _correlated_context(metrics: list[MetricSample], label: str, cutoff: datetime) -> str:
        previous_start = cutoff - timedelta(seconds=240)
        recent = [
            item for item in metrics
            if item.timestamp >= cutoff and item.status == MetricStatus.OK
            and isinstance(item.value, (int, float))
        ]
        previous = [
            item for item in metrics
            if previous_start <= item.timestamp < cutoff and item.status == MetricStatus.OK
            and isinstance(item.value, (int, float))
        ]
        current_values: dict[str, list[float]] = defaultdict(list)
        previous_values: dict[str, list[float]] = defaultdict(list)
        for item in recent:
            current_values[item.metric_name].append(float(item.value))
        for item in previous:
            previous_values[item.metric_name].append(float(item.value))

        parts = []
        for metric, title, unit in (
            ("cpu_percent", "Current CPU utilization median", "%"),
            ("gpu_percent", "Current GPU utilization median", "%"),
            ("cpu_frequency_mhz", "Current CPU frequency median", "MHz"),
        ):
            if current_values.get(metric):
                current_median = median(current_values[metric])
                parts.append(f"{title} {current_median:.1f} {unit}")
                if previous_values.get(metric):
                    previous_median = median(previous_values[metric])
                    parts.append(
                        f"{metric.replace('_', ' ')} preceding-window median "
                        f"{previous_median:.1f} {unit}"
                    )
        if not parts:
            return "No concurrent utilization or clock measurements were available."
        return "Concurrent measurements: " + ", ".join(parts) + ". Clock and utilization changes do not prove performance loss or thermal throttling."
