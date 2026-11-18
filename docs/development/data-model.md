# Diagnosys Data Model

## MetricSample

```text
MetricSample
├── timestamp
├── metric_name
├── value
├── unit
├── source
├── entity_id (optional)
└── status / reason
```

## NetworkProbe

```text
NetworkProbe
├── timestamp
├── target
├── protocol
├── latency_ms
├── success
├── error_type
└── metadata
```

## Anomaly

```text
Anomaly
├── timestamp
├── category
├── severity
├── metric
├── observed_value
├── expected_value
├── rule_id
└── explanation
```

## Evidence

```text
Evidence
├── metric
├── observed_value
├── expected_value
├── time_window
├── direction
└── strength
```

## DiagnosisHypothesis

```text
DiagnosisHypothesis
├── category
├── evidence[]
├── contradictory_evidence[]
├── limitations[]
└── recommended_checks[]
```

Hypotheses do not contain probability, confidence, or arbitrary score fields. Ordering is based on the number and type of recorded observations, and the UI must explain that this is evidence ordering rather than probability.

## Hardware history

- `thermal_samples`: timestamp, sensor identity, label, temperature or fan RPM, and hardware-reported limits where available.
- `disk_health_samples`: timestamp, device identity, SMART/NVMe health fields, state, and collection reason.
- `game_sessions`: process identity and observed session start/end.
- `game_process_samples`: per-process CPU, memory, thread count, disk I/O, and contemporaneous system CPU/GPU context.
- `process_samples`: sampled process resource usage, start time, thread count, disk I/O, and available connection counts.

Missing values remain NULL and must not be converted to fabricated zeroes. SQLite schema migration 9 makes metric values nullable while preserving existing metric rows and timestamp indexes.

## DiagnosisResult

```text
DiagnosisResult
├── status
├── primary_hypothesis
├── alternatives[]
├── time_window
├── generated_at
└── data_quality
```

## Captured investigation

```text
Investigation
├── symptom
├── started_at / ended_at
├── status (investigating / captured / resolved / still_happening)
├── user markers and notes
├── measurements, anomalies, process observations, and system events
├── before / during comparison
├── after-change verification window
└── redacted support export
```

An empty anomaly list is not sufficient to call an investigation healthy. The capture also records how much usable measurement history is available.
