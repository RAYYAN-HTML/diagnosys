# Diagnosys Architecture

## 1. Product architecture

```text
                         ┌──────────────────┐
                         │       GUI        │
                         └────────┬─────────┘
                                  │
                                  ▼
                      ┌──────────────────────┐
                      │ UI Task Coordinator  │
                      └──────────┬───────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 ▼               ▼               ▼
          ┌────────────┐  ┌────────────┐  ┌────────────┐
          │  System    │  │  Network   │  │  Process   │
          │ Collectors │  │ Collectors │  │ Collectors │
          └──────┬─────┘  └──────┬─────┘  └──────┬─────┘
                 └───────────────┼────────────────┘
                                 ▼
                        ┌────────────────┐
                        │ Domain Models  │
                        └───────┬────────┘
                                ▼
                         ┌────────────┐
                         │  SQLite    │
                         └─────┬──────┘
                               ▼
                    ┌────────────────────┐
                    │ Anomaly Detection  │
                    └─────────┬──────────┘
                              ▼
                     ┌─────────────────┐
                     │  Correlation    │
                     └────────┬────────┘
                              ▼
                     ┌─────────────────┐
                     │  Diagnostics    │
                     └────────┬────────┘
                              ▼
                    ┌──────────────────┐
                    │ Reports / Output │
                    └────────┬─────────┘
                             │
                             ▼
                     ┌─────────────────┐
                     │ Optional AI     │
                     │ Explanation     │
                     └─────────────────┘
```

## 2. Architectural principles

### Local-first

Measurements and history live locally unless the user explicitly enables an external integration.

### Evidence-first

The diagnostic engine operates on measurements. Explanations are downstream.

### Deterministic core

The core must work without an LLM.

### Graceful degradation

Unsupported hardware or unavailable network methods become explicit unavailable states.

### Separation of concerns

Collectors collect. Storage stores. Diagnostics diagnose. The desktop GUI
displays results and coordinates user actions.

## 3. Package structure

```text
src/diagnosys/
├── gui.py
├── __main__.py
├── ui/
│   ├── main_window.py
│   ├── components.py
│   └── theme/
├── core/
│   └── capabilities.py
├── models/
│   ├── metrics.py
│   ├── diagnostics.py
│   ├── network.py
│   ├── incidents.py
│   └── reports.py
├── collectors/
│   ├── base.py
│   ├── system/
│   └── network/
├── diagnostics/
│   ├── rules.py
│   └── engine.py
├── correlation/
│   └── engine.py
├── storage/
│   ├── database.py
│   ├── repositories.py
│   └── incidents.py
├── reports/
│   └── generator.py
├── ai/
│   ├── base.py
│   └── providers/
├── config/
│   ├── settings.py
│   └── logging.py
```

## 4. Collector contract

A collector should have a predictable contract:

```text
collect()
  ↓
Measurement(s)
  OR
measurement with an unavailable status and reason
```

It should not:
- print directly to the terminal
- write SQL directly
- perform diagnosis
- call an LLM

## 5. Storage contract

Repositories hide SQLite details.

Example:

```text
MetricRepository.save(sample)
MetricRepository.query(window)
AnomalyRepository.save(anomaly)
```

The diagnostic engine should not depend directly on SQL statements.

## 6. Domain flow

```text
measurement
    ↓
normalization
    ↓
persistence
    ↓
window selection
    ↓
anomaly detection
    ↓
correlation
    ↓
hypothesis generation
    ↓
evidence scoring
    ↓
diagnosis result
    ↓
presentation
```

## 7. Correlation model

Correlation operates on time windows.

For each hypothesis, retain:

```text
Hypothesis
├── category
├── score
├── confidence
├── evidence[]
├── contradictory_evidence[]
├── time_window
└── limitations[]
```

## 8. AI boundary

```text
                 Deterministic Core
                       │
                       │ structured evidence
                       ▼
                  AI Explainer
                       │
                       ▼
                natural-language
                   explanation
```

The AI boundary must not flow backward into unrestricted system control.

## 9. Failure isolation

Each collector runs independently.

```text
CPU collector ── OK
RAM collector ── OK
GPU collector ── unavailable
Ping collector ── timeout
DNS collector ── OK
```

The monitoring cycle still completes.

## 10. Future architecture

Potential later modules:
- richer time-aware baselines
- TUI dashboard
- local web dashboard
- plugin system
- application/game diagnostics
- local LLM provider
- notification service

These must preserve the deterministic core.

## 11. Investigation workflow

The primary user path is symptom-first:

```text
symptom selection
    ↓
persistent capture marker
    ↓
pre-capture + live local history
    ↓
system, process, network, and Windows event evidence
    ↓
ranked leads + focused checks
    ↓
after-change comparison
    ↓
user-confirmed outcome
```

An investigation record stores its symptom, notes, capture status, evidence,
after-change measurements, and user-reported outcome. Measurements are queried
by explicit time range; they are not inferred from the anomaly list alone.
The evidence question helper reads only the selected local incident. Export
redaction is reviewed before a support bundle is written.

The current tray option keeps the desktop process alive while its window is
hidden. It is not a Windows service and does not collect while the process is
stopped. A service mode would need a separate lifecycle and installer design.
