# Telemetry features

## Thermal

Thermal sampling reads temperatures and fan speeds only where the operating system or supported vendor utility exposes them. Sensor identity, current reading, hardware-provided high/critical limits, freshness, and history are shown. GPU temperature is added to thermal history when the NVIDIA collector returns a value.

A sustained thermal warning requires at least three readings spanning 20 seconds at or above a sensor-reported high limit. A critical finding is raised when a sample reaches a sensor-reported critical limit. If no hardware limit is exposed, Diagnosys shows the temperature without inventing a warning threshold.

Concurrent CPU/GPU utilization and CPU frequency are included as context. The diagnostic compares recent clock/utilization readings with the preceding window, but does not claim that temperature caused throttling or performance loss.

## Disk health

Disk discovery and SMART/NVMe queries use optional smartmontools. All commands are read-only. The page distinguishes tool missing, no queryable devices, unsupported devices, permission errors, query errors, unknown health, and explicit warnings. It displays returned temperature, wear indicator, power-on hours, available spare, media errors, critical warning, and reallocated-sector information where present.

No health percentage or failure prediction is generated. A missing SMART result is unknown, not healthy.

## Gaming

Users configure executable process names in Settings. Diagnosys samples matching process CPU, memory, threads, and disk I/O where available. Sessions begin and end based on observed process presence and are persisted locally.

System CPU/GPU utilization and GPU temperature are stored as session context. Session tables provide average and peak comparisons. Utilization comparisons are investigative clues only, not proof of a CPU/GPU bottleneck. FPS and frame-time remain unavailable.

## Processes

The Processes page presents the highest sampled CPU and memory consumers, process start time, elapsed duration, thread count, disk I/O, and historical samples. The list is limited to the collectors' selected top processes and may omit protected processes. Resource consumption is not a security verdict.
