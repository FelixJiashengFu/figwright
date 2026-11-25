/* Settings: which model does what, provider keys, and the locked house style. */

import { api, el, fail, state, toast } from './app.js';
import { getLang, t } from './i18n.js';

const zh = () => getLang() === 'zh';

function providerById(id) { return (state.config.providers || []).find((p) => p.id === id); }

async function save(patch) {
  state.config = await api.send('/api/config', patch, 'PUT');
  draw();
}

function drawRoles() {
  const box = document.getElementById('roles');
  box.replaceChildren();
  for (const role of ['text', 'vision', 'image']) {
    const cur = state.config.roles[role] || {};
    const sel = el('select');
    sel.append(el('option', { value: '', text: t('provider.none'), selected: !cur.provider }));
    for (const p of state.config.providers) {
      if (!p.roles.includes(role)) continue;
      sel.append(el('option', { value: p.id, text: p.label[getLang()] || p.label.zh, selected: p.id === cur.provider }));
    }
    const model = el('input', { type: 'text', value: cur.model || '', placeholder: t('provider.model'), list: `models-${role}` });
    const datalist = el('datalist', { id: `models-${role}` });
    const commit = () => save({ roles: { [role]: { provider: sel.value, model: model.value.trim() } } }).catch(fail);
    sel.addEventListener('change', commit);
    model.addEventListener('change', commit);
    const list = el('button', {
      text: t('provider.list'),
      onclick: async () => {
        if (!sel.value) return;
        try {
          const out = await api.send('/api/config/models', { provider: sel.value });
          datalist.replaceChildren();
          for (const m of out.models || []) datalist.append(el('option', { value: m }));
          toast(out.models && out.models.length
            ? (zh() ? `${out.models.length} 个模型，点输入框选` : `${out.models.length} models: click the box to choose`)
            : (zh() ? '这个接口没有返回模型列表，手填一个' : 'This provider did not list any models; type one in'));
        } catch (err) { fail(err); }
      },
    });
    const test = el('button', {
      text: t('provider.test'),
      onclick: async () => {
        if (!sel.value) return;
        try {
          const out = await api.send('/api/config/test', { provider: sel.value, model: model.value.trim() });
          toast(out.ok ? (zh() ? `通了：${out.model}${out.ms ? ` · ${out.ms} ms` : ''}` : `Working: ${out.model}${out.ms ? ` in ${out.ms} ms` : ''}`) : out.message, !out.ok);
        } catch (err) { fail(err); }
      },
    });
    box.append(el('div', { class: 'prop' }, [
      el('label', { text: t(`role.${role}`), style: 'width:84px' }), sel, model, datalist, list, test,
    ]));
    box.append(el('p', { class: 'note', text: t(`role.${role}.hint`) }));
  }
}

function drawProviders() {
  const box = document.getElementById('providers');
  box.replaceChildren();
  for (const p of state.config.providers) {
    if (p.id === 'mock') continue;
    const row = el('div', { class: 'pane', style: 'margin-bottom:8px' });
    const head = el('div', { class: 'pane-head' }, [
      el('b', { text: p.label[getLang()] || p.label.zh }),
      el('span', { class: 'muted', text: p.roles.join(' · ') }),
    ]);
    row.append(head);
    if (p.needs_key) {
      const key = el('input', { type: 'password', placeholder: p.key_set ? `${p.key_hint} ${p.key_from_env ? t('provider.key.env') : t('provider.key.set')}` : (p.env || t('provider.key')), autocomplete: 'off' });
      const saveBtn = el('button', {
        text: t('provider.save'),
        onclick: async () => {
          if (!key.value.trim()) return;
          try { await save({ providers: { [p.id]: { api_key: key.value.trim() } } }); key.value = ''; toast(t('saved')); } catch (err) { fail(err); }
        },
      });
      const clear = el('button', {
        class: 'ghost', text: t('provider.clear'),
        onclick: async () => { try { await save({ providers: { [p.id]: { clear_key: true } } }); toast(t('saved')); } catch (err) { fail(err); } },
      });
      row.append(el('div', { class: 'prop' }, [el('label', { text: t('provider.key') }), key, saveBtn, p.key_set ? clear : null]));
    }
    const url = el('input', { type: 'text', value: p.base_url_overridden ? p.base_url : '', placeholder: p.default_base_url || 'https://…' });
    url.addEventListener('change', () => save({ providers: { [p.id]: { base_url: url.value.trim() } } }).catch(fail));
    row.append(el('div', { class: 'prop' }, [el('label', { text: t('provider.url') }), url]));
    box.append(row);
  }
  box.append(el('p', { class: 'note', text: `${zh() ? '设置文件' : 'Settings file'}: ${state.config.config_path}` }));
}

function drawHouse() {
  const box = document.getElementById('house');
  box.replaceChildren();
  const house = state.config.house_style;
  if (!house) {
    box.append(el('p', { class: 'note', text: zh() ? '现在没有锁定。在画图页勾上“锁定样式”，就会把当前这张图的样式记下来。' : 'Nothing is locked. Tick "Lock house style" on the Draw tab to remember the current figure\'s style.' }));
    return;
  }
  const list = el('div');
  for (const [k, v] of Object.entries(house)) {
    if (typeof v === 'object') continue;
    list.append(el('div', { class: 'prop' }, [el('label', { text: k, style: 'width:120px' }), el('span', { text: String(v) })]));
  }
  box.append(list);
  box.append(el('div', { class: 'row' }, [el('button', {
    class: 'ghost', text: zh() ? '解除锁定' : 'Unlock',
    onclick: async () => { await save({ house_style: null }); document.getElementById('lock-style').checked = false; },
  })]));
}

function draw() {
  drawRoles();
  drawProviders();
  drawHouse();
  document.getElementById('lock-style').checked = Boolean(state.config.house_style);
}

export function setupSettings() {
  draw();
  window.addEventListener('fw:lang', draw);
  window.addEventListener('fw:tab', (e) => { if (e.detail === 'settings') draw(); });
}
