const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const D = require('../src/domain.js');
const L = require('../src/locale-pl.js');
const fixtures = require('../src/fixtures.js');

test('localisation updates seed content while preserving saved edits and workflow state', () => {
  const state = D.copy(fixtures);
  state.customers[0].name = 'Moja własna nazwa';
  state.customers[0].contacts[0].label = 'Mój kontakt';
  state.notes[0].body = 'Moja notatka';
  state.visits[0].status = 'cancelled';
  state.actions[0].status = 'done';
  L.localizeFixtures(state);
  assert.equal(state.customers[0].name, 'Moja własna nazwa');
  assert.equal(state.customers[0].contacts[0].label, 'Mój kontakt');
  assert.equal(state.customers[1].name, 'Łąki i Zboża');
  assert.equal(state.notes[0].body, 'Moja notatka');
  assert.equal(state.visits[0].status, 'cancelled');
  assert.equal(state.actions[0].status, 'done');
  assert.equal(state.actions[0].title, 'Potwierdź popołudniową wizytę');
  const before = D.copy(state);
  assert.deepEqual(L.localizeFixtures(state), before);
});

test('Polska input keeps Polish postal code and NIP validation active', () => {
  const state = D.copy(fixtures);
  const input = { name: 'Test języka', country: L.countryValue(' Polska '), contacts: [], postcode: '1234' };
  assert.equal(L.country(input.country), 'Polska');
  assert.throws(() => D.saveCustomer(state, input, state.users[0]), /postal code/);
  input.postcode = '00-001'; input.nip = '1234567890';
  assert.throws(() => D.saveCustomer(state, input, state.users[0]), /checksum/);
  input.nip = '';
  assert.equal(D.saveCustomer(state, input, state.users[0]).record.country, 'Poland');
  assert.equal(L.countryValue('Germany'), 'Germany');
});

test('all static domain errors have Polish presentation and dynamic conflicts retain names', () => {
  const source = fs.readFileSync(require.resolve('../src/domain.js'), 'utf8');
  const messages = [...source.matchAll(/new Error\('([^']+)'\)/g)].map(match => match[1]);
  for (const message of messages) assert.ok(L.errors[message], `Missing translation: ${message}`);
  assert.equal(L.errorMessage('A customer with this tax ID already exists: Łąki.'), 'Klient z tym identyfikatorem podatkowym już istnieje: Łąki.');
  assert.ok(L.errorMessage('Unexpected internal error').startsWith('Nie udało'));
});

test('Polish visit counts use correct plural forms', () => {
  const expected = ['0 wizyt', '1 wizyta', '2 wizyty', '5 wizyt', '12 wizyt', '22 wizyty'];
  assert.deepEqual([0, 1, 2, 5, 12, 22].map(n => L.plural(n, 'wizyta', 'wizyty', 'wizyt')), expected);
});
