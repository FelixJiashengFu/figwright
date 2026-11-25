/* The right-hand panels: properties of whatever is selected, and the layer list. */

import { el, fillIconSelect, state } from './app.js';
import { getLang, name, t } from './i18n.js';
import * as S from './scene.js';

const ALIGNS = [['left', '⇤'], ['hcenter', '⇔'], ['right', '⇥']];
const VALIGNS = [['top', '⇡'], ['middle', '⇕'], ['bottom', '⇣']];

function field(label, control) {
  return el('div', { class: 'prop' }, [el('label', { text: label }), control]);
}

function numberInput(value, onChange, step = 1) {
  const input = el('input', { type: 'number', value: Math.round(Number(value) || 0), step });
  input.addEventListener('change', () => onChange(Number(input.value)));
  return input;
}

function colorField(label, value, onChange, allowNone) {
  const picker = el('input', { type: 'color', value: /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#ffffff' });
  picker.addEventListener('input', () => onChange(picker.value));
  const row = el('div', { class: 'prop' }, [el('label', { text: label }), picker]);
  const style = state.editor.scene.style || {};
  const swatches = el('div', { class: 'swatches' });
  for (const c of [...(style.soft || []), ...(style.palette || [])].slice(0, 12)) {
    swatches.append(el('button', { style: `background:${c}`, title: c, onclick: () => onChange(c) }));
  }
  if (allowNone) swatches.append(el('button', { text: '∅', title: getLang() === 'zh' ? '无' : 'none', onclick: () => onChange('none') }));
  row.append(swatches);
  return row;
}

function segmented(label, items, current, onPick) {
  const seg = el('div', { class: 'seg' });
  for (const [value, text, title] of items) {
    seg.append(el('button', { text, title: title || text, class: value === current ? 'on' : '', onclick: () => onPick(value) }));
  }
  return field(label, seg);
}

function selectField(label, values, group, current, onPick) {
  const sel = el('select');
  for (const v of values) sel.append(el('option', { value: v, text: group ? name(group, v) : v, selected: v === current }));
  sel.addEventListener('change', () => onPick(sel.value));
  return field(label, sel);
}

export function drawProps(ed) {
  const box = document.getElementById('props');
  box.replaceChildren();
  const zh = getLang() === 'zh';
  const ids = [...ed.selection];
  if (!ids.length) { drawSceneProps(ed, box); return; }

  const nodes = ed.selectedNodes();
  const edges = (ed.scene.edges || []).filter((e) => ed.selection.has(e.id));

  if (nodes.length === 1 && !edges.length) drawNodeProps(ed, box, nodes[0]);
  else if (edges.length === 1 && !nodes.length) drawEdgeProps(ed, box, edges[0]);
  else if (nodes.length > 1) {
    box.append(el('p', { class: 'note', text: zh ? `选中 ${nodes.length} 个对象` : `${nodes.length} objects selected` }));
    const grid = el('div', { class: 'grid' });
    for (const [how, label] of [['left', zh ? '左对齐' : 'Left'], ['hcenter', zh ? '水平居中' : 'Centre'], ['right', zh ? '右对齐' : 'Right'],
      ['top', zh ? '顶对齐' : 'Top'], ['vcenter', zh ? '垂直居中' : 'Middle'], ['bottom', zh ? '底对齐' : 'Bottom'],
      ['hspread', zh ? '横向等距' : 'Space across'], ['vspread', zh ? '纵向等距' : 'Space down']]) {
      grid.append(el('button', { text: label, onclick: () => ed.align(how) }));
    }
    box.append(grid);
    box.append(el('div', { class: 'row' }, [
      el('button', { class: 'grow', text: zh ? '编组' : 'Group', onclick: () => ed.group() }),
      el('button', { class: 'grow', text: zh ? '取消编组' : 'Ungroup', onclick: () => ed.ungroup() }),
    ]));
    box.append(commonPaint(ed, nodes));
  }
  if (ids.length) {
    box.append(el('div', { class: 'row' }, [
      el('button', { class: 'grow', text: zh ? '复制一份' : 'Duplicate', onclick: () => ed.duplicate() }),
      el('button', { class: 'grow danger', text: t('delete'), onclick: () => ed.remove([...ed.selection]) }),
    ]));
  }
}

function commonPaint(ed, nodes) {
  const zh = getLang() === 'zh';
  const wrap = el('div');
  wrap.append(colorField(zh ? '填充' : 'Fill', nodes[0].fill, (v) => ed.change(() => { for (const n of nodes) n.fill = v; }), true));
  wrap.append(colorField(zh ? '边框' : 'Outline', nodes[0].stroke, (v) => ed.change(() => { for (const n of nodes) n.stroke = v; }), true));
  wrap.append(colorField(zh ? '文字' : 'Text', nodes[0].color, (v) => ed.change(() => { for (const n of nodes) n.color = v; })));
  return wrap;
}

function drawNodeProps(ed, box, node) {
  const zh = getLang() === 'zh';
  const meta = state.meta;
  const set = (patch, label) => ed.change(() => Object.assign(node, patch), label);

  box.append(selectField(zh ? '形状' : 'Shape', meta.node_types, 'node', node.type, (v) => set({ type: v })));

  if (node.type === 'icon') {
    const sel = fillIconSelect(el('select'), node.icon || 'target');
    sel.addEventListener('change', () => set({ icon: sel.value }));
    box.append(field(zh ? '图标' : 'Icon', sel));
  }

  if (!['image', 'bilayer', 'path'].includes(node.type)) {
    const area = el('textarea', { rows: 2 });
    area.value = node.text || '';
    area.addEventListener('change', () => set({ text: area.value }));
    box.append(field(zh ? '文字' : 'Text', area));
    box.append(segmented(zh ? '对齐' : 'Align', ALIGNS, node.align || 'center', (v) => set({ align: v === 'hcenter' ? 'center' : v })));
    box.append(segmented(zh ? '纵向' : 'Vertical', VALIGNS, node.valign || 'middle', (v) => set({ valign: v })));
    const fs = numberInput(node.fontSize || (ed.scene.style.fontSize || 16), (v) => set({ fontSize: Math.max(6, v) }));
    const bold = el('button', { text: 'B', class: node.fontWeight === 'bold' ? 'on' : '', style: 'font-weight:700', onclick: () => set({ fontWeight: node.fontWeight === 'bold' ? 'normal' : 'bold' }) });
    const italic = el('button', { text: 'I', class: node.fontStyle === 'italic' ? 'on' : '', style: 'font-style:italic', onclick: () => set({ fontStyle: node.fontStyle === 'italic' ? 'normal' : 'italic' }) });
    box.append(el('div', { class: 'prop' }, [el('label', { text: zh ? '字号' : 'Size' }), fs, el('div', { class: 'seg' }, [bold, italic])]));
  }

  box.append(commonPaint(ed, [node]));
  const dash = el('input', { type: 'checkbox', checked: Boolean(node.dash) });
  dash.addEventListener('change', () => set({ dash: dash.checked }));
  const sw = numberInput(node.strokeWidth ?? (ed.scene.style.strokeWidth || 2), (v) => set({ strokeWidth: Math.max(0, v) }));
  box.append(el('div', { class: 'prop' }, [el('label', { text: zh ? '线宽' : 'Line' }), sw,
    el('label', { class: 'check' }, [dash, el('span', { text: zh ? '虚线' : 'Dashed' })])]));

  const geo = el('div', { class: 'prop' }, [
    el('label', { text: zh ? '位置' : 'Position' }),
    numberInput(node.x, (v) => set({ x: v })), numberInput(node.y, (v) => set({ y: v })),
  ]);
  const size = el('div', { class: 'prop' }, [
    el('label', { text: zh ? '大小' : 'Size' }),
    numberInput(node.w, (v) => set({ w: Math.max(8, v) })), numberInput(node.h, (v) => set({ h: Math.max(8, v) })),
  ]);
  box.append(geo, size);
  box.append(el('div', { class: 'prop' }, [
    el('label', { text: zh ? '旋转' : 'Rotate' }),
    numberInput(node.rotation || 0, (v) => set({ rotation: ((v % 360) + 360) % 360 }), 5),
    el('button', { text: '↺', title: zh ? '归零' : 'Reset', onclick: () => set({ rotation: 0 }) }),
  ]));

  const order = el('div', { class: 'row' }, [
    el('button', { class: 'grow', text: zh ? '置顶' : 'Front', onclick: () => ed.order(Infinity) }),
    el('button', { class: 'grow', text: zh ? '上移' : 'Up', onclick: () => ed.order(1) }),
    el('button', { class: 'grow', text: zh ? '下移' : 'Down', onclick: () => ed.order(-1) }),
    el('button', { class: 'grow', text: zh ? '置底' : 'Back', onclick: () => ed.order(-Infinity) }),
  ]);
  box.append(order);
}

function drawEdgeProps(ed, box, edge) {
  const zh = getLang() === 'zh';
  const meta = state.meta;
  const set = (patch) => ed.change(() => Object.assign(edge, patch));
  box.append(selectField(zh ? '箭头' : 'Head', meta.edge_heads, 'head', edge.head || 'arrow', (v) => set({ head: v })));
  box.append(selectField(zh ? '走线' : 'Route', meta.edge_routings, 'routing', edge.routing || 'straight', (v) => set({ routing: v })));
  const sides = ['', 'top', 'right', 'bottom', 'left'];
  const sideName = (s) => (s ? (zh ? { top: '上', right: '右', bottom: '下', left: '左' }[s] : s) : (zh ? '自动' : 'auto'));
  const from = el('select');
  const to = el('select');
  for (const s of sides) {
    from.append(el('option', { value: s, text: sideName(s), selected: (edge.fromSide || '') === s }));
    to.append(el('option', { value: s, text: sideName(s), selected: (edge.toSide || '') === s }));
  }
  from.addEventListener('change', () => set({ fromSide: from.value || null }));
  to.addEventListener('change', () => set({ toSide: to.value || null }));
  box.append(el('div', { class: 'prop' }, [el('label', { text: zh ? '起止边' : 'Sides' }), from, to]));

  const label = el('input', { type: 'text', value: edge.label || '' });
  label.addEventListener('change', () => set({ label: label.value }));
  box.append(field(zh ? '标注' : 'Label', label));
  box.append(colorField(zh ? '颜色' : 'Colour', edge.color, (v) => set({ color: v })));
  const dash = el('input', { type: 'checkbox', checked: Boolean(edge.dash) });
  dash.addEventListener('change', () => set({ dash: dash.checked }));
  box.append(el('div', { class: 'prop' }, [
    el('label', { text: zh ? '线宽' : 'Width' }),
    numberInput(edge.width || ed.scene.style.edgeWidth || 2, (v) => set({ width: Math.max(0.5, v) })),
    el('label', { class: 'check' }, [dash, el('span', { text: zh ? '虚线' : 'Dashed' })]),
  ]));
  box.append(el('div', { class: 'row' }, [el('button', {
    class: 'grow', text: zh ? '调换方向' : 'Swap direction',
    onclick: () => set({ from: edge.to, to: edge.from, fromSide: edge.toSide || null, toSide: edge.fromSide || null }),
  })]));
}

function drawSceneProps(ed, box) {
  const zh = getLang() === 'zh';
  const scene = ed.scene;
  const set = (patch) => ed.change(() => Object.assign(scene, patch));
  box.append(el('p', { class: 'note', text: zh ? '没选中东西，这里是整张图的设置。' : 'Nothing selected, so these are the settings for the whole figure.' }));
  const title = el('input', { type: 'text', value: scene.title || '' });
  title.addEventListener('change', () => set({ title: title.value }));
  box.append(field(zh ? '标题' : 'Title', title));
  box.append(el('div', { class: 'prop' }, [
    el('label', { text: zh ? '画布' : 'Canvas' }),
    numberInput(scene.width, (v) => set({ width: Math.max(80, v) })),
    numberInput(scene.height, (v) => set({ height: Math.max(80, v) })),
  ]));
  box.append(colorField(zh ? '背景' : 'Background', scene.background, (v) => set({ background: v }), true));
  box.append(el('div', { class: 'row' }, [el('button', {
    class: 'grow', text: zh ? '裁到内容大小' : 'Crop to contents',
    onclick: () => {
      const b = S.sceneBounds(scene);
      if (!b) return;
      const pad = 24;
      ed.change(() => {
        for (const n of scene.nodes) { n.x -= b[0] - pad; n.y -= b[1] - pad; }
        scene.width = Math.ceil(b[2] - b[0] + pad * 2);
        scene.height = Math.ceil(b[3] - b[1] + pad * 2);
      });
      ed.fit();
      ed.render();
    },
  })]));
  const counts = `${(scene.nodes || []).length} ${zh ? '个对象' : 'objects'} · ${(scene.edges || []).length} ${zh ? '条连线' : 'connectors'}`;
  box.append(el('p', { class: 'note', text: counts }));
  const prov = (scene.meta && scene.meta.provenance) || [];
  if (prov.length) {
    const last = prov[prov.length - 1];
    box.append(el('p', { class: 'note', text: `${zh ? '最近一步' : 'Last step'}: ${last.action} · ${last.provider}${last.model ? ' ' + last.model : ''}` }));
  }
}

export function drawLayers(ed) {
  const box = document.getElementById('layers');
  box.replaceChildren();
  const zh = getLang() === 'zh';
  const nodes = [...(ed.scene.nodes || [])].reverse();
  for (const n of nodes) {
    const row = el('div', { class: `layer${ed.selection.has(n.id) ? ' on' : ''}`, onclick: (e) => ed.select(n.id, e.shiftKey) });
    row.append(el('span', { class: 'kind', text: name('node', n.type) }));
    row.append(el('span', { class: 't', text: (n.text || '').split('\n')[0] || n.id }));
    row.append(el('button', {
      text: n.hidden ? '○' : '●', title: zh ? '显示 / 隐藏' : 'Show / hide',
      onclick: (e) => { e.stopPropagation(); ed.change(() => { n.hidden = !n.hidden; }); },
    }));
    row.append(el('button', {
      text: n.locked ? '🔒' : '🔓', title: zh ? '锁定' : 'Lock',
      onclick: (e) => { e.stopPropagation(); ed.change(() => { n.locked = !n.locked; }); },
    }));
    box.append(row);
  }
  for (const e of ed.scene.edges || []) {
    const row = el('div', { class: `layer${ed.selection.has(e.id) ? ' on' : ''}`, onclick: (ev) => ed.select(e.id, ev.shiftKey) });
    row.append(el('span', { class: 'kind', text: zh ? '连线' : 'edge' }));
    row.append(el('span', { class: 't', text: e.label || `${e.from} → ${e.to}` }));
    box.append(row);
  }
  if (!box.children.length) box.append(el('p', { class: 'note', text: zh ? '还是空的。左边写一句话，或者挑个模板。' : 'Empty. Describe a figure on the left, or pick a template.' }));
}
