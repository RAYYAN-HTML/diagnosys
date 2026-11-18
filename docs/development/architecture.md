# Diagnosys Architecture

## Product principles

- **Local-first:** measurements and history remain on the device.
- **Evidence-first:** every diagnostic lead is traceable to collected observations.
- **Deterministic:** diagnosis uses explicit rules and transparent evidence ordering. No generated diagnosis layer is used.
- **Graceful degradation:** unsupported sensors and permission failures are represented as unavailable states, never as fabricated values.
- **Read-only by default:** collection and health inspection must not modify the operating system or storage devices.

## Runtime flow

```text
Desktop shell and page modules
   |
Background task coordinator
   |
Collectors -------------------- Capability discovery
   |
Typed measurements and snapshots
   |
SQLite repositories
   |
Personal baselines and hardware-reported limit rules
   |
Evidence correlation and investigation
   |
Reports and UI presentation
```

## Package structure

```text
src/diagnosys/
├── gui.py
├── __main__.py
├── ui/
│   ├── main_window.py       # Application shell and cross-page orchestration
│   ├── components.py        # Shared visual components
│   ├── pages/               # Overview, network, diagnostics, history, settings,
│   │                       # performance, thermal, disk health, gaming, and processes
│   ├── controllers/         # Investigation, network, and report workflows
│   ├── tasks.py             # Background Qt task worker and result routing
│   ├── formatters.py        # Pure report and metric formatting helpers
│   └── theme/               # Shared tokens and Qt stylesheet
├── core/                    # Runtime capability discovery
├── models/                  # Measurements, diagnoses, incidents, reports
├── collectors/
│   ├── system/              # CPU, memory, disk, GPU, thermal, SMART, processes, gaming
│   └── network/             # Network probes and interface counters
├── diagnostics/             # Deterministic rules and investigation logic
├── correlation/             # Time-window evidence correlation
├── storage/                 # SQLite schema, migrations, repositories
├── reports/                 # Text, Markdown, JSON and HTML report output
└── config/                  # Runtime settings and logging
```

## Component responsibilities

### Collectors

Collectors read operating-system or hardware telemetry and return typed values. They do not write SQL, render UI, or make diagnostic conclusions. A missing sensor, unsupported device, permission failure, or timeout must be represented explicitly.

### Background task coordinator

Potentially slow collection and probing run outside the Qt UI thread. Disk discovery and SMART queries are rate-limited independently from live sampling. Each collector should fail without preventing unrelated measurements from completing.

### Storage

Repositories own SQLite access. Schema changes are versioned and tested against an existing database. Hardware and process observations retain timestamps and available device/process identity. Missing values remain NULL rather than being replaced with zero.

### Diagnostics

The diagnostic engine compares observations with personal baselines where sufficient history exists. Thermal limit findings use high and critical values reported by the sensor itself. Results are ordered by transparent evidence criteria, not probability, confidence, or arbitrary scores. Time overlap is correlation, not proof of causation or throttling.

### UI

Page construction lives in `ui/pages/`; shared widgets and theme tokens are reused across pages. The main window remains the application coordinator and is still being reduced. Pages present measurements, freshness, capability availability, evidence, limitations, and next checks.

## Diagnostic result contract

A finding should include:
- category or observed pattern
- supporting measurements and timestamps
- relevant process or device context when available
- contradictory or missing evidence
- limitations
- recommended next checks

Do not present an overall health score, diagnostic confidence percentage, or fabricated sensor reading.

## Privacy and safety

- No hidden telemetry or automatic upload.
- Diagnostic findings are generated locally through deterministic rules and remain traceable to measurements.
- Do not collect passwords, tokens, cookies, keystrokes, private messages, browser history, or arbitrary personal files.
- SMART queries must be read-only.
- Game process names are explicitly configured by the user.
- Any future operation that changes system state requires explicit user confirmation and documented rollback behavior.

## Current implementation boundaries

Overview, performance, thermal, disk-health, gaming, and process pages are connected to collection and SQLite history. Sensor coverage remains hardware- and OS-dependent. GPU vendor coverage is currently limited, and FPS/frame-time telemetry is not available. `ui/main_window.py` now acts primarily as the application shell and telemetry coordinator. Investigation, network, and report workflows are delegated to controllers; the remaining live-collection and history coordination will continue to be extracted where that improves ownership and testability.
