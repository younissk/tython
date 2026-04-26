# Diagnostic Schema

The machine-readable diagnostic payload is versioned so tooling can detect changes before it
starts parsing fields by position or assumption.

## Version

- `schema_version`: `1`

## Core Fields

These fields are present in the structured diagnostic record used by tooling such as LSP and
the internal compiler/formatter/linter APIs:

- `code`
- `severity`
- `phase`
- `message`
- `file`
- `range`
- `timestamp`
- `schema_version`

## Optional Fields

These fields may be present when the diagnostic has richer context:

- `expected`
- `found`
- `notes`
- `help`
- `related`
- `trace`
- `fixes`
- `recovery`
- `symbol`
- `command`
- `module`

## LLM Payload

Some diagnostic renderers may include a compact, versioned `llm_fields` payload alongside the
human-facing message. It mirrors the diagnostic record with a smaller, prompt-friendly shape:

- `schema_version`
- `code`
- `phase`
- `severity`
- `message`
- `file`
- `range`
- `expected`
- `found`
- `notes`
- `help`
- `related`
- `fixes`
- `recovery`
- `symbol`
- `command`
- `module`

Consumers should key off `schema_version` before relying on any field outside the error code and
human-facing message.
