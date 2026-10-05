# Diagnosys

Diagnosys is a local-first PC and Internet health diagnostic agent designed to answer the eternal question: *"Why does my computer feel slow right now?"*

Rather than relying on black-box external services, Diagnosys continuously (or on-demand) collects measurable system and network signals, detects anomalies, correlates events over time, ranks likely causes, and explains the result using deterministic, transparent evidence. 

All data remains completely local to your machine. 

## Features (MVP)

- **System Diagnostics**: Instantly captures CPU utilization, per-core metrics, Memory pressure, Disk I/O, and uptime.
- **Process Intelligence**: Identifies top CPU and Memory consumers gracefully without requiring root/administrator privileges.
- **Network Health**: Natively tests packet loss, jitter, DNS latency, and HTTP response times.
- **Persistent Monitoring**: A lightweight background engine (`diagnosys monitor`) collects metrics and records them directly into a local SQLite database with automatic retention pruning.
- **Anomaly Detection**: Deterministic rules parse system snapshots to automatically flag anomalies (e.g., `CPU_PRESSURE`, `NETWORK_INSTABILITY`).
- **Diagnostic Engine**: The correlation engine (`diagnosys diagnose`) examines recent history to provide a clear, ranked hypothesis with supporting evidence and recommended next steps.

## Installation

Diagnosys is built for Python 3.11+.

```bash
# Clone the repository
git clone https://github.com/RAYYAN-HTML/diagnosys.git
cd diagnosys

# Create a virtual environment
python -m venv venv
# Windows: venv\Scripts\activate
# Unix/MacOS: source venv/bin/activate

# Install the package 
pip install -e .
```

## Usage

Diagnosys operates exclusively through a clean, unified CLI.

### 1. Instant Snapshots
Quickly see what is happening right now:
```bash
diagnosys status     # View CPU, Memory, Disk, and Uptime
diagnosys processes  # View top process consumers
diagnosys network    # Check ping, packet loss, DNS, and HTTP health
```
*(All commands support a `--json` flag for integration with other tools)*

### 2. Continuous Monitoring
Start the background daemon to build a historical baseline (press `Ctrl+C` to stop):
```bash
diagnosys monitor --interval 10
```

### 3. Diagnosis & History
When your PC feels slow, review the recent historical anomalies and ask the diagnostic engine to correlate them:
```bash
# View the raw historical record
diagnosys history --window 3600

# Get a ranked diagnostic hypothesis based on recent anomalies
diagnosys diagnose --window 3600
```

## Privacy & Architecture

**Local First:** Diagnosys is explicitly designed to protect your privacy. There is no telemetry, no cloud backend, and no data leaves your machine. Your SQLite database is stored locally in your OS's standard AppData directory (handled safely via `platformdirs`).

**Deterministic Rules:** While AI explanation layers are planned for the future, the core diagnostic engine operates on 100% deterministic, transparent Python code (see `src/diagnosys/diagnostics/rules.py`).

## License

This project is licensed under the MIT License.
