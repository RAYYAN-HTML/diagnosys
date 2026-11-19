# Diagnosys Development Stages

This document distinguishes connected implementation, automated verification, and physical validation.

## Connected foundation

The following workflows are implemented in the current codebase:

- PySide6 desktop application with background collection and dedicated pages.
- CPU, memory, disk activity, GPU (currently NVIDIA `nvidia-smi` where supported), uptime, network, and process monitoring.
- SQLite-backed metrics, process samples, incidents, hardware history, gaming sessions, and reports.
- Deterministic personal-baseline anomaly detection and evidence-led investigations.
- Capability reporting and explicit unavailable states for unsupported telemetry.
- Thermal and fan collection through psutil where the OS exposes it, with persisted history and sensor-reported limits.
- Read-only SMART/NVMe discovery and health queries through optional smartmontools.
- Configured game-process sessions with lifecycle, process resource history, system context, and comparisons.
- Dedicated Overview, Performance, Processes, Thermal, Disk Health, Gaming, Network, Diagnostics, History, Capabilities, and Settings workflows.
- Local reports and incident capture with redaction support.
- Versioned SQLite migrations, including nullable metric values for unavailable readings.

## Remaining validation and release stages

### 1. Physical hardware validation
- Validate CPU/platform thermal and fan sensors on supported hardware.
- Validate NVIDIA GPU telemetry, multiple GPU systems, hybrid graphics, and unsupported GPU vendors.
- Validate SMART/NVMe health on ATA and NVMe devices, USB bridges, and RAID controllers.
- Record permissions, driver versions, OS versions, and unavailable interfaces.
- Do not represent CI mocks as hardware validation.

### 2. Gaming validation
- Exercise multi-process games, launchers, helper processes, crashes, and rapid restarts.
- Confirm process lifecycle and session boundaries against actual launches.
- Validate GPU context and process association where OS/vendor telemetry supports it.
- Keep FPS and frame-time unavailable until a real, documented source is integrated.

### 3. Diagnostic and network validation
- Validate baselines with longer monitoring histories and sparse/partial telemetry.
- Review false positives and ensure recommendations remain traceable to evidence.
- Test network diagnostics on filtered ICMP, DNS failures, captive portals, IPv4, and IPv6.
- Never infer ISP failure from a failed ping alone.

### 4. Desktop quality and architecture
- Exercise all pages on Windows, macOS, and Linux desktop environments.
- Review accessibility, keyboard navigation, long-running chart performance, memory use, shutdown, and worker cleanup.
- Continue extracting modules only where responsibility boundaries improve.

### 5. Release readiness
- Build and smoke-test installers/packages on each target OS.
- Test upgrade and uninstall behavior while preserving local history.
- Review dependencies, licensing, version metadata, and distribution notices.
- Keep platform claims limited to environments actually tested.

## Automated verification

GitHub Actions runs Windows, macOS, and Ubuntu with Python 3.11 and 3.12. CI compiles source and tests, builds Python distributions, and runs pytest. CI is useful for repeatable software verification but cannot prove physical sensor availability or SMART pass-through.

## Non-goals

- No arbitrary confidence percentage, universal health score, or fabricated benchmark.
- No automatic destructive repair or system modification.
- No claim of FPS or frame-time support without an actual data source.

## Completion criteria

Release readiness requires passing CI, successful package smoke tests on target platforms, reviewed documentation and dependencies, and a clearly recorded physical hardware validation matrix. Any hardware not physically tested must remain explicitly unverified.
