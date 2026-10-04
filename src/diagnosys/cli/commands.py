import argparse
from datetime import datetime, timezone
import json
import dataclasses

from diagnosys.models.metrics import SystemSnapshot
from diagnosys.collectors.system.cpu import CPUCollector
from diagnosys.collectors.system.memory import MemoryCollector
from diagnosys.collectors.system.disk import DiskCollector
from diagnosys.collectors.system.uptime import UptimeCollector

_disk_collector = DiskCollector()

def bytes_to_gb(b: int) -> float:
    return b / (1024**3)

def handle_status(args: argparse.Namespace) -> int:
    cpu = CPUCollector().collect()
    memory = MemoryCollector().collect()
    disk = _disk_collector.collect()
    uptime = UptimeCollector().collect()
    
    snapshot = SystemSnapshot(
        timestamp=datetime.now(timezone.utc),
        cpu=cpu,
        memory=memory,
        disk=disk,
        uptime_seconds=uptime
    )
    
    if args.json:
        # Convert to dictionary and handle datetime serialization
        def default_serializer(o):
            if isinstance(o, datetime):
                return o.isoformat()
            return str(o)
            
        print(json.dumps(dataclasses.asdict(snapshot), default=default_serializer, indent=2))
    else:
        print("DIAGNOSYS STATUS")
        print("-----------------------------")
        
        # Uptime
        hours, remainder = divmod(int(uptime), 3600)
        minutes, seconds = divmod(remainder, 60)
        print(f"Uptime: {hours}h {minutes}m {seconds}s")
        print("")
        
        # CPU
        print("CPU:")
        if cpu.available:
            print(f"  Utilization: {cpu.utilization_percent}%")
            print(f"  Per-core:    {', '.join(f'{c}%' for c in cpu.per_core_utilization_percent)}")
            if cpu.frequency_mhz:
                print(f"  Frequency:   {cpu.frequency_mhz:.0f} MHz")
            if cpu.load_average:
                print(f"  Load Avg:    {cpu.load_average[0]:.2f}, {cpu.load_average[1]:.2f}, {cpu.load_average[2]:.2f}")
        else:
            print(f"  Unavailable ({cpu.reason})")
        print("")
        
        # Memory
        print("Memory:")
        if memory.available:
            print(f"  Total:       {bytes_to_gb(memory.total_bytes):.1f} GB")
            print(f"  Used:        {bytes_to_gb(memory.used_bytes):.1f} GB ({memory.percent_used}%)")
            print(f"  Available:   {bytes_to_gb(memory.available_bytes):.1f} GB")
            if memory.swap_percent is not None:
                print(f"  Swap Used:   {memory.swap_percent}%")
        else:
            print(f"  Unavailable ({memory.reason})")
        print("")
        
        # Disk
        print("Disk (Primary):")
        if disk.available:
            print(f"  Total:       {bytes_to_gb(disk.total_bytes):.1f} GB")
            print(f"  Free:        {bytes_to_gb(disk.free_bytes):.1f} GB")
            print(f"  Used:        {disk.percent_used}%")
            if disk.busy_percent is not None:
                print(f"  Busy:        {disk.busy_percent:.1f}%")
        else:
            print(f"  Unavailable ({disk.reason})")
        
    return 0

def handle_processes(args: argparse.Namespace) -> int:
    from diagnosys.collectors.system.process import ProcessCollector
    
    snapshot = ProcessCollector().collect()
    
    if args.json:
        def default_serializer(o):
            if isinstance(o, datetime):
                return o.isoformat()
            return str(o)
            
        print(json.dumps(dataclasses.asdict(snapshot), default=default_serializer, indent=2))
    else:
        print("DIAGNOSYS PROCESSES")
        print("-----------------------------")
        
        if not snapshot.available:
            print(f"Unavailable: {snapshot.reason}")
            return 1
            
        print(f"Total Processes: {snapshot.process_count}")
        print("")
        
        print("Top CPU Consumers:")
        for i, p in enumerate(snapshot.top_cpu, 1):
            user = p.username or "unknown"
            print(f"  {i}. [{p.pid}] {p.name} ({user}) - {p.cpu_percent:.1f}%")
            
        print("")
        print("Top Memory Consumers:")
        for i, p in enumerate(snapshot.top_memory, 1):
            user = p.username or "unknown"
            print(f"  {i}. [{p.pid}] {p.name} ({user}) - {p.memory_percent:.1f}%")
            
    return 0

def handle_network(args: argparse.Namespace) -> int:
    from diagnosys.collectors.network.ping import PingCollector
    from diagnosys.collectors.network.dns import DNSCollector
    from diagnosys.collectors.network.http import HTTPCollector
    from diagnosys.models.network import NetworkSnapshot
    
    ping = PingCollector(target="8.8.8.8").collect()
    dns = DNSCollector(target="google.com").collect()
    http = HTTPCollector().collect()
    
    snapshot = NetworkSnapshot(
        timestamp=datetime.now(timezone.utc),
        ping=ping,
        dns=dns,
        http=http
    )
    
    if args.json:
        def default_serializer(o):
            if isinstance(o, datetime):
                return o.isoformat()
            return str(o)
            
        print(json.dumps(dataclasses.asdict(snapshot), default=default_serializer, indent=2))
    else:
        print("DIAGNOSYS NETWORK")
        print("-----------------------------")
        
        # Ping
        print(f"Ping ({ping.target}):")
        if ping.available:
            if ping.min_ms is not None:
                print(f"  Min:    {ping.min_ms:.1f} ms")
                print(f"  Median: {ping.median_ms:.1f} ms")
                print(f"  p95:    {ping.p95_ms:.1f} ms")
                print(f"  Max:    {ping.max_ms:.1f} ms")
                print(f"  Jitter: {ping.jitter_ms:.1f} ms")
            print(f"  Loss:   {ping.packet_loss_percent:.1f}%")
            if ping.reason:
                print(f"  Note:   {ping.reason}")
        else:
            print(f"  Unavailable ({ping.reason})")
        print("")
        
        # DNS
        print(f"DNS ({dns.target}):")
        if dns.success:
            print(f"  Latency: {dns.latency_ms:.1f} ms")
        elif dns.timeout:
            print("  Timeout")
        else:
            print(f"  Failed:  {dns.reason}")
        print("")
        
        # HTTP
        print(f"HTTP ({http.target}):")
        if http.success:
            print(f"  Latency: {http.latency_ms:.1f} ms")
            print(f"  Status:  {http.status_code}")
        elif http.timeout:
            print("  Timeout")
        else:
            print(f"  Failed:  {http.reason}")
            
    return 0

def handle_history(args: argparse.Namespace) -> int:
    from diagnosys.storage.database import get_connection, init_db, prune_db
    from diagnosys.storage.repositories import MetricRepository, AnomalyRepository
    
    conn = get_connection()
    init_db(conn)
    prune_db(conn)
    
    metric_repo = MetricRepository(conn)
    anomaly_repo = AnomalyRepository(conn)
    
    metrics = metric_repo.query(window_seconds=args.window)
    anomalies = anomaly_repo.query(window_seconds=args.window)
    
    print("DIAGNOSYS HISTORY")
    print("-----------------------------")
    print(f"Time window: last {args.window} seconds")
    print(f"Metrics collected: {len(metrics)}")
    print(f"Anomalies detected: {len(anomalies)}")
    
    if anomalies:
        print("\nRecent Anomalies:")
        for idx, a in enumerate(anomalies[:10], 1):
            print(f"  {idx}. [{a.timestamp.strftime('%H:%M:%S')}] {a.severity} {a.category} - {a.explanation}")
        
        if len(anomalies) > 10:
            print(f"  ... and {len(anomalies) - 10} more")
            
    return 0

def handle_diagnose(args: argparse.Namespace) -> int:
    from diagnosys.storage.database import get_connection, init_db
    from diagnosys.storage.repositories import AnomalyRepository
    from diagnosys.diagnostics.engine import DiagnosticEngine
    
    conn = get_connection()
    init_db(conn)
    anomaly_repo = AnomalyRepository(conn)
    
    anomalies = anomaly_repo.query(window_seconds=args.window)
    engine = DiagnosticEngine()
    
    result = engine.diagnose(anomalies, window_seconds=args.window)
    
    print("DIAGNOSYS")
    print("-----------------------------")
    print(f"\nStatus: {result.status}\n")
    
    if result.primary_hypothesis:
        h = result.primary_hypothesis
        print("Most likely cause:")
        print(h.category.replace("_", " ").title())
        print("")
        
        if h.evidence:
            print("Evidence:")
            for e in h.evidence:
                print(f"• {e.metric}: {e.observed_value}")
            print("")
        else:
            print("Evidence: No direct anomalies recorded.")
            print("")
            
        print(f"Confidence: {h.confidence}")
        print("")
        
        if h.recommended_checks:
            print("Recommended next checks:")
            for i, check in enumerate(h.recommended_checks, 1):
                print(f"{i}. {check}")
                
    return 0

def setup_commands(parser: argparse.ArgumentParser) -> None:
    """Setup subparsers for the CLI commands."""
    subparsers = parser.add_subparsers(title="Commands", dest="command")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show current system and network status")
    status_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    status_parser.set_defaults(func=handle_status)
    
    # Processes command
    processes_parser = subparsers.add_parser("processes", help="Show top running processes")
    processes_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    processes_parser.set_defaults(func=handle_processes)
    
    # Network command
    network_parser = subparsers.add_parser("network", help="Show network health metrics")
    network_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    network_parser.set_defaults(func=handle_network)

    # History command
    history_parser = subparsers.add_parser("history", help="Show recent historical metrics and anomalies")
    history_parser.add_argument("--window", type=int, default=3600, help="Window in seconds (default 3600)")
    history_parser.set_defaults(func=handle_history)
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Start continuous monitoring engine")
    monitor_parser.add_argument("--interval", type=int, default=10, help="Sampling interval in seconds (default 10)")
    from diagnosys.core.monitor import handle_monitor
    monitor_parser.set_defaults(func=handle_monitor)
    
    # Diagnose command
    diagnose_parser = subparsers.add_parser("diagnose", help="Run the diagnostic engine")
    diagnose_parser.add_argument("--window", type=int, default=3600, help="Window in seconds (default 3600)")
    diagnose_parser.set_defaults(func=handle_diagnose)
