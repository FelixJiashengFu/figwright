"""The local web app: a small JSON API plus the static editor.

Security model, in short:

* The server listens on this computer only unless started with ``--allow-remote``.
* Requests must be addressed to a local host name (stops DNS-rebinding) and
  must not come from another web site (``Origin`` / ``Sec-Fetch-Site`` checks),
  so a page you visit cannot quietly drive the app or read your figures.
* With ``--allow-remote`` every request needs the access token printed at start-up.
* API keys are stored locally, shown masked, and never returned by any endpoint.
* Nothing a model writes is executed: models return data (a scene, a chart
  description) that is validated and drawn by this program.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import __version__, export_share, generate, offline, plot, raster, render, store, vectorize
from .builders import BUILDERS
from .config import PRESETS, ROLES, ConfigError, load_config, provider_settings, public_config, update_config
from .examples import EXAMPLES, TEMPLATE_FORMS
from .icons import icon_catalog
from .lint import autofix, lint
from .providers import ProviderError, make_provider
from .scene import EDGE_HEADS, EDGE_ROUTINGS, NODE_TYPES, normalize_scene
from .sources import SourceError, extract_text
from .themes import DEFAULT_THEME, THEMES, retheme

WEB_DIR = Path(__file__).parent / "web"
MAX_JSON = 80 * 1024 * 1024
MAX_UPLOAD = 40 * 1024 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
TOKEN_HEADER = "x-figwright-token"
TOKEN_COOKIE = "fw_token"
CSP = "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; font-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"

_PROVIDER_STATUS = {"auth": 502, "permission": 502, "not_found": 502, "rate_limit": 502, "refusal": 502, "network": 502, "server": 502, "empty": 502, "bad_request": 502, "unsupported": 400, "config": 400}
_STORE_STATUS = {"not_found": 404, "bad_id": 400, "conflict": 409, "too_large": 413, "damaged": 500}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def error_payload(exc: BaseException) -> tuple[int, dict]:
    """Map any exception to ``(http status, {"code", "message"})`` without leaking internals."""
    if isinstance(exc, ApiError):
        return exc.status, {"code": exc.code, "message": exc.message}
    if isinstance(exc, generate.GenerationError):
        return 422, {"code": exc.code, "message": str(exc)}
    if isinstance(exc, ProviderError):
        return _PROVIDER_STATUS.get(exc.code, 502), {"code": f"provider_{exc.code}", "message": str(exc)}
    if isinstance(exc, store.StoreError):
        return _STORE_STATUS.get(exc.code, 400), {"code": exc.code, "message": str(exc)}
    if isinstance(exc, (ConfigError, plot.PlotError, raster.ImageError, SourceError, export_share.ExportError)):
        return 400, {"code": type(exc).__name__.replace("Error", "").lower() or "bad_request", "message": str(exc)}
    if isinstance(exc, ValueError):
        return 400, {"code": "bad_request", "message": str(exc)[:400] or "The request could not be processed."}
    return 500, {"code": "internal", "message": f"Something went wrong inside Figwright ({type(exc).__name__}). The terminal window has the details."}


# ------------------------------------------------------------------------------------ jobs
class Jobs:
    """Long calls (a model can take a minute) run here; the browser polls for the result."""

    KEEP_SECONDS = 1800

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="figwright-job")

    def start(self, fn: Callable[[Callable[[str], None]], Any]) -> str:
        jid = secrets.token_urlsafe(12)
        job = {"status": "running", "stage": "queued", "created": time.time(), "result": None, "error": None, "cancelled": False}
        with self._lock:
            self._sweep()
            self._jobs[jid] = job

        def run() -> None:
            try:
                result = fn(lambda stage: job.__setitem__("stage", str(stage)))
                job.update(status="done", result=result)
            except Exception as exc:  # noqa: BLE001 - reported to the client
                status, payload = error_payload(exc)
                if status >= 500:
                    import traceback

                    traceback.print_exc()
                job.update(status="error", error=payload)
            finally:
                job["finished"] = time.time()

        self._pool.submit(run)
        return jid

    def _sweep(self) -> None:
        now = time.time()
        for jid in [k for k, j in self._jobs.items() if j.get("finished") and now - j["finished"] > self.KEEP_SECONDS]:
            self._jobs.pop(jid, None)

    def get(self, jid: str) -> dict:
        with self._lock:
            job = self._jobs.get(jid)
        if job is None:
            raise ApiError(404, "not_found", "This job no longer exists.")
        return job

    def view(self, jid: str) -> dict:
        job = self.get(jid)
        if job["cancelled"]:
            return {"status": "cancelled"}
        out = {"status": job["status"], "stage": job["stage"], "seconds": round(time.time() - job["created"], 1)}
        if job["status"] == "done":
            out["result"] = job["result"]
        elif job["status"] == "error":
            out["error"] = job["error"]
        return out

    def cancel(self, jid: str) -> None:
        self.get(jid)["cancelled"] = True  # the worker finishes, its result is discarded


# ---------------------------------------------------------------------------------- helpers
def _host_of(value: str) -> str:
    v = (value or "").strip().lower()
    if v.startswith("["):
        return v[1 : v.find("]")] if "]" in v else v
    return v.rsplit(":", 1)[0] if v.count(":") == 1 else v


def _attachment(name: str, ext: str) -> str:
    base = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", str(name or "")).strip().strip(".")[:80] or "figure"
    ascii_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip("_ ") or "figure"
    return f"attachment; filename=\"{ascii_name}.{ext}\"; filename*=UTF-8''{quote(base)}.{ext}"


def _file(data: bytes | str, media: str, name: str, ext: str, notes: list[str] | None = None, info: dict | None = None) -> Response:
    headers = {"Content-Disposition": _attachment(name, ext), "Cache-Control": "no-store"}
    if notes:
        headers["X-Figwright-Notes"] = quote(json.dumps(notes[:20], ensure_ascii=False))
    if info:
        headers["X-Figwright-Info"] = quote(json.dumps(info, ensure_ascii=False))
    return Response(content=data if isinstance(data, bytes) else data.encode("utf-8"), media_type=media, headers=headers)


async def _json(request: Request) -> dict:
    raw = await request.body()
    if len(raw) > MAX_JSON:
        raise ApiError(413, "too_large", "The request is too large.")
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "bad_json", "The request body is not valid JSON.") from None
    if not isinstance(data, dict):
        raise ApiError(400, "bad_json", "The request body must be a JSON object.")
    return data


async def _upload(file: UploadFile | None, limit: int = MAX_UPLOAD) -> tuple[str, bytes]:
    if file is None:
        raise ApiError(400, "no_file", "No file was sent.")
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise ApiError(413, "too_large", f"The file is larger than {limit // (1024 * 1024)} MB.")
    if not data:
        raise ApiError(400, "empty_file", "The file is empty.")
    return file.filename or "", data


def _scene(body: dict, key: str = "scene") -> dict:
    raw = body.get(key)
    if not isinstance(raw, dict):
        raise ApiError(400, "no_scene", "The request has no figure in it.")
    return normalize_scene(raw)


def _theme(value: Any) -> str | None:
    return value if isinstance(value, str) and value in THEMES else None


def _lang(value: Any, cfg: dict | None = None) -> str:
    if value in ("zh", "en"):
        return value
    return (cfg or load_config()).get("lang", "zh")


def _data_url(data: bytes) -> str:
    kind = "png"
    if data[:3] == b"\xff\xd8\xff":
        kind = "jpeg"
    elif data[:4] == b"RIFF":
        kind = "webp"
    elif data[:2] in (b"II", b"MM"):
        kind = "tiff"
    return f"data:image/{kind};base64,{base64.b64encode(data).decode('ascii')}"


def _from_data_url(value: Any) -> bytes:
    if not isinstance(value, str) or not value.startswith("data:image/") or ";base64," not in value[:64]:
        raise ApiError(400, "bad_image", "Expected an embedded image.")
    try:
        data = base64.b64decode(value.split(",", 1)[1], validate=False)
    except ValueError:
        raise ApiError(400, "bad_image", "The embedded image is damaged.") from None
    if len(data) > MAX_UPLOAD:
        raise ApiError(413, "too_large", "The image is too large.")
    return data


def _table(body: dict):
    csv = body.get("csv")
    if not isinstance(csv, str) or not csv.strip():
        raise ApiError(400, "no_table", "Load a table first.")
    return plot.load_table("table.csv", csv.encode("utf-8"))


def meta_payload(cfg: dict) -> dict:
    return {
        "version": __version__,
        "lang": cfg.get("lang", "zh"),
        "offline": {role: (cfg.get("roles", {}).get(role, {}).get("provider") or ("mock" if role != "vision" else cfg.get("roles", {}).get("text", {}).get("provider"))) == "mock" for role in ROLES},
        "themes": [{"id": k, "label": v["label"], "bg": v["bg"], "ink": v["ink"], "muted": v["muted"], "line": v["line"], "panel": v["panel"], "strong": v["strong"], "soft": v["soft"]} for k, v in THEMES.items()],
        "default_theme": DEFAULT_THEME,
        "kinds": list(offline.KINDS),
        "node_types": list(NODE_TYPES),
        "edge_heads": list(EDGE_HEADS),
        "edge_routings": list(EDGE_ROUTINGS),
        "qualities": list(generate.QUALITIES),
        "image_styles": list(generate.IMAGE_STYLES),
        "plot_kinds": list(plot.KINDS),
        "plot_errors": list(plot.ERRORS),
        "plot_palettes": list(plot.PALETTES),
        "vector_details": list(vectorize.DETAIL),
        "cvd_kinds": list(raster.CVD_KINDS),
        "sizes": {"zh": export_share.describe_sizes("zh"), "en": export_share.describe_sizes("en")},
        "examples": EXAMPLES,
        "templates": TEMPLATE_FORMS,
        "refine_help": offline.REFINE_HELP,
        "limits": {"upload_mb": MAX_UPLOAD // (1024 * 1024), "table_mb": plot.MAX_BYTES // (1024 * 1024)},
    }


# -------------------------------------------------------------------------------------- app
def create_app(token: str | None = None, allow_remote: bool = False) -> FastAPI:
    """Build the application. ``token`` protects every request; it is required with ``allow_remote``."""
    if allow_remote and not token:
        raise ValueError("Remote access needs an access token.")
    app = FastAPI(title="Figwright", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    jobs = Jobs()
    app.state.jobs = jobs

    def token_ok(request: Request) -> bool:
        if not token:
            return True
        offered = request.headers.get(TOKEN_HEADER) or request.cookies.get(TOKEN_COOKIE) or request.query_params.get("token") or ""
        return secrets.compare_digest(offered.encode("utf-8"), token.encode("utf-8"))

    @app.middleware("http")
    async def guard(request: Request, call_next):
        def deny(status: int, code: str, message: str) -> Response:
            return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)

        host = _host_of(request.headers.get("host", ""))
        if not allow_remote and host not in LOCAL_HOSTS:
            return deny(403, "bad_host", "Figwright only answers on this computer (localhost). Start it with --allow-remote to use it from other devices.")
        path = request.url.path
        api = path.startswith("/api/")
        unsafe = request.method not in ("GET", "HEAD", "OPTIONS")
        if api or unsafe:
            site = request.headers.get("sec-fetch-site")
            if site and site not in ("same-origin", "none"):
                return deny(403, "cross_site", "Requests from other web sites are not accepted.")
            origin = request.headers.get("origin")
            if origin is not None and (unsafe or api):
                parsed = urlparse(origin)
                if origin == "null" or parsed.netloc.lower() != request.headers.get("host", "").lower():
                    return deny(403, "cross_site", "Requests from other web sites are not accepted.")
        if token and (api or path == "/" or path.startswith("/static/")) and not token_ok(request):
            if api:
                return deny(401, "token", "This Figwright server needs its access token. Open the address printed in the terminal.")
            return HTMLResponse("<!doctype html><meta charset='utf-8'><title>Figwright</title><p style='font:16px sans-serif;margin:3em'>This Figwright server needs its access token. Open the full address printed in the terminal where it was started.</p>", status_code=401)
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_JSON:
            return deny(413, "too_large", "The request is too large.")
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if not api:
            response.headers.setdefault("Content-Security-Policy", CSP)
            response.headers.setdefault("Cache-Control", "no-cache")
        else:
            response.headers.setdefault("Cache-Control", "no-store")
        if token and request.query_params.get("token") and token_ok(request) and not request.cookies.get(TOKEN_COOKIE):
            response.set_cookie(TOKEN_COOKIE, token, httponly=True, samesite="strict", max_age=30 * 24 * 3600)
        return response

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    async def known_error(_request: Request, exc: Exception):
        status, payload = error_payload(exc)
        return JSONResponse({"error": payload}, status_code=status)

    for known in (generate.GenerationError, ProviderError, store.StoreError, ConfigError, plot.PlotError, raster.ImageError, SourceError, export_share.ExportError):
        app.add_exception_handler(known, known_error)

    @app.exception_handler(Exception)
    async def any_error(_request: Request, exc: Exception):
        status, payload = error_payload(exc)
        if status >= 500:
            import traceback

            traceback.print_exception(type(exc), exc, exc.__traceback__)
        return JSONResponse({"error": payload}, status_code=status)

    async def call(fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Run blocking work off the event loop; known errors become clean JSON answers."""
        try:
            return await run_in_threadpool(fn, *args, **kwargs)
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            status, payload = error_payload(exc)
            if status >= 500:
                import traceback

                traceback.print_exc()
            raise ApiError(status, payload["code"], payload["message"]) from exc

    # ---- pages -------------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response((WEB_DIR / "logo.svg").read_bytes(), media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"})

    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    # ---- basics ------------------------------------------------------------------------
    @app.get("/api/meta")
    def meta() -> dict:
        return meta_payload(load_config())

    @app.get("/api/icons")
    def icons() -> dict:
        return icon_catalog()

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    # ---- settings ----------------------------------------------------------------------
    @app.get("/api/config")
    def get_config() -> dict:
        return public_config(load_config())

    @app.put("/api/config")
    async def put_config(request: Request) -> dict:
        patch = await _json(request)
        return public_config(await call(lambda: update_config(load_config(), patch)))

    @app.post("/api/config/models")
    async def config_models(request: Request) -> dict:
        body = await _json(request)
        pid = str(body.get("provider") or "")

        def work() -> dict:
            if pid not in PRESETS:
                raise ApiError(400, "bad_provider", "Unknown provider.")
            provider = make_provider(provider_settings(load_config(), pid))
            try:
                return {"models": provider.list_models()[:400]}
            finally:
                provider.close()

        return await call(work)

    @app.post("/api/config/test")
    async def config_test(request: Request) -> dict:
        """One tiny request with the chosen model, started only by the user's click."""
        body = await _json(request)
        pid, model = str(body.get("provider") or ""), str(body.get("model") or "").strip()

        def work() -> dict:
            if pid not in PRESETS:
                raise ApiError(400, "bad_provider", "Unknown provider.")
            settings = provider_settings(load_config(), pid)
            settings["model"] = model or settings["default_model"]
            if settings["type"] != "mock" and not settings["model"]:
                raise ApiError(400, "no_model", "Choose a model first (the 'list models' button shows what the provider offers).")
            provider = make_provider(settings)
            started = time.time()
            try:
                if provider.offline:
                    return {"ok": True, "reply": "offline demo", "seconds": 0.0, "model": "offline-demo"}
                result = provider.chat("You are a connection test. Reply with the single word OK.", "Reply with OK.", json_mode=False, max_tokens=64)
                return {"ok": True, "reply": result.text.strip()[:80], "seconds": round(time.time() - started, 1), "model": result.model or settings["model"], "notes": result.notes}
            finally:
                provider.close()

        return await call(work)

    # ---- jobs --------------------------------------------------------------------------
    @app.get("/api/jobs/{jid}")
    def job_status(jid: str) -> dict:
        return jobs.view(jid)

    @app.delete("/api/jobs/{jid}")
    def job_cancel(jid: str) -> dict:
        jobs.cancel(jid)
        return {"ok": True}

    # ---- generation --------------------------------------------------------------------
    @app.post("/api/generate")
    async def api_generate(request: Request) -> dict:
        b = await _json(request)
        prompt, kind, quality, source = str(b.get("prompt") or ""), str(b.get("kind") or "auto"), str(b.get("quality") or "balanced"), str(b.get("source") or "")
        theme = _theme(b.get("theme"))
        return {"job": jobs.start(lambda progress: generate.generate_figure(prompt, kind=kind, theme=theme, quality=quality, source=source, progress=progress).to_dict())}

    @app.post("/api/refine")
    async def api_refine(request: Request) -> dict:
        b = await _json(request)
        scene = _scene(b)
        instruction = str(b.get("instruction") or "")
        selection = [str(s) for s in b.get("selection") or [] if isinstance(s, (str, int))][:200]
        return {"job": jobs.start(lambda progress: generate.refine_figure(scene, instruction, selection=selection or None, progress=progress).to_dict())}

    @app.post("/api/polish")
    async def api_polish(request: Request) -> dict:
        scene = _scene(await _json(request))
        return {"job": jobs.start(lambda progress: generate.polish_figure(scene, progress=progress).to_dict())}

    @app.post("/api/sketch")
    async def api_sketch(file: UploadFile = File(...), prompt: str = Form(""), theme: str = Form("")) -> dict:
        _name, data = await _upload(file)
        th = _theme(theme)
        return {"job": jobs.start(lambda progress: generate.sketch_to_figure(data, prompt=prompt, theme=th, progress=progress).to_dict())}

    @app.post("/api/illustrate")
    async def api_illustrate(prompt: str = Form(""), style: str = Form("flat"), size: str = Form("1024x1024"), theme: str = Form(""), reference: UploadFile | None = File(None)) -> dict:
        ref = (await _upload(reference))[1] if reference is not None and reference.filename else None
        if not re.fullmatch(r"\d{3,4}x\d{3,4}", size):
            size = "1024x1024"
        th = _theme(theme)
        return {"job": jobs.start(lambda progress: generate.illustrate(prompt, style=style, size=size, theme=th, reference=ref, progress=progress).to_dict())}

    @app.post("/api/redraw")
    async def api_redraw(request: Request) -> dict:
        b = await _json(request)
        image = _from_data_url(b.get("image"))
        box = b.get("box")
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
            raise ApiError(400, "bad_region", "Select the region to redraw.")
        prompt, style = str(b.get("prompt") or ""), str(b.get("style") or "flat")

        def work(progress: Callable[[str], None]) -> dict:
            png, info = generate.redraw_region(image, tuple(box), prompt, style=style, progress=progress)
            return {"image": _data_url(png), "info": info}

        return {"job": jobs.start(work)}

    @app.post("/api/source")
    async def api_source(file: UploadFile = File(...)) -> dict:
        name, data = await _upload(file)
        text, notes = await call(extract_text, name, data)
        return {"text": text, "chars": len(text), "notes": notes, "name": name}

    @app.post("/api/template")
    async def api_template(request: Request) -> dict:
        b = await _json(request)
        kind = str(b.get("kind") or "")
        content = b.get("content")
        if kind not in BUILDERS or not isinstance(content, dict):
            raise ApiError(400, "bad_template", "Unknown template.")
        theme = _theme(b.get("theme"))

        def work() -> dict:
            scene = BUILDERS[kind](content, theme)
            warnings = (scene.get("meta") or {}).get("warnings") or []
            scene = normalize_scene(scene)
            scene["kind"] = kind
            scene, fixes = autofix(scene, snap=False)
            generate.stamp(scene, "generate", "local", "template", kind=kind)
            return {"scene": scene, "kind": kind, "notes": fixes + [f"check: {w}" for w in warnings], "issues": lint(scene)}

        return await call(work)

    # ---- scene tools -------------------------------------------------------------------
    @app.post("/api/lint")
    async def api_lint(request: Request) -> dict:
        scene = _scene(await _json(request))
        return {"issues": await call(lint, scene)}

    @app.post("/api/autofix")
    async def api_autofix(request: Request) -> dict:
        b = await _json(request)
        scene = _scene(b)

        def work() -> dict:
            fixed, notes = autofix(scene, snap=b.get("snap") is not False)
            return {"scene": fixed, "notes": notes, "issues": lint(fixed)}

        return await call(work)

    @app.post("/api/retheme")
    async def api_retheme(request: Request) -> dict:
        b = await _json(request)
        theme = _theme(b.get("theme"))
        if not theme:
            raise ApiError(400, "bad_theme", "Unknown theme.")
        scene = _scene(b)
        return {"scene": await call(lambda: normalize_scene(retheme(scene, theme)))}

    @app.post("/api/normalize")
    async def api_normalize(request: Request) -> dict:
        return {"scene": _scene(await _json(request))}

    @app.post("/api/import")
    async def api_import(file: UploadFile = File(...), theme: str = Form("")) -> dict:
        name, data = await _upload(file)
        th = _theme(theme)

        def work() -> dict:
            low = name.lower()
            head = data[:2000].lstrip()
            notes: list[str] = []
            if low.endswith((".json", ".figwright")) or head[:1] == b"{":
                try:
                    raw = json.loads(data.decode("utf-8-sig"))
                except (ValueError, UnicodeDecodeError):
                    raise ApiError(400, "bad_file", "This file is not a Figwright figure (JSON could not be read).") from None
                if isinstance(raw, dict) and isinstance(raw.get("scene"), dict):
                    raw = raw["scene"]
                if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list):
                    raise ApiError(400, "bad_file", "This JSON file does not contain a figure.")
                return {"scene": normalize_scene(raw), "notes": notes, "editable": True}
            if low.endswith(".svg") or b"<svg" in head.lower():
                text = data.decode("utf-8", errors="replace")
                raw = render.extract_scene_from_svg(text)
                if raw is not None:
                    return {"scene": normalize_scene(raw), "notes": notes, "editable": True}
                png = render.foreign_svg_to_png(text)
                scene = normalize_scene(generate.image_scene(png, title=Path(name).stem[:120], theme=th))
                generate.stamp(scene, "import", "local", "svg")
                notes.append("this SVG was not made by Figwright, so it was placed as a picture: use Image lab > Vectorize to turn it into editable shapes")
                return {"scene": scene, "notes": notes, "editable": False}
            try:
                raster.open_image(data)
            except raster.ImageError as exc:
                raise ApiError(400, "bad_file", f"This file cannot be opened as a figure. Use a Figwright SVG / JSON file or a picture. ({exc})") from None
            # Browsers show PNG and JPEG everywhere; anything else (TIFF, BMP...) is converted once here.
            web_safe = data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"
            scene = normalize_scene(generate.image_scene(data if web_safe else raster.encode(raster.open_image(data), "png"), title=Path(name).stem[:120], theme=th))
            generate.stamp(scene, "import", "local", "image")
            return {"scene": scene, "notes": notes, "editable": False}

        return await call(work)

    @app.post("/api/export")
    async def api_export(request: Request) -> Response:
        b = await _json(request)
        scene = _scene(b)
        fmt = str(b.get("format") or "svg").lower()
        lang = _lang(b.get("lang"))
        name = str(b.get("name") or scene.get("title") or "figure")
        include_notes = bool(b.get("include_notes"))

        def num(key: str) -> float | None:
            v = b.get(key)
            return float(v) if isinstance(v, (int, float)) and v == v and v > 0 else None

        def work() -> Response:
            if fmt == "svg":
                return _file(render.render_svg(scene, include_notes=include_notes, embed_scene=b.get("embed") is not False), "image/svg+xml", name, "svg")
            if fmt == "json":
                return _file(json.dumps({"app": "figwright", "version": __version__, "scene": scene}, ensure_ascii=False, indent=1), "application/json", name, "figwright.json")
            if fmt == "pptx":
                from .export_pptx import scene_to_pptx

                data, notes = scene_to_pptx(scene, include_notes=include_notes, disclosure=export_share.disclosure(scene, lang) if b.get("disclosure") is not False else "")
                return _file(data, "application/vnd.openxmlformats-officedocument.presentationml.presentation", name, "pptx", notes)
            if fmt in ("html", "share"):
                return _file(export_share.share_html(scene, lang, include_notes=b.get("include_notes") is not False, record=b.get("record") is not False), "text/html; charset=utf-8", name, "html")
            if fmt == "record":
                return _file(export_share.record_html(scene, lang), "text/html; charset=utf-8", f"{name} record", "html")
            if fmt == "record-json":
                return _file(json.dumps(export_share.provenance_report(scene), ensure_ascii=False, indent=2), "application/json", f"{name} record", "json")
            if fmt in export_share.RASTER_FORMATS or fmt in ("jpg", "tif"):
                data, info = export_share.export_raster(scene, fmt, dpi=num("dpi") or 300.0, width_mm=num("width_mm"), scale=num("scale"), transparent=bool(b.get("transparent")))
                ext = {"jpeg": "jpg", "tiff": "tif"}.get(info["format"], info["format"])
                media = {"png": "image/png", "jpeg": "image/jpeg", "tiff": "image/tiff", "webp": "image/webp", "pdf": "application/pdf"}[info["format"]]
                return _file(data, media, name, ext, [info["note"]] if info.get("note") else None, info)
            raise ApiError(400, "bad_format", f"Unknown export format {fmt!r}.")

        return await call(work)

    @app.post("/api/disclosure")
    async def api_disclosure(request: Request) -> dict:
        scene = _scene(await _json(request))
        return {"zh": export_share.disclosure(scene, "zh"), "en": export_share.disclosure(scene, "en"), "models": export_share.ai_models(scene), "steps": export_share.provenance(scene)}

    # ---- charts ------------------------------------------------------------------------
    def table_payload(df, notes: list[str] | None = None, sheets: list[str] | None = None) -> dict:
        preview = df.head(12)
        return {
            "csv": plot.table_csv(df),
            "columns": plot.describe(df),
            "rows": int(len(df)),
            "preview": {"columns": [str(c) for c in preview.columns], "rows": [["" if v != v or v is None else (round(float(v), 6) if isinstance(v, float) else str(v)) for v in row] for row in preview.itertuples(index=False, name=None)]},
            "sheets": sheets or [],
            "notes": notes or [],
        }

    @app.post("/api/plot/table")
    async def plot_table(file: UploadFile | None = File(None), text: str = Form(""), sheet: str = Form("")) -> dict:
        if file is not None and file.filename:
            name, data = await _upload(file, plot.MAX_BYTES)
        elif text.strip():
            name, data = "pasted.txt", text.encode("utf-8")
        else:
            raise ApiError(400, "no_table", "Choose a file or paste a table.")

        def work() -> dict:
            df = plot.load_table(name, data, sheet or None)
            notes = []
            if len(df) > 20000:
                notes.append(f"the table has {len(df)} rows; charts stay fast up to roughly 20000")
            return table_payload(df, notes, plot.sheet_names(name, data))

        return await call(work)

    @app.post("/api/plot/render")
    async def plot_render(request: Request) -> dict:
        b = await _json(request)
        theme = _theme(b.get("theme"))
        lang = _lang(b.get("lang"))

        def work() -> dict:
            df = _table(b)
            spec = b.get("spec") if isinstance(b.get("spec"), dict) else {}
            svg, info = plot.render_plot(df, spec, theme, "svg")
            return {"svg": svg.decode("utf-8"), "spec": info["spec"], "stats": info.get("stats"), "fit": info.get("fit"), "counts": info.get("counts"), "notes": info.get("notes") or [], "caption": {"zh": plot.caption(info, "zh"), "en": plot.caption(info, "en")}, "lang": lang}

        return await call(work)

    @app.post("/api/plot/suggest")
    async def plot_suggest(request: Request) -> dict:
        b = await _json(request)
        prompt = str(b.get("prompt") or "")
        current = b.get("spec") if isinstance(b.get("spec"), dict) and b.get("spec") else None
        df = await call(_table, b)

        def work(progress: Callable[[str], None]) -> dict:
            spec, info = generate.suggest_plot(prompt, plot.describe(df), current, progress=progress)
            return {"spec": plot.normalize_spec(spec, df), "info": info}

        return {"job": jobs.start(work)}

    @app.post("/api/plot/export")
    async def plot_export(request: Request) -> Response:
        b = await _json(request)
        theme = _theme(b.get("theme"))
        fmt = str(b.get("format") or "svg").lower()
        lang = _lang(b.get("lang"))

        def work() -> Response:
            df = _table(b)
            spec = b.get("spec") if isinstance(b.get("spec"), dict) else {}
            name = str(spec.get("title") or "chart")
            if fmt == "pptx":
                from .export_pptx import plot_to_pptx

                _svg, info = plot.render_plot(df, spec, theme, "svg")
                data, notes = plot_to_pptx(df, spec, theme, caption=plot.caption(info, lang))
                return _file(data, "application/vnd.openxmlformats-officedocument.presentationml.presentation", name, "pptx", notes)
            if fmt not in ("svg", "png", "pdf"):
                raise ApiError(400, "bad_format", f"Unknown chart format {fmt!r}.")
            dpi = b.get("dpi")
            data, _info = plot.render_plot(df, spec, theme, fmt, dpi=int(max(72, min(1200, dpi))) if isinstance(dpi, (int, float)) else 300)
            return _file(data, {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}[fmt], name, fmt)

        return await call(work)

    @app.post("/api/plot/image")
    async def plot_image(request: Request) -> dict:
        """The chart as a picture to drop onto the canvas (for multi-panel figures)."""
        b = await _json(request)
        theme = _theme(b.get("theme"))

        def work() -> dict:
            df = _table(b)
            spec = b.get("spec") if isinstance(b.get("spec"), dict) else {}
            png, info = plot.render_plot(df, spec, theme, "png", dpi=200)
            return {"image": _data_url(png), "width": info["spec"]["width"] * 96, "height": info["spec"]["height"] * 96, "title": info["spec"]["title"]}

        return await call(work)

    # ---- image lab ---------------------------------------------------------------------
    @app.post("/api/image/enhance")
    async def image_enhance(file: UploadFile = File(...), options: str = Form("{}")) -> dict:
        _name, data = await _upload(file)
        try:
            opts = json.loads(options)
        except ValueError:
            raise ApiError(400, "bad_json", "The options are not valid JSON.") from None

        def work() -> dict:
            out, info = raster.enhance(data, opts if isinstance(opts, dict) else {})
            preview = out
            if info.get("format") == "tiff":  # browsers cannot show TIFF
                preview = raster.encode(raster.open_image(out), "png")
            return {"image": _data_url(out), "preview": _data_url(preview) if preview is not out else None, "info": info}

        return await call(work)

    @app.post("/api/image/vectorize")
    async def image_vectorize(file: UploadFile = File(...), colors: int = Form(6), detail: str = Form("medium"), smooth: bool = Form(True), split: bool = Form(False), theme: str = Form("")) -> dict:
        name, data = await _upload(file)
        th = _theme(theme)

        def work() -> dict:
            result = vectorize.vectorize(data, colors=int(max(2, min(vectorize.MAX_COLORS, colors))), detail=detail if detail in vectorize.DETAIL else "medium", smooth=bool(smooth))
            scene = vectorize.vector_scene(result, theme=th, title=Path(name).stem[:120], split=bool(split))
            generate.stamp(scene, "vectorize", "local", "tracer", colors=len(result["colors"]))
            return {"svg": result["svg"], "scene": scene, "info": {"width": result["width"], "height": result["height"], "colors": result["colors"], "points": result["points"], "error": result["error"], "notes": result["notes"], "layers": len(result["layers"])}}

        return await call(work)

    # ---- projects ----------------------------------------------------------------------
    @app.get("/api/projects")
    def projects() -> dict:
        return {"projects": store.list_projects()}

    @app.post("/api/projects")
    async def project_create(request: Request) -> dict:
        b = await _json(request)
        scene = _scene(b)
        return await call(store.create_project, b.get("name"), scene)

    @app.get("/api/projects/{pid}")
    def project_get(pid: str) -> dict:
        return store.load_project(pid)

    @app.put("/api/projects/{pid}")
    async def project_put(pid: str, request: Request) -> dict:
        b = await _json(request)
        scene = _scene(b) if b.get("scene") is not None else None
        base = b.get("base_rev")
        return await call(store.save_project, pid, scene, b.get("name"), int(base) if isinstance(base, int) else None, bool(b.get("snapshot")), str(b.get("label") or ""))

    @app.delete("/api/projects/{pid}")
    def project_delete(pid: str) -> dict:
        store.delete_project(pid)
        return {"ok": True}

    @app.post("/api/projects/{pid}/duplicate")
    def project_duplicate(pid: str) -> dict:
        return store.duplicate_project(pid)

    @app.get("/api/projects/{pid}/thumb.svg")
    def project_thumb(pid: str) -> Response:
        scene = store.load_project(pid)["scene"]
        return Response(render.render_svg(scene, embed_scene=False), media_type="image/svg+xml", headers={"Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'", "Cache-Control": "no-store"})

    @app.get("/api/projects/{pid}/versions")
    def project_versions(pid: str) -> dict:
        return {"versions": store.list_versions(pid)}

    @app.post("/api/projects/{pid}/versions")
    async def project_snapshot(pid: str, request: Request) -> dict:
        b = await _json(request)
        return {"versions": await call(store.snapshot_project, pid, str(b.get("label") or ""))}

    @app.get("/api/projects/{pid}/versions/{index}")
    def project_version(pid: str, index: int) -> dict:
        return store.load_version(pid, index)

    return app
