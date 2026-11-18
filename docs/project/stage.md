# Diagnosys Development Stages

This document distinguishes connected implementation from work still planned.

## Connected foundation

- PySide6 desktop application with background collection.
- CPU, memory, disk activity, GPU (where supported), uptime, network, and process monitoring.
- SQLite-backed metrics, process samples, incidents, and reports.
- Deterministic personal-baseline anomaly detection and evidence-led investigations.
- Capability reporting and graceful handling of unsupported telemetry.
- Dedicated Thermal and Disk Health pages with background collection and local history.
- SMART/NVMe drive discovery through optional smartmontools.
- Dedicated Gaming page with configured process selection, session lifecycle, process resource history, and comparisons.
- Dedicated Processes page with start time, duration, threads, disk I/O, and historical samples.
- Dedicated Performance page with live resource readings and recent metric history.

## Remaining implementation stages

### 1. Finish thermal diagnostics
- Improve sensor identity and CPU/GPU mapping across platforms.
- Expand sustained thermal findings with reliable clock and workload context.
- Add UI tests and verify sensor freshness and history behavior on supported hardware.
- Do not infer throttling from temperature alone.

### 2. Finish disk health
- Expand SMART parsing coverage across ATA, NVMe, RAID, and USB bridge variations.
- Improve device identity and controller-specific diagnostics.
- Test missing tools, permission denial, unsupported devices, malformed output, and actual SMART warnings.
- Keep all health queries read-only and never infer healthy status from missing data.

### 3. Finish gaming diagnostics
- Improve process matching and session lifecycle around multi-process games.
- Add more robust session comparisons and background process correlation.
- Investigate supported vendor telemetry sources for GPU clock and frame-time only when reliable.
- Continue to label FPS/frame-time unavailable until an actual supported source is integrated.

### 4. Complete UI decomposition
- Keep the main window focused on application shell, task coordination, and cross-page actions.
- Continue extracting remaining orchestration and dialogs from `ui/main_window.py`.
- Add dedicated Performance, History, and Overview modules with page-level UI tests.
- Preserve existing network and investigation workflows.

### 5. Improve evidence and history
- Correlate process activity with resource and investigation timelines.
- Add more useful before/after and cross-session comparisons.
- Ensure every recommendation points to collected evidence and states limitations.
- Review remaining diagnostic rules for unjustified fixed thresholds.

### 6. Reliability and release readiness
- Test collectors with mocked hardware and external commands.
- Test SQLite migrations against existing databases.
- Exercise missing permissions, missing tools, unsupported hardware, and partial telemetry.
- Run the full test suite and configured lint/type checks.
- Validate supported platforms and document limitations.
- Keep changes in reviewable pull requests.

## Non-goals

- No arbitrary confidence percentage, universal health score, or fabricated benchmark.
- No automatic destructive repair or system modification.
- No claim of FPS or frame-time support without an actual data source.

## Completion criteria

A feature is complete only when collection, background execution, persistence, diagnostics, UI, failure states, tests, and documentation are connected. A standalone collector or visual page alone does not count.
