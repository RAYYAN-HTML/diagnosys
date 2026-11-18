# Testing and validation

## Local setup

Use Python 3.11 or 3.12 and install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the complete suite:

```bash
pytest
```

The test suite mocks operating-system sensors, process enumeration, and external commands. It should not require physical SMART devices, temperature sensors, game processes, or an NVIDIA GPU.

## Coverage expectations

- Collector tests mock psutil and vendor tools.
- SMART tests use representative JSON responses and mocked smartctl subprocess results.
- Thermal tests verify unavailable sensors and sensor-provided high/critical limits.
- Gaming tests verify explicit process-name selection, session lifecycle, and partial access failures.
- Storage tests initialize in-memory SQLite databases and verify schema migrations.
- Diagnostic tests verify baseline and hardware-evidence rules without physical hardware.
- UI tests import page modules and exercise unavailable-state rendering where Qt runtime libraries are available.

## Platform matrix

GitHub Actions runs pytest on Windows, macOS, and Ubuntu with Python 3.11 and 3.12. A platform test passing does not prove a hardware API is available on every device. Hardware compatibility must be documented separately.

## Manual desktop smoke test

On a machine with a graphical desktop:

1. Install the project and launch `python -m diagnosys`.
2. Confirm Overview, Network, Diagnostics, History, Capabilities, Settings, Thermal, Disk Health, Gaming, and Processes pages open.
3. Confirm unsupported sensors and missing optional tools are described as unavailable, not normal.
4. Configure a known game executable name and verify session start/end after launching and closing that process.
5. If smartmontools is installed and the drive exposes SMART, verify the discovered device and read-only health values.
6. Verify history remains after restarting the application.
7. Review an investigation and export preview for evidence, limitations, and redaction behavior.

Never weaken or skip a failing hardware-independent test to accommodate one developer machine. Add a mock for the missing platform behavior instead.
