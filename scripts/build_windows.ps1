$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pyinstaller = Join-Path $repoRoot ".venv\Scripts\pyinstaller.exe"
$specFile = Join-Path $repoRoot "packaging\windows\Diagnosys.spec"

if (-not (Test-Path -LiteralPath $pyinstaller)) {
    throw "PyInstaller not found. Create .venv, install the project, then install PyInstaller."
}

Push-Location $repoRoot
try {
    & $pyinstaller --noconfirm $specFile
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

Write-Output "Build created at dist\Diagnosys\Diagnosys.exe"
