/* The canvas: an infinite surface you can pan, zoom, select on, drag, resize,
 * rotate, connect and type into. Every change goes through commit(), which
 * redraws, refreshes the panels and pushes an undo step.
 */

import { api, el, fail, state, status } from './app.js';
import { getLang, name, t } from './i18n.js';
import * as S from './scene.js';
import { say } from './notes.js';
import { drawProps, drawLayers } from './panels.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const HANDLES = [['nw', 0, 0], ['n', 0.5, 0], ['ne', 1, 0], ['e', 1, 0.5], ['se', 1, 1], ['s', 0.5, 1], ['sw', 0, 1], ['w', 0, 0.5]];
const MIN_SIZE = 12;

const uid = (prefix, taken) => {
  let i = 1;
  while (taken.has(`${prefix}${i}`)) i++;
  return `${prefix}${i}`;
};

export class Editor {
  constructor(host, wrap) {
    this.host = host;
    this.wrap = wrap;
    this.scene = null;
    this.selection = new Set();
    this.tool = 'select';
    this.zoom = 1;
    this.pan = { x: 0, y: 0 };
    this.showNotes = true;
    this.cvd = '';
    this.undoStack = [];
    this.redoStack = [];
    this.dirty = false;
    this.drag = null;
    this.svg = document.createElementNS(SVG_NS, 'svg');
    this.svg.setAttribute('xmlns', SVG_NS);
    host.append(this.svg);
    this.bind();
  }

  /* ------------------------------------------------------------ lifecycle */
  blank() {
    const theme = state.meta.themes.find((x) => x.id === state.meta.default_theme) || state.meta.themes[0];
    this.load({
      version: 1, kind: 'illustration', title: '', width: 960, height: 600, background: theme.bg,
      style: {}, nodes: [], edges: [], meta: {},
    }, { silent: true, normalize: true });
  }

  async load(scene, opts = {}) {
    if (!opts.keepSelection) this.selection.clear();
    if (this.scene && !opts.silent) this.pushUndo();
    this.scene = scene;
    if (opts.normalize) {
      try { this.scene = (await api.send('/api/normalize', { scene })).scene; } catch { /* keep as given */ }
    }
    this.dirty = !opts.silent;
    for (const id of [...this.selection]) if (!this.byId(id)) this.selection.delete(id);
    this.fit(opts.keepSelection ? null : undefined);
    this.render();
    if (opts.notes && opts.notes.length) status(opts.notes.map(say).join('  ·  '));
    if (opts.issues) this.setIssues(opts.issues);
    else this.checkLater();
  }

  byId(id) {
    return (this.scene.nodes || []).find((n) => n.id === id) || (this.scene.edges || []).find((e) => e.id === id) || null;
  }

  isEdge(id) { return (this.scene.edges || []).some((e) => e.id === id); }

  pushUndo() {
    this.undoStack.push(JSON.stringify(this.scene));
    if (this.undoStack.length > 80) this.undoStack.shift();
    this.redoStack.length = 0;
  }

  commit(label) {
    this.dirty = true;
    this.render();
    this.checkLater();
    if (label) status(label);
  }

  change(fn, label) {
    this.pushUndo();
    fn();
    this.commit(label);
  }

  undo() {
    if (!this.undoStack.length) return;
    this.redoStack.push(JSON.stringify(this.scene));
    this.scene = JSON.parse(this.undoStack.pop());
    this.selection.clear();
    this.render();
    this.checkLater();
  }

  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(JSON.stringify(this.scene));
    this.scene = JSON.parse(this.redoStack.pop());
    this.selection.clear();
    this.render();
    this.checkLater();
  }

  /* ------------------------------------------------------------ rendering */
  render() {
    const sc = this.scene;
    this.svg.setAttribute('width', sc.width * this.zoom);
    this.svg.setAttribute('height', sc.height * this.zoom);
    this.svg.setAttribute('viewBox', `0 0 ${sc.width} ${sc.height}`);
    this.svg.setAttribute('font-family', (sc.style && sc.style.fontFamily) || 'Arial, sans-serif');
    this.svg.style.transform = `translate(${this.pan.x}px, ${this.pan.y}px)`;
    this.svg.style.background = sc.background && sc.background !== 'none' ? sc.background : '#fff';
    this.svg.innerHTML = `${this.cvdFilter()}${S.renderBody(sc, this.showNotes)}${this.overlay()}`;
    this.svg.style.filter = this.cvd ? 'url(#fw-cvd)' : '';
    document.getElementById('size-label').textContent = `${Math.round(sc.width)} × ${Math.round(sc.height)} px`;
    document.getElementById('zoom-label').textContent = `${Math.round(this.zoom * 100)}%`;
    document.getElementById('sel-count').textContent = this.selection.size ? `${this.selection.size}` : '';
    drawProps(this);
    drawLayers(this);
  }

  cvdFilter() {
    if (!this.cvd) return '';
    // Brettel-style approximations, enough to spot a figure that only works in colour.
    const m = {
      deuteranopia: '0.625 0.375 0 0 0  0.7 0.3 0 0 0  0 0.3 0.7 0 0  0 0 0 1 0',
      protanopia: '0.567 0.433 0 0 0  0.558 0.442 0 0 0  0 0.242 0.758 0 0  0 0 0 1 0',
      tritanopia: '0.95 0.05 0 0 0  0 0.433 0.567 0 0  0 0.475 0.525 0 0  0 0 0 1 0',
    }[this.cvd];
    return `<defs><filter id="fw-cvd" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="${m}"/></filter></defs>`;
  }

  /** Selection outlines, resize handles and connection ports, drawn in scene units. */
  overlay() {
    const parts = [];
    const k = 1 / this.zoom;
    for (const id of this.selection) {
      const node = (this.scene.nodes || []).find((n) => n.id === id);
      if (node) {
        const rot = node.rotation ? ` transform="rotate(${node.rotation} ${node.x + node.w / 2} ${node.y + node.h / 2})"` : '';
        parts.push(`<rect class="outline" x="${node.x}" y="${node.y}" width="${node.w}" height="${node.h}" stroke-width="${1.5 * k}"${rot}/>`);
        continue;
      }
      const edge = (this.scene.edges || []).find((e) => e.id === id);
      if (edge) {
        const g = S.edgeGeometry(this.scene, edge);
        if (g) parts.push(`<path class="outline" d="${g.path}" stroke-width="${Math.max(3, g.width + 3) * k}" stroke-opacity="0.35" fill="none"/>`);
      }
    }
    if (this.selection.size === 1) {
      const node = (this.scene.nodes || []).find((n) => n.id === [...this.selection][0]);
      if (node) {
        const r = 4 * k;
        const rot = node.rotation ? ` transform="rotate(${node.rotation} ${node.x + node.w / 2} ${node.y + node.h / 2})"` : '';
        parts.push(`<g${rot}>`);
        for (const [kind, fx, fy] of HANDLES) {
          parts.push(`<rect class="handle ${kind}" data-handle="${kind}" x="${node.x + node.w * fx - r}" y="${node.y + node.h * fy - r}" width="${2 * r}" height="${2 * r}" rx="${r * 0.4}" stroke-width="${1.5 * k}"/>`);
        }
        parts.push(`<circle class="handle rot" data-handle="rotate" cx="${node.x + node.w / 2}" cy="${node.y - 22 * k}" r="${r}" stroke-width="${1.5 * k}"/>`);
        parts.push('</g>');
      }
    }
    if (this.tool === 'connect' && this.hover) {
      const node = (this.scene.nodes || []).find((n) => n.id === this.hover);
      if (node) {
        for (const side of ['top', 'right', 'bottom', 'left']) {
          const [px, py] = S.sideAnchor(node, side, 0);
          parts.push(`<circle class="port${this.drag && this.drag.side === side ? ' on' : ''}" data-port="${side}" data-node="${node.id}" cx="${px}" cy="${py}" r="${5 * k}" stroke-width="${1.5 * k}"/>`);
        }
      }
    }
    if (this.drag && this.drag.kind === 'marquee') {
      const { x0, y0, x1, y1 } = this.drag;
      parts.push(`<rect class="marquee-rect" x="${Math.min(x0, x1)}" y="${Math.min(y0, y1)}" width="${Math.abs(x1 - x0)}" height="${Math.abs(y1 - y0)}" stroke-width="${k}"/>`);
    }
    if (this.drag && this.drag.kind === 'connect' && this.drag.to) {
      const [ax, ay] = this.drag.from;
      parts.push(`<path class="outline" d="M${ax} ${ay} L${this.drag.to[0]} ${this.drag.to[1]}" stroke-width="${2 * k}" stroke-dasharray="${6 * k} ${4 * k}"/>`);
    }
    return parts.join('');
  }

  /* ---------------------------------------------------------------- view */
  fit(force) {
    if (force === null) return;
    const box = this.wrap.getBoundingClientRect();
    const pad = 36;
    this.zoom = Math.max(0.1, Math.min(2.4, Math.min((box.width - pad * 2) / this.scene.width, (box.height - pad * 2) / this.scene.height)));
    this.pan = {
      x: Math.max(pad / 2, (box.width - this.scene.width * this.zoom) / 2),
      y: Math.max(pad / 2, (box.height - this.scene.height * this.zoom) / 2),
    };
  }

  setZoom(z, cx, cy) {
    const box = this.wrap.getBoundingClientRect();
    const px = cx === undefined ? box.width / 2 : cx;
    const py = cy === undefined ? box.height / 2 : cy;
    const before = this.toScene(px + box.left, py + box.top);
    this.zoom = Math.max(0.08, Math.min(6, z));
    const after = this.toScene(px + box.left, py + box.top);
    this.pan.x += (after[0] - before[0]) * this.zoom;
    this.pan.y += (after[1] - before[1]) * this.zoom;
    this.render();
  }

  toScene(clientX, clientY) {
    const box = this.wrap.getBoundingClientRect();
    return [(clientX - box.left - this.pan.x) / this.zoom, (clientY - box.top - this.pan.y) / this.zoom];
  }

  setShowNotes(on) { this.showNotes = on; this.render(); }
  setCvd(kind) { this.cvd = kind; this.render(); }

  /* ------------------------------------------------------------ hit test */
  pick(x, y) {
    const nodes = this.scene.nodes || [];
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (n.hidden || n.locked) continue;
      if (n.type === 'note' && !this.showNotes) continue;
      if (S.pointInNode(n, x, y)) return n.id;
    }
    for (const e of this.scene.edges || []) {
      const g = S.edgeGeometry(this.scene, e);
      if (g && S.distanceToEdge(g, x, y) < Math.max(6, g.width + 4)) return e.id;
    }
    return null;
  }

  /* -------------------------------------------------------------- editing */
  select(id, add = false) {
    if (!add) this.selection.clear();
    if (id) { if (add && this.selection.has(id)) this.selection.delete(id); else this.selection.add(id); }
    this.render();
  }

  selectedNodes() { return (this.scene.nodes || []).filter((n) => this.selection.has(n.id)); }

  addNode(type, at) {
    const taken = new Set((this.scene.nodes || []).map((n) => n.id));
    const defaults = {
      rect: [150, 60], ellipse: [140, 90], diamond: [160, 90], hexagon: [160, 70], parallelogram: [170, 64],
      cylinder: [130, 90], pill: [140, 48], triangle: [120, 100], text: [180, 36], frame: [280, 200],
      note: [170, 80], icon: [84, 96], bilayer: [260, 34], image: [220, 160],
    }[type] || [150, 60];
    const node = {
      id: uid(type === 'note' ? 'note' : 'n', taken), type,
      x: Math.round((at ? at[0] : this.scene.width / 2) - defaults[0] / 2),
      y: Math.round((at ? at[1] : this.scene.height / 2) - defaults[1] / 2),
      w: defaults[0], h: defaults[1],
      text: type === 'bilayer' || type === 'image' ? '' : (getLang() === 'zh' ? '文字' : 'Text'),
    };
    if (type === 'icon') { node.icon = 'target'; node.text = ''; }
    this.change(() => {
      this.scene.nodes.push(node);
      this.selection.clear();
      this.selection.add(node.id);
    });
    if (node.text !== undefined && type !== 'icon' && type !== 'image') this.editText(node.id);
    return node;
  }

  addEdge(from, to, fromSide, toSide) {
    if (from === to) return null;
    const taken = new Set((this.scene.edges || []).map((e) => e.id));
    const edge = { id: uid('e', taken), from, to, head: 'arrow', routing: 'straight' };
    if (fromSide) edge.fromSide = fromSide;
    if (toSide) edge.toSide = toSide;
    this.change(() => {
      this.scene.edges.push(edge);
      this.selection.clear();
      this.selection.add(edge.id);
    });
    return edge;
  }

  remove(ids) {
    const set = new Set(ids);
    if (!set.size) return;
    this.change(() => {
      this.scene.nodes = (this.scene.nodes || []).filter((n) => !set.has(n.id));
      this.scene.edges = (this.scene.edges || []).filter((e) => !set.has(e.id) && !set.has(e.from) && !set.has(e.to));
      this.selection.clear();
    });
  }

  duplicate() {
    const nodes = this.selectedNodes();
    if (!nodes.length) return;
    const taken = new Set((this.scene.nodes || []).map((n) => n.id));
    const made = [];
    this.change(() => {
      for (const n of nodes) {
        const copy = { ...JSON.parse(JSON.stringify(n)), id: uid('n', taken), x: n.x + 24, y: n.y + 24 };
        taken.add(copy.id);
        this.scene.nodes.push(copy);
        made.push(copy.id);
      }
      this.selection.clear();
      for (const id of made) this.selection.add(id);
    });
  }

  order(delta) {
    const nodes = this.scene.nodes;
    const picked = nodes.filter((n) => this.selection.has(n.id));
    if (!picked.length) return;
    this.change(() => {
      for (const n of (delta > 0 ? [...picked].reverse() : picked)) {
        const i = nodes.indexOf(n);
        const j = delta === Infinity ? nodes.length - 1 : (delta === -Infinity ? 0 : Math.max(0, Math.min(nodes.length - 1, i + delta)));
        nodes.splice(i, 1);
        nodes.splice(j, 0, n);
      }
    });
  }

  group() {
    const nodes = this.selectedNodes();
    if (nodes.length < 2) return;
    const tag = `g${Date.now().toString(36).slice(-4)}`;
    this.change(() => { for (const n of nodes) n.group = tag; }, getLang() === 'zh' ? '已编组' : 'Grouped');
  }

  ungroup() {
    const nodes = this.selectedNodes();
    this.change(() => { for (const n of nodes) delete n.group; }, getLang() === 'zh' ? '已取消编组' : 'Ungrouped');
  }

  /** Everything that must move with a node: its own group mates. */
  movingSet(ids) {
    const groups = new Set();
    for (const id of ids) {
      const n = (this.scene.nodes || []).find((x) => x.id === id);
      if (n && n.group) groups.add(n.group);
    }
    const out = new Set(ids);
    for (const n of this.scene.nodes || []) if (n.group && groups.has(n.group)) out.add(n.id);
    return out;
  }

  align(how) {
    const nodes = this.selectedNodes();
    if (nodes.length < 2) return;
    const left = Math.min(...nodes.map((n) => n.x));
    const right = Math.max(...nodes.map((n) => n.x + n.w));
    const top = Math.min(...nodes.map((n) => n.y));
    const bottom = Math.max(...nodes.map((n) => n.y + n.h));
    this.change(() => {
      for (const n of nodes) {
        if (how === 'left') n.x = left;
        else if (how === 'right') n.x = right - n.w;
        else if (how === 'hcenter') n.x = (left + right) / 2 - n.w / 2;
        else if (how === 'top') n.y = top;
        else if (how === 'bottom') n.y = bottom - n.h;
        else if (how === 'vcenter') n.y = (top + bottom) / 2 - n.h / 2;
      }
      if (how === 'hspread' || how === 'vspread') {
        const key = how === 'hspread' ? 'x' : 'y';
        const span = how === 'hspread' ? 'w' : 'h';
        const sorted = [...nodes].sort((a, b) => a[key] - b[key]);
        const first = sorted[0][key];
        const last = sorted[sorted.length - 1][key] + sorted[sorted.length - 1][span];
        const used = sorted.reduce((s, n) => s + n[span], 0);
        const gap = (last - first - used) / (sorted.length - 1);
        let at = first;
        for (const n of sorted) { n[key] = Math.round(at); at += n[span] + gap; }
      }
    });
  }

  /** Grow the canvas so nothing sits outside it. */
  growCanvas() {
    const b = S.sceneBounds(this.scene);
    if (!b) return;
    const pad = 24;
    let changed = false;
    if (b[2] + pad > this.scene.width) { this.scene.width = Math.ceil(b[2] + pad); changed = true; }
    if (b[3] + pad > this.scene.height) { this.scene.height = Math.ceil(b[3] + pad); changed = true; }
    return changed;
  }

  editText(id) {
    const node = (this.scene.nodes || []).find((n) => n.id === id);
    if (!node || ['image', 'bilayer', 'path'].includes(node.type)) return;
    const wrap = document.getElementById('editing');
    const area = wrap.querySelector('textarea');
    const box = S.textArea(node, this.scene.style || {});
    const ns = S.nodeStyle(node, this.scene.style || {});
    wrap.classList.remove('hidden');
    wrap.style.left = `${this.pan.x + box.x * this.zoom}px`;
    wrap.style.top = `${this.pan.y + box.y * this.zoom}px`;
    area.style.width = `${Math.max(60, box.w * this.zoom)}px`;
    area.style.height = `${Math.max(26, box.h * this.zoom)}px`;
    area.style.fontSize = `${ns.fs * this.zoom}px`;
    area.style.textAlign = box.align;
    area.value = node.text || '';
    area.focus();
    area.select();
    const finish = (keep) => {
      wrap.classList.add('hidden');
      area.removeEventListener('blur', onBlur);
      area.removeEventListener('keydown', onKey);
      if (keep && area.value !== (node.text || '')) this.change(() => { node.text = area.value; });
      this.wrap.focus();
    };
    const onBlur = () => finish(true);
    const onKey = (e) => {
      e.stopPropagation();
      if (e.key === 'Escape') { e.preventDefault(); finish(false); }
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); finish(true); }
    };
    area.addEventListener('blur', onBlur);
    area.addEventListener('keydown', onKey);
  }

  /* --------------------------------------------------------------- checks */
  checkLater() {
    clearTimeout(this.checkTimer);
    this.checkTimer = setTimeout(async () => {
      try { this.setIssues((await api.send('/api/lint', { scene: this.scene })).issues); } catch { /* offline */ }
    }, 700);
  }

  setIssues(issues) {
    this.issues = issues || [];
    const box = document.getElementById('issues');
    const errors = this.issues.filter((i) => i.severity === 'error').length;
    box.classList.toggle('bad', errors > 0);
    if (!this.issues.length) { box.textContent = ''; box.title = ''; return; }
    box.textContent = getLang() === 'zh' ? `版面提示 ${this.issues.length}` : `${this.issues.length} layout notes`;
    box.title = this.issues.map((i) => say(i.message)).join('\n');
  }

  /* --------------------------------------------------------------- events */
  bind() {
    const wrap = this.wrap;

    wrap.addEventListener('mousedown', (e) => {
      if (e.button === 1 || (e.button === 0 && e.altKey)) {
        this.drag = { kind: 'pan', x: e.clientX, y: e.clientY, pan: { ...this.pan } };
        wrap.classList.add('dragging');
        e.preventDefault();
        return;
      }
      if (e.button !== 0) return;
      wrap.focus();
      const [x, y] = this.toScene(e.clientX, e.clientY);
      const handle = e.target.dataset ? e.target.dataset.handle : null;
      const port = e.target.dataset ? e.target.dataset.port : null;

      if (port) {
        const from = e.target.dataset.node;
        const [px, py] = S.sideAnchor(this.byId(from), port, 0);
        this.drag = { kind: 'connect', node: from, side: port, from: [px, py], to: [x, y] };
        return;
      }
      if (handle && this.selection.size === 1) {
        const node = (this.scene.nodes || []).find((n) => n.id === [...this.selection][0]);
        this.pushUndo();
        this.drag = { kind: handle === 'rotate' ? 'rotate' : 'resize', handle, node, start: { ...node }, origin: [x, y] };
        return;
      }
      const hit = this.pick(x, y);
      if (this.tool === 'text' || this.tool === 'note') {
        const node = this.addNode(this.tool === 'text' ? 'text' : 'note', [x, y]);
        this.setTool('select');
        if (node) this.editText(node.id);
        return;
      }
      if (this.tool === 'connect') {
        if (hit && !this.isEdge(hit)) {
          const node = this.byId(hit);
          this.drag = { kind: 'connect', node: hit, side: null, from: S.center(node), to: [x, y] };
        }
        return;
      }
      if (!hit) {
        if (!e.shiftKey) this.selection.clear();
        this.drag = { kind: 'marquee', x0: x, y0: y, x1: x, y1: y, add: e.shiftKey, before: new Set(this.selection) };
        this.render();
        return;
      }
      if (e.shiftKey) this.select(hit, true);
      else if (!this.selection.has(hit)) this.select(hit);
      if (!this.isEdge(hit)) {
        this.pushUndo();
        const ids = this.movingSet(this.selection);
        this.drag = {
          kind: 'move', origin: [x, y], moved: false,
          nodes: (this.scene.nodes || []).filter((n) => ids.has(n.id)).map((n) => ({ node: n, x: n.x, y: n.y })),
        };
      }
    });

    window.addEventListener('mousemove', (e) => {
      const d = this.drag;
      if (!d) {
        if (this.tool === 'connect') {
          const [x, y] = this.toScene(e.clientX, e.clientY);
          const hit = this.pick(x, y);
          const node = hit && !this.isEdge(hit) ? hit : null;
          if (node !== this.hover) { this.hover = node; this.render(); }
        }
        return;
      }
      const [x, y] = this.toScene(e.clientX, e.clientY);
      if (d.kind === 'pan') {
        this.pan = { x: d.pan.x + (e.clientX - d.x), y: d.pan.y + (e.clientY - d.y) };
        this.svg.style.transform = `translate(${this.pan.x}px, ${this.pan.y}px)`;
        return;
      }
      if (d.kind === 'move') {
        let dx = x - d.origin[0];
        let dy = y - d.origin[1];
        if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
        const snap = e.ctrlKey || e.metaKey ? 1 : 2;
        for (const item of d.nodes) {
          item.node.x = Math.round((item.x + dx) / snap) * snap;
          item.node.y = Math.round((item.y + dy) / snap) * snap;
        }
        d.moved = Math.abs(dx) + Math.abs(dy) > 1;
        this.render();
        return;
      }
      if (d.kind === 'resize') {
        const s = d.start;
        const dx = x - d.origin[0];
        const dy = y - d.origin[1];
        const n = d.node;
        const west = d.handle.includes('w');
        const east = d.handle.includes('e');
        const north = d.handle.includes('n');
        const south = d.handle.includes('s');
        let w = s.w + (east ? dx : 0) - (west ? dx : 0);
        let h = s.h + (south ? dy : 0) - (north ? dy : 0);
        if (e.shiftKey && (east || west) && (north || south)) {
          const k = Math.max(w / s.w, h / s.h);
          w = s.w * k; h = s.h * k;
        }
        w = Math.max(MIN_SIZE, Math.round(w));
        h = Math.max(MIN_SIZE, Math.round(h));
        n.w = w; n.h = h;
        n.x = Math.round(west ? s.x + s.w - w : s.x);
        n.y = Math.round(north ? s.y + s.h - h : s.y);
        this.render();
        return;
      }
      if (d.kind === 'rotate') {
        const n = d.node;
        const [cx, cy] = S.center(n);
        let deg = (Math.atan2(y - cy, x - cx) * 180) / Math.PI + 90;
        if (e.shiftKey) deg = Math.round(deg / 15) * 15;
        n.rotation = Math.round(((deg % 360) + 360) % 360);
        if (n.rotation === 0) delete n.rotation;
        this.render();
        return;
      }
      if (d.kind === 'marquee') { d.x1 = x; d.y1 = y; this.render(); return; }
      if (d.kind === 'connect') { d.to = [x, y]; this.hover = this.pick(x, y); this.render(); }
    });

    window.addEventListener('mouseup', (e) => {
      const d = this.drag;
      this.drag = null;
      wrap.classList.remove('dragging');
      if (!d) return;
      if (d.kind === 'marquee') {
        const [x0, x1] = [Math.min(d.x0, d.x1), Math.max(d.x0, d.x1)];
        const [y0, y1] = [Math.min(d.y0, d.y1), Math.max(d.y0, d.y1)];
        if (!d.add) this.selection.clear();
        if (x1 - x0 > 3 || y1 - y0 > 3) {
          for (const n of this.scene.nodes || []) {
            const b = S.visualBox(n);
            if (b[0] >= x0 && b[1] >= y0 && b[2] <= x1 && b[3] <= y1 && !n.hidden) this.selection.add(n.id);
          }
        }
        this.render();
        return;
      }
      if (d.kind === 'connect') {
        const [x, y] = this.toScene(e.clientX, e.clientY);
        const target = this.pick(x, y);
        const side = e.target.dataset ? e.target.dataset.port : null;
        this.hover = null;
        if (target && !this.isEdge(target) && target !== d.node) this.addEdge(d.node, target, d.side, side);
        else this.render();
        return;
      }
      if (d.kind === 'move' && !d.moved) { this.undoStack.pop(); this.render(); return; }
      if (['move', 'resize', 'rotate'].includes(d.kind)) {
        if (this.growCanvas()) status(getLang() === 'zh' ? '画布已自动变大' : 'The canvas grew to fit');
        this.commit();
      }
    });

    wrap.addEventListener('dblclick', (e) => {
      const [x, y] = this.toScene(e.clientX, e.clientY);
      const hit = this.pick(x, y);
      if (hit && !this.isEdge(hit)) this.editText(hit);
      else if (hit) {
        const edge = this.byId(hit);
        const text = window.prompt === undefined ? null : null;
        if (text === null) { /* edge labels are edited in the properties panel */ }
      }
    });

    wrap.addEventListener('wheel', (e) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const box = this.wrap.getBoundingClientRect();
        this.setZoom(this.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12), e.clientX - box.left, e.clientY - box.top);
      } else {
        e.preventDefault();
        this.pan.x -= e.deltaX;
        this.pan.y -= e.deltaY;
        this.svg.style.transform = `translate(${this.pan.x}px, ${this.pan.y}px)`;
      }
    }, { passive: false });

    wrap.addEventListener('keydown', (e) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? this.redo() : this.undo(); return; }
      if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); this.redo(); return; }
      if (mod && e.key.toLowerCase() === 'd') { e.preventDefault(); this.duplicate(); return; }
      if (mod && e.key.toLowerCase() === 'a') {
        e.preventDefault();
        for (const n of this.scene.nodes || []) this.selection.add(n.id);
        this.render();
        return;
      }
      if (mod && e.key.toLowerCase() === 'g') { e.preventDefault(); e.shiftKey ? this.ungroup() : this.group(); return; }
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); this.remove([...this.selection]); return; }
      if (e.key === 'Escape') { this.selection.clear(); this.setTool('select'); this.render(); return; }
      if (e.key === 'Enter' && this.selection.size === 1) { e.preventDefault(); this.editText([...this.selection][0]); return; }
      if (['v', 'c', 't', 'n'].includes(e.key.toLowerCase()) && !mod) {
        this.setTool({ v: 'select', c: 'connect', t: 'text', n: 'note' }[e.key.toLowerCase()]);
        return;
      }
      if (e.key.startsWith('Arrow')) {
        const step = e.shiftKey ? 10 : 1;
        const dx = (e.key === 'ArrowRight' ? step : 0) - (e.key === 'ArrowLeft' ? step : 0);
        const dy = (e.key === 'ArrowDown' ? step : 0) - (e.key === 'ArrowUp' ? step : 0);
        const nodes = this.selectedNodes();
        if (!nodes.length) return;
        e.preventDefault();
        this.change(() => { for (const n of nodes) { n.x += dx; n.y += dy; } });
      }
    });

    for (const b of document.querySelectorAll('#toolbar button[data-tool]')) {
      b.addEventListener('click', () => this.setTool(b.dataset.tool));
    }
    document.getElementById('undo').addEventListener('click', () => this.undo());
    document.getElementById('redo').addEventListener('click', () => this.redo());
    document.getElementById('zoom-in').addEventListener('click', () => this.setZoom(this.zoom * 1.2));
    document.getElementById('zoom-out').addEventListener('click', () => this.setZoom(this.zoom / 1.2));
    document.getElementById('zoom-fit').addEventListener('click', () => { this.fit(); this.render(); });
    document.getElementById('add-shape').addEventListener('change', (e) => {
      if (e.target.value) this.addNode(e.target.value);
      e.target.value = '';
    });
    document.getElementById('add-icon').addEventListener('change', (e) => {
      if (e.target.value) {
        const node = this.addNode('icon');
        this.change(() => { node.icon = e.target.value; });
      }
      e.target.value = '';
    });
    document.getElementById('issues').addEventListener('click', () => {
      if (this.issues && this.issues.length) status(this.issues.map((i) => say(i.message)).join('  ·  '));
    });
    window.addEventListener('resize', () => { this.fit(); this.render(); });
    this.wrap.addEventListener('dragover', (e) => e.preventDefault());
    this.wrap.addEventListener('drop', async (e) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (!file) return;
      const data = new FormData();
      data.append('file', file);
      try {
        const out = await api.form('/api/import', data);
        this.load(out.scene, { notes: out.notes, label: 'import' });
      } catch (err) { fail(err); }
    });
  }

  setTool(tool) {
    this.tool = tool;
    this.hover = null;
    for (const b of document.querySelectorAll('#toolbar button[data-tool]')) b.classList.toggle('on', b.dataset.tool === tool);
    this.wrap.style.cursor = tool === 'select' ? '' : 'crosshair';
    this.render();
  }

  /** Put a picture (data URL) on the canvas at its natural size. */
  placeImage(href, width, height, title) {
    const scale = Math.min(1, (this.scene.width - 80) / Math.max(1, width));
    const taken = new Set((this.scene.nodes || []).map((n) => n.id));
    const node = {
      id: uid('img', taken), type: 'image', href,
      w: Math.round(width * scale), h: Math.round(height * scale),
      x: 40, y: 40, text: '',
    };
    const b = S.sceneBounds(this.scene);
    if (b) node.y = Math.round(b[3] + 30);
    this.change(() => {
      this.scene.nodes.push(node);
      this.growCanvas();
      this.selection.clear();
      this.selection.add(node.id);
    }, title || '');
    return node;
  }
}
