/* The chart tab: load a table, pick a chart, get the statistics a paper needs. */

import { api, busy, el, fail, options, runJob, saveBlob, state, status, toast } from './app.js';
import { sayAll } from './notes.js';
import { getLang, name, t } from './i18n.js';

const plot = {
  csv: '', columns: [], spec: {}, info: null, filename: 'chart',
};

function zh() { return getLang() === 'zh'; }

function showTable(out) {
  plot.csv = out.csv;
  plot.columns = out.columns;
  const box = document.getElementById('table-preview');
  const table = el('table');
  const head = el('tr');
  for (const c of out.preview.columns) head.append(el('th', { text: c }));
  table.append(el('thead', {}, [head]));
  const body = el('tbody');
  for (const row of out.preview.rows) {
    const tr = el('tr');
    for (const v of row) tr.append(el('td', { text: String(v) }));
    body.append(tr);
  }
  table.append(body);
  box.replaceChildren(table);
  const info = el('p', { class: 'note', text: `${out.rows} ${zh() ? '行' : 'rows'} × ${out.columns.length} ${zh() ? '列' : 'columns'}` });
  box.append(info);
  for (const n of out.notes || []) toast(n);
  const sheetSel = document.getElementById('sheet');
  sheetSel.classList.toggle('hidden', (out.sheets || []).length < 2);
  if ((out.sheets || []).length > 1) options(sheetSel, out.sheets, null, out.sheets[0]);
}

async function loadFile(file, sheet) {
  const data = new FormData();
  data.append('file', file);
  if (sheet) data.append('sheet', sheet);
  busy(file.name);
  try {
    plot.filename = file.name.replace(/\.[^.]+$/, '');
    plot.lastFile = file;
    showTable(await api.form('/api/plot/table', data));
    plot.spec = {};
    await render();
  } catch (err) { fail(err); } finally { busy(null); }
}

async function loadText(text) {
  const data = new FormData();
  data.append('text', text);
  busy(zh() ? '读取数据' : 'Reading the table');
  try {
    showTable(await api.form('/api/plot/table', data));
    plot.spec = {};
    await render();
  } catch (err) { fail(err); } finally { busy(null); }
}

export async function render() {
  if (!plot.csv) return;
  try {
    const out = await api.send('/api/plot/render', { csv: plot.csv, spec: plot.spec, theme: document.getElementById('theme').value, lang: getLang() });
    plot.spec = out.spec;
    plot.info = out;
    document.getElementById('chart').innerHTML = out.svg;
    document.getElementById('plot-caption').textContent = out.caption[getLang()] || '';
    drawSpec();
    drawStats(out);
    for (const n of sayAll(out.notes)) toast(n);
  } catch (err) { fail(err); }
}

function drawSpec() {
  const box = document.getElementById('plot-spec');
  box.replaceChildren();
  if (!plot.columns.length) {
    box.append(el('p', { class: 'note', text: zh() ? '先打开一个表格。' : 'Open a table first.' }));
    return;
  }
  const spec = plot.spec;
  const names = plot.columns.map((c) => c.name);
  const numeric = plot.columns.filter((c) => c.numeric).map((c) => c.name);
  const set = (patch) => { Object.assign(plot.spec, patch); render(); };

  const row = (label, control) => el('div', { class: 'prop' }, [el('label', { text: label }), control]);
  const select = (values, current, onPick, group, blank) => {
    const sel = el('select');
    if (blank) sel.append(el('option', { value: '', text: blank, selected: !current }));
    for (const v of values) sel.append(el('option', { value: v, text: group ? name(group, v) : v, selected: v === current }));
    sel.addEventListener('change', () => onPick(sel.value));
    return sel;
  };

  box.append(row(zh() ? '图型' : 'Chart', select(state.meta.plot_kinds, spec.kind, (v) => set({ kind: v }), 'plotKind')));
  box.append(row(zh() ? '横轴' : 'X', select(names, spec.x, (v) => set({ x: v }), null, zh() ? '自动' : 'auto')));

  const ySel = el('select', { multiple: true, size: Math.min(5, Math.max(3, numeric.length)) });
  for (const n of numeric) ySel.append(el('option', { value: n, text: n, selected: (spec.y || []).includes(n) }));
  ySel.addEventListener('change', () => set({ y: [...ySel.selectedOptions].map((o) => o.value) }));
  box.append(row(zh() ? '纵轴' : 'Y', ySel));
  box.append(row(zh() ? '分组' : 'Group', select(names, spec.group || '', (v) => set({ group: v || null }), null, zh() ? '不分组' : 'none')));
  box.append(row(zh() ? '误差线' : 'Error', select([...state.meta.plot_errors, 'none'], spec.error || 'none', (v) => set({ error: v === 'none' ? null : v }), 'plotError')));
  box.append(row(zh() ? '配色' : 'Palette', select(state.meta.plot_palettes, spec.palette, (v) => set({ palette: v }), 'palette')));

  const checks = el('div');
  for (const [key, label] of [
    ['stats', zh() ? '组间检验与显著性标记' : 'Compare groups, show significance'],
    ['points', zh() ? '画出每个数据点' : 'Show individual points'],
    ['fit', zh() ? '回归拟合线' : 'Regression line'],
    ['logy', zh() ? '纵轴取对数' : 'Log y axis'],
    ['logx', zh() ? '横轴取对数' : 'Log x axis'],
    ['zscore', zh() ? '按行标准化（热图）' : 'Z-score rows (heatmap)'],
  ]) {
    const input = el('input', { type: 'checkbox', checked: Boolean(spec[key]) });
    input.addEventListener('change', () => set({ [key]: input.checked }));
    checks.append(el('label', { class: 'check', style: 'display:flex;margin:3px 0' }, [input, el('span', { text: label })]));
  }
  box.append(checks);

  for (const [key, label] of [['title', zh() ? '标题' : 'Title'], ['xlabel', zh() ? '横轴标题' : 'X label'], ['ylabel', zh() ? '纵轴标题' : 'Y label']]) {
    const input = el('input', { type: 'text', value: spec[key] || '' });
    input.addEventListener('change', () => set({ [key]: input.value }));
    box.append(row(label, input));
  }

  box.append(el('div', { class: 'row' }, [
    el('button', { class: 'grow', text: zh() ? '放到画布' : 'Put on canvas', onclick: toCanvas }),
  ]));
}

function drawStats(out) {
  const box = document.getElementById('plot-stats');
  box.replaceChildren();
  const st = out.stats;
  if (!st || !st.test) {
    box.append(el('p', { class: 'note', text: zh() ? '勾上“组间检验”就会算统计量，并把星号标在图上。' : 'Tick "compare groups" to run the test and draw the brackets.' }));
    if (out.fit) {
      const f = out.fit;
      const fix = (v, d) => (typeof v === 'number' && Number.isFinite(v) ? v.toFixed(d) : '—');
      box.append(el('p', { text: `r = ${fix(f.r, 3)}, R² = ${fix(f.r2, 3)}, p = ${typeof f.p === 'number' && Number.isFinite(f.p) ? f.p.toExponential(2) : '—'}, n = ${f.n}` }));
    }
    return;
  }
  const n = (v, digits = 4) => (typeof v === 'number' && Number.isFinite(v) ? v.toPrecision(digits) : '—');
  const pval = (v) => (typeof v === 'number' && Number.isFinite(v) ? (v < 0.0001 ? v.toExponential(1) : v.toFixed(4)) : '—');
  const omnibus = st.omnibus ? ` · ${st.omnibus.test} p = ${pval(st.omnibus.p)}` : '';
  box.append(el('p', { text: `${st.test}${omnibus}` }));
  const table = el('table');
  for (const g of st.groups || []) {
    table.append(el('tr', {}, [el('td', { text: g.name }), el('td', { text: `n = ${g.n}` }), el('td', { text: `${n(g.mean)} ± ${n(g.sd, 3)}` })]));
  }
  for (const c of st.comparisons || []) {
    table.append(el('tr', {}, [
      el('td', { text: `${c.a} vs ${c.b}` }),
      el('td', { text: `p = ${pval(c.p_adj ?? c.p)}` }),
      el('td', { class: 'sig', text: c.stars || 'ns' }),
    ]));
  }
  box.append(table);
  for (const n of sayAll(st.notes)) box.append(el('p', { class: 'note', text: n }));
}

async function toCanvas() {
  try {
    busy(zh() ? '生成图片' : 'Rendering');
    const out = await api.send('/api/plot/image', { csv: plot.csv, spec: plot.spec, theme: document.getElementById('theme').value });
    state.editor.placeImage(out.image, out.width, out.height, out.title);
    document.querySelector('#tabs button[data-go="draw"]').click();
    toast(zh() ? '图已放到画布上，可以和别的面板拼在一起' : 'The chart is on the canvas, ready to be combined into a panel figure');
  } catch (err) { fail(err); } finally { busy(null); }
}

async function exportChart(format) {
  try {
    busy(format.toUpperCase());
    const out = await api.download('/api/plot/export', {
      csv: plot.csv, spec: plot.spec, theme: document.getElementById('theme').value, format, lang: getLang(), dpi: 600,
    });
    saveBlob(out.blob, out.filename);
    for (const n of out.notes) toast(n);
  } catch (err) { fail(err); } finally { busy(null); }
}

export function setupPlot() {
  const bar = document.getElementById('plot-toolbar');
  bar.append(el('span', { class: 'muted grow', text: zh() ? '统计图' : 'Charts' }));
  for (const fmt of ['svg', 'png', 'pdf', 'pptx']) {
    bar.append(el('button', { text: fmt.toUpperCase(), class: fmt === 'pptx' ? 'primary' : '', onclick: () => exportChart(fmt) }));
  }

  document.getElementById('table-file').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) loadFile(file);
    e.target.value = '';
  });
  document.getElementById('sheet').addEventListener('change', (e) => {
    if (plot.lastFile) loadFile(plot.lastFile, e.target.value);
  });
  const pasteBox = document.getElementById('table-paste');
  document.getElementById('table-paste-btn').addEventListener('click', () => {
    pasteBox.classList.toggle('hidden');
    if (!pasteBox.classList.contains('hidden')) pasteBox.focus();
  });
  pasteBox.addEventListener('change', () => { if (pasteBox.value.trim()) loadText(pasteBox.value); });

  document.getElementById('plot-ask-go').addEventListener('click', async () => {
    const box = document.getElementById('plot-ask');
    const prompt = box.value.trim();
    if (!prompt || !plot.csv) { if (!plot.csv) toast(zh() ? '先打开一个表格' : 'Open a table first', true); return; }
    try {
      const out = await runJob(() => api.send('/api/plot/suggest', { csv: plot.csv, prompt, spec: plot.spec }), zh() ? '想一想…' : 'Thinking...');
      if (out) {
        plot.spec = out.spec;
        box.value = '';
        for (const n of out.info.notes || []) toast(n);
        await render();
      }
    } catch (err) { fail(err); }
  });

  window.addEventListener('fw:template-plot', async (e) => {
    const tpl = e.detail;
    await loadText(tpl.csv);
    plot.spec = { ...tpl.spec };
    await render();
  });
  window.addEventListener('fw:lang', () => { if (plot.csv) drawSpec(); });
}
