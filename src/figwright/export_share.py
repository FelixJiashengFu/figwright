"""Exports that leave the app: bitmaps at journal size, PDF, a share page and the provenance record.

The share page is one self-contained HTML file. Nothing is uploaded anywhere:
you send the file itself (mail, chat, a shared drive). It carries a strict
Content-Security-Policy, loads nothing from the network and keeps the editable
scene inside its SVG, so the recipient can drop the downloaded SVG back into
Figwright and continue editing.

The provenance record is a plain statement of what the tool logged (which
steps ran, with which provider and model, and when). It is not a licence, a
legal certificate or proof of originality, and the page says so.
"""

from __future__ import annotations

import base64
import hashlib
import html
import io
import json
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .render import render_png, render_svg, svg_to_png
from .scene import scene_hash

RASTER_FORMATS = ("png", "jpeg", "tiff", "webp", "pdf")
MAX_PIXELS = 120_000_000  # refuse exports beyond this (about 11000 x 11000)

# Common figure widths, in millimetres. Journals differ: always check the author guidelines.
SIZE_PRESETS = {
    "single": {"mm": 89.0, "label": {"en": "Single column (89 mm)", "zh": "单栏（89 mm）"}},
    "onehalf": {"mm": 120.0, "label": {"en": "1.5 columns (120 mm)", "zh": "一栏半（120 mm）"}},
    "double": {"mm": 183.0, "label": {"en": "Double column (183 mm)", "zh": "双栏（183 mm）"}},
    "slide": {"mm": 254.0, "label": {"en": "Slide width (254 mm)", "zh": "幻灯片宽（254 mm）"}},
}

_ACTIONS = {
    "en": {"generate": "Generated from a text description", "refine": "Edited by instruction", "polish": "Layout polished", "sketch": "Redrawn from a sketch", "illustrate": "Illustration generated", "redraw": "Region redrawn", "vectorize": "Bitmap traced to vectors", "plot": "Chart drawn from a table", "import": "Imported"},
    "zh": {"generate": "由文字描述生成", "refine": "按指令修改", "polish": "版面润色", "sketch": "由草图重绘", "illustrate": "生成插画", "redraw": "局部重绘", "vectorize": "位图描摹为矢量", "plot": "由数据表绘制图表", "import": "导入"},
}
_LOCAL = ("offline", "mock", "local", "")


class ExportError(ValueError):
    """The requested export is not possible; the message is safe to show."""


# ---------------------------------------------------------------------------- provenance
def provenance(scene: dict) -> list[dict]:
    log = (scene.get("meta") or {}).get("provenance")
    return [e for e in log if isinstance(e, dict)] if isinstance(log, list) else []


def ai_models(scene: dict) -> list[str]:
    """Distinct ``provider / model`` pairs of generative steps that used a real model."""
    out: list[str] = []
    for e in provenance(scene):
        provider, model = str(e.get("provider") or ""), str(e.get("model") or "")
        if provider.lower() in _LOCAL or model.lower() in _LOCAL:
            continue
        name = f"{provider} / {model}"
        if name not in out:
            out.append(name)
    return out


def disclosure(scene: dict, lang: str = "en") -> str:
    """One sentence for a methods section or figure legend, built from the provenance log."""
    models = ai_models(scene)
    tool = f"Figwright {__version__}"
    if lang == "zh":
        if models:
            return f"本图使用开源工具 {tool} 制作，其中部分内容由生成式 AI 模型（{'；'.join(models)}）辅助生成，并经作者人工核对与修改。"
        return f"本图使用开源工具 {tool} 制作，制作过程未调用生成式 AI 模型。"
    if models:
        return f"This figure was prepared with the open-source tool {tool}; parts of it were generated with the assistance of generative AI ({'; '.join(models)}) and were reviewed and edited by the authors."
    return f"This figure was prepared with the open-source tool {tool}. No generative AI model was used."


def provenance_report(scene: dict) -> dict:
    """Machine-readable record: figure fingerprint, logged steps and the disclosure sentences."""
    return {
        "tool": f"Figwright {__version__}",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": scene.get("title") or "",
        "kind": scene.get("kind") or "",
        "size": [scene.get("width"), scene.get("height")],
        "elements": {"nodes": len(scene.get("nodes", [])), "edges": len(scene.get("edges", []))},
        "fingerprint_sha256": scene_hash(scene),
        "ai_models": ai_models(scene),
        "steps": provenance(scene),
        "disclosure": {"en": disclosure(scene, "en"), "zh": disclosure(scene, "zh")},
        "notice": "This record lists what the tool logged. It is not a licence, a certificate of originality or legal advice. Check your journal's policy on AI-generated figures.",
    }


_PAGE_CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#f4f5f8;color:#1f2a44;font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:#66708a;font-size:13px;margin-bottom:18px}
.card{background:#fff;border:1px solid #dfe3ec;border-radius:12px;padding:18px;margin-bottom:18px}
.fig{overflow:auto;text-align:center}
.fig svg{max-width:100%;height:auto}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
button{font:inherit;padding:7px 14px;border-radius:8px;border:1px solid #c9cfdd;background:#fff;color:#1f2a44;cursor:pointer}
button:hover{background:#eef1f7}
h2{font-size:15px;margin:0 0 10px}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{text-align:left;padding:6px 8px;border-bottom:1px solid #eceff5;vertical-align:top}
th{color:#66708a;font-weight:600}
.note{color:#66708a;font-size:12.5px;margin-top:10px}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;word-break:break-all}
blockquote{margin:8px 0;padding:8px 12px;background:#f6f7fb;border-left:3px solid #e2a23b;border-radius:4px}
ul{margin:6px 0;padding-left:20px}
@media print{body{background:#fff}.bar{display:none}.card{border:none;padding:0}}
"""

_T = {
    "en": {
        "shared": "Shared figure",
        "made": "Made with Figwright",
        "dl_svg": "Download SVG (editable)",
        "dl_png": "Download PNG",
        "print": "Print / save as PDF",
        "comments": "Comments",
        "record": "How this figure was made",
        "when": "When (UTC)",
        "what": "Step",
        "with": "Provider / model",
        "none": "No generative step was logged for this figure.",
        "disclosure": "Suggested disclosure sentence",
        "fingerprint": "Figure fingerprint (SHA-256)",
        "notice": "This record lists what the tool logged. It is not a licence, a certificate of originality or legal advice. Policies on AI-generated figures differ between journals: check the one you submit to.",
        "reopen": "To keep editing, download the SVG and open it in Figwright: the editable scene travels inside the file.",
        "record_title": "Provenance record",
        "local": "local, no model",
    },
    "zh": {
        "shared": "分享的图",
        "made": "由 Figwright（图匠）制作",
        "dl_svg": "下载 SVG（可继续编辑）",
        "dl_png": "下载 PNG",
        "print": "打印 / 存为 PDF",
        "comments": "批注",
        "record": "这张图是怎么做出来的",
        "when": "时间（UTC）",
        "what": "步骤",
        "with": "服务商 / 模型",
        "none": "这张图没有记录到任何生成式步骤。",
        "disclosure": "建议的 AI 使用声明",
        "fingerprint": "图的指纹（SHA-256）",
        "notice": "这份记录只是如实列出工具留下的日志，它不是授权书，不是原创性证明，也不是法律意见。各期刊对 AI 生成图片的规定不同，投稿前请以目标期刊的政策为准。",
        "reopen": "想继续编辑：下载 SVG 后在 Figwright 里打开，可编辑的场景数据就在文件里。",
        "record_title": "制作记录",
        "local": "本地，未调用模型",
    },
}


def _steps_table(scene: dict, lang: str) -> str:
    t = _T[lang]
    steps = provenance(scene)
    if not steps:
        return f'<p class="note">{html.escape(t["none"])}</p>'
    rows = []
    for e in steps:
        action = _ACTIONS[lang].get(str(e.get("action")), str(e.get("action") or ""))
        provider, model = str(e.get("provider") or ""), str(e.get("model") or "")
        who = t["local"] if provider.lower() in _LOCAL or model.lower() in _LOCAL else f"{provider} / {model}"
        rows.append(f"<tr><td>{html.escape(str(e.get('at') or ''))}</td><td>{html.escape(action)}</td><td>{html.escape(who)}</td></tr>")
    return f'<table><tr><th>{html.escape(t["when"])}</th><th>{html.escape(t["what"])}</th><th>{html.escape(t["with"])}</th></tr>{"".join(rows)}</table>'


def _record_card(scene: dict, lang: str) -> str:
    t = _T[lang]
    return (
        f'<section class="card"><h2>{html.escape(t["record"])}</h2>{_steps_table(scene, lang)}'
        f'<h2 style="margin-top:16px">{html.escape(t["disclosure"])}</h2><blockquote>{html.escape(disclosure(scene, lang))}</blockquote>'
        f'<p class="note">{html.escape(t["fingerprint"])}: <code>{scene_hash(scene)}</code></p>'
        f'<p class="note">{html.escape(t["notice"])}</p></section>'
    )


def _csp(script: str = "") -> str:
    src = "'none'"
    if script:
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
        src = f"'sha256-{digest}'"
    return f"default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src {src}; base-uri 'none'; form-action 'none'"


_SHARE_JS = """(function(){
var svg=document.querySelector('.fig svg');if(!svg)return;
var name=(document.title||'figure').replace(/[^\\w\\u4e00-\\u9fff-]+/g,'_').slice(0,60)||'figure';
function text(){return new XMLSerializer().serializeToString(svg);}
function save(blob,ext){var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name+'.'+ext;document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},800);}
document.getElementById('dl-svg').addEventListener('click',function(){save(new Blob([text()],{type:'image/svg+xml'}),'svg');});
document.getElementById('dl-png').addEventListener('click',function(){
var vb=svg.viewBox.baseVal,k=Math.min(3,Math.sqrt(16e6/(vb.width*vb.height)));
var img=new Image();var url=URL.createObjectURL(new Blob([text()],{type:'image/svg+xml'}));
img.onload=function(){var c=document.createElement('canvas');c.width=Math.round(vb.width*k);c.height=Math.round(vb.height*k);var g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,c.width,c.height);g.drawImage(img,0,0,c.width,c.height);URL.revokeObjectURL(url);c.toBlob(function(b){if(b)save(b,'png');},'image/png');};
img.src=url;});
document.getElementById('do-print').addEventListener('click',function(){window.print();});
})();"""


def share_html(scene: dict, lang: str = "en", include_notes: bool = True, record: bool = True) -> str:
    """A self-contained page showing the figure, its comments and (optionally) how it was made."""
    lang = "zh" if lang == "zh" else "en"
    t = _T[lang]
    title = str(scene.get("title") or t["shared"])
    svg = render_svg(scene, include_notes=False, embed_scene=True)
    comments = [n for n in scene.get("nodes", []) if n.get("type") == "note" and n.get("text")] if include_notes else []
    parts = [
        "<!doctype html>",
        f'<html lang="{"zh-CN" if lang == "zh" else "en"}"><head><meta charset="utf-8">',
        f'<meta http-equiv="Content-Security-Policy" content="{_csp(_SHARE_JS)}">',
        '<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer">',
        f"<title>{html.escape(title)}</title><style>{_PAGE_CSS}</style></head><body><main>",
        f'<h1>{html.escape(title)}</h1><div class="sub">{html.escape(t["made"])} {__version__}</div>',
        f'<section class="card"><div class="fig">{svg}</div><div class="bar">'
        f'<button id="dl-svg" type="button">{html.escape(t["dl_svg"])}</button><button id="dl-png" type="button">{html.escape(t["dl_png"])}</button>'
        f'<button id="do-print" type="button">{html.escape(t["print"])}</button></div><p class="note">{html.escape(t["reopen"])}</p></section>',
    ]
    if comments:
        items = "".join(f"<li>{('<b>' + html.escape(str(n.get('author'))) + '</b>: ') if n.get('author') else ''}{html.escape(str(n['text']))}</li>" for n in comments)
        parts.append(f'<section class="card"><h2>{html.escape(t["comments"])}</h2><ul>{items}</ul></section>')
    if record:
        parts.append(_record_card(scene, lang))
    parts.append(f"</main><script>{_SHARE_JS}</script></body></html>")
    return "".join(parts)


def record_html(scene: dict, lang: str = "en") -> str:
    """Printable provenance record (use the browser's "save as PDF" for a PDF copy)."""
    lang = "zh" if lang == "zh" else "en"
    t = _T[lang]
    title = str(scene.get("title") or t["shared"])
    thumb = base64.b64encode(svg_to_png(render_svg(scene, embed_scene=False), scale=min(2.0, 900.0 / max(1.0, float(scene.get("width", 1200)))))).decode("ascii")
    report = html.escape(json.dumps(provenance_report(scene), ensure_ascii=False, indent=2))
    return "".join(
        [
            "<!doctype html>",
            f'<html lang="{"zh-CN" if lang == "zh" else "en"}"><head><meta charset="utf-8">',
            f'<meta http-equiv="Content-Security-Policy" content="{_csp()}"><meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{html.escape(t['record_title'])}: {html.escape(title)}</title><style>{_PAGE_CSS}</style></head><body><main>",
            f'<h1>{html.escape(t["record_title"])}</h1><div class="sub">{html.escape(title)} · Figwright {__version__} · {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</div>',
            f'<section class="card"><div class="fig"><img alt="" style="max-width:100%;max-height:420px" src="data:image/png;base64,{thumb}"></div></section>',
            _record_card(scene, lang),
            f'<section class="card"><h2>JSON</h2><pre style="white-space:pre-wrap;font-size:12px;margin:0"><code>{report}</code></pre></section>',
            "</main></body></html>",
        ]
    )


# ------------------------------------------------------------------------------- bitmaps
def raster_scale(scene: dict, dpi: float = 300.0, width_mm: float | None = None, scale: float | None = None) -> tuple[float, int, int]:
    """Zoom factor and pixel size for a bitmap export.

    With ``width_mm`` the figure is exactly that wide at ``dpi``. Without it the
    scene's own size is read as CSS pixels (96 per inch), unless ``scale`` is given.
    """
    w, h = float(scene.get("width", 1200)), float(scene.get("height", 800))
    if width_mm:
        k = (float(width_mm) / 25.4 * float(dpi)) / w
    elif scale:
        k = float(scale)
    else:
        k = float(dpi) / 96.0
    k = max(0.05, k)
    pw, ph = int(round(w * k)), int(round(h * k))
    if pw * ph > MAX_PIXELS or max(pw, ph) > 16000:
        raise ExportError(f"That would be {pw} x {ph} pixels, which is more than this export allows. Lower the dpi or the width.")
    return k, pw, ph


def export_raster(scene: dict, fmt: str = "png", dpi: float = 300.0, width_mm: float | None = None, scale: float | None = None, transparent: bool = False, quality: int = 92) -> tuple[bytes, dict]:
    """Render the figure to PNG / JPEG / TIFF / WebP / (bitmap) PDF with the resolution tag set.

    Returns ``(bytes, info)``; info has the pixel size, the physical size in mm and the dpi.
    """
    from PIL import Image

    fmt = {"jpg": "jpeg", "tif": "tiff"}.get(fmt.lower(), fmt.lower())
    if fmt not in RASTER_FORMATS:
        raise ExportError(f"Unknown format {fmt!r}. Available: {', '.join(RASTER_FORMATS)}.")
    dpi = max(36.0, min(1200.0, float(dpi)))
    k, pw, ph = raster_scale(scene, dpi, width_mm, scale)
    src = scene
    if transparent and fmt in ("png", "tiff", "webp"):
        src = dict(scene, background="none")
    png = render_png(src, scale=k)
    img = Image.open(io.BytesIO(png))
    img.load()
    out_dpi = dpi if (width_mm or not scale) else 96.0 * k
    info = {"format": fmt, "width": img.width, "height": img.height, "dpi": round(out_dpi, 1), "mm": [round(img.width / out_dpi * 25.4, 1), round(img.height / out_dpi * 25.4, 1)]}
    if fmt == "png" and not transparent:
        img = img.convert("RGB")
    if fmt in ("jpeg", "pdf") or (fmt != "png" and not transparent):
        flat = Image.new("RGB", img.size, "white")
        flat.paste(img, mask=img.getchannel("A") if img.mode == "RGBA" else None)
        img = flat
    buf = io.BytesIO()
    if fmt == "png":
        img.save(buf, "PNG", dpi=(out_dpi, out_dpi), optimize=True)
    elif fmt == "jpeg":
        img.save(buf, "JPEG", dpi=(out_dpi, out_dpi), quality=int(max(40, min(100, quality))), subsampling=0, optimize=True)
    elif fmt == "tiff":
        img.save(buf, "TIFF", dpi=(out_dpi, out_dpi), compression="tiff_lzw")
    elif fmt == "webp":
        img.save(buf, "WEBP", quality=int(max(40, min(100, quality))), method=4)
    else:
        img.save(buf, "PDF", resolution=out_dpi, title=str(scene.get("title") or "Figure"), producer=f"Figwright {__version__}")
        info["note"] = "This PDF holds a bitmap. For a vector PDF, use Print in the editor (it sets the page to the figure size) or convert the SVG."
    info["bytes"] = buf.tell()
    return buf.getvalue(), info


def print_html(scene: dict) -> str:
    """A page that prints the figure as vectors on a sheet of exactly the figure's size."""
    w, h = float(scene.get("width", 1200)), float(scene.get("height", 800))
    wmm, hmm = w / 96.0 * 25.4, h / 96.0 * 25.4
    svg = render_svg(scene, include_notes=False, embed_scene=False)
    js = "window.addEventListener('load',function(){setTimeout(function(){window.print();},250);});"
    css = f"@page{{size:{wmm:.2f}mm {hmm:.2f}mm;margin:0}}html,body{{margin:0;padding:0;background:#fff}}svg{{display:block;width:{wmm:.2f}mm;height:{hmm:.2f}mm}}"
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{_csp(js)}">'
        f"<title>{html.escape(str(scene.get('title') or 'Figure'))}</title><style>{css}</style></head><body>{svg}<script>{js}</script></body></html>"
    )


def describe_sizes(lang: str = "en") -> list[dict[str, Any]]:
    lang = "zh" if lang == "zh" else "en"
    return [{"id": k, "mm": v["mm"], "label": v["label"][lang]} for k, v in SIZE_PRESETS.items()]
