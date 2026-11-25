/* The image lab: clean up a photo or scan, trace it to vector, or redraw a region. */

import { api, busy, el, fail, options, runJob, saveBlob, state, toast } from './app.js';
import { sayAll } from './notes.js';
import { getLang } from './i18n.js';

const lab = {
  file: null,      // the original File
  current: null,   // data URL being shown
  original: null,
  info: null,
  box: null,       // selected region in image pixels
  natural: [0, 0],
};

const zh = () => getLang() === 'zh';

const CONTROLS = [
  { id: 'whiten', kind: 'check', zh: '压平光照、把纸压白', en: 'Flatten lighting, whiten the paper' },
  { id: 'denoise', kind: 'range', zh: '去噪', en: 'Denoise' },
  { id: 'contrast', kind: 'range', zh: '局部对比度', en: 'Local contrast' },
  { id: 'sharpen', kind: 'range', zh: '锐化', en: 'Sharpen' },
  { id: 'remove_bg', kind: 'check', zh: '去掉背景（透明）', en: 'Remove the background' },
  { id: 'bg_tolerance', kind: 'range', zh: '去背景容差', en: 'Background tolerance', when: 'remove_bg' },
  { id: 'trim', kind: 'check', zh: '裁掉空白边', en: 'Trim empty margins' },
  { id: 'grayscale', kind: 'check', zh: '转灰度', en: 'Convert to greyscale' },
  { id: 'upscale', kind: 'range', zh: '放大倍数', en: 'Upscale', min: 1, max: 4, step: 0.5, value: 1 },
  { id: 'width_mm', kind: 'number', zh: '印刷宽度 mm', en: 'Print width (mm)' },
  { id: 'dpi', kind: 'number', zh: '分辨率 dpi', en: 'Resolution (dpi)' },
];

function readOptions() {
  const out = {};
  for (const c of CONTROLS) {
    const input = document.getElementById(`lab-${c.id}`);
    if (!input) continue;
    if (c.kind === 'check') { if (input.checked) out[c.id] = true; }
    else {
      const v = Number(input.value);
      if (v && !(c.id === 'upscale' && v === 1)) out[c.id] = v;
    }
  }
  const fmt = document.getElementById('lab-format');
  if (fmt) out.format = fmt.value;
  const cvd = document.getElementById('lab-cvd');
  if (cvd && cvd.value) out.cvd = cvd.value;
  return out;
}

function show(dataUrl) {
  lab.current = dataUrl;
  const view = document.getElementById('lab-view');
  view.replaceChildren();
  if (!dataUrl) return;
  const img = el('img', { src: dataUrl, alt: '' });
  img.addEventListener('load', () => { lab.natural = [img.naturalWidth, img.naturalHeight]; });
  view.append(img);
  if (lab.box) drawBox();
}

function drawBox() {
  const view = document.getElementById('lab-view');
  const img = view.querySelector('img');
  const old = view.querySelector('.marquee');
  if (old) old.remove();
  if (!lab.box || !img) return;
  const k = img.clientWidth / (lab.natural[0] || 1);
  const [x0, y0, x1, y1] = lab.box;
  view.append(el('div', {
    class: 'marquee',
    style: `left:${x0 * k}px; top:${y0 * k}px; width:${(x1 - x0) * k}px; height:${(y1 - y0) * k}px`,
  }));
}

async function apply() {
  if (!lab.file) { toast(zh() ? '先打开一张图片' : 'Open a picture first', true); return; }
  const data = new FormData();
  data.append('file', lab.file);
  data.append('options', JSON.stringify(readOptions()));
  try {
    busy(zh() ? '处理中' : 'Working');
    const out = await api.form('/api/image/enhance', data);
    lab.info = out.info;
    show(out.preview || out.image);
    lab.full = out.image;
    document.getElementById('lab-info').textContent =
      `${out.info.width} × ${out.info.height} px` + (out.info.mm ? `  ·  ${out.info.mm[0]} × ${out.info.mm[1]} mm @ ${out.info.dpi} dpi` : '');
    document.getElementById('lab-status').textContent = sayAll(out.info.steps).join('  ·  ');
    for (const n of out.info.notes || []) toast(n);
  } catch (err) { fail(err); } finally { busy(null); }
}

async function trace() {
  if (!lab.file) { toast(zh() ? '先打开一张图片' : 'Open a picture first', true); return; }
  const data = new FormData();
  data.append('file', lab.file);
  data.append('colors', document.getElementById('vec-colors').value);
  data.append('detail', document.getElementById('vec-detail').value);
  data.append('split', document.getElementById('vec-split').checked ? 'true' : 'false');
  data.append('theme', document.getElementById('theme').value);
  try {
    busy(zh() ? '描图中' : 'Tracing');
    const out = await api.form('/api/image/vectorize', data);
    state.editor.load(out.scene, { notes: out.info.notes, label: 'vectorize' });
    document.querySelector('#tabs button[data-go="draw"]').click();
    toast(zh()
      ? `描成了 ${out.info.layers} 层、${out.info.points} 个点，现在每块颜色都能单独改`
      : `${out.info.layers} layers and ${out.info.points} points: every patch is now its own editable shape`);
  } catch (err) { fail(err); } finally { busy(null); }
}

async function redraw() {
  if (!lab.current) { toast(zh() ? '先打开一张图片' : 'Open a picture first', true); return; }
  if (!lab.box) { toast(zh() ? '先在图上拖一个框' : 'Drag a box on the picture first', true); return; }
  const prompt = document.getElementById('redraw-prompt').value.trim();
  if (!prompt) return;
  try {
    const out = await runJob(() => api.send('/api/redraw', {
      image: lab.full || lab.current, box: lab.box, prompt, style: 'flat',
    }), zh() ? '重绘中…' : 'Redrawing...');
    if (!out) return;
    lab.full = out.image;
    show(out.image);
    lab.file = await dataUrlToFile(out.image, 'redrawn.png');
    for (const n of out.info.notes || []) toast(n);
  } catch (err) { fail(err); }
}

async function dataUrlToFile(dataUrl, name) {
  const blob = await (await fetch(dataUrl)).blob();
  return new File([blob], name, { type: blob.type });
}

export function setupImageLab() {
  const box = document.getElementById('lab-controls');
  for (const c of CONTROLS) {
    const id = `lab-${c.id}`;
    let input;
    if (c.kind === 'check') input = el('input', { type: 'checkbox', id });
    else if (c.kind === 'range') input = el('input', { type: 'range', id, min: c.min ?? 0, max: c.max ?? 1, step: c.step ?? 0.05, value: c.value ?? 0 });
    else input = el('input', { type: 'number', id, min: 0, placeholder: '—' });
    if (c.kind === 'check') box.append(el('label', { class: 'check', style: 'display:flex;margin:4px 0' }, [input, el('span', { text: zh() ? c.zh : c.en })]));
    else box.append(el('div', { class: 'prop' }, [el('label', { text: zh() ? c.zh : c.en, style: 'width:96px' }), input]));
  }
  const fmt = el('select', { id: 'lab-format' });
  options(fmt, ['png', 'jpeg', 'tiff', 'webp'], null, 'png');
  box.append(el('div', { class: 'prop' }, [el('label', { text: zh() ? '保存为' : 'Save as', style: 'width:96px' }), fmt]));
  const cvd = el('select', { id: 'lab-cvd' });
  options(cvd, ['', ...state.meta.cvd_kinds], 'cvd', '');
  box.append(el('div', { class: 'prop' }, [el('label', { text: zh() ? '色盲预览' : 'CVD preview', style: 'width:96px' }), cvd]));
  options(document.getElementById('vec-detail'), state.meta.vector_details, 'detail', 'medium');

  const colors = document.getElementById('vec-colors');
  colors.addEventListener('input', () => { document.getElementById('vec-colors-v').textContent = colors.value; });

  document.getElementById('lab-file').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    lab.file = file;
    lab.box = null;
    const reader = new FileReader();
    reader.onload = () => { lab.original = reader.result; lab.full = reader.result; show(reader.result); };
    reader.readAsDataURL(file);
    document.getElementById('lab-info').textContent = file.name;
  });

  document.getElementById('lab-apply').addEventListener('click', apply);
  document.getElementById('lab-reset').addEventListener('click', () => {
    if (lab.original) { lab.full = lab.original; show(lab.original); }
    for (const c of CONTROLS) {
      const input = document.getElementById(`lab-${c.id}`);
      if (!input) continue;
      if (c.kind === 'check') input.checked = false;
      else input.value = c.value ?? (c.kind === 'range' ? 0 : '');
    }
  });
  document.getElementById('vec-go').addEventListener('click', trace);
  document.getElementById('redraw-go').addEventListener('click', redraw);

  document.getElementById('lab-download').addEventListener('click', async () => {
    if (!lab.full) return;
    const blob = await (await fetch(lab.full)).blob();
    const ext = (lab.info && lab.info.format ? lab.info.format : 'png').replace('jpeg', 'jpg').replace('tiff', 'tif');
    saveBlob(blob, `${(lab.file && lab.file.name ? lab.file.name.replace(/\.[^.]+$/, '') : 'image')}.${ext}`);
  });

  document.getElementById('lab-to-canvas').addEventListener('click', () => {
    if (!lab.full) return;
    const img = document.querySelector('#lab-view img');
    state.editor.placeImage(lab.full, lab.natural[0] || img.naturalWidth, lab.natural[1] || img.naturalHeight, '');
    document.querySelector('#tabs button[data-go="draw"]').click();
  });

  // Drag a region for the local redraw.
  const view = document.getElementById('lab-view');
  let start = null;
  view.addEventListener('mousedown', (e) => {
    const img = view.querySelector('img');
    if (!img) return;
    const r = img.getBoundingClientRect();
    const k = (lab.natural[0] || img.naturalWidth) / r.width;
    start = [(e.clientX - r.left) * k, (e.clientY - r.top) * k];
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!start) return;
    const img = view.querySelector('img');
    const r = img.getBoundingClientRect();
    const k = (lab.natural[0] || img.naturalWidth) / r.width;
    const now = [(e.clientX - r.left) * k, (e.clientY - r.top) * k];
    lab.box = [Math.min(start[0], now[0]), Math.min(start[1], now[1]), Math.max(start[0], now[0]), Math.max(start[1], now[1])].map(Math.round);
    drawBox();
  });
  window.addEventListener('mouseup', () => {
    if (!start) return;
    start = null;
    if (lab.box && (lab.box[2] - lab.box[0] < 8 || lab.box[3] - lab.box[1] < 8)) { lab.box = null; drawBox(); }
  });
}
