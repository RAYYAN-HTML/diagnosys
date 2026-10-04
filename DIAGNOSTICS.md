# Diagnosys Diagnostic Model

## Principle

Diagnosys should answer three questions:

1. What happened?
2. What evidence supports the explanation?
3. What should the user check next?

## Diagnostic categories

- HEALTHY
- CPU_PRESSURE
- MEMORY_PRESSURE
- DISK_PRESSURE
- PROCESS_CONTENTION
- THERMAL_PRESSURE
- NETWORK_LATENCY
- NETWORK_JITTER
- PACKET_LOSS
- DNS_LATENCY
- HTTP_LATENCY
- THROUGHPUT_LIMITATION
- MIXED
- INSUFFICIENT_DATA

## Evidence levels

Prefer:

1. Direct measurement
2. Repeated measurement
3. Independent corroborating measurements
4. Historical deviation
5. Heuristic inference
6. AI explanation

## Example

```text
CPU: 27%
RAM: 49%
Disk: 16%
Ping median: 18ms
Ping p95: 310ms
Packet loss: 7%
DNS: 24ms
```

Likely diagnosis:

```text
NETWORK_INSTABILITY
```

Evidence:
- packet loss is elevated
- latency has a large tail
- CPU/RAM/disk are normal

Confidence:
High

Limitation:
The test identifies instability to the configured targets; it does not prove where in the network path the fault originates.

## Competing hypotheses

Diagnosys should not only produce one answer.

Example:

```text
Primary:
Network instability — High

Alternative:
Wi-Fi interference — Moderate

Alternative:
Remote service latency — Low
```

This makes the system more honest and useful.

## Confidence

Confidence represents the strength and consistency of evidence.

Suggested product labels:

```text
0.00–0.29  Low
0.30–0.59  Moderate
0.60–0.79  High
0.80–1.00  Very High
```

These are product conventions, not scientific probabilities.

## Historical baselines

A user's normal system can vary substantially.

Future baseline logic should compare current measurements with:
- recent history
- long-term history
- time-of-day behavior

Avoid treating every deviation as a fault.
