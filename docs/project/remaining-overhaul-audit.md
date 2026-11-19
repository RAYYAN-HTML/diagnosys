# Diagnosys reliability and release audit

Base: `master` after merge commit `737ccebba735a1b35aee988a4b4f2eeeb2ce608d`.

## Completed foundation verified in source

- The PySide6 desktop app uses background tasks and dedicated page modules for overview, network, diagnostics, history, capabilities, settings, thermal, disk health, gaming, processes, and performance.
- Thermal and fan collection, persisted thermal history, sensor-reported limit findings, SMART/NVMe discovery and health history, configured gaming sessions, process lifecycle history, and nullable metric persistence are connected to SQLite.
- Investigation, network, report, monitoring, and history workflows are separated into controllers.
- The previous fixed-template conversational investigation helper has been removed in favor of explicit evidence, timelines, limitations, and next checks.
- CI covers Windows, macOS, and Ubuntu with Python 3.11 and 3.12.

## Remaining work is validation and product release

1. Physical hardware validation for thermal sensors, fans, GPU telemetry, ATA/NVMe health, and controller/enclosure variations.
2. GPU vendor and multi-device coverage beyond the current NVIDIA `nvidia-smi` collector, only where reliable telemetry interfaces exist.
3. Real-game validation for process lifecycle, helper processes, session comparisons, and GPU context.
4. Longer-running baseline and diagnostic correlation validation, including false-positive review.
5. Real-network validation for gateway, DNS, HTTP, route tracing, filtered ICMP, and IPv6.
6. Desktop smoke tests, accessibility review, worker shutdown, and long-running resource use on supported platforms.
7. Platform-specific package and installer builds, upgrade/uninstall checks, dependency/license review, and release notes.

## Important distinctions

- Passing mocked collector tests does not establish hardware compatibility.
- Passing cross-platform Python CI does not prove every desktop environment launches successfully.
- A temperature coinciding with lower clock speed is not by itself proof of thermal throttling.
- A failed ping is not proof of ISP failure.
- FPS and frame-time are not currently collected.
- Hardware and controller behavior that has not been physically exercised remains unverified.

## Execution standard

Complete all software-verifiable work in a reviewable branch. Use GitHub Actions as the automated test authority. Keep physical hardware and desktop smoke-test gaps explicit. Preserve user history, existing workflows, nullable measurements, and deterministic evidence. Open a pull request for human review and do not merge automatically.
