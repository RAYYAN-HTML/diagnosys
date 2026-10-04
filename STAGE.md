# Diagnosys Development Stages

## Stage 0 — Foundation

Build:
- repository structure
- `pyproject.toml`
- package initialization
- CLI skeleton
- configuration
- logging
- test setup
- basic README

Acceptance:

```bash
python -m pytest
diagnosys --help
```

---

## Stage 1 — System metrics

Build:
- CPU collector
- memory collector
- disk collector
- uptime

Add typed domain models and unit tests.

Command:

```bash
diagnosys status
```

Acceptance:
A clean machine-readable and human-readable snapshot works without crashing.

---

## Stage 2 — Process intelligence

Build:
- process enumeration
- top CPU consumers
- top memory consumers
- process count
- permission handling

Command:

```bash
diagnosys processes
```

---

## Stage 3 — Network health

Build independently testable:
- ping
- packet loss
- jitter
- DNS latency
- HTTP latency

Every network operation needs timeouts.

Command:

```bash
diagnosys network
```

---

## Stage 4 — SQLite history

Build:
- database initialization
- measurement repository
- anomaly repository
- retention policy
- history queries

Command:

```bash
diagnosys history
```

---

## Stage 5 — Monitoring engine

Build:

```bash
diagnosys monitor
```

Requirements:
- configurable sampling interval
- graceful shutdown
- collector isolation
- persistent measurements
- stable resource consumption

---

## Stage 6 — Anomaly detection

Implement transparent rules for:
- CPU spikes
- RAM pressure
- disk pressure
- process spikes
- latency spikes
- jitter
- packet loss
- DNS/HTTP anomalies

No AI yet.

---

## Stage 7 — Correlation

Correlate system and network anomalies.

Important scenarios:

### Local pressure

```text
CPU high
+
disk high
+
network normal
```

### Network instability

```text
CPU normal
+
RAM normal
+
packet loss high
+
latency unstable
```

### Possible resource/network interaction

```text
CPU high
+
network latency high
+
same time window
```

Report this as correlation, not proof of causation.

---

## Stage 8 — Diagnostic engine

Produce ranked hypotheses with:
- score
- confidence
- evidence
- contradictory evidence
- limitations
- recommended next check

Command:

```bash
diagnosys diagnose
```

This is the MVP milestone.

---

## Stage 9 — Historical baselines

Compare current behavior against the user's own history.

Implement:
- rolling median
- percentile baselines
- anomaly deviation
- optional time-of-day baseline

---

## Stage 10 — Reports

Implement:

```bash
diagnosys report
```

Possible output:
- terminal report
- JSON
- Markdown
- optional HTML later

---

## Stage 11 — AI explanation

Only after Stage 8 is stable.

Build:
- provider interface
- optional provider
- prompt templates
- structured input
- output validation
- privacy controls

The AI must explain evidence, not generate facts.

---

## Stage 12 — Dashboard

Optional:
- TUI
- local web UI
- charts
- timeline
- live health status

CLI remains first-class.

---

## Stage 13 — Hardening

Add:
- Windows/Linux/macOS testing
- CI
- packaging
- documentation
- benchmarks
- security review
- dependency audit
- release process

---

## Milestones

### MVP

Stages 0–8.

### Portfolio v1

Stages 0–10 + polished README + CI + screenshots/demo.

### Advanced v2

Stages 11–13.

Do not add AI or a dashboard just because it is trendy. The diagnostic engine is the core product.
