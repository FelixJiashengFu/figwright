# Using Figwright from Claude, Codex or another MCP client

Figwright ships an MCP server, so an assistant that can call tools can draw
figures with it instead of describing one in words.

```bash
pip install "figwright[mcp]"
figwright mcp            # speaks MCP over stdio; a client starts this for you
```

## Connecting it

**Claude Code** (and anything that reads the same config):

```bash
claude mcp add figwright -- figwright mcp
```

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "figwright": {
      "command": "figwright",
      "args": ["mcp"],
      "env": { "FIGWRIGHT_OUTPUT_DIR": "~/Desktop/Figures" }
    }
  }
}
```

**Codex CLI** — in `~/.codex/config.toml`:

```toml
[mcp_servers.figwright]
command = "figwright"
args = ["mcp"]
```

If `figwright` is inside a virtual environment, give the full path to it
(`/path/to/.venv/bin/figwright`, or `.venv\Scripts\figwright.exe` on Windows).

## The tools

| Tool | What it does |
| --- | --- |
| `list_capabilities` | Themes, figure kinds, chart kinds, formats, journal widths, which model is configured. Worth calling first. |
| `generate_figure` | Description → editable figure. `kind="auto"` lets Figwright choose. |
| `refine_figure` | An instruction applied to a saved figure; writes a new file and leaves the original alone. |
| `build_template` | Structured content → figure, with no model involved. |
| `describe_template` | A worked example of the content one template expects. |
| `export_figure` | PPTX (editable shapes), SVG, PNG, TIFF, JPEG, WebP, PDF, at a dpi or a journal column width. |
| `plot_table` | CSV/TSV/XLSX/JSON → chart, with error bars, group comparison and significance brackets. |
| `describe_table` | The columns of a table, their types and example values. |
| `vectorize_image` | Bitmap → editable vector shapes. |
| `enhance_image` | Clean up a photo, gel scan or screenshot; set its print size. |
| `lint_figure` | Report overlaps, clipped text and crossing connectors, and optionally fix them. |

Every tool writes its result into the output folder
(`FIGWRIGHT_OUTPUT_DIR`, by default `~/Figwright`) and returns the path, a short
JSON report and a small preview image. Nothing carries a whole 4 MB file back
through the conversation.

## What it will not do

Reading is deliberately narrow, because a tool server is driven by a model and a
model can be talked into things:

- Only regular files under your home folder, the working folder or the output
  folder are read. Anything else is refused with a message saying so.
- No hidden files or folders (so not `~/.ssh/id_rsa`, not `.env`).
- No symlinks, and nothing larger than 40 MB.
- Names a model chooses for a file are stripped to letters, digits, CJK, dot,
  dash and underscore, so a "name" cannot become a path.
- Nothing is executed, ever. Figwright draws; it does not run.

The model you use *through* Figwright is set separately, in Figwright's own
settings. With none set, the MCP tools still work in offline demo mode, and
`list_capabilities` reports `"offline_demo": true` so the client knows.
