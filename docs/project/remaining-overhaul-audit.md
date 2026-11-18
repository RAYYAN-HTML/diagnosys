# Remaining overhaul audit and implementation plan

Base: `master` at `4e1115d3b18d5a4aefdb83288346e6aa135880cc`.

## Audit findings

This audit is based on the merged source tree and targeted reads of the UI, collectors, diagnostics, storage, project metadata, and tests.

### Existing foundation

- The application is a PySide6 desktop app with SQLite persistence and a background task router.
- CPU, memory, disk activity, GPU, network, process, uptime, investigations, incident capture, reports, and personal baselines already have working code paths.
- Thermal, SMART/NVMe, and game-process collectors exist as standalone modules.
- The README accurately states important limitations such as missing FPS/frame-time telemetry and hardware-dependent sensor availability.
- The diagnostic engine is intended to be deterministic and local-first.

### Confirmed gaps

1. `src/diagnosys/ui/main_window.py` is 2,652 lines (about 137 KB) and owns navigation, page construction, task orchestration, collection, persistence, diagnosis, investigations, reports, and export flows.
2. Navigation now includes Performance, Processes, Thermal, Disk Health, and Gaming pages in addition to the original pages.
3. The main refresh path now collects thermal readings, configured game-process samples, and periodic SMART discovery/health results in background tasks.
4. Thermal samples and GPU temperature are persisted with freshness shown in the UI. Hardware-reported high/critical limits drive deterministic sustained thermal findings.
5. SMART discovery and health queries now expose missing-tool, timeout, permission, unsupported-device, unknown-health, and explicit warning states.
6. Gaming sessions now track observed process start/end, CPU, memory, threads, disk I/O, and contemporaneous system CPU/GPU context. FPS and frame-time remain unavailable.
7. SQLite schema versions now include thermal samples, disk health history, gaming sessions, and process start/thread fields. Repositories own the corresponding persistence.
8. Generic CPU/memory/disk/network cutoff hypotheses and UI utilization color cutoffs were removed. Personal-baseline and hardware-reported-limit rules remain.
9. Original page builders have been moved into individual page modules. Task routing and pure report/metric formatters are also extracted. `main_window.py` is now approximately 1,300 lines. Page construction, background task routing, investigation workflows, network workflows, report workflows, and pure formatters have been extracted. Remaining telemetry/history coordination still needs review.
10. Added mocked collector, storage, diagnostic, formatter, and page-unavailable tests. CI has been enabled for feature-branch pushes; full cross-platform results remain to be confirmed.

## Progress on this branch

- Completed initial integration of Thermal, Disk Health, Gaming, and Processes pages.
- Added SQLite migrations through schema version 7.
- Added hardware-specific thermal findings and removed generic investigation pressure cutoffs.
- Added SMART discovery with read-only queries and explicit failure states.
- Added opt-in gaming process configuration and session history.
- Extracted Overview, Network, Diagnostics, History, Capabilities, and Settings page builders into separate modules.
- Extracted Qt background task routing, investigation/network/report controllers, and pure report/metric formatters.
- Added hardware compatibility documentation and expanded mocked tests.
- Current main window is approximately 2,088 lines and still needs additional service/controller extraction.

## Implementation plan

Work on the feature branch `complete-overhaul`. Keep `master` unchanged.

### Phase 1: Connect missing telemetry end to end
- Add safe SMART device discovery and explicit result states.
- Add thermal, disk-health, and gaming session services.
- Persist timestamped observations through versioned SQLite migrations and repositories.
- Connect collectors to the background task orchestration, not the Qt UI thread.
- Add focused tests with mocked psutil and smartctl behavior.

### Phase 2: Introduce page modules
- Extract reusable page widgets for Thermal, Disk Health, Gaming, Performance, and Processes.
- Keep `MainWindow` as shell/navigation and application coordinator.
- Move page-specific rendering and interaction into separate modules.
- Preserve current Home, Network, Investigate, History, Capabilities, and Settings behavior.

### Phase 3: Evidence and dashboard improvements
- Add current telemetry availability/freshness and relevant trends to the overview.
- Correlate process activity with resource and investigation timelines.
- Replace remaining universal cutoffs only where evidence-based alternatives are available; document limitations where hardware-specific interpretation is not possible.
- Keep all findings traceable to observations and deterministic rules.

### Phase 4: Verification and documentation
- Run the full test suite, formatting, linting, and type checks that are configured.
- Add tests for schema upgrades, unsupported hardware, missing permissions, and UI integration.
- Verify startup and navigation in a desktop environment where available.
- Update README, architecture, compatibility, and known-limitations documentation.
- Open a pull request to `master`; do not merge without review.

## Completion standard

A feature is not complete merely because a collector or page exists. Collection, background execution, persistence, diagnostics, user-facing availability/error states, tests, and documentation must be connected. No FPS, health percentage, diagnosis confidence, or unsupported sensor value may be invented.


## Follow-up implementation updates

- Extracted the six original page builders into `ui/pages/` modules and added dedicated Thermal, Disk Health, Gaming, Processes, and Performance pages.
- Added process lifecycle fields (start time and thread count) to collection and SQLite history, with a versioned migration.
- Added explicit historical process lifetime display and tests for missing process I/O data.
- SMART media errors and reallocated sectors now produce a warning state even when the drive's overall SMART self-test still reports passed.
- SQLite metric values now allow NULL. Unavailable CPU, memory, and disk samples are stored as NULL rather than fabricated zero values, with migration 9 preserving existing metric records and indexes.
- The remaining large UI responsibility is the main-window telemetry and application coordination path. Further extraction and a full live-window smoke test remain outstanding.
- GitHub Actions on intermediate commits exposed a legacy-schema test expectation that still expected schema version 8. The test has been updated to version 9 and expanded to verify preservation of legacy metric data; the latest workflow result is still pending.

- Removed the keyword-matched "Ask this capture" response feature. It presented a few fixed string-matching branches as if they were conversational answers; the investigation now exposes its deterministic findings, evidence, timelines, and explicit next checks directly instead.
- Extracted telemetry refresh, persistence, dashboard updates, and deterministic diagnosis into `ui/controllers/monitoring.py`. The main window is now primarily the application shell and workflow wiring, although some incident/history presentation remains to be separated.
- Further split monitoring and diagnosis into `ui/controllers/monitoring.py`, and history, incident evidence, and capabilities into `ui/controllers/history.py`. The desktop shell is now approximately 760 lines rather than the original 2,652-line module; settings, tray lifecycle, task routing, and some UI coordination remain in the shell.
