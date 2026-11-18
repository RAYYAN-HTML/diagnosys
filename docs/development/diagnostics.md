# Diagnosys Diagnostic Model

## Principle

Diagnosys should answer three questions:

1. What happened?
2. What measurements support the finding?
3. What should the user check next?

## Evidence sources

The diagnostic path uses:
- direct operating-system and hardware measurements
- repeated observations over a stated time window
- personal-baseline deviations when enough local history exists
- hardware-reported high and critical sensor limits
- process and system events that overlap the investigation window
- explicit missing-data and capability information

Time overlap is correlation, not proof of causation. A resource consumer is not labelled malicious based on resource use.

## Personal baselines

The baseline detector requires a minimum history sample count and compares measurements with the device's own distribution using median, percentile, and median absolute deviation. It does not apply universal CPU, memory, disk, or network cutoffs.

A baseline deviation is a signal to investigate, not proof of a fault.

## Thermal findings

Thermal findings use high and critical limits reported by the sensor. A sustained warning requires repeated samples above the reported high limit over a measured time span. A critical finding is recorded when a reading reaches a reported critical limit.

When a sensor does not expose a limit, Diagnosys shows the reading and does not infer a warning from a universal temperature number. CPU/GPU utilization and CPU frequency are shown as concurrent context; they do not prove thermal throttling.

## Hypothesis ordering

Hypotheses are ordered using transparent evidence counts and categories. The order is not a probability, confidence level, or estimate of certainty. The UI should show supporting measurements, missing evidence, limitations, and next checks.

## Example

```text
Observed:
- CPU utilization deviated from this device's recent baseline.
- A process was active during the same capture interval.
- The process and system samples overlap in time.

Interpretation:
- Local resource contention is a possible explanation.
- The time overlap does not prove that the process caused the slowdown.

Next checks:
- Compare process and system history over a longer interval.
- Repeat the capture with the same workload.
```

## Competing explanations

Keep alternatives when the evidence supports more than one interpretation. Do not manufacture a ranking from arbitrary weights. If evidence is insufficient, say so.

## Historical comparisons

Before/after comparisons should show the measured values, sample coverage, and time windows. Small changes should not be promoted to important findings through an arbitrary percentage threshold.

## Non-goals

- No confidence percentage, probability score, or arbitrary hypothesis score.
- No universal health score.
- No fabricated metrics or claims of causation.
