# Diagnosys Privacy Model

## Default

Diagnosys is local-first.

System measurements and diagnostic history are stored locally.

## No default telemetry

The project should not silently upload:
- metrics
- process data
- network history
- diagnostic reports
- machine identifiers

## Sensitive data

Do not collect:
- passwords
- API keys
- cookies
- browser history
- private messages
- keystrokes
- personal documents

## Network probes

Network diagnostics may contact configured test targets.

The UI/documentation should make this clear.

## AI

If the user enables an external AI provider, explain what structured diagnostic information is sent.

Never send unrelated local data.

## Retention

Provide a configurable retention policy for historical measurements.

The user should be able to clear local diagnostic history.
