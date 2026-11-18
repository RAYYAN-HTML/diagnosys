# Diagnosys roadmap

## Current direction

Diagnosys is an evidence-first, deterministic, local-first diagnostic application. It uses real measurements, personal baselines, and hardware-reported limits. It does not use external generated explanations or assign unsupported probabilities.

## Priorities

1. Finish decomposing the remaining orchestration and dialogs in the desktop main window.
2. Improve process-to-system correlation and historical performance comparisons.
3. Expand SMART/NVMe parsing and device/controller compatibility with read-only queries.
4. Improve thermal sensor mapping and corroboration with clock and utilization history without inferring throttling from temperature alone.
5. Investigate additional vendor telemetry only where the source is reliable and transparent. Do not infer FPS or frame-time from CPU/GPU utilization.
6. Improve personal baselines with clear sample sufficiency and historical context.
7. Improve gateway, DNS, destination comparison, and route analysis without assuming a failed ping proves an ISP fault.
8. Package installers and verify supported platforms.

## Non-negotiable principles

- No cloud requirement or account.
- No fabricated confidence score, arbitrary hypothesis score, or causal claim.
- No global hardcoded performance or temperature thresholds presented as universal.
- Missing telemetry is explicitly unavailable.
- Collectors are read-only and isolated from the UI thread.
- User-selected process monitoring only; no game injection or anti-cheat bypass.
