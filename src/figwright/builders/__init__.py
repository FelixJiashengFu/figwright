"""Deterministic layout builders.

Each builder turns *semantic* content (steps, entities, sections...) into a
finished scene. A language model only has to decide what the figure says; the
arithmetic of where things go is done here, which is far more reliable.
"""

from __future__ import annotations

from typing import Callable

from .abstract import build_abstract
from .flowchart import build_flowchart
from .pathway import build_pathway
from .poster import build_poster
from .prisma import build_prisma
from .workflow import build_workflow

BUILDERS: dict[str, Callable[..., dict]] = {
    "flowchart": build_flowchart,
    "workflow": build_workflow,
    "pathway": build_pathway,
    "abstract": build_abstract,
    "poster": build_poster,
    "prisma": build_prisma,
}

__all__ = ["BUILDERS", "build_abstract", "build_flowchart", "build_pathway", "build_poster", "build_prisma", "build_workflow"]
