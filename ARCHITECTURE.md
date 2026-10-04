# Diagnosys Architecture

## 1. Product architecture

```text
                         ┌──────────────────┐
                         │       CLI        │
                         └────────┬─────────┘
                                  │
                                  ▼
                      ┌──────────────────────┐
                      │ Application Services │
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

Collectors collect. Storage stores. Diagnostics diagnose. CLI displays.

## 3. Package structure

```text
src/diagnosys/
├── cli/
│   ├── commands.py
│   └── main.py
├── core/
│   ├── services.py
│   └── scheduling.py
├── models/
│   ├── metrics.py
│   ├── diagnostics.py
│   └── network.py
├── collectors/
│   ├── base.py
│   ├── system/
│   └── network/
├── diagnostics/
│   ├── rules.py
│   ├── scoring.py
│   └── engine.py
├── correlation/
│   └── engine.py
├── storage/
│   ├── database.py
│   └── repositories.py
├── reports/
│   └── formatter.py
├── ai/
│   ├── base.py
│   └── providers/
├── config/
│   └── settings.py
└── utils/
```

## 4. Collector contract

A collector should have a predictable contract:

```text
collect()
  ↓
Measurement(s)
  OR
CollectionError
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
- baseline engine
- TUI dashboard
- local web dashboard
- plugin system
- application/game diagnostics
- local LLM provider
- notification service

These must preserve the deterministic core.
