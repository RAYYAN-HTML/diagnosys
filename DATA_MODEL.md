# Diagnosys Data Model

## MetricSample

Conceptually:

```text
MetricSample
├── timestamp
├── metric_name
├── value
├── unit
├── source
├── entity_id (optional)
└── status
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
├── score
├── confidence
├── evidence[]
├── contradictory_evidence[]
├── limitations[]
└── recommended_checks[]
```

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

The exact Python representation may evolve, but the concepts should remain stable.
