"""Shared fixtures. Every test runs against a throwaway FIGWRIGHT_HOME, so a
test never reads or writes the settings or projects of whoever runs it.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from figwright import scene as scene_mod
from figwright.builders.flowchart import build_flowchart


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Point settings, projects and outputs at a temporary directory."""
    d = tmp_path / "fwhome"
    d.mkdir()
    monkeypatch.setenv("FIGWRIGHT_HOME", str(d))
    monkeypatch.setenv("FIGWRIGHT_OUTPUT_DIR", str(tmp_path / "out"))
    # Never let a test pick up a real key from the environment.
    for name in list(os.environ):
        if name.endswith("_API_KEY"):
            monkeypatch.delenv(name, raising=False)
    return d


FLOW_CONTENT = {
    "title": "Sample preparation",
    "direction": "TB",
    "nodes": [
        {"id": "s", "text": "Collect sample", "kind": "start"},
        {"id": "ex", "text": "Extract DNA"},
        {"id": "qc", "text": "Passed QC?", "kind": "decision"},
        {"id": "lib", "text": "Library prep"},
        {"id": "seq", "text": "Sequencing", "kind": "end"},
    ],
    "edges": [
        {"from": "s", "to": "ex"},
        {"from": "ex", "to": "qc"},
        {"from": "qc", "to": "lib", "label": "yes"},
        {"from": "qc", "to": "ex", "label": "no"},
        {"from": "lib", "to": "seq"},
    ],
}


@pytest.fixture
def flow():
    """A flowchart scene with a decision and a loop back."""
    return build_flowchart(FLOW_CONTENT, theme="forest")


@pytest.fixture
def tiny_scene():
    """Two boxes and a connector, written the way a model would write it."""
    return scene_mod.normalize_scene(
        {
            "width": 600,
            "height": 300,
            "title": "Tiny",
            "nodes": [
                {"id": "a", "type": "box", "x": 40, "y": 60, "w": 180, "h": 80, "text": "Input"},
                {"id": "b", "type": "ellipse", "x": 360, "y": 60, "w": 180, "h": 80, "text": "Output"},
            ],
            "edges": [{"id": "e1", "from": "a", "to": "b", "label": "run", "head": "arrow"}],
        },
        theme="forest",
    )


def png_bytes(array: np.ndarray, dpi: int | None = None) -> bytes:
    buf = io.BytesIO()
    kw = {"dpi": (dpi, dpi)} if dpi else {}
    Image.fromarray(array).save(buf, format="PNG", **kw)
    return buf.getvalue()


@pytest.fixture
def shapes_png():
    """A flat-colour picture: white page, blue square, orange circle. Vector-friendly."""
    img = np.full((240, 320, 3), 255, dtype=np.uint8)
    img[40:120, 40:160] = (40, 80, 200)
    yy, xx = np.mgrid[0:240, 0:320]
    circle = (xx - 220) ** 2 + (yy - 150) ** 2 < 55**2
    img[circle] = (230, 150, 40)
    return png_bytes(img)


@pytest.fixture
def photo_png():
    """A lit, noisy "photo of a page": grey text strokes on an uneven background."""
    rng = np.random.default_rng(7)
    page = np.linspace(170, 240, 200)[:, None] * np.ones((1, 260))
    page = np.repeat(page[:, :, None], 3, axis=2)
    page[60:70, 40:200] = 40  # a dark stroke
    page[120:130, 60:180] = 60
    page = page + rng.normal(0, 6, page.shape)
    return png_bytes(np.clip(page, 0, 255).astype(np.uint8))


@pytest.fixture
def table_csv():
    rows = ["group,dose,value"]
    data = {"ctrl": [1.10, 1.35, 0.98, 1.22], "low": [1.52, 1.61, 1.48, 1.70], "high": [2.31, 2.05, 2.44, 2.20]}
    for name, values in data.items():
        for v in values:
            rows.append(f"{name},1,{v}")
    return "\n".join(rows) + "\n"


@pytest.fixture
def wide_csv():
    """Two numeric columns that actually vary, for scatter and regression."""
    rows = ["sample,conc,signal"]
    for i in range(14):
        rows.append(f"s{i},{i + 1},{2.4 * (i + 1) + (i % 3) * 0.6:.3f}")
    return "\n".join(rows) + "\n"


def read_json(path: Path):
    return json.loads(Path(path).read_text("utf-8"))
