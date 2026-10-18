# Diagnosys Metrics

## CPU

- utilization_percent
- per_core_utilization_percent
- frequency_mhz where available
- load_average where available

## Memory

- total_bytes
- used_bytes
- available_bytes
- percent_used
- swap_percent where available

## Disk

- total_bytes
- free_bytes
- percent_used
- read_bytes_per_sec
- write_bytes_per_sec
- busy_percent where supported

## Processes

- process_count
- process_cpu_percent
- process_memory_percent
- top_cpu_processes
- top_memory_processes

Persist only the process identity information needed for diagnostics.

## Network

### Ping

Collect repeated samples and calculate:
- min
- median
- p95
- max

### Packet loss

```text
failed_probes / total_probes
```

### Jitter

Pick one documented calculation and use it consistently.

### DNS

Collect:
- target hostname
- response time
- success/failure
- timeout

### HTTP

Collect:
- target
- latency
- status code
- timeout/failure

Do not store response bodies by default.

### Throughput

Optional and explicit because it consumes bandwidth.

## Sample metadata

Every measurement should contain:

```text
timestamp
metric
value
unit
source
status
optional entity/interface/target
```

## Unsupported metrics

Use an explicit unavailable state:

```text
available = false
reason = "unsupported_on_platform"
```

Never fabricate data.
