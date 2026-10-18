"""Best-effort, read-only collection of recent Windows reliability events."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess


def recent_system_events(minutes: int = 10, limit: int = 30) -> dict:
    """Return selected Windows system events, or a clear unavailable result."""
    if platform.system().lower() != "windows":
        return {"available": False, "reason": "System event correlation is currently available on Windows only.", "events": []}
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return {"available": False, "reason": "PowerShell is unavailable; Windows event log access was skipped.", "events": []}

    bounded_minutes = max(1, min(int(minutes), 1440))
    bounded_limit = max(1, min(int(limit), 100))
    script = (
        f"$start=(Get-Date).AddMinutes(-{bounded_minutes}); "
        "$systemIds=@(41,6008,7031,7023,19,20,21,22); $appIds=@(1000,1001,1026,1033,1034,11707,11724); "
        f"$system=@(Get-WinEvent -FilterHashtable @{{LogName='System';StartTime=$start;Id=$systemIds}} -MaxEvents {bounded_limit} -ErrorAction SilentlyContinue); "
        f"$application=@(Get-WinEvent -FilterHashtable @{{LogName='Application';StartTime=$start;Id=$appIds}} -MaxEvents {bounded_limit} -ErrorAction SilentlyContinue); "
        "$events=@($system+$application | ForEach-Object { "
        "[pscustomobject]@{time=$_.TimeCreated.ToUniversalTime().ToString('o');Id=$_.Id;log=$_.LogName;source=$_.ProviderName;level=$_.LevelDisplayName; "
        "message=$(if ($_.Message) {$m=$_.Message -replace '[\\r\\n]+',' '; $m.Substring(0,[Math]::Min(400,$m.Length))} else {''})} "
        "} | Sort-Object time -Descending | Select-Object -First " + str(bounded_limit) + "); "
        "$events | ConvertTo-Json -Compress -Depth 3"
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=10, check=False, errors="replace",
        )
        if result.returncode != 0:
            return {"available": False, "reason": "Windows event log access was denied or unavailable.", "events": []}
        output = result.stdout.strip()
        events = json.loads(output) if output else []
        if isinstance(events, dict):
            events = [events]
        return {"available": True, "events": events[:bounded_limit]}
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "Windows event lookup exceeded its 10 second limit.", "events": []}
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"Windows event lookup failed: {exc}", "events": []}
