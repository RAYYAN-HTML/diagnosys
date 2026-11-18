# Diagnosys roadmap

## Current direction

Diagnosys is an evidence-first, deterministic, local-first diagnostic application. It must not invent confidence percentages, probability scores, or universal performance cutoffs.

## Priorities

1. Complete the redesigned desktop experience with clear navigation, accessible charts, a unified timeline, and focused investigation views.
2. Integrate thermal readings, fan telemetry, SMART/NVMe health, and per-process game-session data into the dashboard and incident timeline.
3. Expand per-process resource attribution and correlate process activity with system and network measurements.
4. Add optional frame-time/FPS collection through a dedicated, transparent telemetry provider. Do not infer FPS from CPU/GPU utilization.
5. Improve personal baselines with robust statistics, seasonality-aware windows, and clear data sufficiency indicators.
6. Add gateway, DNS, destination comparison, and route analysis without assuming that a failed ping proves an ISP fault.
7. Add guided, reversible remediation with explicit confirmation and post-change verification.
8. Package signed installers and verify supported platforms.

## Non-negotiable principles

- No cloud requirement or account.
- No AI dependency in the diagnostic path.
- No fabricated confidence score or causal claim.
- No global hardcoded thresholds for performance diagnosis.
- Missing telemetry is explicitly unavailable.
- Collectors are read-only and isolated from the UI thread.
- User-selected process monitoring only; no game injection or anti-cheat bypass.
