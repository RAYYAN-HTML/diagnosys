# Diagnosys Privacy Model

## Local by default

System measurements, process observations, diagnostic history, and reports are stored locally. Diagnosys does not silently upload telemetry.

## Data that must not be collected

Do not collect passwords, API keys, tokens, cookies, browser history, private messages, keystrokes, or arbitrary personal documents.

## Network probes

Network diagnostics may contact the configured test destinations. The UI should identify the destination and purpose of each probe.

## Local diagnostic reasoning

All diagnostic findings are generated locally through deterministic rules and must be traceable to measurements. No external explanation service is used.

## Reports and sharing

Reports can contain host, process, network, and incident details. Redaction should be enabled for support bundles unless the user explicitly chooses otherwise. Explain what a report contains before it is shared.

## Retention

Historical measurements are stored in the local SQLite database according to the configured retention policy. Users should be able to clear local diagnostic history.
