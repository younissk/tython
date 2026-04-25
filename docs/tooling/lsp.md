# LSP

Tython LSP is for editor integration, not for syntax guessing.

## Supported Features

- hover
- go to definition
- references
- completion
- document symbols
- code actions
- document formatting

## Start Server

```bash
tython lsp start
```

The server uses stdio.
Point your editor at that command or use the installer subcommands in the CLI docs.

## Behavior

- Parses custom Tython syntax before analysis.
- Reports diagnostics through LSP.
- Uses workspace files for cross-file definition and completion.

## Logging

Set `TYTHON_LSP_LOG` to mirror server logs into a file while keeping stderr output.

