"""MCP server: lets Claude, Codex and other MCP clients draw figures with Figwright.

Run it with ``figwright mcp`` (stdio). Every tool writes its result into an output
folder (``FIGWRIGHT_OUTPUT_DIR``, by default ``~/Figwright``) and returns the path
plus a small preview, so the client never has to carry a whole file through the chat.

Reading is deliberately narrow: only regular files under the home folder or the
working directory, no hidden path components, and a size cap. The server never
executes anything a model writes.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any

from . import __version__

try:  # mcp 2.x
    from mcp.server.mcpserver import Image, MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]
    from mcp.server.fastmcp import Image  # type: ignore[no-redef]
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]

MAX_READ_BYTES = 40 * 1024 * 1024
PREVIEW_SIDE = 900
SAFE_NAME = re.compile(r"[^0-9A-Za-z一-鿿._-]+")

INSTRUCTIONS = """Figwright draws publication figures: flowcharts, experimental workflows,
signalling pathways, graphical abstracts, posters, PRISMA diagrams, statistical charts and
illustrations. Describe the figure in plain language (Chinese or English) and call
generate_figure; change it with refine_figure; save it as PPTX, SVG, PNG, TIFF or PDF with
export_figure. Every figure stays editable: the scene travels inside the SVG it writes.
Call list_capabilities first if you are unsure which theme, kind or format to ask for."""


def output_dir() -> Path:
    d = Path(os.environ.get("FIGWRIGHT_OUTPUT_DIR") or (Path.home() / "Figwright")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(name: str, suffix: str) -> str:
    stem = SAFE_NAME.sub("-", (name or "figure").strip())[:60].strip("-.") or "figure"
    stem = re.sub(r"-\d{8}-\d{6}$", "", stem) or "figure"  # do not stack a timestamp on a timestamp
    return f"{stem}-{dt.datetime.now():%Y%m%d-%H%M%S}{suffix}"


def thumbnail(data: bytes) -> Image:
    """A small PNG of a picture, for the client to look at without carrying the full file."""
    from . import raster

    img = raster.open_image(data)
    if max(img.size) > PREVIEW_SIDE:
        from PIL import Image as PILImage

        img = img.resize((max(1, round(img.width * PREVIEW_SIDE / max(img.size))), max(1, round(img.height * PREVIEW_SIDE / max(img.size)))), PILImage.LANCZOS)
    return Image(data=raster.encode(img.convert("RGB"), "png"), format="png")


def write_output(data: bytes | str, name: str, suffix: str) -> Path:
    path = output_dir() / _safe_name(name, suffix)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return path


def read_input(path_text: str) -> bytes:
    """Read a file the client named. Only plain files the user could have opened themselves."""
    p = Path(path_text).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()
    roots = [Path.home().resolve(), Path.cwd().resolve(), output_dir().resolve()]
    if not any(p == r or r in p.parents for r in roots):
        raise ValueError(f"For safety Figwright only reads files under {roots[0]} or the current folder. Copy the file there first.")
    if any(part.startswith(".") for part in p.parts[1:]):
        raise ValueError("Hidden files and folders are not read.")
    if not p.is_file() or p.is_symlink():
        raise ValueError(f"No such file: {p}")
    if p.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"{p.name} is larger than {MAX_READ_BYTES // (1024 * 1024)} MB.")
    return p.read_bytes()


def load_scene_file(path_text: str) -> dict:
    from .render import extract_scene_from_svg
    from .scene import normalize_scene

    raw = read_input(path_text)
    text = raw.decode("utf-8-sig", errors="replace")
    if text.lstrip()[:1] == "{":
        obj = json.loads(text)
        obj = obj.get("scene", obj) if isinstance(obj, dict) else obj
    else:
        obj = extract_scene_from_svg(text)
    if not isinstance(obj, dict):
        raise ValueError(f"{path_text} does not contain a Figwright figure. Use import_picture to trace a plain image.")
    return normalize_scene(obj)


def preview(scene: dict) -> Image:
    from .render import render_png
    from .scene import scene_bounds

    bounds = scene_bounds(scene)
    side = max(scene.get("width", 1), scene.get("height", 1), 1) if not bounds else max(bounds[2] - bounds[0], bounds[3] - bounds[1], 1)
    return Image(data=render_png(scene, scale=max(0.4, min(2.0, PREVIEW_SIDE / side))), format="png")


def save_figure(scene: dict, name: str, fmt: str, dpi: float = 300.0, width_mm: float | None = None, lang: str = "en") -> tuple[Path, list[str]]:
    from . import export_share
    from .render import render_svg

    fmt = fmt.lower().lstrip(".")
    notes: list[str] = []
    if fmt == "svg":
        data: bytes | str = render_svg(scene)
    elif fmt == "json":
        data = json.dumps({"app": "figwright", "version": __version__, "scene": scene}, ensure_ascii=False, indent=1)
    elif fmt == "html":
        data = export_share.share_html(scene, lang)
    elif fmt == "pptx":
        from .export_pptx import scene_to_pptx

        data, notes = scene_to_pptx(scene, disclosure=export_share.disclosure(scene, lang))
    elif fmt in ("png", "jpg", "jpeg", "tif", "tiff", "webp", "pdf"):
        data, info = export_share.export_raster(scene, fmt, dpi=dpi, width_mm=width_mm)
        notes = [info["note"]] if info.get("note") else []
    else:
        raise ValueError("Formats: svg, png, jpg, tiff, webp, pdf, pptx, json, html.")
    return write_output(data, name, "." + {"jpg": "jpeg", "tif": "tiff"}.get(fmt, fmt)), notes


def result(path: Path, scene: dict | None = None, notes: list[str] | None = None, **extra: Any) -> list[Any]:
    """What a tool hands back: a short report, then a picture of what was made."""
    report: dict[str, Any] = {"saved": str(path), "bytes": path.stat().st_size, **extra}
    if notes:
        report["notes"] = notes
    out: list[Any] = [json.dumps(report, ensure_ascii=False, indent=1)]
    if scene is not None:
        out.append(preview(scene))
    return out


def expected(fn: Any) -> Any:
    """Turn the failures we know about into a message the client can read and act on.

    Without this the SDK reports every exception as "Error executing tool X",
    which tells the model nothing about what to fix.
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        from .config import ConfigError
        from .export_share import ExportError
        from .generate import GenerationError
        from .plot import PlotError
        from .providers import ProviderError
        from .raster import ImageError
        from .sources import SourceError

        try:
            return fn(*args, **kwargs)
        except (ValueError, KeyError, OSError, GenerationError, ProviderError, ConfigError, PlotError, ImageError, SourceError, ExportError) as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    return wrapper


def build_server() -> Any:
    server = MCPServer(
        name="figwright",
        title="Figwright figure workshop",
        instructions=INSTRUCTIONS,
        version=__version__,
    )

    @server.tool(
        title="List what Figwright can draw",
        description="Themes, figure kinds, chart kinds, export formats, journal widths and which model is configured. Call this before guessing an argument.",
    )
    @expected
    def list_capabilities() -> str:
        from . import plot
        from .config import load_config, public_config
        from .export_share import SIZE_PRESETS
        from .generate import IMAGE_STYLES
        from .offline import KINDS
        from .themes import THEMES

        cfg = public_config(load_config())
        return json.dumps(
            {
                "version": __version__,
                "figure_kinds": list(KINDS),
                "template_kinds": ["flowchart", "workflow", "pathway", "abstract", "poster", "prisma"],
                "themes": sorted(THEMES),
                "chart_kinds": list(plot.KINDS),
                "formats": ["svg", "png", "jpeg", "tiff", "webp", "pdf", "pptx", "json", "html"],
                "journal_widths_mm": {k: v for k, v in SIZE_PRESETS.items()},
                "illustration_styles": sorted(IMAGE_STYLES),
                "models": {role: f"{r.get('provider') or 'none'} {r.get('model') or ''}".strip() for role, r in cfg["roles"].items()},
                "offline_demo": cfg["roles"].get("text", {}).get("provider") in ("", "mock"),
                "output_dir": str(output_dir()),
                "note": "With no API key configured Figwright still works: it falls back to rule-based drawing, marked 'offline demo' in the result.",
            },
            ensure_ascii=False,
            indent=1,
        )

    @server.tool(
        title="Draw a figure from a description",
        description="Text to figure. Describe the steps, the pathway or the panels; kind='auto' lets Figwright choose. Saves an editable SVG and returns a preview.",
        structured_output=False,
    )
    @expected
    def generate_figure(prompt: str, kind: str = "auto", theme: str = "", quality: str = "balanced", source_file: str = "", name: str = "") -> list[Any]:
        from .generate import generate_figure as run

        source = ""
        if source_file:
            from .sources import extract_text

            source, _n = extract_text(Path(source_file).name, read_input(source_file))
        out = run(prompt, kind=kind, theme=theme or None, quality=quality, source=source)
        path, notes = save_figure(out.scene, name or prompt[:40], "svg")
        return result(path, out.scene, out.notes + notes, kind=out.kind, provider=out.provider, model=out.model, issues=[i["message"] for i in out.issues])

    @server.tool(
        title="Change a figure",
        description="Edit an existing Figwright figure (.svg or .json) with an instruction such as 'make the third box green' or 'add a step after QC'. Writes a new file; the original is left alone.",
        structured_output=False,
    )
    @expected
    def refine_figure(figure_file: str, instruction: str, name: str = "") -> list[Any]:
        from .generate import refine_figure as run

        out = run(load_scene_file(figure_file), instruction)
        path, notes = save_figure(out.scene, name or Path(figure_file).stem, "svg")
        return result(path, out.scene, out.notes + notes, summary=out.summary, provider=out.provider)

    @server.tool(
        title="Lay out structured content",
        description="Build a figure from content you already have as data, with no model involved: kind is flowchart, workflow, pathway, abstract, poster or prisma, and content is the JSON for that kind (ask for the shape with describe_template).",
        structured_output=False,
    )
    @expected
    def build_template(kind: str, content: dict, theme: str = "", name: str = "") -> list[Any]:
        from .builders import BUILDERS
        from .lint import autofix, lint
        from .scene import normalize_scene

        if kind not in BUILDERS:
            raise ValueError(f"kind must be one of: {', '.join(BUILDERS)}")
        scene, fixes = autofix(normalize_scene(BUILDERS[kind](content, theme or None)), snap=False)
        scene["kind"] = kind
        path, notes = save_figure(scene, name or kind, "svg")
        return result(path, scene, fixes + notes, issues=[i["message"] for i in lint(scene)])

    @server.tool(
        title="Show a template's content shape",
        description="A worked example of the content JSON that build_template expects for one kind.",
    )
    @expected
    def describe_template(kind: str) -> str:
        from .examples import TEMPLATE_FORMS

        form = next((t for t in TEMPLATE_FORMS if t["id"] == kind or t.get("kind") == kind), None)
        if not form:
            raise ValueError(f"No template called {kind!r}. Try: {', '.join(t['id'] for t in TEMPLATE_FORMS)}")
        return json.dumps(form, ensure_ascii=False, indent=1)

    @server.tool(
        title="Save a figure in another format",
        description="Convert a Figwright figure to PPTX (editable shapes), SVG, PNG, TIFF, JPEG, WebP or PDF. width_mm takes a journal column width, e.g. 89 for single column, 183 for double.",
        structured_output=False,
    )
    @expected
    def export_figure(figure_file: str, format: str = "pptx", dpi: float = 300.0, width_mm: float = 0.0, theme: str = "", lang: str = "en", name: str = "") -> list[Any]:
        scene = load_scene_file(figure_file)
        if theme:
            from .scene import normalize_scene
            from .themes import retheme

            scene = normalize_scene(retheme(scene, theme))
        path, notes = save_figure(scene, name or Path(figure_file).stem, format, dpi=dpi, width_mm=width_mm or None, lang=lang)
        return result(path, scene, notes, format=format)

    @server.tool(
        title="Chart a table",
        description="Turn a CSV, TSV, XLSX or JSON table into a chart with the statistics a paper needs (error bars, group comparison with significance brackets, regression fit). Describe the chart in words with 'ask', or give an explicit spec.",
        structured_output=False,
    )
    @expected
    def plot_table(table_file: str, ask: str = "", spec: dict | None = None, format: str = "svg", dpi: int = 300, theme: str = "", lang: str = "en", name: str = "") -> list[Any]:
        from . import plot
        from .generate import suggest_plot

        df = plot.load_table(Path(table_file).name, read_input(table_file))
        use = dict(spec or {})
        if ask:
            use, _info = suggest_plot(ask, plot.describe(df), use or None)
        fmt = format.lower().lstrip(".")
        if fmt not in ("svg", "png", "pdf", "pptx"):
            raise ValueError("Charts can be saved as svg, png, pdf or pptx.")
        data, info = plot.render_plot(df, use, theme or None, "svg" if fmt == "pptx" else fmt, dpi=dpi)
        if fmt == "pptx":
            from .export_pptx import plot_to_pptx

            data, notes = plot_to_pptx(df, use, theme or None, caption=plot.caption(info, lang))
            path = write_output(data, name or Path(table_file).stem, ".pptx")
            return result(path, None, notes, spec=info["spec"], caption=plot.caption(info, lang))
        path = write_output(data, name or Path(table_file).stem, "." + fmt)
        report = {"saved": str(path), "bytes": path.stat().st_size, "spec": info["spec"], "caption": plot.caption(info, lang)}
        if info.get("stats"):
            report["statistics"] = info["stats"]
        if info.get("fit"):
            report["fit"] = info["fit"]
        png, _i = plot.render_plot(df, use, theme or None, "png", dpi=110)
        return [json.dumps(report, ensure_ascii=False, indent=1, default=str), Image(data=png, format="png")]

    @server.tool(
        title="Describe a table",
        description="The columns of a table file, their types and a few example values, so a chart can be asked for by column name.",
    )
    @expected
    def describe_table(table_file: str) -> str:
        from . import plot

        raw = read_input(table_file)
        df = plot.load_table(Path(table_file).name, raw)
        return json.dumps({"rows": int(len(df)), "columns": plot.describe(df), "sheets": plot.sheet_names(Path(table_file).name, raw)}, ensure_ascii=False, indent=1, default=str)

    @server.tool(
        title="Trace a picture into vector shapes",
        description="Bitmap to editable SVG (colour tracing). Good for logos, line art and flat diagrams; photographs come out posterised.",
        structured_output=False,
    )
    @expected
    def vectorize_image(image_file: str, colors: int = 6, detail: str = "medium", name: str = "") -> list[Any]:
        from . import vectorize as vec

        out = vec.vectorize(read_input(image_file), colors=colors, detail=detail)
        scene = vec.vector_scene(out, title=Path(image_file).stem)
        path, notes = save_figure(scene, name or Path(image_file).stem, "svg")
        return result(path, scene, out["notes"] + notes, colours=out["colors"], points=out["points"])

    @server.tool(
        title="Clean up a photo or scan",
        description="Even out lighting, denoise, sharpen, remove the background, trim margins and set the print size of a photo, gel scan or screenshot.",
        structured_output=False,
    )
    @expected
    def enhance_image(image_file: str, whiten: bool = False, denoise: float = 0.0, contrast: float = 0.0, sharpen: float = 0.0, remove_bg: bool = False, trim: bool = False, width_mm: float = 0.0, dpi: int = 0, format: str = "png", name: str = "") -> list[Any]:
        from . import raster

        options = {"whiten": whiten, "denoise": denoise, "contrast": contrast, "sharpen": sharpen, "remove_bg": remove_bg, "trim": trim, "width_mm": width_mm or None, "dpi": dpi or None, "format": format}
        data, info = raster.enhance(read_input(image_file), {k: v for k, v in options.items() if v})
        path = write_output(data, name or Path(image_file).stem, "." + info["format"].replace("jpeg", "jpg").replace("tiff", "tif"))
        return [json.dumps({"saved": str(path), "bytes": len(data), "width": info["width"], "height": info["height"], "did": info["steps"], "notes": info["notes"]}, ensure_ascii=False, indent=1), thumbnail(data)]

    @server.tool(
        title="Check a figure's layout",
        description="Report overlapping shapes, clipped text, connectors crossing boxes and other layout problems, and optionally fix what can be fixed automatically.",
        structured_output=False,
    )
    @expected
    def lint_figure(figure_file: str, fix: bool = False, name: str = "") -> list[Any]:
        from .lint import autofix, lint

        scene = load_scene_file(figure_file)
        issues = lint(scene)
        if not fix:
            return [json.dumps({"issues": [{"severity": i["severity"], "message": i["message"]} for i in issues] or "no problems found"}, ensure_ascii=False, indent=1), preview(scene)]
        fixed, changes = autofix(scene, snap=True)
        path, notes = save_figure(fixed, name or Path(figure_file).stem + "-fixed", "svg")
        return result(path, fixed, changes + notes, remaining=[i["message"] for i in lint(fixed)])

    return server


def main() -> int:
    build_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
