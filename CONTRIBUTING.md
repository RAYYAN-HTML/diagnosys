# Contributing to Diagnosys

## Before coding

Read:
- ARCHITECTURE.md
- STAGE.md
- DO_AND_DONT.md
- relevant docs/

## Pull requests

Explain:
- what changed
- why
- tests
- platform impact
- privacy/security impact

## New collector

Include:
- collector
- domain model changes if required
- unit tests
- failure behavior
- documentation

## New diagnostic rule

Document:
- rule ID
- inputs
- trigger
- evidence
- limitations
- false positives
- tests

## Commit style

Examples:

```text
feat: add CPU collector
feat: add ping probe
test: cover jitter calculation
fix: handle permission denied process
docs: explain packet-loss diagnosis
```

Keep commits focused.
