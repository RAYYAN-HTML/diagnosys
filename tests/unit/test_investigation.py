from diagnosys.diagnostics.investigation import InvestigationEngine


def test_process_peaks_preserve_thread_and_start_time_evidence():
    rows = [
        {
            "process_name": "game.exe", "cpu_percent": 85.0, "memory_percent": 20.0,
            "thread_count": 32, "create_time": 1700000000.0,
            "read_bytes_per_sec": 4096.0, "write_bytes_per_sec": 1024.0,
            "network_connection_count": 4,
        },
        {
            "process_name": "game.exe", "cpu_percent": 90.0, "memory_percent": 25.0,
            "thread_count": 40, "create_time": 1700000000.0,
            "read_bytes_per_sec": 8192.0, "write_bytes_per_sec": 2048.0,
            "network_connection_count": 5,
        },
    ]
    peaks = InvestigationEngine._process_peaks(rows)
    assert len(peaks) == 1
    assert peaks[0]["peak_cpu_percent"] == 90.0
    assert peaks[0]["peak_thread_count"] == 40
    assert peaks[0]["create_time"] == 1700000000.0
    assert peaks[0]["peak_read_bytes_per_sec"] == 8192.0


def test_hypotheses_do_not_invent_resource_pressure_without_evidence():
    hypotheses = InvestigationEngine._hypotheses({}, {}, [], [])
    assert hypotheses == []
