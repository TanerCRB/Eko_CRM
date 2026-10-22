/* Polish presentation only; identifiers and domain error contracts stay in English. */
(function (root, factory) {
  const locale = factory();
  if (typeof module === 'object' && module.exports) module.exports = locale;
  else root.EkoLocale = locale;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const errors = {
    'This record is not available.': 'Ten rekord nie jest dostępny.',
    'Enter a valid date and time.': 'Podaj poprawną datę i godzinę.',
    'This time does not exist in Europe/Warsaw. Choose another time.': 'Ta godzina nie istnieje w strefie Europe/Warsaw z powodu zmiany czasu. Wybierz inną godzinę.',
    'This time occurs twice when clocks change. Choose a time outside the repeated hour.': 'Ta godzina występuje dwukrotnie przy zmianie czasu. Wybierz godzinę poza powtarzającym się przedziałem.',
    'Name and country are required.': 'Nazwa i kraj są wymagane.',
    'Use a name of 120 characters or fewer.': 'Nazwa może mieć najwyżej 120 znaków.',
    'Use a Polish postal code in the format 00-000.': 'Podaj polski kod pocztowy w formacie 00-000.',
    'Enter a Polish NIP with 10 digits and a valid checksum.': 'Podaj polski NIP: 10 cyfr z poprawną sumą kontrolną.',
    'A customer with this NIP already exists. Contact your manager.': 'Klient z tym NIP-em już istnieje. Skontaktuj się z kierownikiem.',
    'Enter a valid email address.': 'Podaj poprawny adres e-mail.',
    'Use an international phone number, for example +48 500 000 001.': 'Podaj numer telefonu z prefiksem kraju, np. +48 500 000 001.',
    'Choose only one primary contact.': 'Wybierz tylko jeden kontakt główny.',
    'Only the visit owner can change this visit.': 'Tylko opiekun wizyty może ją zmienić.',
    'Choose one of your own active customers.': 'Wybierz jednego ze swoich aktywnych klientów.',
    'The end time must be after the start time.': 'Koniec wizyty musi przypadać po jej rozpoczęciu.',
    'Plan or move a visit to a future time.': 'Wybierz przyszły termin wizyty.',
    'Only the visit owner can cancel this visit.': 'Tylko opiekun wizyty może ją odwołać.',
    'Select one of your non-cancelled visits.': 'Wybierz swoją wizytę, która nie została odwołana.',
    'Only a manager can reassign customers.': 'Tylko kierownik może zmienić opiekuna klienta.',
    'Choose a sales representative.': 'Wybierz handlowca.',
    'Select one of your visits for this note.': 'Wybierz swoją wizytę, do której chcesz dodać notatkę.',
    'Select a visit for this customer.': 'Wybierz wizytę u tego klienta.',
    'Write a note before saving.': 'Wpisz treść notatki przed zapisaniem.',
    'Only the author can edit this note.': 'Tylko autor może edytować tę notatkę.',
    'A manager can only close another person’s action.': 'Kierownik może jedynie zamknąć zadanie innej osoby.',
    'This status transition is not allowed.': 'Ta zmiana statusu nie jest dozwolona.'
  };
  function errorMessage(message) {
    const prefix = 'A customer with this tax ID already exists: ';
    if (message.startsWith(prefix)) return 'Klient z tym identyfikatorem podatkowym już istnieje: ' + message.slice(prefix.length);
    return errors[message] || 'Nie udało się zapisać zmian. Sprawdź dane i spróbuj ponownie.';
  }
  const country = value => value === 'Poland' ? 'Polska' : value;
  const countryValue = value => value.trim().toLocaleLowerCase('pl-PL') === 'polska' ? 'Poland' : value;
  function plural(count, one, few, many) {
    const category = new Intl.PluralRules('pl-PL').select(count);
    return `${count} ${category === 'one' ? one : category === 'few' ? few : many}`;
  }
  const seedText = {
    customers: {
      c1: { name: ['Willow Farm', 'Gospodarstwo Pod Wierzbą'] },
      c2: { name: ['Meadow & Grain', 'Łąki i Zboża'] },
      c3: { name: ['Oakfield Growers', 'Dębowe Pole'] },
      c4: { name: ['Green Acre Farm', 'Zielony Łan'] },
      c5: { name: ['Birch Hollow', 'Brzozowa Dolina'] },
      c6: { name: ['Riverbend Fields', 'Nad Zakolem'] },
      c7: { name: ['Clover Hill', 'Koniczynowe Wzgórze'] },
      c8: { name: ['Old Mill Farm', 'Stary Młyn'] }
    },
    visits: {
      v1: { purpose: ['Autumn check-in', 'Jesienna wizyta'] },
      v2: { purpose: ['Season review & next steps', 'Podsumowanie sezonu i dalsze plany'] },
      v3: { purpose: ['Follow-up meeting', 'Omówienie dalszych działań'] },
      v4: { purpose: ['Quarterly conversation', 'Spotkanie kwartalne'] },
      v5: { purpose: ['First visit', 'Pierwsza wizyta'] },
      v6: { purpose: ['Introduction', 'Spotkanie zapoznawcze'] },
      v7: { purpose: ['Rescheduled by customer', 'Zmiana terminu na prośbę klienta'] },
      v8: { purpose: ['Regular check-in', 'Wizyta okresowa'] },
      v9: { purpose: ['Season review', 'Podsumowanie sezonu'] },
      v10: { purpose: ['Autumn check-in', 'Jesienna wizyta'] }
    },
    notes: {
      n1: { body: ['Good catch-up this morning. The customer would like a short follow-up call next week. Confirm a convenient time before planning another visit.', 'Udane spotkanie dziś rano. Klient prosi o krótką rozmowę telefoniczną w przyszłym tygodniu. Przed zaplanowaniem kolejnej wizyty potwierdź dogodny termin.'] },
      n2: { body: ['The afternoon works better for the next meeting. Call to confirm the new time and bring the information requested at our last visit.', 'Kolejne spotkanie najlepiej zaplanować po południu. Zadzwoń, aby potwierdzić nowy termin, i przygotuj informacje, o które klient prosił podczas ostatniej wizyty.'] },
      n3: { body: ['Please check that the primary contact details are still current during the next visit.', 'Podczas kolejnej wizyty sprawdź, czy dane głównego kontaktu są nadal aktualne.'] }
    },
    actions: {
      a1: { title: ['Confirm the afternoon visit', 'Potwierdź popołudniową wizytę'] },
      a2: { title: ['Check primary contact details', 'Sprawdź dane głównego kontaktu'] },
      a3: { title: ['Arrange a follow-up call', 'Umów kolejną rozmowę telefoniczną'] },
      a4: { title: ['Review previous meeting notes', 'Przejrzyj notatki z ostatniego spotkania'] }
    }
  };
  function localizeFixtures(state) {
    for (const [collection, rows] of Object.entries(seedText)) {
      for (const row of state[collection]) {
        for (const [key, [original, translated]] of Object.entries(rows[row.id] || {})) {
          if (row[key] === original) row[key] = translated;
        }
      }
    }
    for (const c of state.customers.filter(c => seedText.customers[c.id])) {
      for (const contact of c.contacts) {
        if (contact.label === 'Main contact · synthetic') contact.label = 'Kontakt główny · dane fikcyjne';
        if (contact.label === 'Office') contact.label = 'Biuro';
      }
    }
    return state;
  }
  return { errors, errorMessage, country, countryValue, plural, localizeFixtures };
});
