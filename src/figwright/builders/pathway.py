"""Signalling pathway: entities sorted into cell compartments, relations as arrows."""

from __future__ import annotations

from typing import Any

from ..layout import layered_layout
from .common import MARGIN, Canvas, as_list, clean, has_cjk, slug

# entity type -> (node type, soft colour slot; -1 = neutral panel)
TYPES = {
    "ligand": ("ellipse", 1),
    "receptor": ("rect", 0),
    "protein": ("rect", 0),
    "kinase": ("ellipse", 2),
    "tf": ("hexagon", 4),
    "gene": ("rect", 5),
    "rna": ("parallelogram", 5),
    "complex": ("rect", 3),
    "molecule": ("ellipse", 5),
    "drug": ("pill", 3),
    "process": ("rect", -1),
}
_TYPE_ALIASES = {
    "hormone": "ligand",
    "cytokine": "ligand",
    "growth factor": "ligand",
    "growth_factor": "ligand",
    "antigen": "ligand",
    "channel": "receptor",
    "transporter": "receptor",
    "gpcr": "receptor",
    "enzyme": "kinase",
    "phosphatase": "kinase",
    "protease": "kinase",
    "gtpase": "kinase",
    "transcription factor": "tf",
    "transcription_factor": "tf",
    "transcriptionfactor": "tf",
    "dna": "gene",
    "promoter": "gene",
    "mrna": "rna",
    "mirna": "rna",
    "lncrna": "rna",
    "metabolite": "molecule",
    "small molecule": "molecule",
    "small_molecule": "molecule",
    "ion": "molecule",
    "second messenger": "molecule",
    "second_messenger": "molecule",
    "lipid": "molecule",
    "inhibitor": "drug",
    "compound": "drug",
    "antibody": "drug",
    "phenotype": "process",
    "outcome": "process",
    "response": "process",
    "effect": "process",
    "adaptor": "protein",
    "adapter": "protein",
    "scaffold": "protein",
}

BANDS = {"extracellular": 0, "membrane": 1, "cytoplasm": 2, "nucleus": 3, "outcome": 4}
_LOCATION_ALIASES = {
    "outside": "extracellular",
    "ecm": "extracellular",
    "extracellular space": "extracellular",
    "extracellular_space": "extracellular",
    "serum": "extracellular",
    "plasma membrane": "membrane",
    "plasma_membrane": "membrane",
    "cell membrane": "membrane",
    "cell_membrane": "membrane",
    "cell surface": "membrane",
    "surface": "membrane",
    "cytosol": "cytoplasm",
    "cytoplasmic": "cytoplasm",
    "intracellular": "cytoplasm",
    "mitochondria": "cytoplasm",
    "mitochondrion": "cytoplasm",
    "er": "cytoplasm",
    "nuclear": "nucleus",
    "phenotype": "outcome",
    "cellular response": "outcome",
    "response": "outcome",
    "胞外": "extracellular",
    "细胞外": "extracellular",
    "细胞膜": "membrane",
    "膜": "membrane",
    "胞质": "cytoplasm",
    "细胞质": "cytoplasm",
    "胞浆": "cytoplasm",
    "细胞核": "nucleus",
    "核": "nucleus",
    "核内": "nucleus",
    "表型": "outcome",
    "结局": "outcome",
}
_DEFAULT_LOCATION = {"ligand": "extracellular", "drug": "extracellular", "receptor": "membrane", "tf": "nucleus", "gene": "nucleus", "process": "outcome"}

# relation -> (line ending, dashed)
RELATIONS = {
    "activate": ("arrow", False),
    "inhibit": ("inhibit", False),
    "bind": ("none", False),
    "translocate": ("arrow", True),
    "indirect": ("arrow", True),
    "indirect_inhibit": ("inhibit", True),
}
_REL_ALIASES = {
    "activation": "activate",
    "activates": "activate",
    "stimulate": "activate",
    "promote": "activate",
    "promotes": "activate",
    "induce": "activate",
    "induces": "activate",
    "phosphorylate": "activate",
    "phosphorylates": "activate",
    "upregulate": "activate",
    "express": "activate",
    "transcribe": "activate",
    "translate": "activate",
    "produce": "activate",
    "recruit": "activate",
    "arrow": "activate",
    "+": "activate",
    "->": "activate",
    "inhibition": "inhibit",
    "inhibits": "inhibit",
    "repress": "inhibit",
    "represses": "inhibit",
    "suppress": "inhibit",
    "block": "inhibit",
    "blocks": "inhibit",
    "downregulate": "inhibit",
    "degrade": "inhibit",
    "antagonize": "inhibit",
    "-|": "inhibit",
    "-": "inhibit",
    "binding": "bind",
    "binds": "bind",
    "associate": "bind",
    "interact": "bind",
    "complex": "bind",
    "none": "bind",
    "transport": "translocate",
    "translocation": "translocate",
    "move": "translocate",
    "secrete": "translocate",
    "import": "translocate",
    "export": "translocate",
    "indirect_activate": "indirect",
    "indirect activation": "indirect",
    "indirect inhibition": "indirect_inhibit",
}

_LABELS = {
    "en": {
        "extracellular": "Extracellular",
        "membrane": "Membrane",
        "cytoplasm": "Cytoplasm",
        "nucleus": "Nucleus",
        "outcome": "Outcome",
        "activate": "activation",
        "inhibit": "inhibition",
        "bind": "binding",
        "indirect": "indirect / translocation",
        "indirect_inhibit": "indirect inhibition",
    },
    "zh": {
        "extracellular": "胞外",
        "membrane": "细胞膜",
        "cytoplasm": "胞质",
        "nucleus": "细胞核",
        "outcome": "表型",
        "activate": "激活",
        "inhibit": "抑制",
        "bind": "结合",
        "indirect": "间接作用 / 转位",
        "indirect_inhibit": "间接抑制",
    },
}

GUTTER = 104.0


def _entity_size(c: Canvas, etype: str, text: str, fs: float) -> tuple[float, float]:
    ntype = TYPES[etype][0]
    if etype == "receptor":
        tw, th = c.text_size(text, 110, fs, True)
        return max(76.0, tw + 30), max(92.0, th + 44)
    if ntype == "ellipse":
        tw, th = c.text_size(text, 130, fs)
        return max(84.0, tw / 0.72 + 8), max(46.0, th / 0.76 + 8)
    if ntype == "hexagon":
        tw, th = c.text_size(text, 140, fs)
        return max(110.0, tw + 46), max(50.0, th + 22)
    if ntype == "parallelogram":
        tw, th = c.text_size(text, 140, fs)
        return max(110.0, tw + 48), max(46.0, th + 20)
    if ntype == "pill":
        tw, th = c.text_size(text, 140, fs)
        return max(90.0, tw + 40), max(42.0, th + 18)
    tw, th = c.text_size(text, 150, fs, etype == "process")
    return max(92.0, tw + 34), max(44.0, th + 22)


def build_pathway(content: dict, theme: str | None = None) -> dict:
    """Build from ``{"title", "entities": [{"id", "name", "type", "location"}], "relations": [{"from", "to", "type", "label"}]}``."""
    c = Canvas(theme, "pathway", clean(content.get("title"), 160))
    fs = float(c.style["fontSize"]) - 1

    specs: list[dict] = []
    alias: dict[str, str] = {}
    used: set[str] = set()
    for i, raw in enumerate(as_list(content.get("entities") or content.get("nodes"))):
        if not isinstance(raw, dict):
            raw = {"name": raw}
        name = clean(raw.get("name") or raw.get("text") or raw.get("label"), 80)
        if not name:
            continue
        etype = str(raw.get("type") or raw.get("kind") or "protein").strip().lower()
        etype = _TYPE_ALIASES.get(etype, etype)
        if etype not in TYPES:
            etype = "protein"
        loc = str(raw.get("location") or raw.get("compartment") or "").strip().lower()
        loc = _LOCATION_ALIASES.get(loc, loc)
        placed_by_author = loc in BANDS
        if loc not in BANDS:
            loc = _DEFAULT_LOCATION.get(etype, "cytoplasm")
        orig = str(raw.get("id") if raw.get("id") is not None else name)
        nid = slug(orig, f"p{i + 1}")
        while nid in used or nid in ("title", "membrane", "nucleus"):
            nid += "_"
        used.add(nid)
        alias[orig] = nid
        alias.setdefault(name, nid)
        w, h = _entity_size(c, etype, name, fs)
        specs.append({"id": nid, "text": name, "etype": etype, "loc": loc, "w": w, "h": h, "free": not placed_by_author})
    if not specs:
        raise ValueError("The pathway has no entities.")
    by_id = {s["id"]: s for s in specs}
    zh = has_cjk(c.scene["title"], *(s["text"] for s in specs))
    L = _LABELS["zh" if zh else "en"]

    rels: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in as_list(content.get("relations") or content.get("edges")):
        if not isinstance(raw, dict):
            continue
        a = alias.get(str(raw.get("from", raw.get("source"))))
        b = alias.get(str(raw.get("to", raw.get("target"))))
        if not a or not b or a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        rtype = str(raw.get("type") or raw.get("relation") or raw.get("head") or "activate").strip().lower()
        rtype = _REL_ALIASES.get(rtype, rtype)
        if rtype not in RELATIONS:
            rtype = "activate"
        rels.append({"from": a, "to": b, "type": rtype, "label": clean(raw.get("label") or raw.get("text"), 40)})

    bands = {s["id"]: BANDS[s["loc"]] for s in specs}

    # A drug with a single target reads best right beside it (a short horizontal bar),
    # not up in the extracellular row with a line across the whole figure.
    has_upstream = {r["to"] for r in rels}
    beside: dict[str, str] = {}
    for s in specs:
        outs = [r["to"] for r in rels if r["from"] == s["id"]]
        if s["etype"] == "drug" and s["free"] and s["id"] not in has_upstream and len(outs) == 1 and by_id[outs[0]]["etype"] != "drug":
            beside[s["id"]] = outs[0]

    def arrange(side: dict[str, str]) -> tuple[dict, dict[str, int], str | None]:
        main = [s for s in specs if s["id"] not in side]
        # Receptors must share one row (they all sit in the membrane), so relations
        # between two membrane entities do not take part in ranking.
        pairs = [(r["from"], r["to"]) for r in rels if r["from"] not in side and not (bands[r["from"]] == 1 and bands[r["to"]] == 1)]
        lay = layered_layout(main, pairs, direction="TB", layer_gap=44, node_gap=38, bands={s["id"]: bands[s["id"]] for s in main}, band_gap=30)
        boxes = {s["id"]: (lay["pos"][s["id"]][0], lay["pos"][s["id"]][1], s["w"], s["h"]) for s in main}
        where: dict[str, int] = {}
        for sid, tid in side.items():
            me, (tx, ty, tw, th) = by_id[sid], boxes[tid]
            y = ty + th / 2.0 - me["h"] / 2.0
            for sign in (1, -1):
                x = tx + tw + 58 if sign > 0 else tx - 58 - me["w"]
                clash = any(x < ox + ow + 18 and ox < x + me["w"] + 18 and y < oy + oh + 10 and oy < y + me["h"] + 10 for ox, oy, ow, oh in boxes.values())
                if not clash:
                    boxes[sid] = (x, y, me["w"], me["h"])
                    where[sid] = sign
                    break
            else:
                return lay, where, sid
        # Shift so that nothing sits left of zero, and report the widened size.
        shift = -min(0.0, min(b[0] for b in boxes.values()))
        lay["pos"] = {k: (b[0] + shift, b[1]) for k, b in boxes.items()}
        lay["size"] = (max(b[0] + b[2] for b in boxes.values()) + shift, lay["size"][1])
        return lay, where, None

    while True:
        lay, side_sign, failed = arrange(beside)
        if failed is None:
            break
        beside.pop(failed)  # no room next to its target: it goes back into the normal rows
    for sid, tid in beside.items():
        bands[sid] = bands[tid]

    present = sorted(set(bands.values()))
    show_labels = len(present) > 1
    gutter = GUTTER if show_labels else 0.0
    width = max(lay["size"][0] + gutter + 2 * MARGIN, 520.0 if c.scene["title"] else 320.0)
    top = c.title(c.scene["title"], width) if c.scene["title"] else MARGIN
    off_x = MARGIN + gutter + (width - 2 * MARGIN - gutter - lay["size"][0]) / 2.0

    band_rows: dict[int, list[tuple[float, float]]] = {}
    for rank, band in enumerate(lay["band_of_rank"]):
        band_rows.setdefault(band, []).append(lay["layers"][rank])

    def band_span(band: int) -> tuple[float, float]:
        rows = band_rows[band]
        return top + rows[0][0], top + rows[-1][0] + rows[-1][1]

    # ---- backdrops (drawn first so they sit behind the entities) -----------------
    membrane_y: float | None = None
    if 1 in band_rows:
        y0, y1 = band_span(1)
        membrane_y = (y0 + y1) / 2.0
    elif 0 in band_rows and any(b in band_rows for b in (2, 3)):
        inner = min(b for b in (2, 3) if b in band_rows)
        membrane_y = (band_span(0)[1] + band_span(inner)[0]) / 2.0
    if membrane_y is not None:
        c.add("bilayer", MARGIN, membrane_y - 20, width - 2 * MARGIN, 40, id="membrane", fill=c.soft(1), stroke=c.muted, name=L["membrane"], role="membrane")

    if 3 in band_rows:
        members = [s for s in specs if bands[s["id"]] == 3]  # includes a drug parked beside a nuclear target
        x0 = min(lay["pos"][s["id"]][0] for s in members) + off_x
        x1 = max(lay["pos"][s["id"]][0] + s["w"] for s in members) + off_x
        want = max(x1 - x0 + 64, (width - 2 * MARGIN - gutter) * 0.6)
        mid = (x0 + x1) / 2.0
        fx0 = max(MARGIN + gutter, min(mid - want / 2.0, width - MARGIN - want))
        fx1 = min(width - MARGIN, fx0 + want)
        fx0, fx1 = min(fx0, x0 - 24), max(fx1, x1 + 24)
        y0, y1 = band_span(3)
        c.add("frame", fx0, y0 - 36, fx1 - fx0, y1 - y0 + 58, id="nucleus", text=L["nucleus"], fill=c.panel, stroke=c.muted, dash=True, rx=30, role="compartment")

    if show_labels:
        for band, key in ((0, "extracellular"), (2, "cytoplasm"), (4, "outcome")):
            if band in band_rows:
                y0, y1 = band_span(band)
                c.add("text", MARGIN, (y0 + y1) / 2.0 - 12, gutter - 10, 24, text=L[key], fontSize=13, fontStyle="italic", color=c.muted, align="left", role="band-label")

    # ---- entities ---------------------------------------------------------------------
    for s in specs:
        ntype, slot = TYPES[s["etype"]]
        x, y = lay["pos"][s["id"]]
        props: dict[str, Any] = {"text": s["text"], "fontSize": fs, "role": s["etype"]}
        if slot < 0:
            props.update(fill=c.panel, stroke=c.line, fontWeight="bold", rx=6)
        else:
            props.update(fill=c.soft(slot), stroke=c.strong(slot))
        if s["etype"] == "receptor":
            props.update(rx=18, fontWeight="bold")
        elif s["etype"] == "gene":
            props.update(rx=3, fontStyle="italic")
        elif s["etype"] == "complex":
            props.update(rx=16)
        c.add(ntype, x + off_x, y + top, s["w"], s["h"], id=s["id"], **props)

    # ---- relations ----------------------------------------------------------------------
    used_kinds: list[str] = []
    for r in rels:
        head, dash = RELATIONS[r["type"]]
        kind = "indirect" if r["type"] == "translocate" else r["type"]
        if kind not in used_kinds:
            used_kinds.append(kind)
        sides: dict[str, str] = {}
        if r["from"] in beside:
            right = side_sign[r["from"]] > 0
            sides = {"fromSide": "left" if right else "right", "toSide": "right" if right else "left"}
        c.edge(r["from"], r["to"], head=head, dash=dash, label=r["label"], color=c.strong(1) if head == "inhibit" else None, **sides)

    # ---- legend ---------------------------------------------------------------------------
    bottom = top + lay["size"][1]
    if 3 in band_rows:
        bottom = max(bottom, band_span(3)[1] + 22)
    if len(used_kinds) > 1 or (used_kinds and used_kinds[0] != "activate"):
        y = bottom + 34
        x = MARGIN
        order = [k for k in ("activate", "inhibit", "bind", "indirect", "indirect_inhibit") if k in used_kinds]
        for kind in order:
            head, dash = RELATIONS[kind]
            tw, _th = c.text_size(L[kind], 400, 12)
            if x + 44 + tw > width - MARGIN and x > MARGIN:
                x, y = MARGIN, y + 22
            c.edge([round(x, 1), round(y, 1)], [round(x + 34, 1), round(y, 1)], head=head, dash=dash, color=c.strong(1) if head == "inhibit" else None)
            c.add("text", x + 42, y - 10, tw + 8, 20, text=L[kind], fontSize=12, color=c.muted, align="left", role="legend")
            x += 42 + tw + 30
        bottom = y + 6
    return c.finish(width, bottom + MARGIN)
