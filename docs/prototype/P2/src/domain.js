/* Pure prototype rules. The production API must enforce these independently. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.EkoDomain = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const NOW = '2026-10-22T08:15:00Z';
  const TODAY = '2026-10-22';
  const transitions = { todo: ['progress', 'done', 'cancelled'], progress: ['todo', 'done', 'cancelled'], done: ['todo'], cancelled: ['todo'] };
  const copy = value => JSON.parse(JSON.stringify(value));
  const id = prefix => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const person = (state, userId) => state.users.find(u => u.id === userId);
  const visible = (rows, user) => rows.filter(row => user.role === 'manager' || row.owner === user.id);
  const customer = (state, customerId) => state.customers.find(c => c.id === customerId);
  const canRead = (record, user) => Boolean(record && (user.role === 'manager' || record.owner === user.id));
  function requireRead(record, user) { if (!canRead(record, user)) throw new Error('This record is not available.'); }
  function stateOf(visit, now = NOW) {
    if (visit.status === 'cancelled' || visit.status === 'decision') return visit.status;
    return Date.parse(visit.end) <= Date.parse(now) ? 'held' : 'planned';
  }
  const overdue = (action, today = TODAY) => Boolean(action.due && action.due < today && !['done', 'cancelled'].includes(action.status));
  function dayOf(instant) {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(instant));
  }
  function localParts(instant) {
    const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(instant));
    const p = Object.fromEntries(parts.map(v => [v.type, v.value]));
    return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
  }
  function toInstant(local) {
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) throw new Error('Enter a valid date and time.');
    const base = Date.parse(`${local}:00Z`);
    const candidates = [base - 7200000, base - 3600000].filter(t => localParts(new Date(t).toISOString()) === local);
    if (!candidates.length) throw new Error('This time does not exist in Europe/Warsaw. Choose another time.');
    if (candidates.length > 1) throw new Error('This time occurs twice when clocks change. Choose a time outside the repeated hour.');
    return new Date(candidates[0]).toISOString();
  }
  function normalizeNip(nip) { return nip.trim().replace(/^PL/i, '').replace(/[\s-]/g, ''); }
  function validNip(nip) {
    const n = normalizeNip(nip);
    return /^\d{10}$/.test(n) && [6, 5, 7, 2, 3, 4, 5, 6, 7].reduce((sum, w, i) => sum + w * Number(n[i]), 0) % 11 === Number(n[9]);
  }
  function saveCustomer(state, input, user) {
    const existing = input.id ? customer(state, input.id) : null;
    if (input.id) requireRead(existing, user);
    const name = String(input.name || '').trim();
    const country = String(input.country || '').trim();
    if (!name || !country) throw new Error('Name and country are required.');
    if (name.length > 120) throw new Error('Use a name of 120 characters or fewer.');
    const nip = country === 'Poland' ? normalizeNip(input.nip || '') : (input.nip || '').trim();
    if (country === 'Poland' && input.postcode && !/^\d{2}-\d{3}$/.test(input.postcode)) throw new Error('Use a Polish postal code in the format 00-000.');
    if (country === 'Poland' && nip && !validNip(nip)) throw new Error('Enter a Polish NIP with 10 digits and a valid checksum.');
    const conflict = nip && state.customers.find(c => c.id !== input.id && c.nip === nip);
    if (conflict) throw new Error(user.role === 'manager' ? `A customer with this tax ID already exists: ${conflict.name}.` : 'A customer with this NIP already exists. Contact your manager.');
    const contacts = (input.contacts || []).filter(c => c.value.trim()).map(c => ({ ...c, value: c.value.trim() }));
    for (const c of contacts) {
      if (c.kind === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c.value)) throw new Error('Enter a valid email address.');
      if (c.kind === 'phone') {
        c.value = c.value.replace(/[\s()-]/g, '');
        if (/^\d{9}$/.test(c.value)) c.value = '+48' + c.value;
        if (!/^\+[1-9]\d{7,14}$/.test(c.value)) throw new Error('Use an international phone number, for example +48 500 000 001.');
      }
    }
    if (contacts.filter(c => c.primary).length > 1) throw new Error('Choose only one primary contact.');
    const others = visible(state.customers, user).filter(c => c.id !== input.id);
    const duplicate = others.some(c => (c.name.trim().toLowerCase() === name.toLowerCase() && c.town.trim().toLowerCase() === (input.town || '').trim().toLowerCase()) || c.contacts.some(a => contacts.some(b => a.value.toLowerCase() === b.value.toLowerCase())));
    const record = { id: existing?.id || id('customer'), name, country, street: input.street || '', town: input.town || '', postcode: input.postcode || '', nip, contacts, owner: existing?.owner || user.id, archived: existing?.archived || false };
    if (existing) Object.assign(existing, record); else state.customers.push(record);
    return { record, duplicate };
  }
  function saveVisit(state, input, user) {
    const existing = input.id ? state.visits.find(v => v.id === input.id) : null;
    if (input.id && (!existing || existing.owner !== user.id)) throw new Error('Only the visit owner can change this visit.');
    const c = customer(state, existing?.customerId || input.customerId);
    if (!c || c.owner !== user.id || c.archived) throw new Error('Choose one of your own active customers.');
    if (!Number.isFinite(Date.parse(input.start)) || !Number.isFinite(Date.parse(input.end)) || Date.parse(input.end) <= Date.parse(input.start)) throw new Error('The end time must be after the start time.');
    if (Date.parse(input.start) <= Date.parse(NOW)) throw new Error('Plan or move a visit to a future time.');
    const record = { id: existing?.id || id('visit'), customerId: c.id, owner: user.id, start: input.start, end: input.end, status: 'planned', moved: Boolean(existing?.moved || existing && (Date.parse(existing.start) !== Date.parse(input.start) || existing.status === 'decision')), unsynced: state.connections[user.id] !== 'connected', purpose: input.purpose || '', location: input.location || '' };
    if (existing) Object.assign(existing, record); else state.visits.push(record);
    return record;
  }
  function cancelVisit(state, visitId, user) {
    const v = state.visits.find(v => v.id === visitId);
    if (!v || v.owner !== user.id) throw new Error('Only the visit owner can cancel this visit.');
    v.status = 'cancelled'; v.unsynced = state.connections[user.id] !== 'connected';
  }
  function googleDelete(state, visitId, user) {
    const v = state.visits.find(v => v.id === visitId);
    if (!v || v.owner !== user.id || stateOf(v) === 'cancelled') throw new Error('Select one of your non-cancelled visits.');
    v.status = 'decision';
  }
  function setConnection(state, user, connected) {
    state.connections[user.id] = connected ? 'connected' : 'expired';
    if (connected) state.visits.filter(v => v.owner === user.id).forEach(v => { v.unsynced = false; });
  }
  function archiveCustomer(state, customerId, user) {
    const c = customer(state, customerId); requireRead(c, user); c.archived = true;
    state.visits.filter(v => v.customerId === c.id && Date.parse(v.start) > Date.parse(NOW)).forEach(v => { v.status = 'cancelled'; v.unsynced = state.connections[v.owner] !== 'connected'; });
    state.actions.filter(a => a.customerId === c.id && ['todo', 'progress'].includes(a.status)).forEach(a => { a.status = 'cancelled'; a.changedBy = user.id; });
  }
  function restoreCustomer(state, customerId, user) {
    const c = customer(state, customerId); requireRead(c, user); c.archived = false;
  }
  function reassignCustomer(state, customerId, owner, user) {
    if (user.role !== 'manager') throw new Error('Only a manager can reassign customers.');
    const c = customer(state, customerId);
    if (!c || !person(state, owner) || person(state, owner).role !== 'rep') throw new Error('Choose a sales representative.');
    c.owner = owner;
    state.visits.filter(v => v.customerId === c.id && Date.parse(v.start) > Date.parse(NOW) && v.status !== 'cancelled').forEach(v => { v.owner = owner; v.unsynced = state.connections[owner] !== 'connected'; });
    state.actions.filter(a => a.customerId === c.id && ['todo', 'progress'].includes(a.status)).forEach(a => { a.owner = owner; });
  }
  function addNote(state, input, user) {
    const c = customer(state, input.customerId); requireRead(c, user);
    const visit = state.visits.find(v => v.id === input.visitId);
    if (user.role !== 'manager' && (!visit || visit.customerId !== c.id || visit.owner !== user.id)) throw new Error('Select one of your visits for this note.');
    if (visit && visit.customerId !== c.id) throw new Error('Select a visit for this customer.');
    if (!input.body?.trim()) throw new Error('Write a note before saving.');
    const note = { id: id('note'), customerId: c.id, visitId: visit?.id || null, author: user.id, body: input.body.trim(), created: NOW };
    state.notes.push(note);
    if (input.action?.trim()) state.actions.push({ id: id('action'), noteId: note.id, customerId: c.id, owner: user.role === 'manager' ? c.owner : user.id, author: user.id, title: input.action.trim(), due: input.due || '', status: 'todo', changedBy: user.id });
    return note;
  }
  function editNote(state, noteId, body, user) {
    const note = state.notes.find(n => n.id === noteId);
    if (!note || note.author !== user.id) throw new Error('Only the author can edit this note.');
    if (!body.trim()) throw new Error('Write a note before saving.');
    note.body = body.trim();
  }
  function changeAction(state, actionId, status, user) {
    const action = state.actions.find(a => a.id === actionId); requireRead(action, user);
    if (action.owner !== user.id && user.role === 'manager' && !['done', 'cancelled'].includes(status)) throw new Error('A manager can only close another person’s action.');
    if (!transitions[action.status]?.includes(status)) throw new Error('This status transition is not allowed.');
    action.status = status; action.changedBy = user.id;
  }
  function metrics(visits, from, to) {
    const rows = visits.filter(v => dayOf(v.start) >= from && dayOf(v.start) <= to);
    return { planned: rows.filter(v => ['planned', 'held'].includes(stateOf(v))).length, held: rows.filter(v => stateOf(v) === 'held').length, moved: rows.filter(v => v.moved).length, cancelled: rows.filter(v => stateOf(v) === 'cancelled').length, decision: rows.filter(v => stateOf(v) === 'decision').length };
  }
  return { NOW, TODAY, transitions, copy, id, person, customer, visible, canRead, stateOf, overdue, dayOf, localParts, toInstant, normalizeNip, validNip, saveCustomer, saveVisit, cancelVisit, googleDelete, setConnection, archiveCustomer, restoreCustomer, reassignCustomer, addNote, editNote, changeAction, metrics };
});
