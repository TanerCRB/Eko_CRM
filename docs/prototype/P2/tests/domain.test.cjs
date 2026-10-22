const { test } = require('node:test');
const assert = require('node:assert/strict');
const D = require('../src/domain.js');
const fixtures = require('../src/fixtures.js');
const setup = () => { const state = D.copy(fixtures); return { state, rep: state.users[0], other: state.users[1], manager: state.users[2] }; };

test('held derives from end time; cancellation and decision take precedence', () => {
  const { state } = setup();
  assert.equal(D.stateOf(state.visits[0]), 'held');
  assert.equal(D.stateOf(state.visits[1]), 'planned');
  assert.equal(D.stateOf({ ...state.visits[0], status: 'decision' }), 'decision');
  assert.equal(D.stateOf({ ...state.visits[0], status: 'cancelled' }), 'cancelled');
});
test('rep visibility excludes another owner; manager sees all', () => {
  const { state, rep, manager } = setup();
  assert.equal(D.visible(state.customers, rep).some(c => c.owner === 'julia'), false);
  assert.equal(D.visible(state.customers, manager).length, state.customers.length);
});
test('a manager cannot move or cancel another owner’s visit', () => {
  const { state, manager } = setup();
  assert.throws(() => D.saveVisit(state, { ...state.visits[1], start: '2026-10-23T10:00:00Z', end: '2026-10-23T11:00:00Z' }, manager), /Only the visit owner/);
  assert.throws(() => D.cancelVisit(state, 'v2', manager), /Only the visit owner/);
});
test('moving start sets moved; duration and equivalent ISO formatting do not', () => {
  const { state, rep } = setup();
  const initial = state.visits.find(v => v.id === 'v2');
  D.saveVisit(state, { ...initial, start: '2026-10-22T09:00:00.000Z', end: '2026-10-22T10:30:00Z' }, rep);
  assert.equal(initial.moved, false);
  D.saveVisit(state, { ...initial, start: '2026-10-22T09:30:00Z' }, rep);
  assert.equal(initial.moved, true);
});
test('Google deletion requires a decision, and rescheduling marks moved', () => {
  const { state, rep } = setup();
  D.googleDelete(state, 'v2', rep);
  assert.equal(D.stateOf(state.visits[1]), 'decision');
  D.saveVisit(state, { ...state.visits[1], start: '2026-10-23T09:00:00Z', end: '2026-10-23T10:00:00Z' }, rep);
  assert.equal(D.stateOf(state.visits[1]), 'planned');
  assert.equal(state.visits[1].moved, true);
});
test('connection expiry changes no visit state and saving offline marks unsynced', () => {
  const { state, rep } = setup();
  const before = state.visits.map(v => [v.id, v.status]);
  D.setConnection(state, rep, false);
  assert.deepEqual(state.visits.map(v => [v.id, v.status]), before);
  const visit = D.saveVisit(state, { customerId: 'c1', start: '2026-10-23T09:00:00Z', end: '2026-10-23T10:00:00Z' }, rep);
  assert.equal(visit.unsynced, true);
  D.setConnection(state, rep, true);
  assert.equal(visit.unsynced, false);
});
test('archive cancels only that customer’s future visits and open actions; retains notes', () => {
  const { state, rep } = setup();
  const unrelated = D.copy(state.visits.filter(v => v.customerId !== 'c3'));
  const notes = D.copy(state.notes);
  D.archiveCustomer(state, 'c3', rep);
  assert.equal(state.visits.find(v => v.id === 'v3').status, 'cancelled');
  assert.equal(D.stateOf(state.visits.find(v => v.id === 'v10')), 'held');
  assert.equal(state.actions.find(a => a.id === 'a1').status, 'cancelled');
  assert.equal(state.actions.find(a => a.id === 'a4').status, 'done');
  assert.deepEqual(state.visits.filter(v => v.customerId !== 'c3'), unrelated);
  assert.deepEqual(state.notes, notes);
  D.restoreCustomer(state, 'c3', rep);
  assert.equal(D.customer(state, 'c3').archived, false);
  assert.equal(state.visits.find(v => v.id === 'v3').status, 'cancelled');
});
test('reassignment preserves history, moved flags and unrelated data', () => {
  const { state, manager } = setup();
  const unrelated = D.copy(state.visits.filter(v => v.customerId !== 'c3'));
  D.reassignCustomer(state, 'c3', 'julia', manager);
  assert.equal(D.customer(state, 'c3').owner, 'julia');
  assert.equal(state.visits.find(v => v.id === 'v3').owner, 'julia');
  assert.equal(state.visits.find(v => v.id === 'v3').moved, true);
  assert.equal(state.visits.find(v => v.id === 'v10').owner, 'alex');
  assert.equal(state.notes.find(n => n.id === 'n2').author, 'alex');
  assert.equal(state.actions.find(a => a.id === 'a1').owner, 'julia');
  assert.equal(state.actions.find(a => a.id === 'a4').owner, 'alex');
  assert.deepEqual(state.visits.filter(v => v.customerId !== 'c3'), unrelated);
});
test('rep cannot reassign, create for another owner, or edit another owner’s customer', () => {
  const { state, rep } = setup();
  assert.throws(() => D.reassignCustomer(state, 'c1', 'julia', rep), /Only a manager/);
  assert.throws(() => D.saveVisit(state, { customerId: 'c6' }, rep), /own active customers/);
  assert.throws(() => D.saveCustomer(state, { ...D.customer(state, 'c6'), name: 'Changed' }, rep), /not available/);
});
test('manager note creates an action owned by the customer owner with author attribution', () => {
  const { state, manager } = setup();
  const note = D.addNote(state, { customerId: 'c1', body: 'Synthetic manager note', action: 'Follow up', due: '' }, manager);
  const a = state.actions.find(a => a.noteId === note.id);
  assert.equal(note.author, manager.id);
  assert.equal(a.owner, 'alex');
  assert.equal(a.author, manager.id);
  assert.equal(D.overdue(a), false);
});
test('rep note needs its own matching visit; manager cannot edit a rep note', () => {
  const { state, rep, manager } = setup();
  assert.throws(() => D.addNote(state, { customerId: 'c1', body: 'Test' }, rep), /Select one of your visits/);
  assert.throws(() => D.addNote(state, { customerId: 'c1', visitId: 'v2', body: 'Test' }, rep), /Select one of your visits/);
  assert.throws(() => D.editNote(state, 'n1', 'Changed', manager), /Only the author/);
});
test('manager can close others’ actions but cannot reopen or start them', () => {
  const { state, manager } = setup();
  assert.throws(() => D.changeAction(state, 'a1', 'progress', manager), /only close/);
  D.changeAction(state, 'a1', 'done', manager);
  assert.equal(state.actions[0].changedBy, manager.id);
  assert.throws(() => D.changeAction(state, 'a1', 'todo', manager), /only close/);
});
test('action transitions reject done to progress and allow reopen to todo', () => {
  const { state, rep } = setup();
  assert.throws(() => D.changeAction(state, 'a4', 'progress', rep), /not allowed/);
  D.changeAction(state, 'a4', 'todo', rep);
  assert.equal(state.actions.find(a => a.id === 'a4').status, 'todo');
});
test('overdue is computed only for open dated actions', () => {
  assert.equal(D.overdue({ due: '2026-10-21', status: 'todo' }), true);
  assert.equal(D.overdue({ due: '2026-10-22', status: 'todo' }), false);
  assert.equal(D.overdue({ due: '2026-10-21', status: 'done' }), false);
  assert.equal(D.overdue({ due: '', status: 'progress' }), false);
});
test('NIP checksum and normalisation; collision message conceals another rep’s identity', () => {
  const { state, rep } = setup();
  assert.equal(D.validNip('PL 123-456-32-18'), true);
  assert.equal(D.validNip('1234563219'), false);
  D.customer(state, 'c6').nip = '1234563218';
  assert.throws(() => D.saveCustomer(state, { name: 'Synthetic', country: 'Poland', nip: 'PL 123-456-32-18' }, rep), error => error.message === 'A customer with this NIP already exists. Contact your manager.');
});
test('minimal customer, phone default, foreign tax ID, and postal validation', () => {
  const { state, rep } = setup();
  const { record } = D.saveCustomer(state, { name: 'Synthetic', country: 'Poland', contacts: [{ kind: 'phone', value: '500 000 099', label: '', primary: true }] }, rep);
  assert.equal(record.contacts[0].value, '+48500000099');
  assert.throws(() => D.saveCustomer(state, { name: 'Test', country: 'Poland', postcode: '1234' }, rep), /00-000/);
  assert.equal(D.saveCustomer(state, { name: 'Foreign test', country: 'Germany', postcode: '12345', nip: 'DE-test' }, rep).record.nip, 'DE-test');
});
test('duplicate warnings see only accessible customers and do not block saving', () => {
  const { state, rep, manager } = setup();
  const input = { name: 'Riverbend Fields', town: 'Żnin', country: 'Poland' };
  assert.equal(D.saveCustomer(state, input, rep).duplicate, false);
  assert.equal(D.saveCustomer(state, input, manager).duplicate, true);
});
test('Warsaw conversions use DST and reject nonexistent or ambiguous local times', () => {
  assert.equal(D.toInstant('2026-10-22T11:00'), '2026-10-22T09:00:00.000Z');
  assert.equal(D.toInstant('2026-12-22T11:00'), '2026-12-22T10:00:00.000Z');
  assert.throws(() => D.toInstant('2026-03-29T02:30'), /does not exist/);
  assert.throws(() => D.toInstant('2026-10-25T02:30'), /occurs twice/);
  assert.equal(D.dayOf('2026-10-21T23:00:00Z'), '2026-10-22');
});
test('dashboard includes held in planned, separates decision and counts moved once', () => {
  const { state, rep } = setup();
  const m = D.metrics(D.visible(state.visits, rep), '2026-10-19', '2026-10-25');
  assert.deepEqual(m, { planned: 6, held: 3, moved: 2, cancelled: 1, decision: 1 });
  const single = D.metrics(D.visible(state.visits, rep), '2026-10-22', '2026-10-22');
  assert.deepEqual(single, { planned: 3, held: 1, moved: 1, cancelled: 0, decision: 1 });
});
test('cancellation preserves notes and archive does not delete customer records', () => {
  const { state, rep } = setup();
  D.cancelVisit(state, 'v1', rep);
  assert.equal(state.notes.find(n => n.visitId === 'v1').body, fixtures.notes[0].body);
  D.archiveCustomer(state, 'c1', rep);
  assert.equal(state.customers.length, fixtures.customers.length);
});
