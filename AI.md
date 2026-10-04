# Diagnosys AI Layer

## Purpose

AI is an optional natural-language explanation layer.

It is NOT the primary diagnostic engine.

## Architecture

```text
Measurements
    ↓
Deterministic analysis
    ↓
Structured diagnosis
    ↓
AI explainer
    ↓
Natural-language explanation
```

## Input

Provide only structured evidence needed for explanation.

Example:

```json
{
  "primary_category": "PACKET_LOSS",
  "confidence": 0.88,
  "window_seconds": 60,
  "evidence": [
    {"metric": "packet_loss_percent", "value": 7.1},
    {"metric": "ping_median_ms", "value": 18},
    {"metric": "ping_p95_ms", "value": 290},
    {"metric": "cpu_percent", "value": 32}
  ]
}
```

## Rules

The AI do:
- use only supplied evidence
- acknowledge uncertainty
- distinguish correlation from causation
- preserve diagnostic limitations
- never invent measurements
- never claim to have run a test it did not run

The AI does not:
- execute commands
- modify settings
- install software
- access credentials
- silently upload arbitrary machine data

## Provider abstraction

 Application can support:

```text
NoAIProvider
HostedLLMProvider
LocalLLMProvider
```

The project run normally with `NoAIProvider`.
