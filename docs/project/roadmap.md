# Diagnosys roadmap

## Current state

The foundation overhaul is merged into `master`. The application now includes connected thermal, disk-health, gaming-session, process-history, performance, network, investigation, reporting, and capability workflows. SQLite migrations preserve existing records and unavailable numeric readings remain NULL.

This roadmap tracks verification and release work, not already completed foundation features.

## Remaining priorities

1. **Real hardware validation:** exercise thermal and fan sensors, SMART/NVMe, and GPU telemetry on representative Windows, Linux, and macOS machines. Record exact hardware, OS, driver, permissions, and collector outcomes.
2. **Hardware coverage:** expand GPU vendor and multi-device support only where a reliable vendor or OS interface exists. The current NVIDIA collector queries a selected device index and defaults to GPU 0. Do not infer telemetry for unsupported vendors.
3. **Storage compatibility:** validate ATA/NVMe output variations, RAID and USB bridge pass-through, permission behavior, and unknown SMART attributes using real devices.
4. **Gaming evidence:** validate process matching and lifecycle under real multi-process games. Improve GPU association and session timelines where the available OS interfaces provide reliable identifiers. FPS/frame-time remain unavailable without a supported source.
5. **Diagnostic correlation:** validate baseline sufficiency and process/system/thermal/network time alignment with longer real-world captures. Keep correlation distinct from causation.
6. **Network validation:** test local gateway, DNS, HTTP, packet loss, and route behavior across real network environments, including filtered ICMP and IPv6.
7. **UI and architecture:** continue focused decomposition only where it improves ownership or testability. Validate responsiveness, accessibility, and long-running memory use on desktop systems.
8. **Release engineering:** build and smoke-test platform-specific packages, verify upgrade/uninstall behavior, and complete dependency/license review.

## Automated verification

GitHub Actions is the source of truth for supported CI combinations. The workflow tests Windows, macOS, and Ubuntu with Python 3.11 and 3.12, compiles source and tests, builds distributions, and runs pytest. A passing CI job validates automated behavior, not physical sensor or controller support.

## Non-negotiable principles

- No cloud requirement or account.
- No fabricated confidence score, arbitrary hypothesis score, or causal claim.
- No global hardcoded performance or temperature thresholds presented as universal.
- Missing telemetry is explicitly unavailable.
- Collectors are read-only and isolated from the UI thread.
- User-selected process monitoring only; no game injection or anti-cheat bypass.
