# Diagnosys

Diagnosys is a local-first desktop diagnostic application for understanding PC slowdowns, thermal behaviour, storage health, game-session resource use, and network instability.

## Core principles

- **Local-first:** measurements and incident history stay on the device.
- **Evidence-first:** diagnoses show the observations and rules behind each finding.
- **Deterministic:** no AI provider, fabricated confidence percentage, or opaque diagnosis score.
- **Adaptive:** anomaly detection compares readings with a sufficiently populated personal baseline instead of global CPU, RAM, disk, or network cutoffs.
- **Honest telemetry:** unsupported sensors and missing readings are shown as unavailable, never as zero.

## Current capabilities

- CPU, memory, storage, process, uptime, and network monitoring.
- Personal-baseline anomaly detection using median, percentile, and median absolute deviation.
- Evidence-backed diagnosis with explicit limitations and recommended checks.
- Thermal and fan sensor collection where exposed by the OS and hardware.
- Optional SMART/NVMe health queries through the locally installed `smartctl` utility.
- User-selected game-process monitoring for CPU, memory, thread, and disk-I/O activity. FPS and frame-time capture are not claimed without a dedicated frame telemetry source.
- Local SQLite history, investigation capture, before/after comparison, and redacted support reports.

## Run from source

Requires Python 3.11 or later and a desktop environment.

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m diagnosys
```

Linux:

```bash
.venv/bin/python -m pip install -e .
.venv/bin/python -m diagnosys
```

## Optional hardware tools

Install smartmontools and ensure `smartctl` is on PATH to query supported drive health. SMART access may require elevated permissions and some USB enclosures do not pass SMART data through.

Thermal sensor availability depends on the operating system, hardware, drivers, and permissions. Game-process monitoring only samples process names explicitly supplied by the user. It does not inject into games or bypass anti-cheat systems.

See [privacy details](docs/privacy.md), [contributing](CONTRIBUTING.md), and the [documentation index](docs/README.md).
