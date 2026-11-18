# Project structure

```text
src/diagnosys/
├── gui.py
├── __main__.py
├── ui/
│   ├── main_window.py
│   ├── components.py
│   ├── pages/
│   │   ├── overview.py
│   │   ├── network.py
│   │   ├── diagnostics.py
│   │   ├── history.py
│   │   ├── capabilities.py
│   │   ├── settings.py
│   │   ├── thermal.py
│   │   ├── disk_health.py
│   │   ├── gaming.py
│   │   └── processes.py
│   ├── controllers/         Investigation, network, and report workflows
│   ├── tasks.py             Background Qt task routing
│   ├── formatters.py        Pure report and metric formatting
│   └── theme/
├── core/                 Capability discovery
├── models/               Typed measurements and diagnostic data
├── config/               Settings and logging
├── collectors/
│   ├── system/           CPU, memory, disk, GPU, thermal, SMART, processes, gaming
│   └── network/          Network probes and interface telemetry
├── diagnostics/          Deterministic rules and investigations
├── correlation/          Time-window evidence correlation
├── storage/              SQLite schema, migrations, repositories
└── reports/              Text, Markdown, JSON and HTML report output

tests/
├── unit/
└── integration/

docs/
├── development/
└── project/
```

Keep UI presentation, collection, persistence, and diagnostic reasoning in their respective layers. Optional hardware support must degrade gracefully and must never be represented by invented measurements.
