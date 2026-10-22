(function (root, factory) {
  const fixtures = factory();
  if (typeof module === 'object' && module.exports) module.exports = fixtures;
  else root.EkoFixtures = fixtures;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const contact = n => [{ kind: 'phone', value: `+48500000${String(n).padStart(3, '0')}`, label: 'Main contact · synthetic', primary: true }, { kind: 'email', value: `farm${n}@example.invalid`, label: 'Office', primary: false }];
  return {
    version: 1,
    users: [{ id: 'alex', name: 'Alex Morgan', initials: 'AM', role: 'rep', region: 'Wielkopolskie' }, { id: 'julia', name: 'Julia Reed', initials: 'JR', role: 'rep', region: 'Kujawsko-pomorskie' }, { id: 'robin', name: 'Robin Ellis', initials: 'RE', role: 'manager', region: 'Team manager' }],
    connections: { alex: 'connected', julia: 'expired', robin: 'connected' },
    customers: [
      { id: 'c1', name: 'Willow Farm', town: 'Śrem', street: 'Testowa 12', postcode: '63-100', country: 'Poland', nip: '', contacts: contact(1), owner: 'alex', archived: false },
      { id: 'c2', name: 'Meadow & Grain', town: 'Kórnik', street: 'Przykładowa 8', postcode: '62-035', country: 'Poland', nip: '', contacts: contact(2), owner: 'alex', archived: false },
      { id: 'c3', name: 'Oakfield Growers', town: 'Mosina', street: 'Testowa 21', postcode: '62-050', country: 'Poland', nip: '', contacts: contact(3), owner: 'alex', archived: false },
      { id: 'c4', name: 'Green Acre Farm', town: 'Puszczykowo', street: 'Przykładowa 4', postcode: '62-040', country: 'Poland', nip: '', contacts: contact(4), owner: 'alex', archived: false },
      { id: 'c5', name: 'Birch Hollow', town: 'Kościan', street: 'Testowa 3', postcode: '64-000', country: 'Poland', nip: '', contacts: contact(5), owner: 'alex', archived: false },
      { id: 'c6', name: 'Riverbend Fields', town: 'Żnin', street: 'Testowa 6', postcode: '88-400', country: 'Poland', nip: '', contacts: contact(6), owner: 'julia', archived: false },
      { id: 'c7', name: 'Clover Hill', town: 'Nakło nad Notecią', street: 'Testowa 7', postcode: '89-100', country: 'Poland', nip: '', contacts: contact(7), owner: 'julia', archived: false },
      { id: 'c8', name: 'Old Mill Farm', town: 'Śrem', street: 'Testowa 18', postcode: '63-100', country: 'Poland', nip: '', contacts: contact(8), owner: 'alex', archived: true }
    ],
    visits: [
      { id: 'v1', customerId: 'c1', owner: 'alex', start: '2026-10-22T07:00:00Z', end: '2026-10-22T08:00:00Z', status: 'planned', moved: false, unsynced: false, purpose: 'Autumn check-in', location: '' },
      { id: 'v2', customerId: 'c2', owner: 'alex', start: '2026-10-22T09:00:00Z', end: '2026-10-22T10:00:00Z', status: 'planned', moved: false, unsynced: false, purpose: 'Season review & next steps', location: '' },
      { id: 'v3', customerId: 'c3', owner: 'alex', start: '2026-10-22T11:30:00Z', end: '2026-10-22T12:15:00Z', status: 'planned', moved: true, unsynced: true, purpose: 'Follow-up meeting', location: '' },
      { id: 'v4', customerId: 'c4', owner: 'alex', start: '2026-10-22T13:00:00Z', end: '2026-10-22T14:00:00Z', status: 'decision', moved: false, unsynced: false, purpose: 'Quarterly conversation', location: '' },
      { id: 'v5', customerId: 'c5', owner: 'alex', start: '2026-10-23T08:00:00Z', end: '2026-10-23T09:00:00Z', status: 'planned', moved: false, unsynced: false, purpose: 'First visit', location: '' },
      { id: 'v6', customerId: 'c1', owner: 'alex', start: '2026-10-20T08:00:00Z', end: '2026-10-20T09:00:00Z', status: 'planned', moved: true, unsynced: false, purpose: 'Introduction', location: '' },
      { id: 'v7', customerId: 'c2', owner: 'alex', start: '2026-10-21T10:00:00Z', end: '2026-10-21T11:00:00Z', status: 'cancelled', moved: false, unsynced: false, purpose: 'Rescheduled by customer', location: '' },
      { id: 'v8', customerId: 'c6', owner: 'julia', start: '2026-10-22T07:00:00Z', end: '2026-10-22T08:00:00Z', status: 'planned', moved: false, unsynced: false, purpose: 'Regular check-in', location: '' },
      { id: 'v9', customerId: 'c7', owner: 'julia', start: '2026-10-23T09:00:00Z', end: '2026-10-23T10:00:00Z', status: 'planned', moved: false, unsynced: true, purpose: 'Season review', location: '' },
      { id: 'v10', customerId: 'c3', owner: 'alex', start: '2026-10-19T07:30:00Z', end: '2026-10-19T08:30:00Z', status: 'planned', moved: false, unsynced: false, purpose: 'Autumn check-in', location: '' }
    ],
    notes: [
      { id: 'n1', customerId: 'c1', visitId: 'v1', author: 'alex', created: '2026-10-22T08:05:00Z', body: 'Good catch-up this morning. The customer would like a short follow-up call next week. Confirm a convenient time before planning another visit.' },
      { id: 'n2', customerId: 'c3', visitId: 'v10', author: 'alex', created: '2026-10-19T08:35:00Z', body: 'The afternoon works better for the next meeting. Call to confirm the new time and bring the information requested at our last visit.' },
      { id: 'n3', customerId: 'c2', visitId: null, author: 'robin', created: '2026-10-21T12:00:00Z', body: 'Please check that the primary contact details are still current during the next visit.' }
    ],
    actions: [
      { id: 'a1', noteId: 'n2', customerId: 'c3', owner: 'alex', author: 'alex', title: 'Confirm the afternoon visit', due: '2026-10-21', status: 'todo', changedBy: 'alex' },
      { id: 'a2', noteId: 'n3', customerId: 'c2', owner: 'alex', author: 'robin', title: 'Check primary contact details', due: '2026-10-22', status: 'todo', changedBy: 'robin' },
      { id: 'a3', noteId: 'n1', customerId: 'c1', owner: 'alex', author: 'alex', title: 'Arrange a follow-up call', due: '2026-10-23', status: 'progress', changedBy: 'alex' },
      { id: 'a4', noteId: 'n2', customerId: 'c3', owner: 'alex', author: 'alex', title: 'Review previous meeting notes', due: '', status: 'done', changedBy: 'alex' }
    ]
  };
});
