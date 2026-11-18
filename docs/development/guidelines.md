# Diagnosys Development Guidelines

## Core principles

- Keep Diagnosys deterministic, local-first, and evidence-based.
- Keep measurements separate from diagnostic findings.
- Show the time window, source, and freshness of important observations.
- Use personal baselines when sufficient history exists.
- Make missing data, unsupported capabilities, and collection errors explicit.
- Isolate collector failures and use bounded timeouts.
- Keep collectors, storage, diagnostics, and UI in separate layers.
- Run slow collection outside the Qt UI thread.
- Prefer safe, read-only diagnostics.
- Write hardware-independent tests using mocks.
- Document assumptions, limitations, and platform differences.
- Avoid rewriting working modules without a concrete reason.

## Diagnostic language

Prefer:
- observed
- elevated relative to this device's baseline
- repeated during the capture window
- correlated in time
- insufficient evidence
- unavailable

Do not claim correlation proves causation. Do not call a process malicious based on resource usage. Do not describe a device as healthy when its health data is unavailable.

## Avoid misleading metrics

- No fabricated measurements, FPS, frame-time, or benchmark values.
- No diagnostic confidence percentages or arbitrary hypothesis scores.
- No overall health score without a defensible, documented measurement model.
- No universal hardware thresholds presented as authoritative.
- Do not substitute stale values without clearly marking them stale.

## Platform compatibility

Windows, Linux, and macOS expose different metrics and permissions. Use capability detection and report unsupported features explicitly. The normal workflow should not require administrator or root privileges.

## Safety and privacy

- Do not collect passwords, tokens, cookies, browser history, keystrokes, private messages, or arbitrary personal files.
- Do not silently upload measurements or reports.
- SMART and other device health queries must remain read-only.
- Any future operation that changes system state requires explicit user confirmation, an explanation, and a rollback plan where practical.

## Current application workflow

```text
python -m diagnosys
        |
desktop dashboard
        ├── live system metrics and history
        ├── network health checks
        ├── evidence-based investigations
        ├── capability inspection
        ├── incident history
        └── report export
```

GUI actions should call existing collectors, repositories, and deterministic engines. Do not put diagnostic logic in button handlers. Do not add placeholder controls.
