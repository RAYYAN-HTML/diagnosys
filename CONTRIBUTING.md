# Contributing to Diagnosys

## Before coding

Read:
- [Architecture](docs/development/architecture.md)
- [Development guidelines](docs/development/guidelines.md)
- [Desktop packaging](docs/development/packaging.md)
- [Current stage](docs/project/stage.md)
- Relevant domain documents from the [documentation index](docs/README.md)

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
