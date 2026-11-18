# Hardware and platform compatibility

Diagnosys uses read-only operating-system APIs and optional vendor utilities. Availability varies by device, controller, driver, operating system, and permissions. An unavailable reading is not interpreted as a normal value.

## Core system telemetry

CPU utilization, memory, disk activity, uptime, process information, and network interface counters use `psutil` where the current operating system exposes the relevant API. Per-process disk I/O, thread count, process start time, and network connection details may be unavailable for protected or system-owned processes.

## Thermal sensors

- CPU and platform temperatures are collected through `psutil.sensors_temperatures()` where implemented by the OS.
- Fan speeds are collected through `psutil.sensors_fans()` where implemented by the OS.
- Many Windows and macOS systems do not expose these sensor APIs through psutil. A missing sensor is shown as unavailable.
- NVIDIA GPU temperature is collected through `nvidia-smi` when the utility and a supported NVIDIA driver are present.
- Other GPU vendors are not currently covered by the vendor-specific GPU collector.
- Hardware high and critical limits are used only when supplied by the sensor. No universal temperature threshold is assumed.
- Sustained thermal findings currently require at least three samples spanning 20 seconds above a sensor-reported high limit. A critical finding is raised when a reading reaches a sensor-reported critical limit. These are observation-duration requirements, not universal temperature thresholds.
- Temperature and utilization occurring together do not prove thermal throttling. Diagnosys reports concurrent CPU utilization and frequency measurements as context, not proof of causation.

## SMART and NVMe health

- Install smartmontools and make sure `smartctl` is available on PATH.
- Drive discovery uses smartctl JSON output. Each discovered device is queried read-only.
- ATA SMART and NVMe health fields are displayed only when returned by the device.
- USB enclosures, RAID controllers, storage bridges, virtual disks, and some vendor firmware may hide or translate SMART data.
- Some systems require elevated privileges for device health queries. Diagnosys does not silently elevate privileges.
- Missing smartctl, permission denial, unsupported devices, query errors, unknown health, and explicit drive warnings are separate states.
- A drive is never labelled healthy solely because SMART data is missing.
- SMART attributes differ between manufacturers. Raw attribute values are not converted into generic failure percentages or predictions.

## Gaming sessions

- Configure one or more executable process names in Settings, separated by commas.
- Matching is case-insensitive and based on the process name exposed by the operating system.
- Session boundaries are inferred from observed process presence. Very short launches or exits between sampling intervals may not be observed.
- Per-process CPU, memory, thread count, and disk I/O are shown where accessible.
- System CPU and supported GPU utilization and temperature are stored as session context. These values can help compare concurrent activity but cannot alone establish a bottleneck.
- FPS and frame-time are not currently collected. They are explicitly unavailable rather than estimated.
- Game monitoring does not inject into a process, hook graphics APIs, bypass anti-cheat, or collect game content.

## Platform validation

The CI workflow tests the Python test suite on Windows, macOS, and Ubuntu with Python 3.11 and 3.12. Passing CI confirms mocked and platform-independent behavior; it does not guarantee that every hardware sensor or SMART controller is available on every machine.
