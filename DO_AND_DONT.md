# Diagnosys — Do & Don't

## DO

- Build the deterministic diagnostic engine first.
- Keep measurements separate from diagnoses.
- Show evidence for every important conclusion.
- Track the time window used.
- Use historical baselines where possible.
- Make uncertainty visible.
- Handle unavailable metrics explicitly.
- Use bounded network timeouts.
- Isolate collector failures.
- Keep data local by default.
- Write tests for calculations and diagnostic rules.
- Use dependency injection where it improves testability.
- Keep the CLI simple.
- Document assumptions.
- Prefer safe read-only diagnostics.
- Make bandwidth-heavy operations opt-in.
- Keep AI optional.

## DON'T

### Don't call correlation causation

Bad:

> CPU caused my Internet to lag.

Better:

> CPU utilization and network latency increased during the same interval. This is a correlation; additional testing is needed to establish causation.

### Don't equate ping with speed

Latency, jitter, packet loss, and throughput are different properties.

### Don't blame the ISP automatically

A network problem can originate from:
- local Wi-Fi
- router
- local machine
- access point
- DNS
- network path
- remote service
- ISP

The tool should not identify the cause beyond its evidence.

### Don't make AI the brain

AI is an explanation layer.

The measured facts and deterministic diagnostics remain authoritative.

### Don't execute AI-generated commands

Never automatically execute commands produced by an LLM.

### Don't collect private data

Never collect:
- passwords
- tokens
- cookies
- browser history
- keystrokes
- private messages
- arbitrary personal files

### Don't silently upload data

No hidden telemetry.

### Don't require admin/root

The normal workflow should not require elevated privileges.

### Don't hard-code platform assumptions

Windows, Linux, and macOS differ.

Use capability detection.

### Don't use magic numbers

Bad:

```python
if ping > 200:
    ...
```

without documenting why.

Prefer named thresholds/configuration.

### Don't crash because a sensor is missing

Represent unsupported capabilities explicitly.

### Don't add infrastructure prematurely

No microservices, Kubernetes, Redis, Kafka, or distributed databases for the initial local app.

### Don't rewrite working modules unnecessarily

Prefer small, reviewable changes.

### Don't hide failures

If a measurement failed, report that it failed.

Never substitute fake or stale values without marking them.

## Safety boundary

Diagnosys should primarily be a read-only diagnostic tool.

Any future feature that changes system state must:
1. be explicitly designed
2. require user confirmation
3. explain the change
4. provide a safe rollback where practical
5. never be triggered directly by an AI-generated instruction
