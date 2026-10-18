# Diagnosys roadmap

## Available now

- Problem-first home and guided symptom selection for slow PCs, game stutter, internet trouble, crashes, and overheating.
- Native desktop dashboard for CPU, memory, disk, processes, uptime, and network activity.
- On-demand ping, packet-loss, jitter, DNS, and HTTP checks.
- Local SQLite history with configurable retention for measurements and anomalies.
- Deterministic anomaly detection and ranked diagnosis with supporting evidence and limitations.
- Persistent investigation capture with pre-capture history, user notes, resource and process timelines, Windows reliability events, ranked evidence, and symptom-specific next checks.
- One-minute after-change comparisons, user-reported resolution tracking, local evidence questions, and redacted incident support bundles.
- Saved incident bookmarks, runtime capability details, and Markdown/JSON report export.
- Optional GPU and CPU-temperature readings when the machine exposes them.
- Opt-in tray monitoring while the app window is closed.

## Next priorities

1. Make investigation timelines interactive, searchable, and filterable by symptom, process, and measurement.
2. Add per-application session focus and deeper Windows change history for installs, drivers, startup items, and updates.
3. Expand platform-specific sensors and network comparisons while keeping unavailable readings explicit.
4. Add guided, reversible remediation with a clear preview and post-change verification; keep all system changes opt-in.
5. Package signed installers and verify the app on Windows, macOS, and Linux.

## Longer term

- Broader GPU, thermal, battery, and disk-health coverage where supported.
- Route and hop-by-hop network diagnostics.
- Background service mode with startup controls and resource-aware sampling.
- Per-application history and resource/network correlation, including game frame-time capture where supported.
- Optional notifications and integrations with explicit user control.
- Optional local or hosted AI explanations that use only the selected structured evidence.

All future work should preserve local-first storage, transparent rules, graceful handling of unavailable sensors, and the distinction between correlation and causation.
