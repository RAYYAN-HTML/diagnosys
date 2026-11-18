# Diagnosys

Diagnosys is a local-first desktop diagnostic application for understanding PC slowdowns, thermal behaviour, storage health, game-session resource use, and network instability.

## Core principles

- **Local-first:** measurements and incident history stay on the device.
- **Evidence-first:** diagnoses show the observations and rules behind each finding.
- **Deterministic:** diagnoses are derived from explicit measurements and rules, without opaque scores or unsupported certainty.
- **Adaptive:** anomaly detection compares readings with a sufficiently populated personal baseline instead of global CPU, RAM, disk, or network cutoffs.
- **Honest telemetry:** unsupported sensors and missing readings are shown as unavailable, never as zero.
- **Read-only:** hardware health collection does not modify disks or system settings.

## Current capabilities

- Live CPU, memory, disk activity, GPU (where supported), network, uptime, and process monitoring.
- Personal-baseline anomaly detection using median, percentile, and median absolute deviation.
- Evidence-backed investigations with timelines, process context, explicit limitations, and next checks.
- Thermal and fan collection where exposed by the operating system or hardware, with persisted history and sensor-reported high/critical limit findings.
- Read-only SMART/NVMe discovery and health queries through optional `smartctl`, including explicit unavailable and error states.
- User-selected game-process sessions with per-process CPU, memory, threads, and disk I/O, plus system CPU/GPU context and session comparisons.
- Process start-time, duration, thread-count, disk-I/O, and resource history where process permissions allow.
- Local SQLite history, incident capture, before/after comparison, and redacted support reports.

The desktop includes dedicated Performance, Processes, Thermal, Disk Health, and Gaming pages. The existing overview, network, investigation, history, capabilities, and settings workflows remain available.

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

Linux and macOS:

```bash
.venv/bin/python -m pip install -e .
.venv/bin/python -m diagnosys
```

For development and tests, install `pip install -e ".[dev]"` and run `pytest`.

## Optional hardware tools

Install smartmontools and ensure `smartctl` is on PATH to discover and query supported drive health. SMART access may require elevated permissions. Some USB enclosures, RAID controllers, and storage bridges do not pass health data through. Diagnosys does not run destructive disk commands.

Thermal sensor availability depends on the operating system, hardware, drivers, and permissions. NVIDIA GPU telemetry requires the vendor's `nvidia-smi` utility. Other GPU vendors may expose no supported telemetry through the current collector.

Game monitoring samples only process names explicitly configured in Settings. Add executable names separated by commas, for example `game.exe, another-game.exe`. It does not inject into games or bypass anti-cheat systems. FPS and frame-time are not currently collected.

See [hardware compatibility](docs/hardware-compatibility.md), [privacy details](docs/privacy.md), [contributing](CONTRIBUTING.md), and the [documentation index](docs/README.md).
