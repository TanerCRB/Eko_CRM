(function () {
  'use strict';
  const D = window.EkoDomain;
  const U = window.EkoUI;
  const { escape: e, icon, badge, button, iconButton, empty, time, date, avatar, field } = U;
  const STORAGE = 'eko-crm-p2-v1';
  let state = D.copy(window.EkoFixtures);
  let storageAvailable = true;
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE) || 'null');
    if (saved?.version === 1 && ['users', 'customers', 'visits', 'notes', 'actions'].every(k => Array.isArray(saved[k])) && saved.connections) state = saved;
  } catch { storageAvailable = false; }
  let persona = 'alex';
  let selectedDay = D.TODAY;
  let view = 'today';
  let customerFilter = 'active';
  let query = '';
  let ownerFilter = 'all';
  let visitLayout = 'week';
  let actionFilter = 'open';
  let periodFrom = '2026-10-19';
  let periodTo = '2026-10-25';
  let openCustomer = null;
  let customerTab = 'overview';
  let toastTimer;
  let menuOpen = false;
  const modal = document.querySelector('#modal');
  const sheet = document.querySelector('#sheet');
  const user = () => D.person(state, persona);
  const own = rows => D.visible(rows, user());
  const visits = () => own(state.visits).sort((a, b) => a.start.localeCompare(b.start));
  const customers = () => own(state.customers);
  const personName = id => D.person(state, id)?.name || 'Unknown user';
  const cName = id => D.customer(state, id)?.name || 'Customer';
  const ownDecisions = () => state.visits.filter(v => v.owner === persona && D.stateOf(v) === 'decision');
  const days = ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23'];
  const nav = [ ['today', 'sun', 'My day'], ['customers', 'users', 'Customers'], ['visits', 'calendar', 'Visits'], ['actions', 'task', 'Follow-ups'], ['team', 'chart', 'Team overview'], ['calendar', 'link', 'Google Calendar'] ];
  function persist() {
    try { localStorage.setItem(STORAGE, JSON.stringify(state)); } catch { storageAvailable = false; }
  }
  function toast(text) {
    clearTimeout(toastTimer);
    const el = document.querySelector('#toast'); el.textContent = text; el.classList.add('visible');
    toastTimer = setTimeout(() => el.classList.remove('visible'), 4500);
  }
  function mutate(fn, message, close = true) {
    try {
      const result = fn(); persist();
      if (close) modal.close();
      render();
      if (sheet.open && openCustomer) showCustomer(openCustomer, customerTab);
      if (message) toast(message);
      return result;
    } catch (error) {
      const errorBox = modal.open && modal.querySelector('.form-error');
      if (errorBox) { errorBox.textContent = error.message; errorBox.focus(); }
      else toast(error.message);
      return null;
    }
  }
  function heading(title, subtitle, action = '') { return `<div class="page-heading"><div><h1>${e(title)}</h1><p>${e(subtitle)}</p></div>${action}</div>`; }
  function titleForView() { return view === 'components' ? 'Design library' : nav.find(n => n[0] === view)?.[2] || 'My day'; }
  function render() {
    const reminderCount = own(state.actions).filter(a => a.due && a.due <= D.TODAY && !['done', 'cancelled'].includes(a.status)).length;
    document.title = `${titleForView()} · Eko CRM P2`;
    document.querySelector('#app').innerHTML = `
      <aside class="sidebar ${menuOpen ? 'is-open' : ''}" aria-label="Main navigation">
        <button class="icon-button mobile-menu nav-close" data-action="menu" aria-label="Close navigation">${icon('close')}</button>
        <a class="brand" href="#today"><img src="assets/mark.svg" alt=""><div><strong>eko<span style="font-weight:300">crm</span></strong><small>Closer to your customers</small></div></a>
        <p class="nav-caption">Your workspace</p>
        <nav>${nav.filter(n => n[0] !== 'team' || user().role === 'manager').map(([key, glyph, title]) => `<a href="#${key}" class="nav-link ${view === key ? 'active' : ''}" ${view === key ? 'aria-current="page"' : ''}>${icon(glyph)}<span>${title}</span>${key === 'actions' && reminderCount ? `<span class="nav-count">${reminderCount}</span>` : key === 'team' ? '<span class="nav-count">Later</span>' : ''}</a>`).join('')}</nav>
        <div class="sidebar-spacer"></div>
        <div class="field-note">${icon('leaf')}<p>Good relationships grow<br>one conversation at a time.</p></div>
        <a href="#components" class="nav-link ${view === 'components' ? 'active' : ''}" ${view === 'components' ? 'aria-current="page"' : ''}>${icon('grid')}<span>Design library</span></a>
        <div class="profile">${avatar(user().name, 'avatar-person')}<div><strong>${e(user().name)}</strong><small>${user().role === 'manager' ? 'Team manager' : 'Sales representative'}</small></div></div>
      </aside>
      <div class="workspace">
        <header class="topbar"><div class="row gap-small"><button class="icon-button mobile-menu" data-action="menu" aria-label="Toggle navigation" aria-expanded="${menuOpen}">${icon('menu')}</button><div class="breadcrumb"><span>Workspace</span>${icon('chevron')}<strong>${titleForView()}</strong></div></div><div class="top-actions"><button class="search-trigger" data-action="search" aria-label="Find a customer">${icon('search')}<span>Find a customer</span><kbd>/</kbd></button><span class="demo-pill">P2 prototype</span></div></header>
        <main id="main" tabindex="-1">${globalNotice()}${content()}
          <footer class="demo-footer"><span>Synthetic data · 22 Oct 2026, 10:15 · Europe/Warsaw</span><div class="demo-controls"><label for="persona">Demo persona</label><select id="persona" aria-label="Demo persona">${state.users.map(p => `<option value="${p.id}" ${p.id === persona ? 'selected' : ''}>${e(p.name)} · ${p.role === 'manager' ? 'Manager' : 'Rep'}</option>`).join('')}</select><button class="text-link" data-action="reset">Reset demo</button></div></footer>
          ${!storageAvailable ? '<p class="spec">Browser storage is unavailable. Changes last only for this open page.</p>' : ''}
        </main>
      </div>`;
  }
  function globalNotice() {
    let html = '';
    const decisions = ownDecisions();
    if (decisions.length) html += `<div class="notice">${icon('warning')}<p><strong>${decisions.length === 1 ? 'A visit needs your decision' : `${decisions.length} visits need your decision`}</strong>${e(cName(decisions[0].customerId))} was removed from Google Calendar.</p>${button('Review visit', 'visit-detail', decisions[0].id)}</div>`;
    if (state.connections[persona] !== 'connected') html += `<div class="notice">${icon('link')}<p><strong>Reconnect your Google Calendar</strong>Your visits are safe. New changes will sync after reconnecting.</p>${button('Reconnect (demo)', 'reconnect')}</div>`;
    return html;
  }
  function content() {
    return ({ today: todayView, customers: customersView, visits: visitsView, actions: actionsView, team: teamView, calendar: calendarView, components: componentsView }[view] || todayView)();
  }
  function dateStrip() {
    return `<div class="week-strip" aria-label="Choose a day">${days.map(d => { const count = visits().filter(v => D.dayOf(v.start) === d).length; return `<button class="day-button ${selectedDay === d ? 'selected' : ''}" data-action="day" data-id="${d}" aria-pressed="${selectedDay === d}" aria-label="${date(d, { weekday: 'long' })}, ${count} visits"><span>${date(d, { weekday: 'short' }).split(',')[0].split(' ')[0]} <strong>${d.slice(8)}</strong></span><span class="day-dots" aria-hidden="true">${Array(Math.min(count, 4)).fill('<span class="day-dot"></span>').join('')}</span></button>`; }).join('')}</div>`;
  }
  function visitFlags(v) { return `<div class="row wrap gap-small">${badge(D.stateOf(v))}${v.moved ? badge('moved') : ''}${v.unsynced ? badge('unsynced') : ''}</div>`; }
  function agendaRow(v) {
    const c = D.customer(state, v.customerId);
    return `<div class="agenda-row is-${D.stateOf(v)}" role="button" tabindex="0" data-action="visit-detail" data-id="${e(v.id)}" aria-label="${e(c.name)}, ${time(v.start)}, ${U.labels[D.stateOf(v)]}"><div class="agenda-time">${time(v.start)}<small>${time(v.end)}</small></div><div class="agenda-detail"><h3>${e(c.name)}</h3><p>${e(c.town)}${v.purpose ? ` · ${e(v.purpose)}` : ''}</p>${visitFlags(v)}</div>${icon('chevron')}</div>`;
  }
  function todayView() {
    const dayVisits = visits().filter(v => D.dayOf(v.start) === selectedDay);
    const upcoming = dayVisits.find(v => D.stateOf(v) === 'planned');
    const pending = own(state.actions).filter(a => !['done', 'cancelled'].includes(a.status)).sort((a, b) => (a.due || '9999').localeCompare(b.due || '9999'));
    const c = upcoming && D.customer(state, upcoming.customerId);
    const held = dayVisits.filter(v => D.stateOf(v) === 'held').length;
    const list = dayVisits.filter(v => v.id !== upcoming?.id);
    return `${heading(selectedDay === D.TODAY ? 'Your day, in the field.' : date(selectedDay, { weekday: 'long' }), selectedDay === D.TODAY ? 'Thursday, 22 October. A little planning, better conversations.' : 'Your appointments and follow-ups, in one place.', button('Plan a visit', 'new-visit', '', 'primary', 'plus'))}
      ${dateStrip()}<div class="dashboard-grid"><section><div class="section-heading"><h2>${selectedDay === D.TODAY ? 'Today’s visits' : 'Visits'}<span class="count">${dayVisits.length}</span></h2><span class="muted" style="font-size:12px">${held} held · ${dayVisits.filter(v => D.stateOf(v) === 'planned').length} ahead</span></div>
      ${upcoming ? `<article class="next-visit"><div class="next-label">${icon('sun')} Next on your agenda<span>${Math.round((Date.parse(upcoming.end) - Date.parse(upcoming.start)) / 60000)} min</span></div><h3>${e(c.name)}</h3><p>${e(upcoming.purpose || 'Customer visit')}</p><div class="next-time">${icon('clock')}${time(upcoming.start)} <span style="opacity:.5">—</span> ${time(upcoming.end)}</div><div class="address">${icon('pin')}${e(c.street)}, ${e(c.town)}</div><div class="next-footer">${button('Open visit', 'visit-detail', upcoming.id, 'leaf', 'arrow')}${button('Customer details', 'customer', c.id, 'ghost')}</div></article>` : ''}
      ${list.length ? `<div class="agenda">${list.map(agendaRow).join('')}</div>` : !upcoming ? `<div class="panel">${empty('Room for a conversation', 'No visits on this day. Plan a visit with one of your customers.', button('Plan a visit', 'new-visit', '', 'primary', 'plus'))}</div>` : ''}
      <div class="row between" style="margin-top:16px"><span class="eyeline">${icon('info')} Held status updates automatically after a visit ends.</span><a class="text-link" style="font-size:12px" href="#visits">View week</a></div></section>
      <aside class="dashboard-aside"><section class="panel"><div class="section-heading"><h2>Keep things moving</h2>${icon('task')}</div><p class="muted" style="font-size:12px">Your next steps after the conversation.</p><div class="task-list">${pending.length ? pending.slice(0, 3).map(taskRow).join('') : empty('All caught up', 'Create a follow-up from a visit note.')}</div><div class="panel-footer"><a href="#actions" class="text-link" style="font-size:12px">All follow-ups</a><span class="muted" style="font-size:11px">${pending.length} open</span></div></section>
      ${syncCard()}<div class="gentle-note">${icon('note')}<p><strong>A note now. A better visit next time.</strong>Capture the conversation while it’s fresh. Add a follow-up directly from your visit note.</p></div></aside></div>`;
  }
  function taskRow(a) {
    return `<div class="task-item"><button class="task-check" data-action="complete-action" data-id="${e(a.id)}" aria-label="Complete: ${e(a.title)}">${icon('check')}</button><div class="task-content"><strong>${e(a.title)}</strong><button class="text-link" data-action="customer" data-id="${e(a.customerId)}">${e(cName(a.customerId))}</button><div class="task-due ${D.overdue(a) ? 'late' : ''}">${icon('clock')}${dueLabel(a)}</div>${actionAttribution(a)}</div></div>`;
  }
  function actionAttribution(a) {
    return `${D.person(state, a.author)?.role === 'manager' ? `<div class="attribution">Created by ${e(personName(a.author))} · Manager</div>` : ''}${D.person(state, a.changedBy)?.role === 'manager' ? `<div class="attribution">Status set by ${e(personName(a.changedBy))} · Manager</div>` : ''}`;
  }
  function dueLabel(a) { return !a.due ? 'No due date' : D.overdue(a) ? `${date(a.due)} · overdue` : a.due === D.TODAY ? 'Due today' : `Due ${date(a.due)}`; }
  function syncCard() {
    const connected = state.connections[persona] === 'connected';
    const pending = state.visits.filter(v => v.owner === persona && v.unsynced).length;
    return `<section class="panel"><div class="row"><span class="sync-icon">${icon('calendar')}</span><div><h3 style="font-size:14px">Google Calendar</h3><span class="sync-status"><span class="status-dot"></span>${connected ? 'Connected' : 'Reconnect needed'}</span></div></div><p class="sync-meta">${pending ? `${pending} change${pending === 1 ? '' : 's'} waiting to sync.` : 'Your appointments are up to date.'}<br>Only visits created in Eko CRM are synced.</p><div class="panel-footer"><a href="#calendar" class="text-link" style="font-size:12px">Manage connection</a>${icon('arrow')}</div></section>`;
  }
  function customersView() {
    return `${heading('People behind the fields.', `${customers().filter(c => !c.archived).length} active customers. Every relationship has a place.`, button('Add customer', 'new-customer', '', 'primary', 'plus'))}
      <div class="toolbar"><label class="search-field">${icon('search')}<span class="sr-only">Search customers</span><input id="customer-search" value="${e(query)}" placeholder="Search name, town or contact…"></label><div class="segments" aria-label="Customer status">${['active', 'archived'].map(s => `<button data-action="customer-filter" data-id="${s}" class="${customerFilter === s ? 'active' : ''}" aria-pressed="${customerFilter === s}">${s === 'active' ? 'Active' : 'Archived'}</button>`).join('')}</div>${user().role === 'manager' ? ownerSelect() : ''}</div><div id="customer-results">${customerResults()}</div>`;
  }
  function ownerSelect() { return `<label><span class="sr-only">Customer owner</span><select id="owner-filter"><option value="all">All representatives</option>${state.users.map(p => `<option value="${p.id}" ${ownerFilter === p.id ? 'selected' : ''}>${e(p.name)}</option>`).join('')}</select></label>`; }
  function customerResults() {
    const q = query.trim().toLocaleLowerCase();
    const rows = customers().filter(c => c.archived === (customerFilter === 'archived') && (ownerFilter === 'all' || c.owner === ownerFilter) && [c.name, c.town, ...c.contacts.map(p => p.value)].some(v => v.toLocaleLowerCase().includes(q)));
    if (!rows.length) return `<div class="panel">${empty('No customers found', query ? 'Try a different name, town or contact.' : 'Add a customer or change the status filter.', button('Add customer', 'new-customer', '', 'primary', 'plus'))}</div>`;
    return `<div class="table-wrap" tabindex="0" role="region" aria-label="Customer list"><table><thead><tr><th>Customer</th><th>Location</th><th>Next visit</th><th>${user().role === 'manager' ? 'Owner' : 'Open follow-ups'}</th><th><span class="sr-only">Open customer</span></th></tr></thead><tbody>${rows.map(c => {
      const v = state.visits.filter(v => v.customerId === c.id && D.canRead(v, user()) && D.stateOf(v) === 'planned').sort((a, b) => a.start.localeCompare(b.start))[0];
      const count = own(state.actions).filter(a => a.customerId === c.id && ['todo', 'progress'].includes(a.status)).length;
      return `<tr><td><button class="text-link customer-name" data-action="customer" data-id="${e(c.id)}">${avatar(c.name)}<span><strong>${e(c.name)}</strong><small>${e((c.contacts.find(p => p.primary) || c.contacts[0])?.value || 'No contact added')}</small></span></button></td><td>${e(c.town || 'Not provided')}<small>${e(c.country)}</small></td><td>${v ? `${date(v.start)}<small>${time(v.start)} ${v.moved ? '· Moved' : ''}</small>` : '<span class="muted">Not planned</span>'}</td><td>${user().role === 'manager' ? e(personName(c.owner)) : `<span class="count" style="margin:0">${count}</span>`}</td><td>${iconButton(`Open ${c.name}`, 'customer', c.id, 'chevron')}</td></tr>`;
    }).join('')}</tbody></table></div><div class="table-foot"><span>${rows.length} customer${rows.length === 1 ? '' : 's'}${query ? ' matching your search' : ''}</span><span>${user().role === 'manager' ? 'Team customer register' : 'Only your customers are shown'}</span></div>`;
  }
  function visitsView() {
    const rows = visits();
    return `${heading('Make room for good visits.', 'Plan, reschedule and keep the conversation going.', button('Plan a visit', 'new-visit', '', 'primary', 'plus'))}<div class="toolbar between"><div class="row">${icon('calendar')}<strong>19–23 October 2026</strong><span class="muted" style="font-size:12px">Europe/Warsaw</span></div><div class="segments">${['week', 'list'].map(layout => `<button data-action="visit-layout" data-id="${layout}" class="${visitLayout === layout ? 'active' : ''}" aria-pressed="${visitLayout === layout}">${layout === 'week' ? 'Week' : 'All visits'}</button>`).join('')}</div></div>
      ${visitLayout === 'week' ? `<div class="board-scroll" tabindex="0" role="region" aria-label="Weekly visits"><div class="week-board">${days.map(d => { const vs = rows.filter(v => D.dayOf(v.start) === d); return `<section class="week-column ${d === D.TODAY ? 'today' : ''}"><h3>${date(d, { weekday: 'short' })}${d === D.TODAY ? '<small class="muted" style="display:block;margin-top:6px">Today</small>' : ''}</h3>${vs.length ? vs.map(v => `<button class="week-event is-${D.stateOf(v)}" data-action="visit-detail" data-id="${e(v.id)}"><span>${time(v.start)}–${time(v.end)}</span><strong>${e(cName(v.customerId))}</strong><small>${e(v.purpose || 'Customer visit')}</small>${visitFlags(v)}</button>`).join('') : '<p class="muted" style="font-size:12px;text-align:center">No visits</p>'}</section>`; }).join('')}</div></div>` : rows.length ? rows.reduce((html, v, i) => { const day = D.dayOf(v.start); return html + (i === 0 || D.dayOf(rows[i-1].start) !== day ? `${i ? '</div>' : ''}<h2 style="margin-top:24px">${date(day, { weekday: 'long' })}</h2><div class="agenda">` : '') + agendaRow(v) + (i === rows.length - 1 ? '</div>' : ''); }, '') : empty('Your calendar is clear', 'Plan your first customer visit.')}
      <p class="spec">A changed start time adds the Moved flag. Held is automatic. Recurring visits are a later release.</p>`;
  }
  function actionCard(a) {
    const available = D.transitions[a.status].filter(s => a.owner === persona || user().role !== 'manager' || ['done', 'cancelled'].includes(s));
    return `<article class="action-card"><h3>${e(a.title)}</h3><button class="text-link" style="font-size:12px" data-action="customer" data-id="${e(a.customerId)}">${e(cName(a.customerId))}</button><div class="task-due ${D.overdue(a) ? 'late' : ''}">${icon('clock')}${dueLabel(a)}</div>${D.person(state, a.author)?.role === 'manager' ? `<div class="attribution">Created by ${e(personName(a.author))} · Manager</div>` : ''}${D.person(state, a.changedBy)?.role === 'manager' ? `<div class="attribution">Status set by ${e(personName(a.changedBy))} · Manager</div>` : ''}<label><span class="sr-only">Status for ${e(a.title)}</span><select data-action-status="${e(a.id)}"><option value="${a.status}">${U.labels[a.status]}</option>${available.map(s => `<option value="${s}">${U.labels[s]}</option>`).join('')}</select></label><button class="text-link" style="font-size:11px;margin-top:12px" data-action="source-note" data-id="${e(a.noteId)}">Read source note</button></article>`;
  }
  function actionsView() {
    let rows = own(state.actions);
    if (actionFilter === 'due') rows = rows.filter(a => a.due && a.due <= D.TODAY && ['todo', 'progress'].includes(a.status));
    return `${heading('Keep the conversation going.', 'Small next steps, connected to the note that started them.')}
      <div class="toolbar between"><div class="segments">${[['open', 'All follow-ups'], ['due', 'Due & overdue']].map(([key, label]) => `<button class="${actionFilter === key ? 'active' : ''}" data-action="action-filter" data-id="${key}" aria-pressed="${actionFilter === key}">${label}</button>`).join('')}</div><span class="muted" style="font-size:12px">Add follow-ups from a visit or customer note.</span></div>
      <div class="action-board">${[['todo', 'To do'], ['progress', 'In progress'], ['closed', 'Closed']].map(([key, title]) => { const list = rows.filter(a => key === 'closed' ? ['done', 'cancelled'].includes(a.status) : a.status === key); return `<section class="action-column"><h2>${title}<span class="count">${list.length}</span></h2>${list.length ? list.map(actionCard).join('') : empty(key === 'todo' ? 'Nothing waiting' : key === 'progress' ? 'Ready when you are' : 'No closed follow-ups', key === 'progress' ? 'Move a follow-up here when work begins.' : 'Follow-ups appear here as their status changes.')}</section>`; }).join('')}</div>`;
  }
  function teamView() {
    if (user().role !== 'manager') return empty('Manager view', 'Select the manager demo persona to explore the team overview.');
    const rows = ownerFilter === 'all' ? state.visits : state.visits.filter(v => v.owner === ownerFilter);
    const m = D.metrics(rows, periodFrom, periodTo);
    return `${heading('A clearer view of the team.', 'Visit activity without the manual report.')}<div class="notice notice-info">${icon('info')}<p><strong>Later release preview</strong>The team dashboard follows the MVP. These metrics use the prototype data.</p></div>
      <div class="toolbar">${ownerSelect()}<label class="row gap-small">From <input type="date" id="period-from" value="${periodFrom}"></label><label class="row gap-small">To <input type="date" id="period-to" value="${periodTo}"></label>${button('This week', 'this-week')}</div>
      <div class="metrics">${[['planned', 'Planned', 'Includes held visits'], ['held', 'Held', 'End time has passed'], ['moved', 'Moved', 'Counted once per visit'], ['cancelled', 'Cancelled', 'Explicitly cancelled']].map(([key, label, detail]) => `<div class="metric"><span>${label}</span><strong>${m[key]}</strong><small>${detail}</small></div>`).join('')}</div>
      <div class="table-wrap"><table><thead><tr><th>Representative</th><th>Planned</th><th>Held</th><th>Moved</th><th>Cancelled</th><th>Held / planned</th></tr></thead><tbody>${state.users.filter(u => ownerFilter === 'all' || u.id === ownerFilter).map(p => { const a = D.metrics(state.visits.filter(v => v.owner === p.id), periodFrom, periodTo); return `<tr><td><div class="row">${avatar(p.name, 'avatar-person')}<strong>${e(p.name)}</strong></div></td><td>${a.planned}</td><td>${a.held}</td><td>${a.moved}</td><td>${a.cancelled}</td><td><div class="bar" role="img" aria-label="${a.held} of ${a.planned} visits held"><span style="width:${a.planned ? a.held / a.planned * 100 : 0}%"></span></div></td></tr>`; }).join('')}</tbody></table></div><p class="spec">${m.decision} awaiting decision, reported separately. Period boundaries are inclusive, in Europe/Warsaw. Past visits remain attributed to their original owner.</p>`;
  }
  function calendarView() {
    const connected = state.connections[persona] === 'connected';
    const pending = state.visits.filter(v => v.owner === persona && v.unsynced);
    return `${heading('One calendar. Fewer loose ends.', 'Your customer visits, alongside the rest of your day.')}<div class="settings-grid"><div><section class="panel"><div class="row"><span class="sync-icon">${icon('calendar')}</span><div><h2 style="margin-bottom:3px">Google Calendar</h2><span class="sync-status">${connected ? 'Connected in this demo' : 'Connection expired in this demo'}</span></div></div><p style="margin-top:20px">Personal Google account · primary calendar<br>This preview simulates a connection. It does not access Google.</p><div class="setting-line"><div><strong>Visits created in Eko CRM</strong><small class="muted">Date, time and deletion sync both ways.</small></div>${icon('check')}</div><div class="setting-line"><div><strong>Your other calendar events</strong><small class="muted">Stay private. Never imported or changed.</small></div>${icon('check')}</div><div class="setting-line"><div><strong>No invitations to customers</strong><small class="muted">No customer is added as an attendee.</small></div>${icon('check')}</div>${button(connected ? 'Disconnect (demo)' : 'Reconnect (demo)', connected ? 'disconnect' : 'reconnect', '', connected ? 'secondary' : 'primary', 'link')}</section><section class="panel"><h2>Waiting to sync <span class="count">${pending.length}</span></h2>${pending.length ? pending.map(v => `<div class="setting-line"><div><strong>${e(cName(v.customerId))}</strong><small class="muted">${date(v.start)} at ${time(v.start)}</small></div>${badge('unsynced')}</div>`).join('') : '<p>No pending changes.</p>'}${connected && pending.length ? button('Retry sync (demo)', 'reconnect', '', 'primary', 'refresh') : ''}</section></div><section class="panel"><h2>Explore the sync scenarios</h2><p>These controls change local demo data so you can review the recovery experience.</p><div class="setting-line"><div><strong>Calendar access expires</strong><p>Visits keep their status. A reconnect notice appears.</p>${button('Simulate expired access', 'disconnect')}</div></div><div class="setting-line"><div><strong>A visit is deleted in Google</strong><p>The visit owner must reschedule or cancel it. Nothing is silently lost.</p><label class="field"><span>Select your visit</span><select id="delete-demo-visit">${state.visits.filter(v => v.owner === persona && D.stateOf(v) !== 'cancelled').map(v => `<option value="${e(v.id)}">${e(cName(v.customerId))} · ${date(v.start)}</option>`).join('')}</select></label>${button('Simulate deletion', 'simulate-delete')}</div></div></section></div>`;
  }
  function componentsView() {
    return `${heading('The building blocks.', 'Shared components, tokens and states used by this prototype.')}
      <div class="catalogue-grid"><section class="panel"><h2>A palette from the field</h2><div class="swatches">${[['Forest', '#244b3b'], ['Young leaf', '#d8e8b3'], ['Mist', '#f3f6f3'], ['Paper', '#ffffff'], ['Ink', '#253b35'], ['Harvest', '#a36518']].map(([label, color]) => `<div class="swatch"><i style="background:${color}"></i><strong>${label}</strong><br>${color}</div>`).join('')}</div><p class="spec">styles/tokens.css · semantic colour and layout variables</p></section>
      <section class="panel"><h2>Type with a purpose</h2><h1 style="margin:16px 0">Closer to your customers.</h1><h3>Give the next conversation context.</h3><p class="muted">Bahnschrift headings. Segoe UI body text. Local system fallbacks keep the demo self-contained.</p><p class="spec">32 / 28 / 20 / 16 / 14 / 12px · headings align left</p></section>
      <section class="panel"><h2>Actions & hierarchy</h2><div class="row wrap">${button('Plan a visit', 'new-visit', '', 'primary', 'plus')}${button('Add customer', 'new-customer', '', 'secondary', 'users')}${button('Preview toast', 'sample-toast', '', 'ghost') }<button class="button" disabled>Unavailable</button></div><p class="spec">Button · IconButton · visible keyboard focus · native disabled state</p></section>
      <section class="panel"><h2>State is more than colour</h2><div class="row wrap">${['planned', 'held', 'decision', 'cancelled', 'moved', 'unsynced', 'todo', 'progress', 'done'].map(s => badge(s)).join('')}</div><p class="spec">StatusBadge · moved and unsynchronised are flags, not states</p></section>
      <section class="panel"><h2>Forms with a clear next step</h2>${field('Customer name', 'sample-name', '', 'text', 'placeholder="For example, Willow Farm"') }<div class="form-error">Enter a Polish postal code in the format 00-000.</div><p class="spec">Field · associated labels · inline errors · no placeholder-only labels</p></section>
      <section class="panel"><h2>A useful empty state</h2>${empty('Room for a conversation', 'No visits planned. Start with a customer you would like to see.', button('Plan a visit', 'new-visit', '', 'primary', 'plus'))}</section>
      <section class="panel"><h2>Icon set</h2><div class="row wrap">${['sun', 'users', 'calendar', 'task', 'chart', 'pin', 'note', 'leaf', 'warning', 'refresh', 'archive', 'phone'].map(i => `<span title="${i}" style="padding:10px">${icon(i)}</span>`).join('')}</div><p class="spec">Original SVG paths · 24px viewBox · 1.6px stroke · decorative icons hidden from assistive technology</p></section>
      <section class="panel"><h2>Development handoff</h2><p class="muted">The same view helpers and rules drive the demo and this library. See the handoff files for contracts, scenarios and requirement coverage.</p><div class="row wrap"><a href="HANDOFF.md" class="button">Handoff notes</a><a href="REQUIREMENTS.md" class="button">Requirement map</a></div><p class="spec">src/components.js · src/domain.js · src/contracts.d.ts</p></section></div>`;
  }
  function openModal(title, subtitle, body, footer = '', form = '') {
    modal.innerHTML = `<div class="dialog-header"><div><h2 id="dialog-title">${e(title)}</h2><p>${e(subtitle)}</p></div>${iconButton('Close dialog', 'close-modal', '', 'close')}</div>${form ? `<form id="${form}">` : ''}<div class="dialog-body"><div class="form-error" role="alert" tabindex="-1"></div>${body}</div>${footer ? `<div class="dialog-footer">${footer}</div>` : ''}${form ? '</form>' : ''}`;
    if (!modal.open) modal.showModal();
  }
  function saveFooter(label) { return `${button('Cancel', 'close-modal')}<button class="button button-primary" type="submit">${e(label)}</button>`; }
  function showVisit(visitId) {
    const v = state.visits.find(v => v.id === visitId);
    if (!D.canRead(v, user())) return toast('This visit is not available.');
    const c = D.customer(state, v.customerId);
    const status = D.stateOf(v);
    const editable = v.owner === persona;
    const notes = state.notes.filter(n => n.visitId === v.id);
    openModal(c.name, `${date(v.start, { weekday: 'long' })} · ${time(v.start)}–${time(v.end)}`, `
      ${visitFlags(v)}
      ${status === 'decision' ? '<div class="notice" style="margin-top:18px"><p><strong>Removed from Google Calendar</strong>Choose a new time or cancel this visit. Dismissing this dialog keeps the reminder visible.</p></div>' : ''}
      <dl class="detail-grid"><div><dt>Purpose</dt><dd>${e(v.purpose || 'Customer visit')}</dd></div><div><dt>Visit owner</dt><dd>${e(personName(v.owner))}</dd></div><div><dt>Meeting address</dt><dd>${e(v.location || `${c.street}, ${c.town}`)}</dd></div><div><dt>Primary contact</dt><dd>${e((c.contacts.find(p => p.primary) || c.contacts[0])?.value || 'Not provided')}</dd></div></dl>
      <div class="row wrap">${button('Customer details', 'customer', c.id, 'secondary', 'users')}${button('Add a note', 'visit-note', v.id, 'secondary', 'note')}</div>
      ${notes.length ? `<h3 style="margin-top:24px">Visit notes</h3>${notes.map(noteCard).join('')}` : '<p class="spec">No notes yet. Capture the conversation and create a follow-up.</p>'}
      ${!editable ? '<p class="spec">Only the visit owner can move or cancel this visit.</p>' : ''}`,
      editable && status !== 'cancelled' ? `${button(status === 'held' ? 'Did not happen' : 'Cancel visit', 'cancel-visit', v.id, 'danger')}${status !== 'held' ? button(status === 'decision' ? 'Choose a new time' : 'Move visit', 'move-visit', v.id, 'primary', 'calendar') : button('Add a note', 'visit-note', v.id, 'primary', 'note')}` : button('Close', 'close-modal'));
  }
  function visitForm(visitId = '', customerId = '') {
    const v = state.visits.find(v => v.id === visitId);
    const eligible = state.customers.filter(c => c.owner === persona && !c.archived);
    if (!eligible.length) return openModal('Start with a customer', 'Visits are planned for your own active customers.', empty('No active customers', 'Add a customer or switch the demo persona to a representative.'), button('Add customer', 'new-customer', '', 'primary'));
    const start = v ? D.localParts(v.start) : `${selectedDay >= D.TODAY ? selectedDay : D.TODAY}T16:00`;
    const end = v ? D.localParts(v.end) : `${selectedDay >= D.TODAY ? selectedDay : D.TODAY}T17:00`;
    openModal(v ? 'Move visit' : 'Plan a visit', 'All times are in Europe/Warsaw.', `<input type="hidden" name="id" value="${e(visitId)}"><label class="field"><span>Customer *</span><select name="customerId" required ${v ? 'disabled' : ''}>${eligible.map(c => `<option value="${e(c.id)}" ${c.id === (v?.customerId || customerId) ? 'selected' : ''}>${e(c.name)} · ${e(c.town)}</option>`).join('')}</select></label><div class="form-grid">${field('Starts *', 'start', start, 'datetime-local', 'required')}${field('Ends *', 'end', end, 'datetime-local', 'required')}</div>${field('Purpose', 'purpose', v?.purpose || '', 'text', 'maxlength="160" placeholder="What would you like to discuss?"')}${field('Meeting address override', 'location', v?.location || '', 'text', 'maxlength="200" placeholder="Leave empty to use the customer address"')}<p class="spec">${v ? 'Changing the start time sets the Moved flag. A duration or address change alone does not.' : 'The visit is saved even if Google Calendar is unavailable. No invitation is sent to the customer.'}</p>`, saveFooter(v ? 'Save new time' : 'Plan visit'), 'visit-form');
  }
  function noteCard(n) {
    const manager = D.person(state, n.author)?.role === 'manager';
    return `<article class="note-card"><div class="row between"><strong style="font-size:12px">${e(personName(n.author))} ${manager ? '<span class="manager-label">Manager</span>' : ''}</strong>${n.author === persona ? iconButton('Edit your note', 'edit-note', n.id, 'edit') : ''}</div><small>${date(n.created)} · ${time(n.created)}${n.visitId ? ' · Visit note' : ' · Customer note'}</small><p>${e(n.body)}</p>${state.actions.filter(a => a.noteId === n.id && D.canRead(a, user())).map(a => `<div style="padding-top:10px;border-top:1px solid var(--color-line)"><div class="row between"><span style="font-size:12px">${e(a.title)}</span>${badge(a.status)}</div>${actionAttribution(a)}</div>`).join('')}</article>`;
  }
  function showCustomer(customerId, tab = 'overview') {
    const c = D.customer(state, customerId);
    if (!D.canRead(c, user())) { sheet.close(); openCustomer = null; return toast('This customer is not available in this view.'); }
    modal.close(); openCustomer = c.id; customerTab = tab;
    const vs = own(state.visits).filter(v => v.customerId === c.id).sort((a, b) => b.start.localeCompare(a.start));
    const notes = state.notes.filter(n => n.customerId === c.id).slice().reverse();
    sheet.innerHTML = `<div class="dialog-header"><div><h2 id="sheet-title">Customer details</h2><p>${c.archived ? 'Archived customer' : 'Active customer'}</p></div>${iconButton('Close customer details', 'close-sheet', '', 'close')}</div><div class="dialog-body"><div class="record-heading">${avatar(c.name)}<div><h3>${e(c.name)}</h3><p>${e(c.town)}, ${e(c.country)}</p></div></div><div class="row wrap">${button('Edit details', 'edit-customer', c.id, 'secondary', 'edit')}${!c.archived && c.owner === persona ? button('Plan a visit', 'customer-visit', c.id, 'primary', 'plus') : ''}${user().role === 'manager' ? button('Reassign', 'reassign', c.id) : ''}</div>
      <div class="record-tabs" aria-label="Customer sections">${[['overview', 'Overview'], ['visits', `Visits (${vs.length})`], ['notes', `Notes (${notes.length})`]].map(([key, label]) => `<button data-action="customer-tab" data-id="${key}" class="${tab === key ? 'active' : ''}" aria-pressed="${tab === key}">${label}</button>`).join('')}</div>
      ${tab === 'overview' ? `<dl class="detail-grid"><div><dt>Address</dt><dd>${e(c.street || 'Not provided')}<br>${e(c.postcode)} ${e(c.town)}</dd></div><div><dt>Owner</dt><dd>${e(personName(c.owner))}</dd></div><div><dt>Tax ID / NIP</dt><dd>${e(c.nip || 'Not provided')}</dd></div><div><dt>Country</dt><dd>${e(c.country)}</dd></div></dl><h3>Contacts</h3>${c.contacts.length ? c.contacts.map(p => `<div class="setting-line"><div class="row">${icon(p.kind === 'phone' ? 'phone' : 'mail')}<div><strong>${e(p.value)}</strong><small class="muted">${e(p.label || p.kind)}${p.primary ? ' · Primary' : ''}</small></div></div></div>`).join('') : '<p class="muted">No contact details added.</p>'}<h3 style="margin-top:24px">Latest conversation</h3>${notes[0] ? noteCard(notes[0]) : empty('Start the conversation', 'Add your first note to a visit.')}${!c.archived ? button('Archive customer', 'archive', c.id, 'danger', 'archive') : button('Restore customer', 'restore', c.id, 'primary', 'refresh')}` : tab === 'visits' ? (vs.length ? `<div class="agenda">${vs.map(agendaRow).join('')}</div>` : empty('No visits yet', 'Plan a visit to start this customer’s history.')) : `<div class="row between"><p class="muted" style="font-size:12px;margin:0">Notes stay with the customer.</p>${(user().role === 'manager' || vs.length) ? button('Add note', 'customer-note', c.id, 'secondary', 'plus') : ''}</div>${notes.length ? notes.map(noteCard).join('') : empty('A fresh start', 'Notes added to visits will appear here.')}`}</div>`;
    if (!sheet.open) sheet.showModal();
  }
  function contactEditor(c = {}, i = 0) {
    return `<div class="contact-edit"><div class="form-grid"><label class="field"><span>Contact type</span><select name="contactKind"><option value="phone" ${c.kind !== 'email' ? 'selected' : ''}>Phone</option><option value="email" ${c.kind === 'email' ? 'selected' : ''}>Email</option></select></label>${field('Contact value', 'contactValue', c.value || '', 'text', 'maxlength="150"')}</div>${field('Contact note', 'contactLabel', c.label || '', 'text', 'maxlength="120" placeholder="Who does this reach?"')}<div class="row between"><label class="row gap-small"><input type="radio" name="primaryContact" value="${i}" ${c.primary ? 'checked' : ''}>Primary contact</label>${button('Remove', 'remove-contact', '', 'ghost')}</div></div>`;
  }
  function customerForm(customerId = '') {
    const c = D.customer(state, customerId);
    openModal(c ? 'Edit customer' : 'Add a customer', 'Use synthetic data only. Fields marked * are required.', `<input type="hidden" name="id" value="${e(customerId)}">${field('Customer name *', 'name', c?.name || '', 'text', 'required maxlength="120" placeholder="For example, Willow Farm"')}<div class="form-grid">${field('Country *', 'country', c?.country || 'Poland', 'text', 'required maxlength="80"')}${field('Tax ID / NIP', 'nip', c?.nip || '', 'text', 'maxlength="40"')}</div>${field('Street and number', 'street', c?.street || '', 'text', 'maxlength="160"')}<div class="form-grid">${field('Postal code', 'postcode', c?.postcode || '', 'text', 'maxlength="20"')}${field('Town / post office', 'town', c?.town || '', 'text', 'maxlength="100"')}</div><h3>Contact details</h3><div id="contact-editors">${(c?.contacts.length ? c.contacts : [{}]).map(contactEditor).join('')}</div>${button('Add another contact', 'add-contact', '', 'secondary', 'plus')}<p class="spec">Nine-digit phone numbers default to +48. Region and county selectors are documented for development; they are not modelled in this demo.</p>`, saveFooter(c ? 'Save customer' : 'Add customer'), 'customer-form');
  }
  function noteForm(customerId, visitId = '', noteId = '') {
    const c = D.customer(state, customerId);
    const existing = state.notes.find(n => n.id === noteId);
    const availableVisits = own(state.visits).filter(v => v.customerId === c.id);
    openModal(existing ? 'Edit your note' : 'Capture the conversation', c.name, `<input type="hidden" name="id" value="${e(noteId)}"><input type="hidden" name="customerId" value="${e(customerId)}">${!existing ? `<label class="field"><span>${user().role === 'manager' ? 'Link to visit (optional)' : 'Visit *'}</span><select name="visitId" ${user().role !== 'manager' ? 'required' : ''}>${user().role === 'manager' ? '<option value="">Customer note</option>' : ''}${availableVisits.map(v => `<option value="${e(v.id)}" ${v.id === visitId ? 'selected' : ''}>${date(v.start)} · ${time(v.start)} · ${U.labels[D.stateOf(v)]}</option>`).join('')}</select></label>` : ''}<label class="field"><span>Note *</span><textarea name="body" required maxlength="4000" rows="5" placeholder="What did you discuss? What matters for the next visit?">${e(existing?.body || '')}</textarea></label>${!existing ? `<div style="border-top:1px solid var(--color-line);padding-top:20px"><h3>Turn a note into a next step</h3><p class="muted" style="font-size:12px">Optional. The follow-up stays linked to this note.</p>${field('Follow-up description', 'action', '', 'text', 'maxlength="200" placeholder="What needs to happen next?"')}${field('Due date (optional)', 'due', '', 'date')}</div>` : ''}${user().role === 'manager' ? '<p class="spec">Your note and follow-up will be visibly attributed to you as manager. The follow-up belongs to the customer’s owner.</p>' : ''}`, saveFooter(existing ? 'Save note' : 'Save note & follow-up'), 'note-form');
  }
  function confirmAction(title, subtitle, message, action, target, label, danger = false) {
    openModal(title, subtitle, `<p>${e(message)}</p>`, `${button('Go back', 'close-modal')}${button(label, action, target, danger ? 'danger' : 'primary')}`);
  }
  function navigate(next) {
    const allowed = [...nav.map(n => n[0]), 'components'];
    view = allowed.includes(next) ? next : 'today';
    if (view === 'team' && user().role !== 'manager') view = 'today';
    menuOpen = false; modal.close(); sheet.close(); openCustomer = null; render();
    window.scrollTo(0, 0);
  }
  document.addEventListener('click', event => {
    if (event.target.closest('.skip-link')) { event.preventDefault(); document.querySelector('#main').focus(); return; }
    const trigger = event.target.closest('[data-action]');
    if (!trigger) return;
    const { action, id } = trigger.dataset;
    switch (action) {
      case 'menu': menuOpen = !menuOpen; render(); break;
      case 'day': selectedDay = id; render(); break;
      case 'new-visit': visitForm(); break;
      case 'customer-visit': visitForm('', id); break;
      case 'move-visit': visitForm(id); break;
      case 'visit-detail': showVisit(id); break;
      case 'customer': showCustomer(id); break;
      case 'customer-tab': showCustomer(openCustomer, id); break;
      case 'new-customer': customerForm(); break;
      case 'edit-customer': customerForm(id); break;
      case 'customer-filter': customerFilter = id; render(); break;
      case 'visit-layout': visitLayout = id; render(); break;
      case 'action-filter': actionFilter = id; render(); break;
      case 'close-modal': modal.close(); break;
      case 'close-sheet': sheet.close(); openCustomer = null; break;
      case 'complete-action': mutate(() => D.changeAction(state, id, 'done', user()), 'Follow-up completed.'); break;
      case 'cancel-visit': confirmAction('Cancel this visit?', cName(state.visits.find(v => v.id === id).customerId), 'The visit will be cancelled and removed from the demo calendar. Its notes will stay with the customer. To keep the visit, go back and choose Move visit.', 'confirm-cancel', id, 'Cancel visit', true); break;
      case 'confirm-cancel': mutate(() => D.cancelVisit(state, id, user()), 'Visit cancelled. Notes retained.'); break;
      case 'archive': {
        const future = state.visits.filter(v => v.customerId === id && Date.parse(v.start) > Date.parse(D.NOW) && v.status !== 'cancelled').length;
        const actions = state.actions.filter(a => a.customerId === id && ['todo', 'progress'].includes(a.status)).length;
        confirmAction('Archive this customer?', cName(id), `${future} future visit(s) and ${actions} open follow-up(s) will be cancelled. Past visits and notes stay available. You can restore the customer, but cancelled items are not reopened.`, 'confirm-archive', id, 'Archive customer', true); break;
      }
      case 'confirm-archive': mutate(() => D.archiveCustomer(state, id, user()), 'Customer archived. History retained.'); break;
      case 'restore': mutate(() => D.restoreCustomer(state, id, user()), 'Customer restored. Cancelled visits remain cancelled.'); break;
      case 'reassign': openModal('Reassign customer', cName(id), `<input type="hidden" name="customerId" value="${e(id)}"><label class="field"><span>New owner</span><select name="owner">${state.users.filter(p => p.role === 'rep').map(p => `<option value="${p.id}" ${D.customer(state, id).owner === p.id ? 'selected' : ''}>${e(p.name)}</option>`).join('')}</select></label><p class="muted">The customer, future visits and open follow-ups move to the new owner. Previous visits and note authors stay unchanged. Reassignment does not count as moving or cancelling a visit.</p>`, saveFooter('Reassign customer'), 'reassign-form'); break;
      case 'visit-note': { const v = state.visits.find(v => v.id === id); noteForm(v.customerId, v.id); break; }
      case 'customer-note': noteForm(id); break;
      case 'edit-note': { const n = state.notes.find(n => n.id === id); noteForm(n.customerId, n.visitId, n.id); break; }
      case 'source-note': { const n = state.notes.find(n => n.id === id); if (n) showCustomer(n.customerId, 'notes'); break; }
      case 'add-contact': { const container = modal.querySelector('#contact-editors'); const indices = [...container.querySelectorAll('[name="primaryContact"]')].map(el => Number(el.value)); container.insertAdjacentHTML('beforeend', contactEditor({}, Math.max(-1, ...indices) + 1)); break; }
      case 'remove-contact': trigger.closest('.contact-edit').remove(); break;
      case 'disconnect': mutate(() => D.setConnection(state, user(), false), 'Calendar access expired in the demo. Visit states are unchanged.'); break;
      case 'reconnect': mutate(() => D.setConnection(state, user(), true), 'Demo calendar connected. Pending changes synced.'); break;
      case 'simulate-delete': {
        const visitId = document.querySelector('#delete-demo-visit')?.value;
        if (!visitId) return toast('There are no visits available for this scenario.');
        mutate(() => D.googleDelete(state, visitId, user()), 'Google deletion simulated. The visit awaits your decision.'); break;
      }
      case 'search':
        query = ''; customerFilter = 'active'; ownerFilter = 'all';
        if (view !== 'customers') { history.replaceState(null, '', '#customers'); navigate('customers'); } else render();
        document.querySelector('#customer-search')?.focus(); break;
      case 'this-week': periodFrom = '2026-10-19'; periodTo = '2026-10-25'; render(); break;
      case 'sample-toast': toast('This is the shared confirmation message.'); break;
      case 'reset': confirmAction('Reset the prototype?', 'Only P2 demo data will change.', 'All edits in this P2 browser demo will be replaced with the original synthetic examples. Other applications and prototypes are unaffected.', 'confirm-reset', '', 'Reset demo', true); break;
      case 'confirm-reset': state = D.copy(window.EkoFixtures); persona = 'alex'; selectedDay = D.TODAY; query = ''; ownerFilter = 'all'; customerFilter = 'active'; periodFrom = '2026-10-19'; periodTo = '2026-10-25'; actionFilter = 'open'; persist(); history.replaceState(null, '', '#today'); navigate('today'); toast('Demo reset. Ready for a fresh walkthrough.'); break;
    }
  });
  document.addEventListener('input', event => {
    if (event.target.id === 'customer-search') { query = event.target.value; document.querySelector('#customer-results').innerHTML = customerResults(); }
  });
  document.addEventListener('change', event => {
    const target = event.target;
    if (target.id === 'persona') { persona = target.value; query = ''; ownerFilter = 'all'; navigate(view); toast(`Demo view: ${user().name}.`); }
    if (target.id === 'owner-filter') { ownerFilter = target.value; render(); }
    if (target.id === 'period-from' || target.id === 'period-to') {
      const from = document.querySelector('#period-from').value;
      const to = document.querySelector('#period-to').value;
      if (from && to && from <= to) { periodFrom = from; periodTo = to; render(); }
      else { toast('Choose a valid range with the end on or after the start.'); render(); }
    }
    if (target.dataset.actionStatus) mutate(() => D.changeAction(state, target.dataset.actionStatus, target.value, user()), 'Follow-up status updated.');
  });
  document.addEventListener('submit', event => {
    if (!event.target.matches('#visit-form, #customer-form, #note-form, #reassign-form')) return;
    event.preventDefault();
    const form = event.target;
    const formId = form.getAttribute('id');
    const input = Object.fromEntries(new FormData(form));
    if (formId === 'visit-form') {
      const result = mutate(() => D.saveVisit(state, { ...input, start: D.toInstant(input.start), end: D.toInstant(input.end) }, user()), 'Visit saved.');
      if (result) { selectedDay = D.dayOf(result.start); if (!days.includes(selectedDay)) { visitLayout = 'list'; history.replaceState(null, '', '#visits'); navigate('visits'); } else render(); }
    }
    if (formId === 'customer-form') {
      input.contacts = [...form.querySelectorAll('.contact-edit')].map(el => ({ kind: el.querySelector('[name="contactKind"]').value, value: el.querySelector('[name="contactValue"]').value, label: el.querySelector('[name="contactLabel"]').value, primary: el.querySelector('[name="primaryContact"]').checked }));
      const result = mutate(() => D.saveCustomer(state, input, user()), '');
      if (result) { showCustomer(result.record.id); if (result.duplicate) openModal('Customer saved with a duplicate warning', result.record.name, '<p>A matching name and town, phone or email exists in the records you can access. Review your customer list before adding more details.</p>', button('Understood', 'close-modal', '', 'primary')); else toast('Customer saved.'); }
    }
    if (formId === 'note-form') mutate(() => input.id ? D.editNote(state, input.id, input.body, user()) : D.addNote(state, input, user()), input.id ? 'Note updated.' : input.action?.trim() ? 'Note and follow-up saved.' : 'Note saved.');
    if (formId === 'reassign-form') mutate(() => D.reassignCustomer(state, input.customerId, input.owner, user()), 'Customer reassigned. Historical attribution preserved.');
  });
  document.addEventListener('keydown', event => {
    if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[role="button"][data-action]')) { event.preventDefault(); event.target.click(); }
    if (event.key === '/' && !event.target.matches('input, textarea, select') && !modal.open && !sheet.open) { event.preventDefault(); document.querySelector('[data-action="search"]')?.click(); }
    if (event.key === 'Escape' && menuOpen) { menuOpen = false; render(); }
  });
  for (const dialog of [modal, sheet]) dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const r = dialog.getBoundingClientRect();
    if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close();
  });
  window.addEventListener('hashchange', () => navigate(location.hash.slice(1)));
  navigate(location.hash.slice(1) || 'today');
})();
