# Desktop packaging

Builds must run on the operating system they target. PyInstaller does not
cross-compile Windows and Linux executables.

## Windows

From PowerShell at the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m pip install pyinstaller
./scripts/build_windows.ps1
```

The app and its Qt DLLs are written to `dist/Diagnosys/`. Distribute the whole
folder or package it in an installer; do not distribute only the executable.

## Linux

Create a Linux environment and install the project plus PyInstaller there, then
build `src/diagnosys/__main__.py` with the `src` search path and include
`src/diagnosys/ui/theme/theme.qss` as package data. Build on the oldest Linux
distribution you intend to support so the bundled native libraries remain
compatible.
