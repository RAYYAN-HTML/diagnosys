import time
import logging
from datetime import datetime, timezone
import argparse

from diagnosys.storage.database import get_connection, init_db, prune_db
from diagnosys.storage.repositories import MetricRepository, AnomalyRepository
from diagnosys.diagnostics.rules import AnomalyDetector

from diagnosys.collectors.system.cpu import CPUCollector
from diagnosys.collectors.system.memory import MemoryCollector
from diagnosys.collectors.system.disk import DiskCollector
from diagnosys.models.metrics import MetricSample, MetricStatus

logger = logging.getLogger(__name__)

class MonitoringEngine:
    def __init__(self, interval_seconds: int = 10):
        self.interval_seconds = interval_seconds
        self.running = False
        
        self.cpu_collector = CPUCollector()
        self.mem_collector = MemoryCollector()
        self.disk_collector = DiskCollector()
        
    def start(self):
        logger.info(f"Starting monitoring engine (interval={self.interval_seconds}s). Press Ctrl+C to stop.")
        self.running = True
        
        conn = get_connection()
        init_db(conn)
        repo = MetricRepository(conn)
        from diagnosys.storage.repositories import AnomalyRepository
        from diagnosys.diagnostics.rules import AnomalyDetector
        anomaly_repo = AnomalyRepository(conn)
        detector = AnomalyDetector()
        
        try:
            while self.running:
                loop_start = time.time()
                
                # Prune old data periodically
                prune_db(conn)
                
                self._collect_and_store(repo, anomaly_repo, detector)
                
                elapsed = time.time() - loop_start
                sleep_time = max(0, self.interval_seconds - elapsed)
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            logger.info("Monitoring engine stopped gracefully.")
        finally:
            conn.close()
            
    def _collect_and_store(self, repo: MetricRepository, anomaly_repo: AnomalyRepository, detector: AnomalyDetector):
        ts = datetime.now(timezone.utc)
        
        def _process(sample: MetricSample):
            repo.save(sample)
            if sample.status == MetricStatus.OK:
                for anomaly in detector.evaluate_sample(sample):
                    anomaly_repo.save(anomaly)

        # CPU
        try:
            cpu = self.cpu_collector.collect()
            _process(MetricSample(
                timestamp=ts, metric_name="cpu_percent", value=cpu.utilization_percent,
                unit="%", source="system", status=MetricStatus.OK if cpu.available else MetricStatus.UNAVAILABLE,
                reason=cpu.reason
            ))
        except Exception as e:
            logger.error(f"CPU collection failed: {e}")
            
        # Memory
        try:
            mem = self.mem_collector.collect()
            _process(MetricSample(
                timestamp=ts, metric_name="memory_percent", value=mem.percent_used,
                unit="%", source="system", status=MetricStatus.OK if mem.available else MetricStatus.UNAVAILABLE,
                reason=mem.reason
            ))
        except Exception as e:
            logger.error(f"Memory collection failed: {e}")
            
        # Disk
        try:
            disk = self.disk_collector.collect()
            _process(MetricSample(
                timestamp=ts, metric_name="disk_percent", value=disk.percent_used,
                unit="%", source="system", status=MetricStatus.OK if disk.available else MetricStatus.UNAVAILABLE,
                reason=disk.reason
            ))
        except Exception as e:
            logger.error(f"Disk collection failed: {e}")

def handle_monitor(args: argparse.Namespace) -> int:
    engine = MonitoringEngine(interval_seconds=args.interval)
    engine.start()
    return 0
