/* Scene model and renderer: the JavaScript twin of text.py, geometry.py and render.py.
 *
 * The editor draws every frame in the browser, so dragging a box is instant and
 * never waits for the server. Both renderers must agree, because a figure drawn
 * here is exported there. tests/test_parity.py renders the same scenes through
 * both and compares the result; keep the two files in step.
 */

export const LINE_HEIGHT = 1.3;
export const GAP = 3.0;
export const STUB = 18.0;
export const NOTE_FILL = '#fff6bf';
export const NOTE_STROKE = '#d9bf3d';
export const ICON_BOX = 64;

const NARROW = new Set("iljI.,:;'|!`");
const SEMI = new Set('ftr()[]{}-"*/\\');
const WIDE = new Set('mwMW@%');
const NO_LINE_START = new Set('，。、；：！？）》」』】〉…,.;:!?)]}%');
const NORMALS = { top: [0, -1], right: [1, 0], bottom: [0, 1], left: [-1, 0] };

let ICONS = {};
export function setIcons(icons) { ICONS = icons || {}; }
export function iconNames() { return Object.keys(ICONS); }

/* ------------------------------------------------------------------ text */
export function isWide(ch) {
  const o = ch.codePointAt(0);
  return (
    (o >= 0x1100 && o <= 0x115f) || (o >= 0x2e80 && o <= 0xa4cf) || (o >= 0xac00 && o <= 0xd7a3) ||
    (o >= 0xf900 && o <= 0xfaff) || (o >= 0xfe30 && o <= 0xfe4f) || (o >= 0xff00 && o <= 0xff60) ||
    (o >= 0xffe0 && o <= 0xffe6) || (o >= 0x20000 && o <= 0x3fffd)
  );
}

export function charWidth(ch, fontSize, bold = false) {
  let w;
  if (isWide(ch)) w = 1.0;
  else if (ch === ' ') w = 0.28;
  else if (NARROW.has(ch)) w = 0.28;
  else if (SEMI.has(ch)) w = 0.36;
  else if (WIDE.has(ch)) w = 0.88;
  else if (ch >= 'A' && ch <= 'Z') w = 0.68;
  else if (ch >= '0' && ch <= '9') w = 0.56;
  else w = 0.54;
  if (bold) w *= 1.06;
  return w * fontSize;
}

export function textWidth(s, fontSize, bold = false) {
  let total = 0;
  for (const ch of String(s ?? '')) total += charWidth(ch, fontSize, bold);
  return total;
}

function tokens(par) {
  const out = [];
  let word = '';
  for (const ch of par) {
    if (ch === ' ' || ch === '\t') {
      if (word) { out.push(word); word = ''; }
      if (!out.length || out[out.length - 1] !== ' ') out.push(' ');
    } else if (isWide(ch)) {
      if (word) { out.push(word); word = ''; }
      out.push(ch);
    } else word += ch;
  }
  if (word) out.push(word);
  return out;
}

export function wrapText(text, maxWidth, fontSize, bold = false) {
  if (text === null || text === undefined) return [];
  const body = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const limit = Math.max(Number(maxWidth) || 0, fontSize);
  const spaceW = charWidth(' ', fontSize, bold);
  const lines = [];
  for (const par of body.split('\n')) {
    let cur = '';
    let curW = 0;
    let pendingSpace = false;
    for (const tok of tokens(par)) {
      if (tok === ' ') { pendingSpace = Boolean(cur); continue; }
      const tw = textWidth(tok, fontSize, bold);
      if (tw > limit && [...tok].length > 1) {
        if (cur) { lines.push(cur); cur = ''; curW = 0; }
        let piece = '';
        let pieceW = 0;
        for (const ch of tok) {
          const cw = charWidth(ch, fontSize, bold);
          if (piece && pieceW + cw > limit) { lines.push(piece); piece = ''; pieceW = 0; }
          piece += ch;
          pieceW += cw;
        }
        cur = piece; curW = pieceW; pendingSpace = false;
        continue;
      }
      const add = tw + (pendingSpace && cur ? spaceW : 0);
      const keep = [...tok].length === 1 && NO_LINE_START.has(tok);
      if (cur && curW + add > limit && !keep) { lines.push(cur); cur = tok; curW = tw; }
      else { cur += (pendingSpace && cur ? ' ' : '') + tok; curW += add; }
      pendingSpace = false;
    }
    lines.push(cur);
  }
  return lines;
}

export function textBlockSize(text, maxWidth, fontSize, bold = false) {
  const lines = wrapText(text, maxWidth, fontSize, bold);
  let w = 0;
  for (const line of lines) w = Math.max(w, textWidth(line, fontSize, bold));
  return { width: w, height: lines.length * fontSize * LINE_HEIGHT, lines };
}

/* -------------------------------------------------------------- geometry */
export function fmt(v) {
  // Matches Python's "%.1f" byte for byte, so a figure drawn in the browser and
  // exported on the server come out the same. The two disagree only on an exact
  // half, which Python rounds to even and toFixed rounds away from zero; at one
  // decimal the only exact halves a double can hold are .25 and .75.
  const n = Number(v);
  const a = Math.abs(n);
  let s;
  if (a < 1e15) {
    const t = a.toFixed(20);
    const frac = t.slice(t.indexOf('.') + 1);
    if ((frac.startsWith('25') || frac.startsWith('75')) && !/[1-9]/.test(frac.slice(2))) {
      const down = Math.floor(a * 10) / 10;            // .25 -> .2,  .75 -> .7
      const half = frac.startsWith('75') ? down + 0.1 : down;  // .75 -> .8 (round half to even)
      s = (n < 0 ? -half : half).toFixed(1);
    }
  }
  if (s === undefined) s = n.toFixed(1);
  if (s.endsWith('.0')) s = s.slice(0, -2);
  return s === '-0' ? '0' : s;
}

const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);

export function center(n) { return [n.x + n.w / 2, n.y + n.h / 2]; }

export function visualBox(n) {
  const rot = Number(n.rotation || 0);
  if (!rot) return [n.x, n.y, n.x + n.w, n.y + n.h];
  const a = (rot * Math.PI) / 180;
  const ca = Math.abs(Math.cos(a));
  const sa = Math.abs(Math.sin(a));
  const bw = n.w * ca + n.h * sa;
  const bh = n.w * sa + n.h * ca;
  const [cx, cy] = center(n);
  return [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2];
}

export function shapePoints(n) {
  const { x, y, w, h } = n;
  const cx = x + w / 2;
  const cy = y + h / 2;
  if (n.type === 'diamond') return [[cx, y], [x + w, cy], [cx, y + h], [x, cy]];
  if (n.type === 'hexagon') {
    const i = Math.min(w * 0.25, h * 0.5);
    return [[x + i, y], [x + w - i, y], [x + w, cy], [x + w - i, y + h], [x + i, y + h], [x, cy]];
  }
  if (n.type === 'parallelogram') {
    const s = Math.min(w * 0.2, h * 0.5);
    return [[x + s, y], [x + w, y], [x + w - s, y + h], [x, y + h]];
  }
  if (n.type === 'triangle') return [[cx, y], [x + w, y + h], [x, y + h]];
  return null;
}

export function sideInset(n) {
  if (n.type === 'triangle') return n.w / 4;
  if (n.type === 'parallelogram') return Math.min(n.w * 0.2, n.h * 0.5) / 2;
  return 0;
}

export function sideAnchor(n, side, gap = GAP) {
  const [cx, cy] = center(n);
  if (side === 'top') return [cx, n.y - gap];
  if (side === 'bottom') return [cx, n.y + n.h + gap];
  const inset = sideInset(n);
  if (side === 'left') return [n.x + inset - gap, cy];
  return [n.x + n.w - inset + gap, cy];
}

export function boundaryPoint(n, toward, gap = GAP) {
  const [cx, cy] = center(n);
  const dx = toward[0] - cx;
  const dy = toward[1] - cy;
  const d = Math.hypot(dx, dy);
  if (d < 1e-6) return [cx, cy];
  const hw = Math.max(n.w / 2, 0.5);
  const hh = Math.max(n.h / 2, 0.5);
  const poly = ['hexagon', 'parallelogram', 'triangle'].includes(n.type) ? shapePoints(n) : null;
  let t;
  if (n.type === 'ellipse') t = 1 / Math.sqrt((dx / hw) ** 2 + (dy / hh) ** 2);
  else if (n.type === 'diamond') t = 1 / (Math.abs(dx) / hw + Math.abs(dy) / hh);
  else if (poly) {
    t = 0;
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i];
      const b = poly[(i + 1) % poly.length];
      const ex = b[0] - a[0];
      const ey = b[1] - a[1];
      const den = dx * ey - dy * ex;
      if (Math.abs(den) < 1e-9) continue;
      const tt = ((a[0] - cx) * ey - (a[1] - cy) * ex) / den;
      const uu = ((a[0] - cx) * dy - (a[1] - cy) * dx) / den;
      if (tt > 0 && uu >= -1e-6 && uu <= 1 + 1e-6) t = Math.max(t, tt);
    }
    if (t <= 0) {
      t = Math.min(Math.abs(dx) > 1e-9 ? hw / Math.abs(dx) : Infinity, Math.abs(dy) > 1e-9 ? hh / Math.abs(dy) : Infinity);
    }
  } else {
    t = Math.min(Math.abs(dx) > 1e-9 ? hw / Math.abs(dx) : Infinity, Math.abs(dy) > 1e-9 ? hh / Math.abs(dy) : Infinity);
  }
  return [cx + dx * t + (dx / d) * gap, cy + dy * t + (dy / d) * gap];
}

export function autoSides(a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? ['right', 'left'] : ['left', 'right'];
  return dy >= 0 ? ['bottom', 'top'] : ['top', 'bottom'];
}

function elbowSimple(p0, p3, sa, sb) {
  const ha = sa === 'left' || sa === 'right';
  const hb = sb === 'left' || sb === 'right';
  if (ha && hb) {
    if (sa === sb) {
      const out = sa === 'right' ? Math.max(p0[0], p3[0]) + 28 : Math.min(p0[0], p3[0]) - 28;
      return [p0, [out, p0[1]], [out, p3[1]], p3];
    }
    if (Math.abs(p0[1] - p3[1]) < 0.5) return [p0, p3];
    const mx = (p0[0] + p3[0]) / 2;
    return [p0, [mx, p0[1]], [mx, p3[1]], p3];
  }
  if (!ha && !hb) {
    if (sa === sb) {
      const out = sa === 'bottom' ? Math.max(p0[1], p3[1]) + 28 : Math.min(p0[1], p3[1]) - 28;
      return [p0, [p0[0], out], [p3[0], out], p3];
    }
    if (Math.abs(p0[0] - p3[0]) < 0.5) return [p0, p3];
    const my = (p0[1] + p3[1]) / 2;
    return [p0, [p0[0], my], [p3[0], my], p3];
  }
  if (ha) return [p0, [p3[0], p0[1]], p3];
  return [p0, [p0[0], p3[1]], p3];
}

function step(a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  if (Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01) return [0, 0];
  if (Math.abs(dy) < 0.01) return [dx > 0 ? 1 : -1, 0];
  if (Math.abs(dx) < 0.01) return [0, dy > 0 ? 1 : -1];
  return [2, 2];
}

function cleanRoute(points) {
  const out = [points[0]];
  let last = null;
  for (const p of points.slice(1)) {
    const d = step(out[out.length - 1], p);
    if (d[0] === 0 && d[1] === 0) continue;
    if (d[0] === 2) return null;
    if (last) {
      if (d[0] === last[0] && d[1] === last[1]) { out[out.length - 1] = p; continue; }
      if (d[0] === -last[0] && d[1] === -last[1]) return null;
    }
    out.push(p);
    last = d;
  }
  return out.length >= 2 ? out : null;
}

function crosses(a, b, box) {
  const [x0, y0, x1, y1] = [box[0] + 1, box[1] + 1, box[2] - 1, box[3] - 1];
  return Math.max(a[0], b[0]) > x0 && Math.min(a[0], b[0]) < x1 && Math.max(a[1], b[1]) > y0 && Math.min(a[1], b[1]) < y1;
}

function routeAround(p0, p3, sa, sb, boxes) {
  const na = NORMALS[sa];
  const nb = NORMALS[sb];
  const s = [p0[0] + na[0] * STUB, p0[1] + na[1] * STUB];
  const e = [p3[0] + nb[0] * STUB, p3[1] + nb[1] * STUB];
  const xs = [p0[0], p3[0], s[0], e[0]];
  const ys = [p0[1], p3[1], s[1], e[1]];
  for (const b of boxes) { xs.push(b[0], b[2]); ys.push(b[1], b[3]); }
  const loX = Math.min(...xs) - STUB;
  const hiX = Math.max(...xs) + STUB;
  const loY = Math.min(...ys) - STUB;
  const hiY = Math.max(...ys) + STUB;
  const mx = (s[0] + e[0]) / 2;
  const my = (s[1] + e[1]) / 2;
  const options = [
    [], [[e[0], s[1]]], [[s[0], e[1]]],
    [[mx, s[1]], [mx, e[1]]], [[s[0], my], [e[0], my]],
    [[s[0], loY], [e[0], loY]], [[s[0], hiY], [e[0], hiY]],
    [[loX, s[1]], [loX, e[1]]], [[hiX, s[1]], [hiX, e[1]]],
  ];
  let best = null;
  let bestCost = Infinity;
  for (const mid of options) {
    const route = cleanRoute([p0, s, ...mid, e, p3]);
    if (!route) continue;
    let cost = 30 * (route.length - 2);
    for (let i = 0; i < route.length - 1; i++) cost += dist(route[i], route[i + 1]);
    for (let i = 1; i < route.length - 2; i++) {
      for (const b of boxes) if (crosses(route[i], route[i + 1], b)) cost += 1000;
    }
    if (cost < bestCost - 1e-6) { best = route; bestCost = cost; }
  }
  return best;
}

function elbow(p0, p3, sa, sb, boxes) {
  const simple = elbowSimple(p0, p3, sa, sb);
  const na = NORMALS[sa];
  const nb = NORMALS[sb];
  const first = step(simple[0], simple[1]);
  const last = step(simple[simple.length - 2], simple[simple.length - 1]);
  if (first[0] === na[0] && first[1] === na[1] && last[0] === -nb[0] && last[1] === -nb[1] && cleanRoute(simple)) return simple;
  return routeAround(p0, p3, sa, sb, boxes || []) || simple;
}

export function bezierPoint(p0, c1, c2, p3, t) {
  const u = 1 - t;
  return [
    u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0],
    u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1],
  ];
}

export function polylineMidpoint(points) {
  let total = 0;
  for (let i = 0; i < points.length - 1; i++) total += dist(points[i], points[i + 1]);
  if (total <= 0) return points[0];
  let run = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const seg = dist(points[i], points[i + 1]);
    if (run + seg >= total / 2 && seg > 0) {
      const t = (total / 2 - run) / seg;
      return [points[i][0] + (points[i + 1][0] - points[i][0]) * t, points[i][1] + (points[i + 1][1] - points[i][1]) * t];
    }
    run += seg;
  }
  return points[points.length - 1];
}

function unit(a, b) {
  const d = dist(a, b);
  if (d < 1e-9) return [1, 0];
  return [(b[0] - a[0]) / d, (b[1] - a[1]) / d];
}

function headShape(kind, tip, direction, size) {
  const [ux, uy] = direction;
  const px = -uy;
  const py = ux;
  if (kind === 'inhibit') {
    const half = size * 0.62;
    return [{ kind: 'inhibit', points: [[tip[0] + px * half, tip[1] + py * half], [tip[0] - px * half, tip[1] - py * half]] }, 0];
  }
  if (kind === 'circle') {
    const r = size * 0.32;
    return [{ kind: 'circle', center: [tip[0] - ux * r, tip[1] - uy * r], r }, 2 * r];
  }
  const base = [tip[0] - ux * size, tip[1] - uy * size];
  const half = size * 0.42;
  return [{ kind: 'arrow', points: [tip, [base[0] + px * half, base[1] + py * half], [base[0] - px * half, base[1] - py * half]] }, size * 0.85];
}

function resolveEnd(end, nodes) {
  if (typeof end === 'string') {
    const n = nodes[end];
    if (!n || n.hidden) return [null, null];
    return [n, center(n)];
  }
  if (Array.isArray(end) && end.length === 2) return [null, [Number(end[0]), Number(end[1])]];
  return [null, null];
}

export function edgeGeometry(scene, edge, nodes) {
  if (edge.hidden) return null;
  if (!nodes) { nodes = {}; for (const n of scene.nodes || []) nodes[n.id] = n; }
  const style = scene.style || {};
  const [na, ca] = resolveEnd(edge.from, nodes);
  const [nb, cb] = resolveEnd(edge.to, nodes);
  if (!ca || !cb) return null;
  const width = Number(edge.width || style.edgeWidth || 2);
  const head = edge.head === undefined ? 'arrow' : edge.head;
  const routing = edge.routing || 'straight';
  const gapEnd = GAP + (head === 'inhibit' ? 2 : 0);

  let bez = null;
  let pts;
  if (routing === 'straight' && !edge.fromSide && !edge.toSide) {
    pts = [na ? boundaryPoint(na, cb, GAP) : ca, nb ? boundaryPoint(nb, ca, gapEnd) : cb];
  } else {
    const [saAuto, sbAuto] = autoSides(ca, cb);
    const sa = edge.fromSide || saAuto;
    const sb = edge.toSide || sbAuto;
    const p0 = na ? sideAnchor(na, sa, GAP) : ca;
    const p3 = nb ? sideAnchor(nb, sb, gapEnd) : cb;
    if (routing === 'curve') {
      const span = dist(p0, p3);
      let k = Math.max(30, span * 0.4);
      if (sa === sb) k = Math.min(120, Math.max(46, span * 0.6));
      const n1 = NORMALS[sa];
      const n2 = NORMALS[sb];
      const c1 = [p0[0] + n1[0] * k, p0[1] + n1[1] * k];
      const c2 = [p3[0] + n2[0] * k, p3[1] + n2[1] * k];
      bez = [p0, c1, c2, p3];
      pts = [];
      for (let i = 0; i <= 20; i++) pts.push(bezierPoint(p0, c1, c2, p3, i / 20));
    } else if (routing === 'elbow') {
      const boxes = [na, nb].filter(Boolean).map(visualBox);
      pts = elbow(p0, p3, sa, sb, boxes);
    } else pts = [p0, p3];
  }
  const deduped = [];
  for (const p of pts) if (!deduped.length || dist(deduped[deduped.length - 1], p) > 0.01) deduped.push(p);
  pts = deduped;
  if (pts.length < 2) return null;

  const size = Number(style.arrowSize || 9) + width * 1.5;
  const heads = [];
  const label = bez ? bezierPoint(bez[0], bez[1], bez[2], bez[3], 0.5) : polylineMidpoint(pts);
  const rawPts = pts.map((p) => [...p]);
  pts = pts.map((p) => [...p]);

  const trim = (points, atEnd, amount) => {
    if (amount <= 0) return;
    const i = atEnd ? points.length - 1 : 0;
    const j = atEnd ? points.length - 2 : 1;
    const seg = dist(points[i], points[j]);
    const take = Math.min(amount, seg * 0.9);
    const [ux, uy] = unit(points[j], points[i]);
    points[i] = [points[i][0] - ux * take, points[i][1] - uy * take];
  };

  if (['arrow', 'inhibit', 'circle', 'both'].includes(head)) {
    const kind = head === 'both' ? 'arrow' : head;
    const direction = bez && dist(bez[2], bez[3]) > 1e-6 ? unit(bez[2], bez[3]) : unit(pts[pts.length - 2], pts[pts.length - 1]);
    const [shape, pullRaw] = headShape(kind, pts[pts.length - 1], direction, size);
    heads.push(shape);
    let pull = pullRaw;
    if (bez) {
      if (dist(bez[2], bez[3]) > 1e-6) pull = Math.min(pull, dist(bez[2], bez[3]) * 0.9);
      bez[3] = [bez[3][0] - direction[0] * pull, bez[3][1] - direction[1] * pull];
    }
    trim(pts, true, pull);
  }
  if (head === 'both') {
    const direction = bez && dist(bez[1], bez[0]) > 1e-6 ? unit(bez[1], bez[0]) : unit(pts[1], pts[0]);
    const [shape, pull] = headShape('arrow', pts[0], direction, size);
    heads.push(shape);
    if (bez) bez[0] = [bez[0][0] - direction[0] * pull, bez[0][1] - direction[1] * pull];
    trim(pts, false, pull);
  }

  const d = bez
    ? `M${fmt(bez[0][0])} ${fmt(bez[0][1])} C${fmt(bez[1][0])} ${fmt(bez[1][1])} ${fmt(bez[2][0])} ${fmt(bez[2][1])} ${fmt(bez[3][0])} ${fmt(bez[3][1])}`
    : 'M' + pts.map(([x, y]) => `${fmt(x)} ${fmt(y)}`).join(' L');
  return {
    path: d, points: rawPts, bezier: bez, heads, label, width,
    color: edge.color || style.edgeColor || '#3b4a66',
    dash: Boolean(edge.dash), size,
  };
}

/* --------------------------------------------------------------- painting */
export function nodeStyle(node, style) {
  const t = node.type;
  let fill = node.fill;
  let stroke = node.stroke;
  let sw = node.strokeWidth;
  if (t === 'frame') {
    fill = fill || style.panel || '#f4f6fa';
    stroke = stroke || style.mutedColor || '#5b6478';
    sw = sw === undefined || sw === null ? 1.5 : sw;
  } else if (t === 'text') {
    fill = fill || 'none'; stroke = stroke || 'none';
    sw = sw === undefined || sw === null ? 0 : sw;
  } else if (t === 'note') {
    fill = fill || NOTE_FILL; stroke = stroke || NOTE_STROKE;
    sw = sw === undefined || sw === null ? 1.5 : sw;
  } else if (t === 'path') {
    fill = fill || style.fill || '#dbe9f8';
    stroke = stroke || 'none';
    sw = (sw === undefined || sw === null) && stroke === 'none' ? 0 : (sw === undefined || sw === null ? (style.strokeWidth ?? 2) : sw);
  } else if (t === 'image') {
    fill = fill || 'none'; stroke = stroke || 'none';
    sw = sw === undefined || sw === null ? 0 : sw;
  } else {
    fill = fill || style.fill || '#dbe9f8';
    stroke = stroke || style.stroke || '#3b4a66';
    sw = sw === undefined || sw === null ? (style.strokeWidth ?? 2) : sw;
  }
  let accent = node.accent;
  if (!accent) {
    const soft = (style.soft || []).map((c) => String(c).toLowerCase());
    const palette = style.palette || [];
    const i = typeof fill === 'string' ? soft.indexOf(fill.toLowerCase()) : -1;
    accent = i >= 0 && palette.length ? palette[i % palette.length] : (palette[0] || stroke);
  }
  const fs = Number(node.fontSize || (style.fontSize ?? 16) * (t === 'frame' || t === 'note' ? 0.9 : 1));
  const color = node.color || (t === 'frame' ? (style.mutedColor || '#5b6478') : (t === 'note' ? '#4a4215' : (style.textColor || '#1f2a44')));
  const bold = node.fontWeight === 'bold' || (t === 'frame' && !('fontWeight' in node));
  return { fill, stroke, sw: Number(sw), accent, fs, color, bold, italic: node.fontStyle === 'italic' };
}

export function iconLayout(node, style) {
  const { x, y, w, h } = node;
  const ns = nodeStyle(node, style);
  const text = node.text || '';
  if (!text) {
    const size = Math.max(8, Math.min(w, h));
    return { ix: x + (w - size) / 2, iy: y + (h - size) / 2, size, lines: [], ty: y + h };
  }
  const lines = wrapText(text, w, ns.fs, ns.bold);
  const th = lines.length * ns.fs * LINE_HEIGHT;
  const size = Math.max(16, Math.min(w, h - th - 6));
  return { ix: x + (w - size) / 2, iy: y, size, lines, ty: y + size + 5 };
}

export function textArea(node, style) {
  const { x, y, w, h } = node;
  const t = node.type;
  const al = node.align;
  const va = node.valign;
  const r = (bx, by, bw, bh, a, v) => ({ x: bx, y: by, w: bw, h: bh, align: al || a, valign: va || v });
  if (t === 'text') return r(x, y, w, h, 'center', 'middle');
  if (t === 'frame') return r(x + 12, y + 9, Math.max(10, w - 24), Math.max(10, h - 18), 'left', 'top');
  if (t === 'note') return r(x + 10, y + 8, Math.max(10, w - 20), Math.max(10, h - 16), 'left', 'top');
  if (t === 'ellipse') return r(x + w * 0.14, y + h * 0.12, w * 0.72, h * 0.76, 'center', 'middle');
  if (t === 'diamond') return r(x + w * 0.2, y + h * 0.2, w * 0.6, h * 0.6, 'center', 'middle');
  if (t === 'hexagon') {
    const inset = Math.min(w * 0.25, h * 0.5);
    return r(x + inset * 0.6 + 4, y + 4, Math.max(10, w - inset * 1.2 - 8), h - 8, 'center', 'middle');
  }
  if (t === 'parallelogram') {
    const skew = Math.min(w * 0.2, h * 0.5);
    return r(x + skew * 0.7 + 4, y + 4, Math.max(10, w - skew * 1.4 - 8), h - 8, 'center', 'middle');
  }
  if (t === 'triangle') return r(x + w * 0.25, y + h * 0.42, w * 0.5, h * 0.5, 'center', 'middle');
  if (t === 'cylinder') {
    const ry = Math.min(h * 0.15, 16);
    return r(x + 10, y + ry * 2, Math.max(10, w - 20), Math.max(10, h - ry * 3), 'center', 'middle');
  }
  if (t === 'pill') {
    const pad = Math.min(h * 0.3, w * 0.2);
    return r(x + pad, y + 4, Math.max(10, w - 2 * pad), h - 8, 'center', 'middle');
  }
  return r(x + 10, y + 6, Math.max(10, w - 20), Math.max(10, h - 12), 'center', 'middle');
}

export function textLayout(node, style) {
  const text = node.text;
  if (!text || ['icon', 'image', 'path', 'bilayer'].includes(node.type)) return null;
  const ns = nodeStyle(node, style);
  const a = textArea(node, style);
  const lines = wrapText(text, a.w, ns.fs, ns.bold);
  const lh = ns.fs * LINE_HEIGHT;
  const total = lines.length * lh;
  let top;
  if (a.valign === 'top') top = a.y;
  else if (a.valign === 'bottom') top = a.y + a.h - total;
  else top = a.y + (a.h - total) / 2;
  let tx;
  let anchor;
  if (a.align === 'left') { tx = a.x; anchor = 'start'; }
  else if (a.align === 'right') { tx = a.x + a.w; anchor = 'end'; }
  else { tx = a.x + a.w / 2; anchor = 'middle'; }
  return { lines, x: tx, y: top + lh / 2 + ns.fs * 0.35, lh, anchor, fs: ns.fs, bold: ns.bold, italic: ns.italic, color: ns.color, top, height: total };
}

export function bilayerGeometry(node) {
  const { x, y, w, h } = node;
  const r = Math.max(2, Math.min(h * 0.17, 9));
  const pitch = 2 * r + 2.5;
  const count = Math.max(1, Math.floor(w / pitch));
  const start = x + (w - (count - 1) * pitch) / 2;
  const heads = [];
  const tails = [];
  const mid = y + h / 2;
  for (let i = 0; i < count; i++) {
    const cx = start + i * pitch;
    heads.push([cx, y + r + 1], [cx, y + h - r - 1]);
    tails.push([[cx, y + 2 * r + 1], [cx, mid - 1]], [[cx, y + h - 2 * r - 1], [cx, mid + 1]]);
  }
  return { r, heads, tails };
}

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const attr = (s) => `"${String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')}"`;

function num(v) {
  let s = Number(v).toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
  return s === '' || s === '-0' ? '0' : s;
}

function rolePaint(role, fill, stroke, accent, sw) {
  if (role === 'f') return { fill, stroke, 'stroke-width': num(sw) };
  if (role === 'a') return { fill: accent, stroke: 'none' };
  if (role === 'A') return { fill: accent, stroke, 'stroke-width': num(sw) };
  if (role === 'w') return { fill: '#ffffff', stroke, 'stroke-width': num(sw) };
  if (role === 's') return { fill: stroke, stroke: 'none' };
  if (role === 'la') return { fill: 'none', stroke: accent, 'stroke-width': num(sw * 1.15) };
  return { fill: 'none', stroke, 'stroke-width': num(sw) };
}

export function iconSvg(name, x, y, size, fill, stroke, accent, strokeWidth = 2) {
  const prims = ICONS[name];
  if (!prims) return '';
  const scale = size / ICON_BOX;
  const sw = size <= 0 ? 2 : Math.max(1.2, Math.min(3.6, (strokeWidth * ICON_BOX) / size));
  const parts = [`<g transform="translate(${num(x)} ${num(y)}) scale(${num(scale)})" stroke-linecap="round" stroke-linejoin="round">`];
  for (const prim of prims) {
    const kind = prim[0];
    const role = prim[prim.length - 1];
    const paint = rolePaint(role, fill, stroke, accent, sw);
    const a = Object.entries(paint).map(([k, v]) => `${k}="${v}"`).join(' ');
    if (kind === 'c') parts.push(`<circle cx="${num(prim[1])}" cy="${num(prim[2])}" r="${num(prim[3])}" ${a}/>`);
    else if (kind === 'e') parts.push(`<ellipse cx="${num(prim[1])}" cy="${num(prim[2])}" rx="${num(prim[3])}" ry="${num(prim[4])}" ${a}/>`);
    else if (kind === 'r') {
      const rx = prim[5] ? ` rx="${num(prim[5])}"` : '';
      parts.push(`<rect x="${num(prim[1])}" y="${num(prim[2])}" width="${num(prim[3])}" height="${num(prim[4])}"${rx} ${a}/>`);
    } else if (kind === 'p') {
      const pts = prim[1];
      const coords = [];
      for (let i = 0; i < pts.length; i += 2) coords.push(`${num(pts[i])},${num(pts[i + 1])}`);
      parts.push(`<${prim[2] ? 'polygon' : 'polyline'} points="${coords.join(' ')}" ${a}/>`);
    } else if (kind === 'd') parts.push(`<path d="${esc(prim[1])}" ${a}/>`);
  }
  parts.push('</g>');
  return parts.join('');
}

function textSvg(lines, x, y, lh, anchor, fs, color, bold, italic) {
  if (!lines.length) return '';
  let a = `x="${fmt(x)}" y="${fmt(y)}" font-size="${fmt(fs)}" fill="${color}" text-anchor="${anchor}"`;
  if (bold) a += ' font-weight="bold"';
  if (italic) a += ' font-style="italic"';
  if (lines.length === 1) return `<text ${a}>${esc(lines[0])}</text>`;
  const spans = lines.map((line, i) => `<tspan x="${fmt(x)}" dy="${fmt(i === 0 ? 0 : lh)}">${esc(line) || ' '}</tspan>`).join('');
  return `<text ${a}>${spans}</text>`;
}

function paint(ns, dash, fill) {
  let out = `fill="${fill !== undefined ? fill : ns.fill}"`;
  if (ns.stroke !== 'none' && ns.sw > 0) {
    out += ` stroke="${ns.stroke}" stroke-width="${fmt(ns.sw)}" stroke-linejoin="round"`;
    if (dash) out += ` stroke-dasharray="${fmt(ns.sw * 3.2)} ${fmt(ns.sw * 2.4)}"`;
  } else out += ' stroke="none"';
  return out;
}

export function safeHref(href) {
  const h = String(href || '').trim();
  const low = h.toLowerCase();
  if (low.startsWith('data:image/') && !low.startsWith('data:image/svg')) return h;
  if (low.startsWith('https://') || low.startsWith('http://')) return h;
  return '';
}

/* A path node's own coordinates mapped into its box (pathutil.path_bbox's twin
 * for the common case: an explicit viewBox, else the extents of the numbers). */
export function pathTransform(node) {
  const d = node.d || '';
  let bx = 0;
  let by = 0;
  let bw;
  let bh;
  if (node.vb) { bw = Number(node.vb[0]); bh = Number(node.vb[1]); }
  else {
    const nums = (d.match(/-?\d*\.?\d+(?:e[-+]?\d+)?/gi) || []).map(Number);
    if (nums.length < 4) return null;
    const xs = [];
    const ys = [];
    for (let i = 0; i + 1 < nums.length; i += 2) { xs.push(nums[i]); ys.push(nums[i + 1]); }
    bx = Math.min(...xs); by = Math.min(...ys);
    bw = Math.max(...xs) - bx; bh = Math.max(...ys) - by;
  }
  if (!(bw > 0) || !(bh > 0)) return null;
  const sx = node.w / bw;
  const sy = node.h / bh;
  return [sx, sy, node.x - bx * sx, node.y - by * sy];
}

export function renderNode(node, style, includeNotes = false) {
  if (node.hidden) return '';
  const t = node.type;
  if (t === 'note' && !includeNotes) return '';
  const { x, y, w, h } = node;
  const ns = nodeStyle(node, style);
  const dash = Boolean(node.dash);
  const body = [];
  if (['rect', 'pill', 'frame', 'note'].includes(t)) {
    let rx;
    if (t === 'pill') rx = h / 2;
    else if (t === 'note') rx = 4;
    else rx = node.rx !== undefined && node.rx !== null ? node.rx : (t === 'rect' ? (style.cornerRadius ?? 10) : 12);
    rx = Math.max(0, Math.min(Number(rx), w / 2, h / 2));
    body.push(`<rect x="${fmt(x)}" y="${fmt(y)}" width="${fmt(w)}" height="${fmt(h)}"${rx ? ` rx="${fmt(rx)}"` : ''} ${paint(ns, dash)}/>`);
    if (t === 'note') {
      const c = Math.min(14, w / 3, h / 3);
      body.push(`<polygon points="${fmt(x + w - c)},${fmt(y + h)} ${fmt(x + w)},${fmt(y + h - c)} ${fmt(x + w - c)},${fmt(y + h - c)}" fill="${NOTE_STROKE}" stroke="none"/>`);
    }
  } else if (t === 'ellipse') {
    body.push(`<ellipse cx="${fmt(x + w / 2)}" cy="${fmt(y + h / 2)}" rx="${fmt(w / 2)}" ry="${fmt(h / 2)}" ${paint(ns, dash)}/>`);
  } else if (['diamond', 'hexagon', 'parallelogram', 'triangle'].includes(t)) {
    const pts = (shapePoints(node) || []).map(([px, py]) => `${fmt(px)},${fmt(py)}`).join(' ');
    body.push(`<polygon points="${pts}" ${paint(ns, dash)}/>`);
  } else if (t === 'cylinder') {
    const ry = Math.min(h * 0.15, 16);
    const rxv = w / 2;
    body.push(`<path d="M${fmt(x)} ${fmt(y + ry)} A${fmt(rxv)} ${fmt(ry)} 0 0 1 ${fmt(x + w)} ${fmt(y + ry)} L${fmt(x + w)} ${fmt(y + h - ry)} A${fmt(rxv)} ${fmt(ry)} 0 0 1 ${fmt(x)} ${fmt(y + h - ry)} Z" ${paint(ns, dash)}/>`);
    body.push(`<path d="M${fmt(x)} ${fmt(y + ry)} A${fmt(rxv)} ${fmt(ry)} 0 0 0 ${fmt(x + w)} ${fmt(y + ry)}" ${paint(ns, dash, 'none')}/>`);
  } else if (t === 'bilayer') {
    const g = bilayerGeometry(node);
    const line = ns.stroke !== 'none' ? ns.stroke : (style.stroke || '#3b4a66');
    const tails = g.tails.map(([a, b]) => `M${fmt(a[0])} ${fmt(a[1])} L${fmt(b[0])} ${fmt(b[1])}`).join(' ');
    body.push(`<path d="${tails}" fill="none" stroke="${line}" stroke-width="${fmt(Math.max(1, ns.sw * 0.6))}" stroke-linecap="round"/>`);
    for (const [hx, hy] of g.heads) {
      body.push(`<circle cx="${fmt(hx)}" cy="${fmt(hy)}" r="${fmt(g.r)}" fill="${ns.fill}" stroke="${line}" stroke-width="${fmt(Math.max(1, ns.sw * 0.6))}"/>`);
    }
  } else if (t === 'icon') {
    const lay = iconLayout(node, style);
    const name = ICONS[node.icon] ? node.icon : 'target';
    body.push(iconSvg(name, lay.ix, lay.iy, lay.size, ns.fill, ns.stroke !== 'none' ? ns.stroke : (style.stroke || '#3b4a66'), ns.accent, ns.sw || 2));
    if (lay.lines.length) {
      const lh = ns.fs * LINE_HEIGHT;
      body.push(textSvg(lay.lines, x + w / 2, lay.ty + lh / 2 + ns.fs * 0.35, lh, 'middle', ns.fs, ns.color, ns.bold, ns.italic));
    }
  } else if (t === 'image') {
    const href = safeHref(node.href);
    if (href) body.push(`<image x="${fmt(x)}" y="${fmt(y)}" width="${fmt(w)}" height="${fmt(h)}" preserveAspectRatio="xMidYMid meet" href=${attr(href)}/>`);
    else body.push(`<rect x="${fmt(x)}" y="${fmt(y)}" width="${fmt(w)}" height="${fmt(h)}" fill="#f1f3f6" stroke="#9aa3b2" stroke-width="1.5" stroke-dasharray="6 4"/>`);
    if (ns.stroke !== 'none' && ns.sw > 0) {
      body.push(`<rect x="${fmt(x)}" y="${fmt(y)}" width="${fmt(w)}" height="${fmt(h)}" fill="none" stroke="${ns.stroke}" stroke-width="${fmt(ns.sw)}"/>`);
    }
  } else if (t === 'path') {
    const tr = pathTransform(node);
    if (tr && node.d) {
      const [sx, sy, tx, ty] = tr;
      const scale = (Math.abs(sx) + Math.abs(sy)) / 2 || 1;
      let p = `fill="${ns.fill}"`;
      if (node.fillRule === 'evenodd') p += ' fill-rule="evenodd"';
      if (ns.stroke !== 'none' && ns.sw > 0) p += ` stroke="${ns.stroke}" stroke-width="${fmt(ns.sw / scale)}" stroke-linejoin="round"`;
      body.push(`<path transform="translate(${fmt(tx)} ${fmt(ty)}) scale(${sx} ${sy})" d=${attr(node.d)} ${p}/>`);
    }
  }
  const tl = textLayout(node, style);
  if (tl) body.push(textSvg(tl.lines, tl.x, tl.y, tl.lh, tl.anchor, tl.fs, tl.color, tl.bold, tl.italic));
  if (!body.length) return '';
  let a = `data-id=${attr(node.id)} data-type="${t}"`;
  if (node.rotation) a += ` transform="rotate(${fmt(node.rotation)} ${fmt(x + w / 2)} ${fmt(y + h / 2)})"`;
  if (node.opacity !== undefined && node.opacity !== null && node.opacity < 1) a += ` opacity="${node.opacity}"`;
  return `<g ${a}>${body.join('')}</g>`;
}

export function renderEdge(scene, edge, nodes) {
  const g = edgeGeometry(scene, edge, nodes);
  if (!g) return '';
  const style = scene.style || {};
  const { color, width } = g;
  const dash = g.dash ? ` stroke-dasharray="${fmt(width * 3.2)} ${fmt(width * 2.6)}"` : '';
  const parts = [`<path d="${g.path}" fill="none" stroke="${color}" stroke-width="${fmt(width)}" stroke-linecap="round" stroke-linejoin="round"${dash}/>`];
  for (const head of g.heads) {
    if (head.kind === 'arrow') {
      const pts = head.points.map(([px, py]) => `${fmt(px)},${fmt(py)}`).join(' ');
      parts.push(`<polygon points="${pts}" fill="${color}" stroke="${color}" stroke-width="${fmt(Math.max(1, width * 0.5))}" stroke-linejoin="round"/>`);
    } else if (head.kind === 'inhibit') {
      const [[ax, ay], [bx, by]] = head.points;
      parts.push(`<path d="M${fmt(ax)} ${fmt(ay)} L${fmt(bx)} ${fmt(by)}" fill="none" stroke="${color}" stroke-width="${fmt(width * 1.4)}" stroke-linecap="round"/>`);
    } else if (head.kind === 'circle') {
      parts.push(`<circle cx="${fmt(head.center[0])}" cy="${fmt(head.center[1])}" r="${fmt(head.r)}" fill="${color}"/>`);
    }
  }
  if (edge.label) {
    const fs = Number(edge.fontSize || (style.fontSize ?? 16) * 0.82);
    const lines = wrapText(String(edge.label), 220, fs);
    const lh = fs * LINE_HEIGHT;
    let tw = 0;
    for (const line of lines) tw = Math.max(tw, textWidth(line, fs));
    const [lx, ly] = g.label;
    const total = lines.length * lh;
    let bg = scene.background || '#ffffff';
    if (bg === 'none') bg = '#ffffff';
    parts.push(`<rect x="${fmt(lx - tw / 2 - 4)}" y="${fmt(ly - total / 2 - 1)}" width="${fmt(tw + 8)}" height="${fmt(total + 2)}" rx="3" fill="${bg}" fill-opacity="0.92"/>`);
    parts.push(textSvg(lines, lx, ly - total / 2 + lh / 2 + fs * 0.35, lh, 'middle', fs, edge.labelColor || style.textColor || '#1f2a44', false, false));
  }
  return `<g data-id=${attr(edge.id)} data-type="edge">${parts.join('')}</g>`;
}

/** The scene's body: everything inside <svg>, without the document wrapper. */
export function renderBody(scene, includeNotes = false) {
  const style = scene.style || {};
  const nodes = {};
  for (const n of scene.nodes || []) nodes[n.id] = n;
  const out = [];
  const bg = scene.background;
  if (bg && bg !== 'none') out.push(`<rect data-type="background" x="0" y="0" width="${fmt(scene.width)}" height="${fmt(scene.height)}" fill="${bg}"/>`);
  for (const n of scene.nodes || []) out.push(renderNode(n, style, includeNotes));
  for (const e of scene.edges || []) out.push(renderEdge(scene, e, nodes));
  return out.join('');
}

/** A standalone SVG document (without the embedded scene: the server adds that on export). */
export function renderSvg(scene, includeNotes = false) {
  const style = scene.style || {};
  const family = style.fontFamily || 'Arial, sans-serif';
  const title = scene.title ? `<title>${esc(scene.title)}</title>` : '';
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${fmt(scene.width)}" height="${fmt(scene.height)}" viewBox="0 0 ${fmt(scene.width)} ${fmt(scene.height)}" font-family=${attr(family)}>${title}${renderBody(scene, includeNotes)}</svg>`;
}

/* ------------------------------------------------------------ hit testing */
export function pointInNode(node, px, py) {
  const [cx, cy] = center(node);
  let x = px;
  let y = py;
  if (node.rotation) {
    const a = (-node.rotation * Math.PI) / 180;
    const dx = px - cx;
    const dy = py - cy;
    x = cx + dx * Math.cos(a) - dy * Math.sin(a);
    y = cy + dx * Math.sin(a) + dy * Math.cos(a);
  }
  if (x < node.x || x > node.x + node.w || y < node.y || y > node.y + node.h) return false;
  if (node.type === 'ellipse') return ((x - cx) / (node.w / 2)) ** 2 + ((y - cy) / (node.h / 2)) ** 2 <= 1;
  const poly = shapePoints(node);
  if (poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i];
      const [xj, yj] = poly[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  return true;
}

export function distanceToEdge(geo, px, py) {
  let best = Infinity;
  const pts = geo.bezier
    ? Array.from({ length: 25 }, (_, i) => bezierPoint(geo.bezier[0], geo.bezier[1], geo.bezier[2], geo.bezier[3], i / 24))
    : geo.points;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i];
    const [bx, by] = pts[i + 1];
    const dx = bx - ax;
    const dy = by - ay;
    const len2 = dx * dx + dy * dy;
    const t = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
    best = Math.min(best, Math.hypot(px - (ax + dx * t), py - (ay + dy * t)));
  }
  return best;
}

export function sceneBounds(scene) {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const n of scene.nodes || []) {
    if (n.hidden) continue;
    const b = visualBox(n);
    x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]);
    x1 = Math.max(x1, b[2]); y1 = Math.max(y1, b[3]);
  }
  return Number.isFinite(x0) ? [x0, y0, x1, y1] : null;
}
