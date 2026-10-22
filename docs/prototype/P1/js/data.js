/*
 * Synthetic seed for the prototype (SEED-1 spirit: test data only, no real personal data).
 * Every name, NIP, phone and address is invented. NIPs are generated with a valid checksum.
 * Dates are relative to a fixed demo clock so the agenda always shows the same story.
 */
(function (global) {
  "use strict";
  const D = global.EkoDomain;

  // Demo clock: today, 11:40 local time.
  const NOW = new Date(); NOW.setHours(11, 40, 0, 0);
  const at = (dayOffset, h, m = 0) => { const d = new Date(NOW); d.setDate(d.getDate() + dayOffset); d.setHours(h, m, 0, 0); return d.toISOString(); };
  const day = (dayOffset) => at(dayOffset, 12).slice(0, 10);

  const users = [
    { id: "u1", name: "Anna Wróbel", role: "rep", google: "linked" },
    { id: "u2", name: "Piotr Nowicki", role: "rep", google: "expired" },
    { id: "u3", name: "Katarzyna Lis", role: "rep", google: "none" },
    { id: "m1", name: "Marek Zając", role: "manager", google: "linked" },
  ];

  let n = 0;
  const nip = (nine) => D.makeNip(nine) || D.makeNip(nine.slice(0, 8) + ((Number(nine[8]) + 1) % 10));
  const c = (ownerId, name, town, street, postalCode, voivodeship, county, nine, phones, emails, extra = {}) => ({
    id: "c" + (++n), ownerId, name, nip: nine ? nip(nine) : "",
    address: { street, postalCode, town, voivodeship, county, country: "Polska" },
    phones, emails, archived: false, ...extra,
  });
  const ph = (value, note, primary = false) => ({ value, note, primary });

  const customers = [
    c("u1", "Gospodarstwo Rolne Tomasz Jędrzejak", "Września", "Słomczyce 14", "62-300", "wielkopolskie", "wrzesiński", "778104512",
      [ph("+48601220341", "Tomasz, właściciel", true), ph("+48612881204", "biuro, rano")], [{ value: "gr.jedrzejak@example.pl", note: "faktury" }]),
    c("u1", "Ferma Drobiu Kołodziej", "Gniezno", "ul. Kłecka 88", "62-200", "wielkopolskie", "gnieźnieński", "784220193",
      [ph("+48693114002", "Ewa Kołodziej", true)], []),
    c("u1", "Agro-Brzozowski sp. j.", "Kościan", "Racot, ul. Główna 3", "64-000", "wielkopolskie", "kościański", "698310227",
      [ph("+48655112090", "sekretariat", true), ph("+48722408118", "Paweł, zakupy nawozów")], [{ value: "zakupy@agro-brzozowski.example.pl", note: "" }]),
    c("u1", "Gospodarstwo Sadownicze Wiśniewscy", "Kalisz", "Dobrzec 52", "62-800", "wielkopolskie", "kaliski", "618440395",
      [ph("+48508771330", "Marta", true)], []),
    c("u1", "Jan Pietrzak", "Pobiedziska", "Kociałkowa Górka 7", "62-010", "wielkopolskie", "poznański", "",
      [ph("+48600918442", "", true)], []),
    c("u1", "Hodowla Bydła Mleczarz", "Leszno", "Gronówko 21", "64-100", "wielkopolskie", "leszczyński", "697902215",
      [ph("+48791002877", "Krzysztof, wieczorem", true)], [{ value: "mleczarz.gronowko@example.pl", note: "" }]),
    c("u1", "Rolnictwo Ekologiczne Zielony Łan", "Września", "Bierzglinek 2", "62-300", "wielkopolskie", "wrzesiński", "789553180",
      [ph("+48664210933", "", true)], [], { archived: true }),
    c("u2", "Gospodarstwo Rolne Adam Szulc", "Inowrocław", "Mątwy 40", "88-100", "kujawsko-pomorskie", "inowrocławski", "556120884",
      [ph("+48605331090", "Adam", true)], []),
    c("u2", "Kujawskie Zboża sp. z o.o.", "Toruń", "ul. Polna 112", "87-100", "kujawsko-pomorskie", "toruński", "879204431",
      [ph("+48566220400", "recepcja", true)], [{ value: "biuro@kujawskiezboza.example.pl", note: "" }]),
    c("u2", "Ferma Trzody Głowacki", "Włocławek", "Smólnik 9", "87-800", "kujawsko-pomorskie", "włocławski", "888410027",
      [ph("+48698441520", "", true)], []),
    c("u3", "Gospodarstwo Rolne Maria Sowa", "Chełm", "Pokrówka 33", "22-100", "lubelskie", "chełmski", "563201176",
      [ph("+48821110455", "Maria", true)], []),
    c("u3", "Lubelska Grupa Producentów Chmielu", "Zamość", "Sitaniec 11", "22-400", "lubelskie", "zamojski", "922118604",
      [ph("+48846330211", "prezes", true), ph("+48605990772", "magazyn")], [{ value: "grupa.chmiel@example.pl", note: "zarząd" }]),
    c("u3", "Jan Pietrzak", "Biała Podlaska", "Sitnik 5", "21-500", "lubelskie", "bialski", "537204418",
      [ph("+48832221009", "", true)], []),
  ];

  let vn = 0;
  const v = (customerId, ownerId, start, end, extra = {}) => ({ id: "v" + (++vn), customerId, ownerId, start, end, cancelled: false, deletedInGoogle: false, moved: false, unsynced: false, place: "", ...extra });

  const visits = [
    // Anna — today
    v("c1", "u1", at(0, 7, 30), at(0, 8, 30)),
    v("c2", "u1", at(0, 9, 30), at(0, 10, 45), { moved: true }),
    v("c3", "u1", at(0, 12, 30), at(0, 13, 30)),
    v("c4", "u1", at(0, 15, 0), at(0, 16, 0), { unsynced: true }),
    // Anna — awaiting decision (deleted in Google yesterday)
    v("c6", "u1", at(-1, 14, 0), at(-1, 15, 0), { deletedInGoogle: true }),
    // Anna — past
    v("c1", "u1", at(-6, 10, 0), at(-6, 11, 0)),
    v("c5", "u1", at(-4, 13, 0), at(-4, 14, 0), { cancelled: true }),
    v("c3", "u1", at(-3, 9, 0), at(-3, 10, 0), { moved: true }),
    v("c7", "u1", at(-12, 9, 0), at(-12, 10, 0)),
    // Anna — upcoming
    v("c5", "u1", at(1, 8, 0), at(1, 9, 0)),
    v("c6", "u1", at(1, 11, 0), at(1, 12, 30), { place: "Pole przy drodze na Rydzynę" }),
    v("c2", "u1", at(3, 10, 0), at(3, 11, 0)),
    // Piotr
    v("c8", "u2", at(0, 9, 0), at(0, 10, 0)),
    v("c9", "u2", at(0, 13, 0), at(0, 14, 30), { unsynced: true }),
    v("c10", "u2", at(-2, 10, 0), at(-2, 11, 0), { moved: true }),
    v("c8", "u2", at(-5, 12, 0), at(-5, 13, 0), { cancelled: true }),
    v("c9", "u2", at(2, 9, 0), at(2, 10, 0)),
    // Katarzyna
    v("c11", "u3", at(0, 8, 0), at(0, 9, 30)),
    v("c12", "u3", at(-1, 10, 0), at(-1, 12, 0)),
    v("c13", "u3", at(-3, 9, 0), at(-3, 10, 0)),
    v("c11", "u3", at(4, 9, 0), at(4, 10, 0)),
  ];

  const notes = [
    { id: "n1", visitId: "v6", customerId: "c1", authorId: "u1", at: at(-6, 11, 5), text: "Pszenica ozima po przezimowaniu w dobrym stanie. Pyta o termin dostawy saletry i cenę przy odbiorze całego TIR-a." },
    { id: "n2", visitId: "v8", customerId: "c3", authorId: "u1", at: at(-3, 10, 10), text: "Przesunięte o tydzień na prośbę klienta. Interesuje ich mikrogranulat startowy pod kukurydzę, ok. 40 ha." },
    { id: "n3", visitId: "v1", customerId: "c1", authorId: "u1", at: at(0, 8, 40), text: "Zamówienie wstępne: 2 t saletry, odbiór w przyszłym tygodniu. Prosi o wizytę agronoma w maju." },
    { id: "n4", visitId: null, customerId: "c1", authorId: "m1", at: at(-2, 16, 0), text: "Klient dzwonił do biura w sprawie reklamacji partii z jesieni. Proszę o kontakt przed kolejną dostawą." },
    { id: "n5", visitId: "v15", customerId: "c10", authorId: "u2", at: at(-2, 11, 10), text: "Rozważa zmianę dostawcy pasz. Wysłać porównanie cen." },
  ];

  const actions = [
    { id: "a1", noteId: "n1", customerId: "c1", ownerId: "u1", authorId: "u1", desc: "Wysłać ofertę na saletrę (TIR)", due: day(-3), status: "inprogress", history: [] },
    { id: "a2", noteId: "n2", customerId: "c3", ownerId: "u1", authorId: "u1", desc: "Sprawdzić dostępność mikrogranulatu", due: day(0), status: "todo", history: [] },
    { id: "a3", noteId: "n3", customerId: "c1", ownerId: "u1", authorId: "u1", desc: "Umówić agronoma na maj", due: day(14), status: "todo", history: [] },
    { id: "a4", noteId: "n4", customerId: "c1", ownerId: "u1", authorId: "m1", desc: "Oddzwonić w sprawie reklamacji", due: day(-1), status: "todo", history: [] },
    { id: "a5", noteId: "n5", customerId: "c10", ownerId: "u2", authorId: "u2", desc: "Porównanie cen pasz dla klienta", due: day(-4), status: "todo", history: [] },
    { id: "a6", noteId: "n2", customerId: "c3", ownerId: "u1", authorId: "u1", desc: "Przygotować próbki", due: null, status: "done", history: [] },
  ];

  global.EkoSeed = { NOW, users, customers, visits, notes, actions };
})(window);
