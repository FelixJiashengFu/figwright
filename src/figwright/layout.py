"""Layered (Sugiyama-style) graph layout for flowcharts and pathways.

Small and dependency-free on purpose. The steps are the classic ones:

1. break cycles (depth-first search, back edges are flipped for ranking only),
2. assign ranks by longest path, optionally inside ordered *bands*
   (e.g. extracellular / membrane / cytoplasm / nucleus),
3. order each rank with barycentre sweeps to reduce crossings,
4. place nodes along the cross axis by pulling them towards their neighbours
   while keeping the order and a minimum gap.
"""

from __future__ import annotations

from collections import defaultdict


def _break_cycles(ids: list[str], edges: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], set[tuple[str, str]]]:
    """Return (edges with back edges reversed so the graph is acyclic, the set of original back edges)."""
    out_adj: dict[str, list[str]] = defaultdict(list)
    for u, v in edges:
        out_adj[u].append(v)
    state: dict[str, int] = {}
    back: set[tuple[str, str]] = set()
    for root in ids:
        if state.get(root):
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        state[root] = 1
        while stack:
            node, i = stack[-1]
            nbrs = out_adj[node]
            if i < len(nbrs):
                stack[-1] = (node, i + 1)
                nxt = nbrs[i]
                st = state.get(nxt, 0)
                if st == 0:
                    state[nxt] = 1
                    stack.append((nxt, 0))
                elif st == 1:
                    back.add((node, nxt))
            else:
                state[node] = 2
                stack.pop()
    return [(v, u) if (u, v) in back else (u, v) for u, v in edges], back


def _longest_path_ranks(ids: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    preds: dict[str, list[str]] = defaultdict(list)
    succs: dict[str, list[str]] = defaultdict(list)
    indeg = {i: 0 for i in ids}
    for u, v in edges:
        preds[v].append(u)
        succs[u].append(v)
        indeg[v] += 1
    rank = {i: 0 for i in ids}
    queue = [i for i in ids if indeg[i] == 0]
    seen = 0
    while queue:
        u = queue.pop(0)
        seen += 1
        for v in succs[u]:
            rank[v] = max(rank[v], rank[u] + 1)
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    return rank


def _crossings(layers: list[list[str]], edges: list[tuple[str, str]], rank: dict[str, int]) -> int:
    pos = {n: i for layer in layers for i, n in enumerate(layer)}
    by_gap: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for u, v in edges:
        if rank[v] == rank[u] + 1:
            by_gap[rank[u]].append((pos[u], pos[v]))
    total = 0
    for pairs in by_gap.values():
        pairs.sort()
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                if pairs[i][0] < pairs[j][0] and pairs[i][1] > pairs[j][1]:
                    total += 1
    return total


def layered_layout(
    nodes: list[dict],
    edges: list[tuple[str, str]],
    direction: str = "TB",
    layer_gap: float = 64.0,
    node_gap: float = 36.0,
    bands: dict[str, int] | None = None,
    band_gap: float = 0.0,
) -> dict:
    """Lay out ``nodes`` (dicts with ``id``, ``w``, ``h``).

    Returns ``{"pos": {id: (x, y)}, "size": (w, h), "rank": {id: rank},
    "layers": [(start, thickness), ...], "band_of_rank": [...]}`` with top-left
    positions and the origin at (0, 0).
    """
    ids = [n["id"] for n in nodes]
    if not ids:
        return {"pos": {}, "size": (0.0, 0.0), "rank": {}, "layers": [], "band_of_rank": []}
    size = {n["id"]: (float(n["w"]), float(n["h"])) for n in nodes}
    idset = set(ids)
    seen: set[tuple[str, str]] = set()
    clean: list[tuple[str, str]] = []
    for u, v in edges:
        if u in idset and v in idset and u != v and (u, v) not in seen:
            seen.add((u, v))
            clean.append((u, v))
    dag, back = _break_cycles(ids, clean)
    flipped = {(v, u) for u, v in back}  # loop-backs, as they appear in ``dag``

    # ---- ranks ---------------------------------------------------------------
    band_of_rank: list[int] = []
    if bands:
        rank: dict[str, int] = {}
        offset = 0
        for band in sorted({bands.get(i, 0) for i in ids}):
            members = [i for i in ids if bands.get(i, 0) == band]
            mset = set(members)
            inner = [(u, v) for u, v in dag if u in mset and v in mset]
            local = _longest_path_ranks(members, inner)
            depth = max(local.values()) + 1
            for i in members:
                rank[i] = offset + local[i]
            band_of_rank += [band] * depth
            offset += depth
        # Inside a band an edge may now point "up"; flip those for ordering purposes.
        dag = [(u, v) if rank[u] <= rank[v] else (v, u) for u, v in dag]
    else:
        rank = _longest_path_ranks(ids, dag)
        band_of_rank = [0] * (max(rank.values()) + 1)
    n_layers = max(rank.values()) + 1
    layers: list[list[str]] = [[] for _ in range(n_layers)]
    for i in ids:
        layers[rank[i]].append(i)

    up: dict[str, list[str]] = defaultdict(list)
    down: dict[str, list[str]] = defaultdict(list)
    # Loop-backs help ordering (keep the loop's ends close) but must not drag
    # the main flow sideways, so coordinates use the forward edges only.
    up_fwd: dict[str, list[str]] = defaultdict(list)
    down_fwd: dict[str, list[str]] = defaultdict(list)
    for u, v in dag:
        if rank[u] < rank[v]:
            down[u].append(v)
            up[v].append(u)
            if (u, v) not in flipped and (v, u) not in flipped:
                down_fwd[u].append(v)
                up_fwd[v].append(u)

    # ---- ordering (barycentre sweeps) ------------------------------------------
    def relpos() -> dict[str, float]:
        return {n: (i + 0.5) / len(layer) for layer in layers for i, n in enumerate(layer)}

    best = [list(layer) for layer in layers]
    best_cross = _crossings(layers, dag, rank)
    for sweep in range(12):
        order = range(1, n_layers) if sweep % 2 == 0 else range(n_layers - 2, -1, -1)
        nbrs = up if sweep % 2 == 0 else down
        for li in order:
            rp = relpos()
            keyed = []
            for idx, n in enumerate(layers[li]):
                ns = nbrs[n]
                bary = sum(rp[m] for m in ns) / len(ns) if ns else rp[n]
                keyed.append((bary, idx, n))
            keyed.sort()
            layers[li] = [n for _b, _i, n in keyed]
        cross = _crossings(layers, dag, rank)
        if cross < best_cross:
            best_cross = cross
            best = [list(layer) for layer in layers]
        if best_cross == 0:
            break
    layers = best

    # ---- coordinates ---------------------------------------------------------------
    horizontal = direction.upper() in ("LR", "RL")
    cross_size = (lambda n: size[n][1]) if horizontal else (lambda n: size[n][0])
    main_size = (lambda n: size[n][0]) if horizontal else (lambda n: size[n][1])

    centre: dict[str, float] = {}
    for layer in layers:
        total = sum(cross_size(n) for n in layer) + node_gap * (len(layer) - 1)
        cur = -total / 2.0
        for n in layer:
            centre[n] = cur + cross_size(n) / 2.0
            cur += cross_size(n) + node_gap

    def settle(layer: list[str], desired: dict[str, float]) -> None:
        if not layer:
            return
        fwd: list[float] = []
        for i, n in enumerate(layer):
            x = desired[n]
            if i:
                prev = layer[i - 1]
                x = max(x, fwd[-1] + (cross_size(prev) + cross_size(n)) / 2.0 + node_gap)
            fwd.append(x)
        bwd: list[float] = [0.0] * len(layer)
        for i in range(len(layer) - 1, -1, -1):
            n = layer[i]
            x = desired[n]
            if i < len(layer) - 1:
                nxt = layer[i + 1]
                x = min(x, bwd[i + 1] - (cross_size(nxt) + cross_size(n)) / 2.0 - node_gap)
            bwd[i] = x
        for i, n in enumerate(layer):
            centre[n] = (fwd[i] + bwd[i]) / 2.0

    for it in range(14):
        downward = it % 2 == 0
        order = range(1, n_layers) if downward else range(n_layers - 2, -1, -1)
        nbrs = up_fwd if downward else down_fwd
        for li in order:
            desired = {}
            for n in layers[li]:
                ns = nbrs[n]
                desired[n] = sum(centre[m] for m in ns) / len(ns) if ns else centre[n]
            settle(layers[li], desired)

    layer_bounds: list[tuple[float, float]] = []
    cursor = 0.0
    for li, layer in enumerate(layers):
        thickness = max((main_size(n) for n in layer), default=0.0)
        if li > 0:
            cursor += layer_gap
            if band_of_rank[li] != band_of_rank[li - 1]:
                cursor += band_gap
        layer_bounds.append((cursor, thickness))
        cursor += thickness

    lo = min(centre[n] - cross_size(n) / 2.0 for n in ids)
    hi = max(centre[n] + cross_size(n) / 2.0 for n in ids)
    pos: dict[str, tuple[float, float]] = {}
    for li, layer in enumerate(layers):
        start, thickness = layer_bounds[li]
        for n in layer:
            c = centre[n] - lo
            m = start + (thickness - main_size(n)) / 2.0
            w, h = size[n]
            pos[n] = (m, c - h / 2.0) if horizontal else (c - w / 2.0, m)
    span = hi - lo
    total = (cursor, span) if horizontal else (span, cursor)
    return {"pos": pos, "size": total, "rank": rank, "layers": layer_bounds, "band_of_rank": band_of_rank}
