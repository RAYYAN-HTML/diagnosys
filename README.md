# Diagnosys

Diagnosys is a free, local-first desktop app that helps you investigate PC slowdowns, game stutter, overheating, crashes, and internet problems.

## What you can do

- Capture a problem while you use your PC, with notes and recent system history.
- Review performance, process, network, and available Windows event evidence.
- Compare readings before and after a change, then record whether it helped.
- Keep investigation history on your device and export a redacted support report.

## Run from source

Requires Python 3.11 or later and a desktop environment.

```bash
python -m venv .venv
```

Install and launch on Windows:

```powershell
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m diagnosys
```

Install and launch on Linux:

```bash
.venv/bin/python -m pip install -e .
.venv/bin/python -m diagnosys
```

## Privacy

Measurements and incident history stay in a local database. Diagnosys does not require an account or upload your history. Network checks contact their configured test targets. Available sensors and Windows event details vary by system.

See [privacy details](docs/privacy.md), [contributing](CONTRIBUTING.md), and the [documentation index](docs/README.md).
