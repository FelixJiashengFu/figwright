/* Projects: saved figures, their history, and what happens when two people
 * save the same project at once (the server refuses; we ask instead of clobbering).
 */

import { api, busy, confirmBox, dialog, el, fail, prompt, state, status, toast } from './app.js';
import { getLang, t } from './i18n.js';

const zh = () => getLang() === 'zh';

function when(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso || '';
  return d.toLocaleString(zh() ? 'zh-CN' : 'en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export async function refresh() {
  try {
    const out = await api.get('/api/projects');
    const box = document.getElementById('project-list');
    box.replaceChildren();
    if (!out.projects.length) {
      box.append(el('p', { class: 'note', text: zh() ? '还没有存过项目。画好一张图，点工具栏的“存档”。' : 'Nothing saved yet. Draw a figure and press Save on the toolbar.' }));
      return;
    }
    for (const p of out.projects) {
      const card = el('div', { class: 'card' });
      card.append(el('div', { class: 'thumb', style: `background-image:url('/api/projects/${p.id}/thumb.svg?rev=${p.rev}')` }));
      card.append(el('div', { class: 'body' }, [
        el('b', { text: p.name || t('untitled') }),
        el('span', { class: 'muted', text: `${when(p.updated)} · ${zh() ? '第' : 'rev '}${p.rev}${zh() ? ' 版' : ''}` }),
      ]));
      card.append(el('div', { class: 'acts' }, [
        el('button', { class: 'primary', text: t('open'), onclick: () => open(p.id) }),
        el('button', { text: t('duplicate'), onclick: async () => { try { await api.send(`/api/projects/${p.id}/duplicate`); refresh(); } catch (err) { fail(err); } } }),
        el('button', {
          class: 'danger', text: t('delete'),
          onclick: async () => {
            if (!(await confirmBox(t('confirm.delete', { name: p.name || t('untitled') }), t('delete')))) return;
            try { await api.del(`/api/projects/${p.id}`); refresh(); } catch (err) { fail(err); }
          },
        }),
      ]));
      box.append(card);
    }
  } catch (err) { fail(err); }
}

async function open(id) {
  try {
    busy(zh() ? '打开' : 'Opening');
    const out = await api.get(`/api/projects/${id}`);
    state.project = { id, name: out.name, rev: out.rev };
    state.editor.load(out.scene, { silent: true, label: out.name });
    state.editor.dirty = false;
    document.querySelector('#tabs button[data-go="draw"]').click();
    status(`${out.name} · ${zh() ? '第' : 'rev '}${out.rev}${zh() ? ' 版' : ''}`);
    versions(id, out.name);
  } catch (err) { fail(err); } finally { busy(null); }
}

async function versions(id, name) {
  document.getElementById('proj-current').textContent = name || '';
  const box = document.getElementById('version-list');
  box.replaceChildren();
  try {
    const out = await api.get(`/api/projects/${id}/versions`);
    if (!out.versions.length) {
      box.append(el('p', { class: 'note', text: zh() ? '这个项目还没有历史版本。每次存档都会自动留一版。' : 'No history yet. Every save keeps a version.' }));
      return;
    }
    out.versions.forEach((v, i) => {
      box.append(el('div', { class: 'v' }, [
        el('span', { class: 'grow', text: `${zh() ? '第' : 'rev '}${v.rev}${zh() ? ' 版' : ''} · ${when(v.saved)}${v.label ? ' · ' + v.label : ''}` }),
        el('button', {
          text: t('restore'),
          onclick: async () => {
            try {
              const got = await api.get(`/api/projects/${id}/versions/${i}`);
              state.editor.load(got.scene, { label: `${zh() ? '恢复到第' : 'restored rev '}${v.rev}${zh() ? ' 版' : ''}` });
              toast(zh() ? '已载入旧版本，存档后才会覆盖当前版本' : 'Old version loaded; it only replaces the current one when you save');
            } catch (err) { fail(err); }
          },
        }),
      ]));
    });
  } catch (err) { fail(err); }
}

export async function saveProject() {
  const ed = state.editor;
  try {
    if (!state.project) {
      const name = await prompt(zh() ? '给这张图起个名字' : 'Name this figure', ed.scene.title || '');
      if (name === undefined) return;
      busy(t('draw.save'));
      const out = await api.send('/api/projects', { name: name || ed.scene.title, scene: ed.scene });
      state.project = { id: out.id, name: out.name, rev: out.rev };
    } else {
      busy(t('draw.save'));
      const out = await api.send(`/api/projects/${state.project.id}`, {
        scene: ed.scene, base_rev: state.project.rev, snapshot: true,
      }, 'PUT');
      state.project.rev = out.rev;
    }
    ed.dirty = false;
    status(`${t('saved')} · ${state.project.name} · ${zh() ? '第' : 'rev '}${state.project.rev}${zh() ? ' 版' : ''}`);
    toast(t('saved'));
    refresh();
    versions(state.project.id, state.project.name);
  } catch (err) {
    if (err.code === 'conflict') return conflict();
    fail(err);
  } finally { busy(null); }
}

/** Someone else saved while we were editing. Never silently overwrite. */
async function conflict() {
  const choice = await dialog((box, close) => {
    box.append(el('h2', { text: zh() ? '版本冲突' : 'Version conflict' }));
    box.append(el('p', { text: t('conflict') }));
    box.append(el('div', { class: 'actions' }, [
      el('button', { class: 'ghost', text: t('cancel'), onclick: () => close() }),
      el('button', { text: t('conflict.reload'), onclick: () => close('reload') }),
      el('button', { class: 'primary', text: t('conflict.overwrite'), onclick: () => close('overwrite') }),
    ]));
  });
  if (!choice) return;
  try {
    if (choice === 'reload') {
      const out = await api.get(`/api/projects/${state.project.id}`);
      state.project.rev = out.rev;
      state.editor.load(out.scene, { label: zh() ? '已载入对方的版本' : 'Loaded their version' });
      return;
    }
    const fresh = await api.get(`/api/projects/${state.project.id}`);
    const out = await api.send(`/api/projects/${state.project.id}`, {
      scene: state.editor.scene, base_rev: fresh.rev, snapshot: true,
    }, 'PUT');
    state.project.rev = out.rev;
    state.editor.dirty = false;
    toast(t('saved'));
    refresh();
  } catch (err) { fail(err); }
}

export function setupProjects() {
  document.getElementById('proj-refresh').addEventListener('click', refresh);
  document.getElementById('save-project').addEventListener('click', saveProject);
  window.addEventListener('fw:tab', (e) => { if (e.detail === 'projects') refresh(); });
}
