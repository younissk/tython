# Diagnostic Schema

The machine-readable diagnostic payload is versioned so tooling can detect changes before it
starts parsing fields by position or assumption.

## Version

- `schema_version`: `1`

## Core Fields

These fields are present in the structured diagnostic record emitted by `--errors json`,
`--errors jsonl`, and the persisted JSONL logs:

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

The `--errors llm` mode emits a compact, versioned `llm_fields` payload on the second line of
the rendered diagnostic. It mirrors the diagnostic record with a smaller, prompt-friendly shape:

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
