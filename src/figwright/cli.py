"""Command line: start the app, or make and convert figures without the browser.

    figwright                      start the app and open the browser
    figwright generate "A -> B"    text to figure (format follows the file name)
    figwright export fig.svg -o fig.pptx
    figwright plot data.csv -o chart.pptx --kind bar --stats
    figwright vectorize logo.png -o logo.svg
    figwright enhance photo.jpg -o photo.tif --whiten --width-mm 89 --dpi 600
    figwright doctor               check the installation
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

from . import __version__

FIGURE_FORMATS = ("svg", "png", "jpg", "jpeg", "tif", "tiff", "webp", "pdf", "pptx", "json", "html")


class CliError(Exception):
    """Something the user can fix; printed without a traceback."""


def _say(*parts: Any) -> None:
    print(*parts, file=sys.stderr)


def _write(path: Path, data: bytes | str) -> None:
    path = path.expanduser()
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    _say(f"saved {path} ({path.stat().st_size / 1024:.0f} KB)")


def _fmt_of(path: Path, explicit: str | None, allowed: tuple[str, ...]) -> str:
    fmt = (explicit or path.suffix.lstrip(".") or allowed[0]).lower()
    if path.name.lower().endswith(".figwright.json"):
        fmt = "json"
    if fmt not in allowed:
        raise CliError(f"Cannot write '.{fmt}' here. Use one of: {', '.join(allowed)}.")
    return fmt


def load_scene(path: Path) -> dict:
    """Read a figure from a Figwright SVG (the scene travels inside it) or a JSON file."""
    from .render import extract_scene_from_svg
    from .scene import normalize_scene

    path = path.expanduser()
    if not path.is_file():
        raise CliError(f"No such file: {path}")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if text.lstrip()[:1] == "{":
        try:
            raw = json.loads(text)
        except ValueError as exc:
            raise CliError(f"{path} is not valid JSON ({exc}).") from None
        if isinstance(raw, dict) and isinstance(raw.get("scene"), dict):
            raw = raw["scene"]
    else:
        raw = extract_scene_from_svg(text)
        if raw is None:
            raise CliError(f"{path} was not made by Figwright (no editable figure inside). To trace a picture use: figwright vectorize")
    if not isinstance(raw, dict):
        raise CliError(f"{path} does not contain a figure.")
    return normalize_scene(raw)


def save_scene(scene: dict, path: Path, fmt: str | None = None, dpi: float = 300.0, width_mm: float | None = None, transparent: bool = False, lang: str = "en", include_notes: bool = False) -> list[str]:
    """Write a figure in the format the file name asks for. Returns notes worth showing."""
    from . import export_share
    from .render import render_svg

    fmt = _fmt_of(path, fmt, FIGURE_FORMATS)
    notes: list[str] = []
    if fmt == "svg":
        _write(path, render_svg(scene, include_notes=include_notes))
    elif fmt == "json":
        _write(path, json.dumps({"app": "figwright", "version": __version__, "scene": scene}, ensure_ascii=False, indent=1))
    elif fmt == "pptx":
        from .export_pptx import scene_to_pptx

        data, notes = scene_to_pptx(scene, include_notes=include_notes, disclosure=export_share.disclosure(scene, lang))
        _write(path, data)
    elif fmt == "html":
        _write(path, export_share.share_html(scene, lang))
    else:
        data, info = export_share.export_raster(scene, fmt, dpi=dpi, width_mm=width_mm, transparent=transparent)
        _write(path, data)
        _say(f"  {info['width']} x {info['height']} px, {info['mm'][0]} x {info['mm'][1]} mm at {info['dpi']:g} dpi")
        if info.get("note"):
            notes.append(info["note"])
    return notes


def _report(notes: list[str], issues: list[dict] | None = None) -> None:
    for n in notes:
        _say(f"  note: {n}")
    for i in (issues or [])[:8]:
        _say(f"  {i.get('severity', 'warning')}: {i.get('message', '')}")


# ---------------------------------------------------------------------------------- serve
def _free_port(host: str, port: int) -> int:
    for candidate in range(port, port + 30):
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, candidate))
                return candidate
            except OSError:
                continue
    raise CliError(f"No free port between {port} and {port + 29}. Close another copy of Figwright or pass --port.")


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    host = args.host
    token = args.token or os.environ.get("FIGWRIGHT_TOKEN") or None
    if args.allow_remote:
        if host in ("127.0.0.1", "localhost"):
            host = "0.0.0.0"
        token = token or secrets.token_urlsafe(18)
    elif host not in ("127.0.0.1", "localhost", "::1"):
        raise CliError("Listening on another address needs --allow-remote (which also turns on the access token).")
    port = _free_port(host, args.port)
    app = create_app(token=token, allow_remote=args.allow_remote)
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{shown}:{port}/" + (f"?token={token}" if token else "")
    _say(f"Figwright {__version__} is running. Open: {url}")
    if args.allow_remote:
        _say("Other devices on your network: replace 127.0.0.1 with this computer's address and keep the token.")
        _say("The connection is plain http: use it on networks you trust, or put it behind an https proxy.")
    _say("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.9, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
    return 0


# ------------------------------------------------------------------------------- figures
def cmd_generate(args: argparse.Namespace) -> int:
    from .generate import generate_figure

    source = ""
    if args.source:
        from .sources import extract_text

        p = Path(args.source).expanduser()
        if not p.is_file():
            raise CliError(f"No such file: {p}")
        source, notes = extract_text(p.name, p.read_bytes())
        _report(notes)
    out = generate_figure(args.prompt, kind=args.kind, theme=args.theme, quality=args.quality, source=source, progress=lambda stage: _say(f"  {stage}..."))
    _report(out.notes + save_scene(out.scene, Path(args.output), dpi=args.dpi, width_mm=args.width_mm, lang=args.lang), out.issues)
    return 0


def cmd_refine(args: argparse.Namespace) -> int:
    from .generate import refine_figure

    scene = load_scene(Path(args.figure))
    out = refine_figure(scene, args.instruction, progress=lambda stage: _say(f"  {stage}..."))
    if out.summary:
        _say(f"  {out.summary}")
    _report(out.notes + save_scene(out.scene, Path(args.output or args.figure), dpi=args.dpi, width_mm=args.width_mm, lang=args.lang), out.issues)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    scene = load_scene(Path(args.figure))
    if args.theme:
        from .scene import normalize_scene
        from .themes import retheme

        scene = normalize_scene(retheme(scene, args.theme))
    _report(save_scene(scene, Path(args.output), fmt=args.format, dpi=args.dpi, width_mm=args.width_mm, transparent=args.transparent, lang=args.lang, include_notes=args.notes))
    return 0


def cmd_template(args: argparse.Namespace) -> int:
    from .builders import BUILDERS
    from .lint import autofix, lint
    from .scene import normalize_scene

    p = Path(args.content).expanduser()
    if not p.is_file():
        raise CliError(f"No such file: {p}")
    try:
        content = json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise CliError(f"{p} is not valid JSON ({exc}).") from None
    try:
        scene = BUILDERS[args.kind](content, args.theme)
    except ValueError as exc:
        raise CliError(str(exc)) from None
    warnings = (scene.get("meta") or {}).get("warnings") or []
    scene, fixes = autofix(normalize_scene(scene), snap=False)
    scene["kind"] = args.kind
    _report(fixes + [f"check: {w}" for w in warnings] + save_scene(scene, Path(args.output), dpi=args.dpi, width_mm=args.width_mm, lang=args.lang), lint(scene))
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    from .lint import lint

    issues = lint(load_scene(Path(args.figure)))
    for i in issues:
        print(f"{i['severity']}: {i['message']}")
    if not issues:
        print("No layout problems found.")
    return 1 if any(i["severity"] == "error" for i in issues) else 0


# ---------------------------------------------------------------------------------- plots
def cmd_plot(args: argparse.Namespace) -> int:
    from . import plot

    p = Path(args.table).expanduser()
    if not p.is_file():
        raise CliError(f"No such file: {p}")
    df = plot.load_table(p.name, p.read_bytes(), args.sheet)
    spec: dict[str, Any] = {}
    if args.spec:
        try:
            spec = json.loads(args.spec)
        except ValueError as exc:
            raise CliError(f"--spec is not valid JSON ({exc}).") from None
    if args.ask:
        from .generate import suggest_plot

        spec, info = suggest_plot(args.ask, plot.describe(df), spec or None)
        _report(info["notes"])
    for key in ("kind", "x", "group", "title", "xlabel", "ylabel", "error", "palette", "test"):
        if getattr(args, key, None) is not None:
            spec[key] = getattr(args, key)
    if args.y:
        spec["y"] = args.y
    for flag in ("stats", "fit", "logx", "logy"):
        if getattr(args, flag):
            spec[flag] = True
    if args.no_points:
        spec["points"] = False
    out = Path(args.output)
    fmt = _fmt_of(out, args.format, ("svg", "png", "pdf", "pptx"))
    data, info = plot.render_plot(df, spec, args.theme, "svg" if fmt == "pptx" else fmt, dpi=int(args.dpi))
    if fmt == "pptx":
        from .export_pptx import plot_to_pptx

        data, notes = plot_to_pptx(df, spec, args.theme, caption=plot.caption(info, args.lang))
        _write(out, data)
        _report(notes)
    else:
        _write(out, data)
    s = info["spec"]
    _say(f"  {s['kind']} chart: x = {s['x']}, y = {', '.join(s['y']) or '-'}" + (f", grouped by {s['group']}" if s["group"] else ""))
    _report((info.get("notes") or []) + list((info.get("stats") or {}).get("notes", [])))
    cap = plot.caption(info, args.lang)
    if cap:
        print(cap)
    return 0


def cmd_vectorize(args: argparse.Namespace) -> int:
    from . import vectorize

    p = Path(args.image).expanduser()
    if not p.is_file():
        raise CliError(f"No such file: {p}")
    result = vectorize.vectorize(p.read_bytes(), colors=args.colors, detail=args.detail, smooth=not args.no_smooth)
    out = Path(args.output)
    fmt = _fmt_of(out, None, ("svg", "json", "pptx"))
    if fmt == "svg" and not args.editable:
        _write(out, result["svg"])
    else:
        scene = vectorize.vector_scene(result, title=p.stem, split=args.split)
        save_scene(scene, out)
    _say(f"  {len(result['colors'])} colours, {result['points']} points, mean colour error {result['error']:.1f}")
    _report(result["notes"])
    return 0


def cmd_enhance(args: argparse.Namespace) -> int:
    from . import raster

    p = Path(args.image).expanduser()
    if not p.is_file():
        raise CliError(f"No such file: {p}")
    out = Path(args.output)
    options = {
        "whiten": args.whiten,
        "denoise": args.denoise,
        "contrast": args.contrast,
        "sharpen": args.sharpen,
        "remove_bg": args.remove_bg,
        "bg_tolerance": args.bg_tolerance,
        "trim": args.trim,
        "upscale": args.upscale,
        "width_mm": args.width_mm,
        "dpi": args.dpi,
        "grayscale": args.grayscale,
        "format": _fmt_of(out, None, ("png", "jpg", "jpeg", "tif", "tiff", "webp")),
    }
    data, info = raster.enhance(p.read_bytes(), {k: v for k, v in options.items() if v not in (None, False)})
    _write(out, data)
    _say(f"  {info['width']} x {info['height']} px" + (f", {info['mm'][0]} x {info['mm'][1]} mm at {info['dpi']} dpi" if info.get("mm") else ""))
    for step in info["steps"]:
        _say(f"  did: {step}")
    _report(info["notes"])
    return 0


# --------------------------------------------------------------------------------- config
def cmd_config(args: argparse.Namespace) -> int:
    from .config import PRESETS, ROLES, config_path, load_config, public_config, update_config

    cfg = load_config()
    if args.action == "show":
        pub = public_config(cfg)
        print(f"settings file: {config_path()}")
        for role in ROLES:
            r = pub["roles"].get(role, {})
            print(f"{role:7s} {r.get('provider') or '(not set)'}  {r.get('model') or ''}")
        for p in pub["providers"]:
            if p["key_set"] or p["base_url_overridden"]:
                print(f"key for {p['id']}: {p['key_hint']}" + (" (from environment)" if p["key_from_env"] else "") + (f"  address: {p['base_url']}" if p["base_url_overridden"] else ""))
        return 0
    if args.action == "providers":
        for pid, preset in PRESETS.items():
            print(f"{pid:12s} {preset['label']['en']}  roles: {', '.join(preset['roles'])}" + (f"  env: {preset['env']}" if preset.get("env") else ""))
        return 0
    if args.action == "set-key":
        if not args.provider or args.provider not in PRESETS:
            raise CliError("Usage: figwright config set-key PROVIDER   (see: figwright config providers)")
        import getpass

        # Read from a prompt or a pipe, never from the command line: arguments end up in shell history.
        key = getpass.getpass(f"API key for {args.provider} (input is hidden): ") if sys.stdin.isatty() else sys.stdin.readline().strip()
        if not key:
            raise CliError("No key entered.")
        update_config(cfg, {"providers": {args.provider: {"api_key": key}}})
        _say(f"key saved for {args.provider}")
        return 0
    if args.action == "clear-key":
        if not args.provider or args.provider not in PRESETS:
            raise CliError("Usage: figwright config clear-key PROVIDER")
        update_config(cfg, {"providers": {args.provider: {"clear_key": True}}})
        _say(f"key removed for {args.provider}")
        return 0
    if args.action == "role":
        if args.provider not in ROLES or not args.model or args.model not in PRESETS:
            raise CliError("Usage: figwright config role {text|vision|image} PROVIDER [MODEL]")
        update_config(cfg, {"roles": {args.provider: {"provider": args.model, "model": args.extra or ""}}})
        _say(f"{args.provider} now uses {args.model} {args.extra or ''}".rstrip())
        return 0
    raise CliError("Unknown config action.")


def cmd_doctor(_args: argparse.Namespace) -> int:
    import importlib
    import platform

    from .config import config_path, home, load_config, public_config

    ok = True
    print(f"Figwright {__version__}, Python {platform.python_version()} on {platform.system()} {platform.machine()}")
    for mod, why in (("fastapi", "web app"), ("uvicorn", "web app"), ("httpx", "model providers"), ("anthropic", "Claude provider"), ("numpy", "images"), ("PIL", "images"), ("cv2", "sketches, vectorizer, image lab"), ("matplotlib", "charts"), ("pandas", "tables"), ("scipy", "statistics"), ("openpyxl", "Excel files"), ("pptx", "PowerPoint export"), ("pypdf", "PDF source material"), ("resvg_py", "PNG export")):
        try:
            m = importlib.import_module(mod)
            print(f"  ok       {mod:11s} {getattr(m, '__version__', '')}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  MISSING  {mod:11s} needed for {why} ({type(exc).__name__})")
    try:
        importlib.import_module("mcp")
        print("  ok       mcp         (figwright mcp is available)")
    except ImportError:
        print("  optional mcp         not installed: pip install 'figwright[mcp]' to use Figwright from Claude or Codex")
    h = home()
    try:
        h.mkdir(parents=True, exist_ok=True)
        probe = h / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        print(f"  ok       data folder {h}")
    except OSError as exc:
        ok = False
        print(f"  PROBLEM  data folder {h} is not writable ({exc})")
    pub = public_config(load_config())
    print(f"  settings {config_path()}")
    for role, r in pub["roles"].items():
        print(f"  {role:8s} {r.get('provider') or '(not set)'} {r.get('model') or ''}".rstrip())
    try:
        from .render import render_png
        from .scene import normalize_scene

        png = render_png(normalize_scene({"width": 240, "height": 120, "nodes": [{"id": "a", "type": "rect", "x": 20, "y": 20, "w": 200, "h": 80, "text": "测试 Test"}]}), scale=1)
        print(f"  ok       rendering self-test ({len(png)} bytes)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  PROBLEM  rendering self-test failed ({type(exc).__name__}: {exc})")
    print("Everything needed is in place." if ok else "Some parts are missing: pip install --upgrade figwright")
    return 0 if ok else 1


def cmd_mcp(_args: argparse.Namespace) -> int:
    from .mcp_server import main as mcp_main

    return mcp_main()


# --------------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    from .offline import KINDS
    from .plot import ERRORS
    from .plot import KINDS as PLOT_KINDS
    from .plot import PALETTES
    from .themes import THEMES

    ap = argparse.ArgumentParser(prog="figwright", description="Figwright: an open-source AI figure workshop for research.")
    ap.add_argument("--version", action="version", version=f"figwright {__version__}")
    sub = ap.add_subparsers(dest="command")

    def size_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dpi", type=float, default=300.0, help="resolution of bitmap output (default 300)")
        p.add_argument("--width-mm", type=float, default=None, help="physical width of bitmap output, e.g. 89 for one journal column")
        p.add_argument("--lang", choices=("en", "zh"), default="en", help="language of generated text such as the AI disclosure")

    p = sub.add_parser("serve", help="start the app (the default when no command is given)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--allow-remote", action="store_true", help="accept connections from other devices; an access token is then required")
    p.add_argument("--token", default=None, help="access token (generated when --allow-remote is used without one)")
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("generate", help="text to figure")
    p.add_argument("prompt")
    p.add_argument("-o", "--output", required=True, help="output file; the extension picks the format (" + ", ".join(FIGURE_FORMATS) + ")")
    p.add_argument("--kind", default="auto", choices=("auto", *KINDS))
    p.add_argument("--theme", default=None, choices=sorted(THEMES))
    p.add_argument("--quality", default="balanced", choices=("fast", "balanced", "best"))
    p.add_argument("--source", default=None, help="a PDF, DOCX, Markdown or text file to draw the content from")
    size_args(p)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("refine", help="change a figure with an instruction")
    p.add_argument("figure", help="a Figwright .svg or .json file")
    p.add_argument("instruction")
    p.add_argument("-o", "--output", default=None, help="default: overwrite the input")
    size_args(p)
    p.set_defaults(func=cmd_refine)

    p = sub.add_parser("export", help="convert a figure to another format")
    p.add_argument("figure", help="a Figwright .svg or .json file")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--format", default=None, choices=FIGURE_FORMATS)
    p.add_argument("--theme", default=None, choices=sorted(THEMES), help="recolour with another theme first")
    p.add_argument("--transparent", action="store_true")
    p.add_argument("--notes", action="store_true", help="include comment notes")
    size_args(p)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("template", help="lay out structured content (JSON) with a builder, no model involved")
    p.add_argument("kind", choices=("flowchart", "workflow", "pathway", "abstract", "poster", "prisma"))
    p.add_argument("content", help="JSON file; see docs/templates.md for the shape of each kind")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--theme", default=None, choices=sorted(THEMES))
    size_args(p)
    p.set_defaults(func=cmd_template)

    p = sub.add_parser("lint", help="check a figure for overlaps, clipped text and other layout problems")
    p.add_argument("figure")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("plot", help="table to chart, with statistics")
    p.add_argument("table", help="CSV, TSV, XLSX or JSON")
    p.add_argument("-o", "--output", required=True, help=".svg, .png, .pdf or .pptx (a native, editable chart where PowerPoint has one)")
    p.add_argument("--format", default=None, choices=("svg", "png", "pdf", "pptx"))
    p.add_argument("--sheet", default=None)
    p.add_argument("--kind", default=None, choices=PLOT_KINDS)
    p.add_argument("--x", default=None)
    p.add_argument("--y", action="append", default=None, help="repeat for several columns")
    p.add_argument("--group", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--xlabel", default=None)
    p.add_argument("--ylabel", default=None)
    p.add_argument("--error", default=None, choices=(*ERRORS, "none"))
    p.add_argument("--palette", default=None, choices=PALETTES)
    p.add_argument("--test", default=None, choices=("parametric", "nonparametric"))
    p.add_argument("--stats", action="store_true", help="compare the groups and draw significance brackets")
    p.add_argument("--fit", action="store_true", help="regression line (scatter)")
    p.add_argument("--logx", action="store_true")
    p.add_argument("--logy", action="store_true")
    p.add_argument("--no-points", action="store_true")
    p.add_argument("--spec", default=None, help="the whole chart description as JSON")
    p.add_argument("--ask", default=None, help="describe the chart in a sentence and let the configured model choose")
    p.add_argument("--theme", default=None, choices=sorted(THEMES))
    p.add_argument("--dpi", type=float, default=300.0)
    p.add_argument("--lang", choices=("en", "zh"), default="en")
    p.set_defaults(func=cmd_plot)

    p = sub.add_parser("vectorize", help="trace a bitmap into an editable SVG")
    p.add_argument("image")
    p.add_argument("-o", "--output", required=True, help=".svg, .json or .pptx")
    p.add_argument("--colors", type=int, default=6)
    p.add_argument("--detail", default="medium", choices=("low", "medium", "high"))
    p.add_argument("--no-smooth", action="store_true", help="keep straight polygon edges")
    p.add_argument("--split", action="store_true", help="one shape per island instead of one per colour")
    p.add_argument("--editable", action="store_true", help="write a Figwright SVG that reopens in the editor")
    p.set_defaults(func=cmd_vectorize)

    p = sub.add_parser("enhance", help="clean up a photo or scan and set its print size")
    p.add_argument("image")
    p.add_argument("-o", "--output", required=True, help=".png, .jpg, .tif or .webp")
    p.add_argument("--whiten", action="store_true", help="even out the lighting and whiten the paper")
    p.add_argument("--denoise", type=float, default=None, metavar="0..1")
    p.add_argument("--contrast", type=float, default=None, metavar="0..1")
    p.add_argument("--sharpen", type=float, default=None, metavar="0..1")
    p.add_argument("--remove-bg", action="store_true", help="make the background transparent")
    p.add_argument("--bg-tolerance", type=float, default=None, metavar="0..1")
    p.add_argument("--trim", action="store_true", help="cut away empty margins")
    p.add_argument("--upscale", type=float, default=None, metavar="1..4")
    p.add_argument("--width-mm", type=float, default=None)
    p.add_argument("--dpi", type=int, default=None)
    p.add_argument("--grayscale", action="store_true")
    p.set_defaults(func=cmd_enhance)

    p = sub.add_parser("config", help="show or change settings")
    p.add_argument("action", choices=("show", "providers", "set-key", "clear-key", "role"))
    p.add_argument("provider", nargs="?", default=None)
    p.add_argument("model", nargs="?", default=None)
    p.add_argument("extra", nargs="?", default=None)
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("doctor", help="check the installation")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("mcp", help="run the MCP server (for Claude, Codex and other MCP clients)")
    p.set_defaults(func=cmd_mcp)
    return ap


def main(argv: list[str] | None = None) -> int:
    from .config import ConfigError
    from .export_share import ExportError
    from .generate import GenerationError
    from .plot import PlotError
    from .providers import ProviderError
    from .raster import ImageError
    from .sources import SourceError

    argv = list(sys.argv[1:] if argv is None else argv)
    ap = build_parser()
    if not argv:
        argv = ["serve"]
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    try:
        return int(args.func(args) or 0)
    except (CliError, GenerationError, ProviderError, ConfigError, PlotError, ImageError, SourceError, ExportError) as exc:
        _say(f"figwright: {exc}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
