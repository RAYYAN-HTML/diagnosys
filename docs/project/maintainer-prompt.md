# Diagnosys Maintainer Guide

## Product goal

Diagnosys is a local-first desktop diagnostic application that helps users understand PC and network performance problems using real measurements and deterministic, explainable analysis.

## Non-negotiable rules

2. No fabricated metrics, FPS, frame-time, health percentages, confidence percentages, or overall health scores.
3. No universal hardware thresholds presented as authoritative.
4. Every finding must link to observations, timestamps, limitations, and practical next checks.
5. Unsupported hardware, missing permissions, missing tools, and collection errors must be explicit states.
6. Collectors remain read-only and do not perform repair operations.
7. Slow collection runs outside the Qt UI thread.
8. Keep UI, collectors, storage, and diagnostics separate.
9. Avoid monolithic modules and disconnected placeholder controls.
10. Do not weaken tests to hide regressions.

## Architecture

The runtime flow is:

```text
Desktop UI
  -> background task coordinator
  -> collectors and capability discovery
  -> typed observations
  -> SQLite repositories
  -> personal baselines and deterministic rules
  -> evidence correlation and investigations
  -> reports and UI presentation
```

Collectors must not write SQL, render widgets, or diagnose. Repositories own database access. Diagnostic logic must not depend on Qt.

## Diagnostic language

Use terms such as:
- observed
- elevated relative to this device's baseline
- repeated during the capture window
- correlated in time
- insufficient evidence
- unavailable

Do not claim causation from time overlap. Do not call a process malicious based on resource usage. Do not claim a device is healthy when its health telemetry is unavailable.

## Current overhaul priorities

1. Finish decomposing remaining cross-page orchestration and dialogs from `ui/main_window.py`.
2. Expand hardware-specific SMART/NVMe support and test controller-specific failure modes.
3. Improve thermal sensor mapping and correlate hardware-reported limits with utilization and clock history.
4. Improve multi-process game session matching and background process correlation.
5. Improve process timelines and historical comparisons.
6. Add UI integration tests and verify the complete suite on Windows, macOS, and Linux.

## Pull request requirements

Every pull request should explain:
- problem and user-visible outcome
- architecture and data-model changes
- tests run and exact results
- platform-specific behavior
- unavailable capabilities and known limitations
- privacy and safety impact

Do not merge without review and successful CI for the exact pull request head.

## Definition of done

A feature is done only when its collector, background task, persistence, diagnostics, UI, error handling, tests, and documentation work together. Never mark a feature complete based only on a class, file, or mockup.
