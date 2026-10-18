# Project structure

```text
Diagnosys/
├── src/diagnosys/
│   ├── __main__.py          Python module entry point
│   ├── gui.py               Desktop application startup
│   ├── ui/                   Main window, widgets, and theme
│   ├── collectors/           System and network measurements
│   ├── diagnostics/          Rules and evidence-led investigations
│   ├── correlation/          Time-window relationships
│   ├── storage/              SQLite schema and repositories
│   ├── reports/              Report generation and export
│   ├── models/               Measurement and result models
│   ├── config/               Runtime settings
│   ├── core/                 Runtime capability discovery
│   └── ai/                   Optional provider interface
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   ├── development/           Architecture and engineering references
│   └── project/               Planning and maintainer material
├── packaging/windows/         Windows PyInstaller configuration
├── scripts/                   Build helpers
├── CONTRIBUTING.md
├── README.md
└── pyproject.toml
```

`python -m diagnosys` and the installed `diagnosys` command launch the desktop
interface. Keep collection and diagnosis logic in service modules so the UI
remains an interface over reusable application logic.

Build the Windows folder package from the repository root with
`./scripts/build_windows.ps1`. It writes to `dist/Diagnosys/`.
