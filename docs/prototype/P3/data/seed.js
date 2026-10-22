/*
 * Eko_CRM prototype P3 — synthetic seed.
 * Invented people, farms and numbers; no real personal data (the brief allows only synthetic
 * data before the GDPR assessment). NIPs get a valid check digit so the form accepts them.
 * The clock is fixed: today at 14:15, so the week board always tells the same story.
 */
import { nipCheckDigit } from "../app/rules.js";

export function makeSeed() {
  const NOW = new Date(); NOW.setHours(14, 15, 0, 0);
  const at = (dayOffset, h, m = 0) => { const d = new Date(NOW); d.setDate(d.getDate() + dayOffset); d.setHours(h, m, 0, 0); return d.toISOString(); };
  const day = (dayOffset) => { const d = new Date(NOW); d.setDate(d.getDate() + dayOffset); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  // Offsets relative to the weekday, so the week always reads Monday to Sunday.
  const dow = (NOW.getDay() + 6) % 7; // 0 = Monday
  const wk = (weekday, weeks = 0) => weekday - dow + 7 * weeks;

  const users = [
    { id: "t1", name: "Tomasz Krawczyk", role: "rep", google: "linked" },
    { id: "t2", name: "Agnieszka Dudek", role: "rep", google: "expired" },
    { id: "t3", name: "Michał Sroka", role: "rep", google: "none" },
    { id: "m1", name: "Beata Wilk", role: "manager", google: "linked" },
  ];

  const nip = (nine) => { let d = nipCheckDigit(nine); if (d === null) { nine = nine.slice(0, 8) + ((Number(nine[8]) + 1) % 10); d = nipCheckDigit(nine); } return nine + d; };
  const ph = (value, who = "", primary = false) => ({ value, who, primary });
  const em = (value, who = "") => ({ value, who });
  let n = 0;
  const cust = (ownerId, name, town, street, postalCode, voivodeship, county, nine, phones, emails, extra = {}) => ({
    id: `c${++n}`, ownerId, name, nip: nine ? nip(nine) : "",
    address: { street, postalCode, town, voivodeship, county, country: "Polska" },
    phones, emails, archived: false, ...extra,
  });

  const customers = [
    cust("t1", "Gospodarstwo Rolne Krystyna i Wiesław Banaś", "Radziejów", "Czołowo 18", "88-200", "kujawsko-pomorskie", "radziejowski", "889204117", [ph("+48602114950", "Wiesław", true), ph("+48542851120", "dom, wieczorem")], [em("banas.czolowo@example.pl", "faktury")]),
    cust("t1", "PHU Agro-Kłos", "Kruszwica", "ul. Kolejowa 7", "88-150", "kujawsko-pomorskie", "inowrocławski", "556901234", [ph("+48523515522", "sklep", true), ph("+48691300211", "Paweł, zamówienia")], [em("zamowienia@agro-klos.example.pl")]),
    cust("t1", "Rolnicza Spółdzielnia Produkcyjna Zorza", "Piotrków Kujawski", "Nowa Wieś 2", "88-230", "kujawsko-pomorskie", "radziejowski", "889330078", [ph("+48542654001", "biuro", true)], [em("rsp.zorza@example.pl", "prezes")]),
    cust("t1", "Marian Gawlik", "Dobre", "Krzywosądz 41", "88-210", "kujawsko-pomorskie", "radziejowski", "", [ph("+48600452217", "", true)], []),
    cust("t1", "Ferma Drobiu Olszewscy", "Mogilno", "Wylatowo 55", "88-300", "kujawsko-pomorskie", "mogileński", "557410839", [ph("+48523180760", "Ewa Olszewska", true)], []),
    cust("t1", "Grupa Producentów Buraka Cukrowego Kujawy", "Brześć Kujawski", "ul. Cukrownicza 3", "87-880", "kujawsko-pomorskie", "włocławski", "888760234", [ph("+48542521099", "sekretariat", true), ph("+48605223301", "agronom")], [em("biuro@gpbc-kujawy.example.pl", "zarząd")]),
    cust("t1", "Sad Dębowski", "Lubraniec", "Dębowo 9", "87-890", "kujawsko-pomorskie", "włocławski", "888921447", [ph("+48515778004", "", true)], [], { archived: true }),
    cust("t2", "Gospodarstwo Rolne Jarosław Pawlak", "Płońsk", "Siedlin 12", "09-100", "mazowieckie", "płoński", "567120994", [ph("+48609551230", "Jarosław", true)], []),
    cust("t2", "Mazowieckie Centrum Hodowli Bydła", "Ciechanów", "ul. Gostkowska 100", "06-400", "mazowieckie", "ciechanowski", "566201338", [ph("+48236725400", "recepcja", true)], [em("biuro@mchb.example.pl")]),
    cust("t2", "Zakład Rolny Sierpc", "Sierpc", "Bledzewo 1", "09-200", "mazowieckie", "sierpecki", "776302210", [ph("+48242752218", "portiernia", true), ph("+48697800145", "kierownik produkcji")], []),
    cust("t2", "Marian Gawlik", "Mława", "Szydłowo 8", "06-500", "mazowieckie", "mławski", "569411020", [ph("+48236543320", "", true)], []),
    cust("t3", "Gospodarstwo Ogrodnicze Pod Lipą", "Łęczyca", "Topola Królewska 14", "99-100", "łódzkie", "łęczycki", "775114203", [ph("+48607332180", "Beata, właścicielka", true)], [em("podlipa@example.pl")]),
    cust("t3", "Kutnowska Spółka Rolna", "Kutno", "ul. Sklęczkowska 20", "99-300", "łódzkie", "kutnowski", "775300921", [ph("+48242534100", "biuro", true)], [em("zakupy@ksr.example.pl", "zakupy")]),
    cust("t3", "Stadnina Koni Borówek", "Łowicz", "Borówek 3", "99-400", "łódzkie", "łowicki", "834200116", [ph("+48468371200", "", true)], []),
    cust("t3", "Krzysztof Maj", "Łęczyca", "Błonie 27", "99-100", "łódzkie", "łęczycki", "", [ph("+48691220430", "", true)], []),
  ];

  let vn = 0;
  const visit = (customerId, ownerId, start, end, extra = {}) => ({ id: `v${++vn}`, customerId, ownerId, start, end, cancelled: false, deletedInGoogle: false, moved: false, unsynced: false, place: "", ...extra });
  const visits = [
    // Tomasz, this week (Monday = wk(0))
    visit("c1", "t1", at(wk(0), 9), at(wk(0), 10)),
    visit("c2", "t1", at(wk(0), 12), at(wk(0), 13), { moved: true }),
    visit("c3", "t1", at(wk(1), 10), at(wk(1), 11, 30)),
    visit("c6", "t1", at(wk(2), 9), at(wk(2), 10), { cancelled: true }),
    visit("c5", "t1", at(wk(2), 14), at(wk(2), 15)),
    visit("c4", "t1", at(wk(3), 8, 30), at(wk(3), 9, 30)),
    visit("c6", "t1", at(wk(3), 11), at(wk(3), 12)),
    visit("c2", "t1", at(wk(3), 15, 30), at(wk(3), 16, 30)),
    visit("c3", "t1", at(wk(4), 10), at(wk(4), 11), { deletedInGoogle: true }),
    visit("c5", "t1", at(wk(4), 13), at(wk(4), 14)),
    visit("c1", "t1", at(wk(0, 1), 9), at(wk(0, 1), 10)),
    visit("c4", "t1", at(wk(2, -1), 10), at(wk(2, -1), 11)),
    // Agnieszka
    visit("c8", "t2", at(wk(0), 10), at(wk(0), 11)),
    visit("c9", "t2", at(wk(1), 11), at(wk(1), 12), { moved: true }),
    visit("c10", "t2", at(wk(3), 10), at(wk(3), 11)),
    visit("c8", "t2", at(wk(3), 16), at(wk(3), 17), { unsynced: true }),
    visit("c11", "t2", at(wk(4), 9), at(wk(4), 10), { unsynced: true }),
    visit("c9", "t2", at(wk(1, -1), 9), at(wk(1, -1), 10), { cancelled: true }),
    // Michał
    visit("c12", "t3", at(wk(0), 9), at(wk(0), 10)),
    visit("c13", "t3", at(wk(2), 10), at(wk(2), 12)),
    visit("c14", "t3", at(wk(3), 9), at(wk(3), 10)),
    visit("c15", "t3", at(wk(3), 17), at(wk(3), 17, 45)),
    visit("c12", "t3", at(wk(5), 9), at(wk(5), 10)),
    visit("c13", "t3", at(wk(1, 1), 10), at(wk(1, 1), 11)),
  ];
  // The story needs some of this week's visits to be past and today's afternoon visit to be
  // ahead. When the demo opens on a Monday or at the weekend, that still holds for the clock.

  const notes = [
    { id: "n1", visitId: "v1", customerId: "c1", authorId: "t1", at: at(wk(0), 10, 5), text: "Pszenica ozima wzeszła równo. Pan Wiesław chce w listopadzie zrobić badanie gleby na całym areale, 48 ha." },
    { id: "n2", visitId: "v2", customerId: "c2", authorId: "t1", at: at(wk(0), 13, 10), text: "Sklep chce ofertę na saletrę amonową na luty: 20 t, z dostawą do magazynu w Kruszwicy. Cena przy odbiorze całego TIR-a." },
    { id: "n3", visitId: "v3", customerId: "c3", authorId: "t1", at: at(wk(1), 11, 40), text: "Spółdzielnia kończy zbiór buraków. Prezes pyta o wapno nawozowe przed orką zimową, 60 ha." },
    { id: "n4", visitId: null, customerId: "c6", authorId: "m1", at: at(wk(1), 16, 40), text: "Klient zgłosił w biurze opóźnienie wrześniowej dostawy. Proszę o kontakt przed następną wizytą." },
    { id: "n5", visitId: "v6", customerId: "c4", authorId: "t1", at: at(wk(3), 9, 35), text: "Pan Gawlik potrzebuje nasion kukurydzy na wiosnę, 12 ha. Pyta też o siewnik, ale to nie nasz zakres." },
    { id: "n6", visitId: "v14", customerId: "c9", authorId: "t2", at: at(wk(1), 12, 15), text: "Centrum chce próbki pasz treściwych dla bydła mlecznego. Decyzja w listopadzie." },
    { id: "n7", visitId: "v20", customerId: "c13", authorId: "t3", at: at(wk(2), 12, 20), text: "Spółka zamawia środek na chwasty w rzepaku ozimym. Termin dostawy do końca października." },
  ];

  const tasks = [
    { id: "a1", noteId: "n2", customerId: "c2", ownerId: "t1", authorId: "t1", text: "Wysłać ofertę na saletrę (20 t, luty)", due: day(-2), status: "progress", log: [] },
    { id: "a2", noteId: "n3", customerId: "c3", ownerId: "t1", authorId: "t1", text: "Sprawdzić dostępność wapna nawozowego", due: day(0), status: "todo", log: [] },
    { id: "a3", noteId: "n4", customerId: "c6", ownerId: "t1", authorId: "m1", text: "Zadzwonić w sprawie opóźnionej dostawy", due: day(-1), status: "todo", log: [] },
    { id: "a4", noteId: "n5", customerId: "c4", ownerId: "t1", authorId: "t1", text: "Przygotować ofertę nasion kukurydzy, 12 ha", due: day(10), status: "todo", log: [] },
    { id: "a5", noteId: "n1", customerId: "c1", ownerId: "t1", authorId: "t1", text: "Umówić pobranie próbek gleby", due: null, status: "done", log: [] },
    { id: "a6", noteId: "n6", customerId: "c9", ownerId: "t2", authorId: "t2", text: "Wysłać próbki pasz treściwych", due: day(-5), status: "todo", log: [] },
    { id: "a7", noteId: "n7", customerId: "c13", ownerId: "t3", authorId: "t3", text: "Potwierdzić dostawę herbicydu", due: day(3), status: "progress", log: [] },
  ];

  return { NOW, users, customers, visits, notes, tasks };
}
