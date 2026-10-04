# Diagnosys — Master Agent Build Prompt

You are a senior Python systems engineer, software architect, SRE, and diagnostics-tool developer.

Build **Diagnosys**, a local-first PC and Internet health diagnostic agent.

## Product idea

Diagnosys answers:

> "Why does my computer or internet feel slow right now?"

It continuously or on-demand collects measurable system and network signals, detects anomalies, correlates events over time, ranks likely causes, and explains the result with evidence.

The product must be useful **without an LLM**. AI is an optional explanation layer added only after the deterministic diagnostic engine works.

## Product goals

1. Diagnose PC performance problems.
2. Diagnose network/Internet quality problems.
3. Correlate PC and network symptoms.
4. Compare current measurements with a historical baseline.
5. Explain conclusions using evidence.
6. Recommend safe next checks.
7. Work locally by default.
8. Be cross-platform where practical.
9. Be easy to understand and extend.
10. Become a strong portfolio-quality Python project.

## Non-goals

Do not initially build:
- a remote administration tool
- a security scanner for arbitrary hosts
- a packet-sniffing platform
- an antivirus
- a system optimizer/cleaner
- an automatic registry/configuration editor
- a tool that silently changes system settings
- an AI agent with unrestricted shell access

## Core user experience

The most important command is:

    diagnosys diagnose

It should eventually produce a concise answer such as:

    DIAGNOSYS
    ─────────────────────────────

    Status: WARNING

    Most likely cause:
    Network instability

    Evidence:
    • Packet loss: 6.8%
    • Ping median: 18 ms
    • Ping p95: 271 ms
    • CPU: 32%
    • RAM: 55%
    • Disk activity: 15%

    PC resources are within normal range.

    Confidence: High

    Recommended next checks:
    1. Test the connection again for 60 seconds.
    2. Compare Wi-Fi and Ethernet if available.
    3. Test another known-good network.

The exact wording can evolve, but the principle must remain:
**diagnosis → evidence → confidence → next action.**

# Technical requirements

## Python

- Target Python 3.11+ unless a later version has a clear reason.
- Use type hints.
- Use `dataclasses` or a validation library for domain models.
- Prefer standard library solutions when sufficient.
- Use `psutil` for cross-platform system metrics where appropriate.
- Use `pytest` for tests.
- Use a modern `pyproject.toml`.
- Use `pathlib`.
- Use `logging`.
- Avoid global mutable state.

## Architecture

Use a layered architecture:

    CLI
      ↓
    Application services
      ↓
    Collectors
      ↓
    Normalization/domain models
      ↓
    Storage
      ↓
    Anomaly detection
      ↓
    Correlation
      ↓
    Diagnostic engine
      ↓
    Reporting
      ↓
    Optional AI explanation

Suggested source layout:

    src/diagnosys/
        __init__.py
        cli/
        core/
        models/
        collectors/
            system/
            network/
        diagnostics/
        correlation/
        storage/
        reports/
        ai/
        config/
        utils/

Tests:

    tests/
        unit/
        integration/
        fixtures/

Documentation:

    docs/
        ARCHITECTURE.md
        STAGE.md
        DO_AND_DONT.md
        DIAGNOSTICS.md
        METRICS.md
        DATA_MODEL.md
        AI.md
        CONTRIBUTING.md
        PRIVACY.md

## Domain models

Design explicit models such as:

- MetricSample
- ProcessSample
- NetworkProbe
- Anomaly
- Evidence
- DiagnosisHypothesis
- DiagnosisResult
- HealthSnapshot
- Baseline
- CollectionError

Every important diagnostic result should be traceable back to measurements.

## System monitoring

Collect, where supported:

### CPU
- overall utilization
- per-core utilization
- load average where available
- CPU frequency where practical

### Memory
- total
- used
- available
- percentage
- swap usage where available

### Disk
- total/free space
- read/write throughput
- disk activity/busy percentage where supported

### Processes
- top CPU consumers
- top memory consumers
- process count
- process CPU/memory snapshots

Handle permission failures gracefully.

### Temperature/GPU

Treat these as optional capabilities.

If unavailable:

    available = false
    reason = "unsupported_or_unavailable"

Never fake a value.

## Network monitoring

Measure independently:

### Latency
Use repeated probes and calculate useful statistics such as:
- min
- median
- p95
- max

### Packet loss

    failed probes / total probes

### Jitter

Choose and document one calculation. Keep it consistent.

### DNS
Measure DNS resolution latency with bounded timeouts.

### HTTP/HTTPS
Measure connection/response timing against safe configurable endpoints.

Do not store response bodies by default.

### Throughput
Make throughput tests optional because they can consume bandwidth.

Clearly warn the user before a bandwidth-intensive test.

## Monitoring

Provide:

    diagnosys monitor

Requirements:
- configurable interval
- graceful Ctrl+C shutdown
- collector isolation
- persistent storage
- bounded resource use
- no busy loops
- no unbounded memory growth

## Historical storage

Use SQLite for the initial implementation.

Store measurements locally.

A measurement should contain at minimum:

- timestamp
- metric name
- numeric value where applicable
- unit
- source
- optional entity identifier
- collection status

Avoid storing sensitive or unnecessary information.

## Baselines

Later, learn the user's normal behavior.

Possible baseline statistics:
- median
- p95
- standard deviation
- median absolute deviation
- time-of-day patterns

Do not immediately assume that one global threshold works for every machine.

The first implementation may use configurable thresholds, then progressively introduce personalized baselines.

## Anomaly detection

Detect events such as:
- CPU saturation
- RAM pressure
- disk pressure
- unusual process activity
- latency spikes
- packet loss
- DNS spikes
- HTTP latency spikes

Start with transparent deterministic rules.

Every rule should document:
- inputs
- threshold/calculation
- reason
- limitations
- false positives

## Correlation engine

This is one of the project's signature features.

Correlate measurements within time windows.

Example:

    CPU spike ───────────┐
                         ├── same time window
    ping spike ─────────┘

Possible result:

    "CPU pressure and network latency increased during
     the same interval."

Do NOT automatically state:

    "CPU caused the network problem."

Correlation is not causation.

The engine should track:
- temporal overlap
- magnitude
- duration
- independent supporting signals
- contradictory signals

## Diagnostic engine

Generate ranked hypotheses.

Example:

    1. Network instability       confidence 0.89
    2. Local resource contention confidence 0.31
    3. DNS issue                 confidence 0.12

Each hypothesis must include evidence.

Use a transparent scoring model initially.

Avoid magic numbers. Put thresholds and weights in named configuration structures.

## Diagnostic categories

At minimum:

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

## Confidence

Confidence is evidence strength, not proof.

Use labels such as:
- Low
- Moderate
- High
- Very High

Document how the score is calculated.

Do not present a heuristic score as scientific certainty.

## Reporting

Commands should eventually include:

    diagnosys status
    diagnosys monitor
    diagnosys diagnose
    diagnosys history
    diagnosys processes
    diagnosys network
    diagnosys report
    diagnosys config

Support machine-readable output:

    --json

A report should contain:
- overall status
- primary diagnosis
- evidence
- competing hypotheses
- confidence
- time window
- recommended next checks
- unavailable measurements
- limitations

## AI layer

Add only after deterministic diagnostics are functional.

Create an abstraction such as:

    AIExplainer

Possible providers:
- hosted LLM
- local LLM
- no-op provider

The AI should receive structured evidence rather than unrestricted machine access.

Example input:

    {
      "window_seconds": 60,
      "cpu_avg": 31,
      "ram_percent": 52,
      "disk_busy_percent": 14,
      "ping_median_ms": 19,
      "ping_p95_ms": 285,
      "packet_loss_percent": 7,
      "anomalies": [...]
    }

The AI must:
- explain the diagnostic engine's evidence
- identify uncertainty
- avoid inventing measurements
- avoid pretending to have performed checks it did not perform

The AI must NOT:
- execute generated shell commands automatically
- change system settings
- install software
- access credentials
- access private files unless a future explicit feature is designed and approved

## Privacy

Default behavior:
- local data
- no telemetry
- no cloud upload
- no credentials
- no browser history
- no cookies
- no private messages
- no keystrokes

External network targets must be configurable and documented.

## Reliability

One collector failing must not kill monitoring.

Example:

    GPU sensor unavailable
       ↓
    record unavailable capability
       ↓
    continue CPU/RAM/network collection

Network timeout:
- record timeout
- continue other probes
- use bounded retries only

## Testing

Every calculation needs unit tests.

Test:
- packet loss
- jitter
- percentiles
- thresholds
- anomaly detection
- scoring
- correlation windows
- SQLite repositories
- malformed configuration
- collector failures
- network timeouts

Use mocks/fakes for external systems.

Tests must not depend on a live Internet connection.

## Code quality

Before considering a stage complete:
- run tests
- run linting if configured
- run type checks if configured
- update docs
- inspect the diff
- avoid unrelated refactors

## Development behavior

When working on this repository:

1. Read `ARCHITECTURE.md`.
2. Read `STAGE.md`.
3. Read `DO_AND_DONT.md`.
4. Read any relevant domain documentation.
5. Inspect the current code.
6. Identify the smallest implementation for the current stage.
7. Implement it.
8. Add/update tests.
9. Run checks.
10. Update documentation.
11. Summarize changes and remaining limitations.

Do not jump ahead several stages unless explicitly asked.

Do not rewrite working code simply to make it look different.

Do not silently introduce a new framework or architectural pattern.

If requirements conflict, prioritize:
1. safety/privacy
2. correctness
3. testability
4. simplicity
5. performance
6. convenience

## Definition of done

A feature is complete only when it has:
- implementation
- tests
- error handling
- type hints
- documentation
- reasonable logging
- clear user-facing behavior
- no unnecessary dependency
- no known privacy regression

The final result should feel like a real open-source Python project, not a tutorial script.
