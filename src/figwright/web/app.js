/* Figwright web app: wiring, API client, tabs and dialogs.
 * The drawing itself lives in editor.js, charts in plot.js, pictures in imagelab.js.
 */

import { getLang, name, setLang, t } from './i18n.js';
import { say } from './notes.js';
import * as S from './scene.js';
import { Editor } from './editor.js';
import { setupPlot } from './plot.js';
import { setupImageLab } from './imagelab.js';
import { setupSettings } from './settings.js';
import { setupProjects } from './projects.js';

export const state = {
  meta: null,
  config: null,
  editor: null,
  project: null, // {id, name, rev}
};

/* ------------------------------------------------------------------- api */
const TOKEN_KEY = 'fw.token';

function token() {
  const q = new URLSearchParams(location.search).get('token');
  if (q) {
    try { sessionStorage.setItem(TOKEN_KEY, q); } catch { /* private window */ }
    history.replaceState(null, '', location.pathname);
    return q;
  }
  try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
}

function headers(extra) {
  const h = { ...(extra || {}) };
  const tk = token();
  if (tk) h['X-Figwright-Token'] = tk;
  return h;
}

export class ApiError extends Error {
  constructor(message, code, status) { super(message); this.code = code; this.status = status; }
}

async function parse(res) {
  if (res.ok) return res;
  let message = `HTTP ${res.status}`;
  let code = 'http';
  try {
    const body = await res.json();
    if (body && body.error) { message = body.error.message || message; code = body.error.code || code; }
  } catch { /* not JSON */ }
  throw new ApiError(message, code, res.status);
}

export const api = {
  async get(path) {
    const res = await parse(await fetch(path, { headers: headers(), credentials: 'same-origin' }));
    return res.json();
  },
  async send(path, body, method = 'POST') {
    const res = await parse(await fetch(path, {
      method, credentials: 'same-origin',
      headers: headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body ?? {}),
    }));
    return res.status === 204 ? null : res.json();
  },
  async form(path, data) {
    const res = await parse(await fetch(path, { method: 'POST', credentials: 'same-origin', headers: headers(), body: data }));
    return res.json();
  },
  async del(path) {
    const res = await parse(await fetch(path, { method: 'DELETE', credentials: 'same-origin', headers: headers() }));
    return res.json();
  },
  /** POST that returns a file; hands back the blob plus the server's notes. */
  async download(path, body) {
    const res = await parse(await fetch(path, {
      method: 'POST', credentials: 'same-origin',
      headers: headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body ?? {}),
    }));
    const read = (h) => { try { return JSON.parse(decodeURIComponent(res.headers.get(h) || '')) ; } catch { return null; } };
    const disp = res.headers.get('Content-Disposition') || '';
    const star = /filename\*=UTF-8''([^;]+)/i.exec(disp);
    const plain = /filename="([^"]+)"/i.exec(disp);
    return {
      blob: await res.blob(),
      filename: star ? decodeURIComponent(star[1]) : (plain ? plain[1] : 'figwright'),
      notes: read('X-Figwright-Notes') || [],
      info: read('X-Figwright-Info'),
    };
  },
};

/** Start a background job and wait for it, showing progress. */
export async function runJob(start, label) {
  const { job } = await start();
  busy(label || '...', async () => { try { await api.del(`/api/jobs/${job}`); } catch { /* already gone */ } });
  try {
    for (let i = 0; ; i++) {
      await new Promise((r) => setTimeout(r, i < 10 ? 220 : 600));
      const view = await api.get(`/api/jobs/${job}`);
      if (view.stage) busyText(`${view.stage}${view.seconds > 2 ? `  ${Math.round(view.seconds)}s` : ''}`);
      if (view.status === 'done') return view.result;
      if (view.status === 'cancelled') return null;
      if (view.status === 'error') throw new ApiError(view.error?.message || 'failed', view.error?.code);
    }
  } finally { busy(null); }
}

/* ------------------------------------------------------------------- ui */
let busyCancel = null;
export function busy(text, onCancel) {
  const box = document.getElementById('busy');
  busyCancel = onCancel || null;
  document.getElementById('busy-cancel').classList.toggle('hidden', !onCancel);
  if (!text) { box.classList.add('hidden'); return; }
  busyText(text);
  box.classList.remove('hidden');
}
export function busyText(text) { document.getElementById('busy-text').textContent = text; }

let toastTimer = 0;
export function toast(message, bad = false) {
  const el = document.getElementById('toast');
  el.textContent = say(message);
  el.classList.toggle('bad', Boolean(bad));
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), bad ? 6500 : 3200);
}

export function fail(err) {
  const message = say(err instanceof ApiError ? err.message : (err && err.message) || String(err));
  toast(/Failed to fetch|NetworkError/i.test(message) ? t('err.network') : message, true);
  if (!(err instanceof ApiError)) console.error(err);
}

export function status(text) { document.getElementById('status').textContent = say(text) || ''; }

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'html') node.innerHTML = v;      // only ever called with values this app builds
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of [].concat(children)) if (c) node.append(c);
  return node;
}

export function options(select, values, group, current) {
  select.replaceChildren();
  for (const v of values) {
    const value = typeof v === 'string' ? v : v.id;
    const label = typeof v === 'string' ? (group ? name(group, v) : v) : (v.label?.[getLang()] || v.label || value);
    select.append(el('option', { value, text: label, selected: value === current }));
  }
  if (current !== undefined) select.value = current;
}

/** A modal dialog. `build(close)` fills the body; resolves with whatever close() was given. */
export function dialog(build) {
  const overlay = document.getElementById('overlay');
  const box = document.getElementById('dialog');
  return new Promise((resolve) => {
    const close = (value) => {
      overlay.classList.add('hidden');
      box.replaceChildren();
      document.removeEventListener('keydown', onKey);
      overlay.removeEventListener('mousedown', onBackdrop);
      resolve(value);
    };
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(undefined); } };
    const onBackdrop = (e) => { if (e.target === overlay) close(undefined); };
    box.replaceChildren();
    build(box, close);
    overlay.classList.remove('hidden');
    document.addEventListener('keydown', onKey);
    overlay.addEventListener('mousedown', onBackdrop);
    const first = box.querySelector('input, textarea, button.primary, button');
    if (first) first.focus();
  });
}

export function confirmBox(message, okLabel) {
  return dialog((box, close) => {
    box.append(el('p', { text: message }));
    box.append(el('div', { class: 'actions' }, [
      el('button', { class: 'ghost', text: t('cancel'), onclick: () => close(false) }),
      el('button', { class: 'primary', text: okLabel || t('ok'), onclick: () => close(true) }),
    ]));
  });
}

export function prompt(message, value) {
  return dialog((box, close) => {
    box.append(el('p', { text: message }));
    const input = el('input', { type: 'text', value: value || '' });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') close(input.value.trim()); });
    box.append(input);
    box.append(el('div', { class: 'actions' }, [
      el('button', { class: 'ghost', text: t('cancel'), onclick: () => close(undefined) }),
      el('button', { class: 'primary', text: t('ok'), onclick: () => close(input.value.trim()) }),
    ]));
  });
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/* ---------------------------------------------------------------- export */
const RASTER = ['png', 'jpeg', 'tiff', 'webp', 'pdf'];

export async function exportDialog(scene) {
  const sizes = state.meta.sizes[getLang()];
  const pick = { format: 'pptx', size: 'double', dpi: 300, transparent: false, notes: false, record: false, disclosure: true };
  const formats = [
    ['pptx', 'PowerPoint', getLang() === 'zh' ? '形状和文字都能继续改' : 'editable shapes and text'],
    ['svg', 'SVG', getLang() === 'zh' ? 'Illustrator、Inkscape 都认；再打开还能编辑' : 'opens in Illustrator or Inkscape, and reopens here'],
    ['png', 'PNG', getLang() === 'zh' ? '投稿最常要的位图' : 'the usual bitmap for submission'],
    ['tiff', 'TIFF', getLang() === 'zh' ? '很多期刊点名要' : 'asked for by many journals'],
    ['jpeg', 'JPEG', getLang() === 'zh' ? '有损，给幻灯片用' : 'lossy, fine for slides'],
    ['pdf', 'PDF', getLang() === 'zh' ? '位图 PDF；要矢量用下面的打印' : 'bitmap PDF; use Print below for vector'],
    ['html', getLang() === 'zh' ? '分享页' : 'Share page', getLang() === 'zh' ? '单个 HTML，发给别人直接看' : 'one HTML file anyone can open'],
    ['record', getLang() === 'zh' ? '制作记录' : 'Provenance record', getLang() === 'zh' ? '这张图是怎么来的' : 'how this figure was made'],
    ['json', 'JSON', getLang() === 'zh' ? '原始数据，方便脚本处理' : 'the raw scene, for scripts'],
  ];
  await dialog((box, close) => {
    box.append(el('h2', { text: t('export.title') }));
    const fmtWrap = el('div', { class: 'opts' });
    const sizeSet = el('fieldset');
    const refresh = () => {
      for (const b of fmtWrap.children) b.classList.toggle('on', b.dataset.v === pick.format);
      sizeSet.classList.toggle('hidden', !RASTER.includes(pick.format));
    };
    for (const [id, label, hint] of formats) {
      fmtWrap.append(el('button', { 'data-v': id, onclick: () => { pick.format = id; refresh(); } }, [
        el('b', { text: label }), el('small', { text: hint }),
      ]));
    }
    box.append(el('fieldset', {}, [el('legend', { text: t('export.format') }), fmtWrap]));

    const sizeSel = el('select');
    for (const s of sizes) sizeSel.append(el('option', { value: s.id, text: `${s.label} — ${s.mm} mm` }));
    sizeSel.value = pick.size;
    sizeSel.addEventListener('change', () => { pick.size = sizeSel.value; });
    const dpiSel = el('select');
    for (const d of [150, 300, 600, 1200]) dpiSel.append(el('option', { value: d, text: `${d} dpi`, selected: d === 300 }));
    dpiSel.addEventListener('change', () => { pick.dpi = Number(dpiSel.value); });
    const tr = el('input', { type: 'checkbox' });
    tr.addEventListener('change', () => { pick.transparent = tr.checked; });
    sizeSet.append(el('legend', { text: t('export.size') }), el('div', { class: 'row' }, [sizeSel, dpiSel]),
      el('label', { class: 'check' }, [tr, el('span', { text: t('export.transparent') })]));
    box.append(sizeSet);

    const notes = el('input', { type: 'checkbox' });
    notes.addEventListener('change', () => { pick.notes = notes.checked; });
    const disc = el('input', { type: 'checkbox', checked: true });
    disc.addEventListener('change', () => { pick.disclosure = disc.checked; });
    box.append(el('div', { class: 'row' }, [
      el('label', { class: 'check' }, [notes, el('span', { text: t('export.notes') })]),
      el('label', { class: 'check' }, [disc, el('span', { text: t('export.disclosure') })]),
    ]));

    box.append(el('div', { class: 'actions' }, [
      el('button', { class: 'ghost', text: t('export.print'), onclick: () => { close(); printVector(scene); } }),
      el('button', { class: 'ghost', text: t('cancel'), onclick: () => close() }),
      el('button', {
        class: 'primary', text: t('export.go'),
        onclick: async () => {
          close();
          const size = sizes.find((s) => s.id === pick.size);
          try {
            busy(t('export.go'));
            const body = {
              scene, format: pick.format, lang: getLang(), include_notes: pick.notes,
              disclosure: pick.disclosure, name: scene.title || 'figure',
            };
            if (RASTER.includes(pick.format)) { body.dpi = pick.dpi; body.width_mm = size ? size.width_mm : null; body.transparent = pick.transparent; }
            const out = await api.download('/api/export', body);
            saveBlob(out.blob, out.filename);
            if (out.info && out.info.width) status(`${out.filename}  ${out.info.width} x ${out.info.height} px`);
            for (const n of out.notes) toast(n);
          } catch (err) { fail(err); } finally { busy(null); }
        },
      }),
    ]));
    refresh();
  });
}

/** Vector PDF without a server round trip: print a page that holds only the figure. */
export function printVector(scene) {
  const root = document.getElementById('print-root');
  root.innerHTML = S.renderSvg(scene, false);
  const mm = (px) => (px / 96) * 25.4;
  const sheet = el('style', { text: `@page { size: ${mm(scene.width).toFixed(1)}mm ${mm(scene.height).toFixed(1)}mm; margin: 0 }` });
  document.head.append(sheet);
  const cleanup = () => { sheet.remove(); root.replaceChildren(); window.removeEventListener('afterprint', cleanup); };
  window.addEventListener('afterprint', cleanup);
  setTimeout(() => window.print(), 60);
}

/* ------------------------------------------------------------------ tabs */
export function showTab(id) {
  document.body.dataset.tab = id;
  for (const b of document.querySelectorAll('#tabs button')) b.classList.toggle('on', b.dataset.go === id);
  for (const s of document.querySelectorAll('.tab')) s.classList.toggle('on', s.id === `tab-${id}`);
  window.dispatchEvent(new CustomEvent('fw:tab', { detail: id }));
}

/* ------------------------------------------------------------------ boot */
async function boot() {
  const [meta, icons, config] = await Promise.all([api.get('/api/meta'), api.get('/api/icons'), api.get('/api/config')]);
  state.meta = meta;
  state.config = config;
  S.setIcons(icons.icons);
  state.icons = icons;
  setLang(meta.lang);
  document.getElementById('version').textContent = `v${meta.version}`;
  document.getElementById('offline-flag').classList.toggle('hidden', !meta.offline.text);

  state.editor = new Editor(document.getElementById('canvas'), document.getElementById('canvas-wrap'));
  setupDraw();
  setupPlot();
  setupImageLab();
  setupSettings();
  setupProjects();

  for (const b of document.querySelectorAll('#tabs button')) b.addEventListener('click', () => showTab(b.dataset.go));
  document.getElementById('lang-btn').addEventListener('click', () => {
    const next = setLang(getLang() === 'zh' ? 'en' : 'zh');
    api.send('/api/config', { lang: next }, 'PUT').catch(() => {});
    window.dispatchEvent(new CustomEvent('fw:lang'));
  });
  document.getElementById('busy-cancel').addEventListener('click', () => { if (busyCancel) busyCancel(); });
  window.addEventListener('beforeunload', (e) => {
    if (state.editor && state.editor.dirty) { e.preventDefault(); e.returnValue = ''; }
  });
  state.editor.blank();
}

/* ------------------------------------------------------------- draw tab */
function setupDraw() {
  const meta = state.meta;
  const ed = state.editor;
  options(document.getElementById('kind'), ['auto', ...meta.kinds], 'kind', 'auto');
  options(document.getElementById('quality'), meta.qualities, 'quality', 'balanced');
  options(document.getElementById('ill-style'), meta.image_styles, 'style', 'flat');
  options(document.getElementById('cvd'), ['', ...meta.cvd_kinds], 'cvd', '');
  options(document.getElementById('add-shape'), ['', ...meta.node_types.filter((n) => !['path', 'image'].includes(n))], 'node', '');
  document.getElementById('add-shape').firstChild.textContent = getLang() === 'zh' ? '加形状…' : 'Add shape…';
  const themeSel = document.getElementById('theme');
  options(themeSel, meta.themes, null, meta.default_theme);
  const iconSel = document.getElementById('add-icon');
  iconSel.append(el('option', { value: '', text: getLang() === 'zh' ? '加图标…' : 'Add icon…' }));
  fillIconSelect(iconSel);
  document.getElementById('refine-help').textContent = meta.refine_help[getLang()] || meta.refine_help.zh || '';

  const kindSel = document.getElementById('kind');
  const promptBox = document.getElementById('prompt');
  let source = '';

  document.getElementById('go').addEventListener('click', async () => {
    const text = promptBox.value.trim();
    if (!text && !source) { promptBox.focus(); return; }
    try {
      const out = await runJob(() => api.send('/api/generate', {
        prompt: text, kind: kindSel.value, theme: themeSel.value,
        quality: document.getElementById('quality').value, source,
      }), getLang() === 'zh' ? '正在画…' : 'Drawing...');
      if (out) ed.load(out.scene, { notes: out.notes, issues: out.issues, label: 'generate' });
    } catch (err) { fail(err); }
  });

  document.getElementById('example').addEventListener('click', () => {
    const kind = kindSel.value === 'auto' ? meta.kinds[Math.floor(Math.random() * meta.kinds.length)] : kindSel.value;
    const list = (meta.examples[kind] || {})[getLang()] || [];
    if (list.length) { promptBox.value = list[Math.floor(Math.random() * list.length)]; kindSel.value = kind; }
  });

  document.getElementById('source-file').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = '';
    try {
      const data = new FormData();
      data.append('file', file);
      busy(file.name);
      const out = await api.form('/api/source', data);
      source = out.text;
      const note = document.getElementById('source-note');
      note.classList.remove('hidden');
      note.textContent = `${out.name}: ${out.chars} ${getLang() === 'zh' ? '字' : 'characters'}${out.notes.length ? '  ·  ' + out.notes.join(' ') : ''}`;
    } catch (err) { fail(err); } finally { busy(null); }
  });

  document.getElementById('sketch-file').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = '';
    const data = new FormData();
    data.append('file', file);
    data.append('prompt', promptBox.value.trim());
    data.append('theme', themeSel.value);
    try {
      const out = await runJob(() => api.form('/api/sketch', data), getLang() === 'zh' ? '看草图…' : 'Reading the sketch...');
      if (out) ed.load(out.scene, { notes: out.notes, issues: out.issues, label: 'sketch' });
    } catch (err) { fail(err); }
  });

  document.getElementById('import-file').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = '';
    const data = new FormData();
    data.append('file', file);
    try {
      busy(file.name);
      const out = await api.form('/api/import', data);
      ed.load(out.scene, { notes: out.notes, label: 'import' });
      state.project = null;
      if (!out.editable) toast(getLang() === 'zh' ? '这是一张图片，已放到画布上' : 'That is a picture; it is now on the canvas');
    } catch (err) { fail(err); } finally { busy(null); }
  });

  document.getElementById('ill-go').addEventListener('click', async () => {
    const text = document.getElementById('ill-prompt').value.trim();
    if (!text) return;
    const data = new FormData();
    data.append('prompt', text);
    data.append('style', document.getElementById('ill-style').value);
    data.append('theme', themeSel.value);
    try {
      const out = await runJob(() => api.form('/api/illustrate', data), getLang() === 'zh' ? '作画…' : 'Painting...');
      if (out) ed.load(out.scene, { notes: out.notes, label: 'illustrate' });
    } catch (err) { fail(err); }
  });

  document.getElementById('refine').addEventListener('click', async () => {
    const box = document.getElementById('instruct');
    const instruction = box.value.trim();
    if (!instruction) return;
    try {
      const out = await runJob(() => api.send('/api/refine', {
        scene: ed.scene, instruction, selection: [...ed.selection],
      }), getLang() === 'zh' ? '修改中…' : 'Editing...');
      if (out) {
        ed.load(out.scene, { notes: out.notes, issues: out.issues, label: 'refine', keepSelection: true });
        box.value = '';
        if (out.summary) status(out.summary);
      }
    } catch (err) { fail(err); }
  });

  document.getElementById('tidy').addEventListener('click', async () => {
    try {
      busy(t('draw.tidy'));
      const out = await api.send('/api/autofix', { scene: ed.scene, snap: true });
      ed.load(out.scene, { notes: out.notes, issues: out.issues, label: 'tidy', keepSelection: true });
    } catch (err) { fail(err); } finally { busy(null); }
  });

  document.getElementById('polish').addEventListener('click', async () => {
    try {
      const out = await runJob(() => api.send('/api/polish', { scene: ed.scene }), t('draw.polish'));
      if (out) ed.load(out.scene, { notes: out.notes, issues: out.issues, label: 'polish', keepSelection: true });
    } catch (err) { fail(err); }
  });

  themeSel.addEventListener('change', async () => {
    try {
      const out = await api.send('/api/retheme', { scene: ed.scene, theme: themeSel.value });
      ed.load(out.scene, { label: 'theme', keepSelection: true });
    } catch (err) { fail(err); }
  });

  document.getElementById('export').addEventListener('click', () => exportDialog(ed.scene));
  document.getElementById('show-notes').addEventListener('change', (e) => ed.setShowNotes(e.target.checked));
  document.getElementById('cvd').addEventListener('change', (e) => ed.setCvd(e.target.value));
  document.getElementById('lock-style').addEventListener('change', async (e) => {
    const style = e.target.checked ? ed.scene.style : null;
    try {
      await api.send('/api/config', { house_style: style }, 'PUT');
      toast(e.target.checked
        ? (getLang() === 'zh' ? '以后生成的图都沿用这套样式' : 'New figures will follow this style')
        : (getLang() === 'zh' ? '已解除锁定' : 'Unlocked'));
    } catch (err) { fail(err); }
  });

  // Templates gallery
  const gallery = document.getElementById('templates');
  for (const tpl of meta.templates) {
    gallery.append(el('button', { title: tpl.label[getLang()], onclick: () => useTemplate(tpl) }, [
      el('span', { html: iconMarkup(tpl.icon) }),
      el('span', { text: tpl.label[getLang()] }),
    ]));
  }
}

/** Group the icon library by category for a <select>, in the current language. */
export function fillIconSelect(select, current) {
  const meta = state.icons.meta || {};
  const cats = state.icons.categories || {};
  const byCat = new Map();
  for (const n of Object.keys(state.icons.icons || {})) {
    const cat = (meta[n] && meta[n].cat) || 'general';
    if (!byCat.has(cat)) byCat.set(cat, []);
    byCat.get(cat).push(n);
  }
  for (const [cat, names] of byCat) {
    const label = (cats[cat] && (cats[cat][getLang()] || cats[cat].zh)) || cat;
    const group = el('optgroup', { label });
    for (const n of names.sort()) {
      group.append(el('option', { value: n, text: getLang() === 'zh' ? ((meta[n] && meta[n].zh) || n) : n, selected: n === current }));
    }
    select.append(group);
  }
  if (current) select.value = current;
  return select;
}

function iconMarkup(iconName) {
  const body = S.iconSvg(iconName, 0, 0, 26, '#dbe9f8', '#1b2a4a', '#e8a33d', 2);
  return `<svg viewBox="0 0 26 26" width="26" height="26" aria-hidden="true">${body}</svg>`;
}

async function useTemplate(tpl) {
  const ed = state.editor;
  const theme = document.getElementById('theme').value;
  if (tpl.type === 'illustrate') {
    document.getElementById('ill-prompt').value = tpl.prompt?.[getLang()] || '';
    document.getElementById('ill-style').value = tpl.style || 'flat';
    document.getElementById('ill-go').click();
    return;
  }
  if (tpl.type === 'plot') {
    showTab('plot');
    window.dispatchEvent(new CustomEvent('fw:template-plot', { detail: tpl }));
    return;
  }
  if (tpl.form === 'prisma') {
    const content = await prismaDialog(tpl);
    if (!content) return;
    try {
      busy(tpl.label[getLang()]);
      const out = await api.send('/api/template', { kind: tpl.kind, content, theme });
      ed.load(out.scene, { notes: out.notes, issues: out.issues, label: 'template' });
    } catch (err) { fail(err); } finally { busy(null); }
    return;
  }
  try {
    busy(tpl.label[getLang()]);
    const out = await api.send('/api/template', { kind: tpl.kind, content: tpl.content[getLang()] || tpl.content.en, theme });
    ed.load(out.scene, { notes: out.notes, issues: out.issues, label: 'template' });
    toast(getLang() === 'zh' ? '模板已放好，直接在画布上改文字' : 'Template ready: edit the text straight on the canvas');
  } catch (err) { fail(err); } finally { busy(null); }
}

/** PRISMA asks for counts, so it gets a small form instead of a canned example. */
function prismaDialog(tpl) {
  const fields = tpl.fields || [];
  const base = tpl.content[getLang()] || tpl.content.en || {};
  return dialog((box, close) => {
    box.append(el('h2', { text: tpl.label[getLang()] }));
    box.append(el('p', { class: 'note', text: getLang() === 'zh' ? '填你自己的数字，留空的行不会画出来。' : 'Put in your own counts; empty rows are left out.' }));
    const inputs = {};
    for (const f of fields) {
      const input = el('input', { type: 'number', min: '0', value: base[f.id] ?? '' });
      inputs[f.id] = input;
      box.append(el('div', { class: 'prop' }, [el('label', { text: f.label[getLang()] || f.id, style: 'width:200px' }), input]));
    }
    box.append(el('div', { class: 'actions' }, [
      el('button', { class: 'ghost', text: t('cancel'), onclick: () => close(undefined) }),
      el('button', {
        class: 'primary', text: t('ok'),
        onclick: () => {
          const content = {};
          for (const [k, input] of Object.entries(inputs)) if (input.value !== '') content[k] = Number(input.value);
          close(content);
        },
      }),
    ]));
  });
}

boot().catch((err) => {
  fail(err);
  document.getElementById('status').textContent = String(err);
});
