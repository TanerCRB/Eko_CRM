(function () {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const paths = {
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3a4 4 0 0 1 0 8"/><circle cx="9" cy="7" r="4"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M16 3v4M8 3v4M3 11h18m-13 4h2m4 0h2m-8 3h2"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    task: '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="m7 12 3 3 7-7"/>',
    chart: '<path d="M4 3v18h17M9 16v-5m5 5V7m5 9V4"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    link: '<path d="m10 13 4-4m-6 7-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 1 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    chevron: '<path d="m9 5 7 7-7 7"/>',
    down: '<path d="m6 9 6 6 6-6"/>',
    pin: '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    phone: '<path d="M21 16v3a2 2 0 0 1-2 2C10 21 3 14 3 5a2 2 0 0 1 2-2h3l2 5-3 2a15 15 0 0 0 7 7l2-3Z"/>',
    note: '<path d="M14 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-9M14 3v7h7l-7-7ZM7 14h10m-10 3h7"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    warning: '<path d="m10 4-8 14a2 2 0 0 0 2 3h16a2 2 0 0 0 2-3L14 4a2.3 2.3 0 0 0-4 0ZM12 9v4m0 4h.01"/>',
    refresh: '<path d="M20 7a9 9 0 0 0-15-2L2 8m0-5v5h5m-3 9a9 9 0 0 0 15 2l3-3m0 5v-5h-5"/>',
    archive: '<rect x="3" y="3" width="18" height="5" rx="1"/><path d="M5 8v13h14V8m-10 4h6"/>',
    edit: '<path d="m16 3 5 5L8 21H3v-5L16 3Zm-3 3 5 5"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    leaf: '<path d="M20 3C6 1 1 9 5 16s18 4 15-13ZM4 21 16 9"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>'
  };
  const icon = (name, cls = '') => `<svg class="icon ${escape(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.leaf}</svg>`;
  const labels = { planned: 'Planned', held: 'Held', cancelled: 'Cancelled', decision: 'Awaiting decision', todo: 'To do', progress: 'In progress', done: 'Done', moved: 'Moved', unsynced: 'Not synced' };
  const badge = (status, text) => `<span class="badge badge-${escape(status)}">${icon(status === 'held' || status === 'done' ? 'check' : status === 'decision' || status === 'unsynced' ? 'warning' : status === 'moved' ? 'refresh' : 'clock')}${escape(text || labels[status] || status)}</span>`;
  const button = (text, action, id = '', style = 'secondary', glyph = '') => `<button class="button button-${style}" type="button" data-action="${escape(action)}" data-id="${escape(id)}">${glyph ? icon(glyph) : ''}${escape(text)}</button>`;
  const iconButton = (label, action, id, glyph) => `<button type="button" class="icon-button" aria-label="${escape(label)}" title="${escape(label)}" data-action="${escape(action)}" data-id="${escape(id)}">${icon(glyph)}</button>`;
  const empty = (title, body, action = '') => `<div class="empty">${icon('leaf')}<h3>${escape(title)}</h3><p>${escape(body)}</p>${action}</div>`;
  const time = instant => new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit' }).format(new Date(instant));
  const date = (value, options = {}) => new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Warsaw', day: 'numeric', month: 'short', ...options }).format(new Date(value.length === 10 ? `${value}T12:00:00Z` : value));
  const avatar = (name, cls = '') => `<span class="avatar ${escape(cls)}" aria-hidden="true">${escape(name.split(/[ &]+/).slice(0, 2).map(v => v[0]).join(''))}</span>`;
  const field = (label, name, value = '', type = 'text', extra = '') => `<label class="field"><span>${escape(label)}</span><input name="${escape(name)}" type="${type}" value="${escape(value)}" ${extra}></label>`;
  window.EkoUI = { escape, icon, badge, button, iconButton, empty, time, date, avatar, field, labels };
})();
