(function () {
  'use strict';
  const D = window.EkoDomain;
  const L = window.EkoLocale;
  const U = window.EkoUI;
  const { escape: e, icon, badge, button, iconButton, empty, time, date, avatar, field } = U;
  const STORAGE = 'eko-crm-p2-v1';
  let state = L.localizeFixtures(D.copy(window.EkoFixtures));
  let storageAvailable = true;
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE) || 'null');
    if (saved?.version === 1 && ['users', 'customers', 'visits', 'notes', 'actions'].every(k => Array.isArray(saved[k])) && saved.connections) state = L.localizeFixtures(saved);
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
  const personName = id => D.person(state, id)?.name || 'Nieznany użytkownik';
  const cName = id => D.customer(state, id)?.name || 'Klient';
  const ownDecisions = () => state.visits.filter(v => v.owner === persona && D.stateOf(v) === 'decision');
  const days = ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23'];
  const nav = [ ['today', 'sun', 'Mój dzień'], ['customers', 'users', 'Klienci'], ['visits', 'calendar', 'Wizyty'], ['actions', 'task', 'Zadania'], ['team', 'chart', 'Zespół'], ['calendar', 'link', 'Kalendarz Google'] ];
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
      if (errorBox) { errorBox.textContent = L.errorMessage(error.message); errorBox.focus(); }
      else toast(L.errorMessage(error.message));
      return null;
    }
  }
  function heading(title, subtitle, action = '') { return `<div class="page-heading"><div><h1>${e(title)}</h1><p>${e(subtitle)}</p></div>${action}</div>`; }
  function titleForView() { return view === 'components' ? 'Biblioteka UI' : nav.find(n => n[0] === view)?.[2] || 'Mój dzień'; }
  function render() {
    const reminderCount = own(state.actions).filter(a => a.due && a.due <= D.TODAY && !['done', 'cancelled'].includes(a.status)).length;
    document.title = `${titleForView()} · Eko CRM P2`;
    document.querySelector('#app').innerHTML = `
      <aside class="sidebar ${menuOpen ? 'is-open' : ''}" aria-label="Nawigacja główna">
        <button class="icon-button mobile-menu nav-close" data-action="menu" aria-label="Zamknij nawigację">${icon('close')}</button>
        <a class="brand" href="#today"><img src="assets/mark.svg" alt=""><div><strong>eko<span style="font-weight:300">crm</span></strong><small>Bliżej Twoich klientów</small></div></a>
        <p class="nav-caption">Twoje miejsce pracy</p>
        <nav>${nav.filter(n => n[0] !== 'team' || user().role === 'manager').map(([key, glyph, title]) => `<a href="#${key}" class="nav-link ${view === key ? 'active' : ''}" ${view === key ? 'aria-current="page"' : ''}>${icon(glyph)}<span>${title}</span>${key === 'actions' && reminderCount ? `<span class="nav-count">${reminderCount}</span>` : key === 'team' ? '<span class="nav-count">Później</span>' : ''}</a>`).join('')}</nav>
        <div class="sidebar-spacer"></div>
        <div class="field-note">${icon('leaf')}<p>Dobre relacje rosną<br>z każdą rozmową.</p></div>
        <a href="#components" class="nav-link ${view === 'components' ? 'active' : ''}" ${view === 'components' ? 'aria-current="page"' : ''}>${icon('grid')}<span>Biblioteka UI</span></a>
        <div class="profile">${avatar(user().name, 'avatar-person')}<div><strong>${e(user().name)}</strong><small>${user().role === 'manager' ? 'Kierownik zespołu' : 'Handlowiec'}</small></div></div>
      </aside>
      <div class="workspace">
        <header class="topbar"><div class="row gap-small"><button class="icon-button mobile-menu" data-action="menu" aria-label="Otwórz lub zamknij nawigację" aria-expanded="${menuOpen}">${icon('menu')}</button><div class="breadcrumb"><span>Pulpit</span>${icon('chevron')}<strong>${titleForView()}</strong></div></div><div class="top-actions"><button class="search-trigger" data-action="search" aria-label="Znajdź klienta">${icon('search')}<span>Znajdź klienta</span><kbd>/</kbd></button><span class="demo-pill">Prototyp P2</span></div></header>
        <main id="main" tabindex="-1">${globalNotice()}${content()}
          <footer class="demo-footer"><span>Dane fikcyjne · 22 paź 2026, 10:15 · Europe/Warsaw</span><div class="demo-controls"><label for="persona">Użytkownik demo</label><select id="persona" aria-label="Użytkownik demo">${state.users.map(p => `<option value="${p.id}" ${p.id === persona ? 'selected' : ''}>${e(p.name)} · ${p.role === 'manager' ? 'Kierownik' : 'Handlowiec'}</option>`).join('')}</select><button class="text-link" data-action="reset">Przywróć demo</button></div></footer>
          ${!storageAvailable ? '<p class="spec">Pamięć przeglądarki jest niedostępna. Zmiany będą dostępne tylko na otwartej stronie.</p>' : ''}
        </main>
      </div>`;
  }
  function globalNotice() {
    let html = '';
    const decisions = ownDecisions();
    if (decisions.length) html += `<div class="notice">${icon('warning')}<p><strong>${decisions.length === 1 ? 'Wizyta wymaga Twojej decyzji' : `Wizyty wymagające decyzji: ${decisions.length}`}</strong>Usunięto wizytę w Kalendarzu Google: ${e(cName(decisions[0].customerId))}.</p>${button('Sprawdź wizytę', 'visit-detail', decisions[0].id)}</div>`;
    if (state.connections[persona] !== 'connected') html += `<div class="notice">${icon('link')}<p><strong>Połącz ponownie Kalendarz Google</strong>Twoje wizyty są bezpieczne. Zmiany zsynchronizują się po ponownym połączeniu.</p>${button('Połącz ponownie (demo)', 'reconnect')}</div>`;
    return html;
  }
  function content() {
    return ({ today: todayView, customers: customersView, visits: visitsView, actions: actionsView, team: teamView, calendar: calendarView, components: componentsView }[view] || todayView)();
  }
  function dateStrip() {
    return `<div class="week-strip" aria-label="Wybierz dzień">${days.map(d => { const count = visits().filter(v => D.dayOf(v.start) === d).length; return `<button class="day-button ${selectedDay === d ? 'selected' : ''}" data-action="day" data-id="${d}" aria-pressed="${selectedDay === d}" aria-label="${date(d, { weekday: 'long' })}, ${L.plural(count, 'wizyta', 'wizyty', 'wizyt')}"><span>${date(d, { weekday: 'short' }).split(',')[0].split(' ')[0]} <strong>${d.slice(8)}</strong></span><span class="day-dots" aria-hidden="true">${Array(Math.min(count, 4)).fill('<span class="day-dot"></span>').join('')}</span></button>`; }).join('')}</div>`;
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
    return `${heading(selectedDay === D.TODAY ? 'Twój dzień w terenie.' : date(selectedDay, { weekday: 'long' }), selectedDay === D.TODAY ? 'Czwartek, 22 października. Dobry plan to lepsze rozmowy.' : 'Wizyty i zadania w jednym miejscu.', button('Zaplanuj wizytę', 'new-visit', '', 'primary', 'plus'))}
      ${dateStrip()}<div class="dashboard-grid"><section><div class="section-heading"><h2>${selectedDay === D.TODAY ? 'Dzisiejsze wizyty' : 'Wizyty'}<span class="count">${dayVisits.length}</span></h2><span class="muted" style="font-size:12px">Odbyte: ${held} · Przed Tobą: ${dayVisits.filter(v => D.stateOf(v) === 'planned').length}</span></div>
      ${upcoming ? `<article class="next-visit"><div class="next-label">${icon('sun')} Najbliższa wizyta<span>${Math.round((Date.parse(upcoming.end) - Date.parse(upcoming.start)) / 60000)} min</span></div><h3>${e(c.name)}</h3><p>${e(upcoming.purpose || 'Wizyta u klienta')}</p><div class="next-time">${icon('clock')}${time(upcoming.start)} <span style="opacity:.5">—</span> ${time(upcoming.end)}</div><div class="address">${icon('pin')}${e(c.street)}, ${e(c.town)}</div><div class="next-footer">${button('Otwórz wizytę', 'visit-detail', upcoming.id, 'leaf', 'arrow')}${button('Karta klienta', 'customer', c.id, 'ghost')}</div></article>` : ''}
      ${list.length ? `<div class="agenda">${list.map(agendaRow).join('')}</div>` : !upcoming ? `<div class="panel">${empty('Czas na rozmowę', 'W tym dniu nie ma wizyt. Zaplanuj spotkanie z jednym ze swoich klientów.', button('Zaplanuj wizytę', 'new-visit', '', 'primary', 'plus'))}</div>` : ''}
      <div class="row between" style="margin-top:16px"><span class="eyeline">${icon('info')} Po zakończeniu wizyty status zmienia się automatycznie na „Odbyta”.</span><a class="text-link" style="font-size:12px" href="#visits">Pokaż tydzień</a></div></section>
      <aside class="dashboard-aside"><section class="panel"><div class="section-heading"><h2>Sprawy do załatwienia</h2>${icon('task')}</div><p class="muted" style="font-size:12px">Kolejne kroki po spotkaniu.</p><div class="task-list">${pending.length ? pending.slice(0, 3).map(taskRow).join('') : empty('Wszystko na bieżąco', 'Dodaj zadanie do notatki z wizyty.')}</div><div class="panel-footer"><a href="#actions" class="text-link" style="font-size:12px">Wszystkie zadania</a><span class="muted" style="font-size:11px">Otwarte: ${pending.length}</span></div></section>
      ${syncCard()}<div class="gentle-note">${icon('note')}<p><strong>Notatka dziś. Lepsza wizyta jutro.</strong>Zapisz ustalenia, póki dobrze je pamiętasz. Dodaj zadanie bezpośrednio z notatki z wizyty.</p></div></aside></div>`;
  }
  function taskRow(a) {
    return `<div class="task-item"><button class="task-check" data-action="complete-action" data-id="${e(a.id)}" aria-label="Oznacz jako wykonane: ${e(a.title)}">${icon('check')}</button><div class="task-content"><strong>${e(a.title)}</strong><button class="text-link" data-action="customer" data-id="${e(a.customerId)}">${e(cName(a.customerId))}</button><div class="task-due ${D.overdue(a) ? 'late' : ''}">${icon('clock')}${dueLabel(a)}</div>${actionAttribution(a)}</div></div>`;
  }
  function actionAttribution(a) {
    return `${D.person(state, a.author)?.role === 'manager' ? `<div class="attribution">Autor: ${e(personName(a.author))} · Kierownik</div>` : ''}${D.person(state, a.changedBy)?.role === 'manager' ? `<div class="attribution">Status zmieniony przez: ${e(personName(a.changedBy))} · Kierownik</div>` : ''}`;
  }
  function dueLabel(a) { return !a.due ? 'Bez terminu' : D.overdue(a) ? `${date(a.due)} · po terminie` : a.due === D.TODAY ? 'Termin: dzisiaj' : `Termin: ${date(a.due)}`; }
  function syncCard() {
    const connected = state.connections[persona] === 'connected';
    const pending = state.visits.filter(v => v.owner === persona && v.unsynced).length;
    return `<section class="panel"><div class="row"><span class="sync-icon">${icon('calendar')}</span><div><h3 style="font-size:14px">Kalendarz Google</h3><span class="sync-status"><span class="status-dot"></span>${connected ? 'Połączono' : 'Wymagane ponowne połączenie'}</span></div></div><p class="sync-meta">${pending ? `Zmiany oczekujące na synchronizację: ${pending}.` : 'Twoje wizyty są aktualne.'}<br>Synchronizujemy tylko wizyty utworzone w Eko CRM.</p><div class="panel-footer"><a href="#calendar" class="text-link" style="font-size:12px">Zarządzaj połączeniem</a>${icon('arrow')}</div></section>`;
  }
  function customersView() {
    return `${heading('Relacje zaczynają się od ludzi.', `Aktywni klienci: ${customers().filter(c => !c.archived).length}. Każda relacja ma swoje miejsce.`, button('Dodaj klienta', 'new-customer', '', 'primary', 'plus'))}
      <div class="toolbar"><label class="search-field">${icon('search')}<span class="sr-only">Szukaj klientów</span><input id="customer-search" value="${e(query)}" placeholder="Szukaj nazwy, miejscowości lub kontaktu…"></label><div class="segments" aria-label="Status klienta">${['active', 'archived'].map(s => `<button data-action="customer-filter" data-id="${s}" class="${customerFilter === s ? 'active' : ''}" aria-pressed="${customerFilter === s}">${s === 'active' ? 'Aktywni' : 'Archiwum'}</button>`).join('')}</div>${user().role === 'manager' ? ownerSelect() : ''}</div><div id="customer-results">${customerResults()}</div>`;
  }
  function ownerSelect() { return `<label><span class="sr-only">Opiekun klienta</span><select id="owner-filter"><option value="all">Wszyscy handlowcy</option>${state.users.map(p => `<option value="${p.id}" ${ownerFilter === p.id ? 'selected' : ''}>${e(p.name)}</option>`).join('')}</select></label>`; }
  function customerResults() {
    const q = query.trim().toLocaleLowerCase();
    const rows = customers().filter(c => c.archived === (customerFilter === 'archived') && (ownerFilter === 'all' || c.owner === ownerFilter) && [c.name, c.town, ...c.contacts.map(p => p.value)].some(v => v.toLocaleLowerCase().includes(q)));
    if (!rows.length) return `<div class="panel">${empty('Nie znaleziono klientów', query ? 'Wpisz inną nazwę, miejscowość lub dane kontaktowe.' : 'Dodaj klienta lub zmień filtr statusu.', button('Dodaj klienta', 'new-customer', '', 'primary', 'plus'))}</div>`;
    return `<div class="table-wrap" tabindex="0" role="region" aria-label="Lista klientów"><table><thead><tr><th>Klient</th><th>Lokalizacja</th><th>Następna wizyta</th><th>${user().role === 'manager' ? 'Opiekun' : 'Otwarte zadania'}</th><th><span class="sr-only">Otwórz kartę klienta</span></th></tr></thead><tbody>${rows.map(c => {
      const v = state.visits.filter(v => v.customerId === c.id && D.canRead(v, user()) && D.stateOf(v) === 'planned').sort((a, b) => a.start.localeCompare(b.start))[0];
      const count = own(state.actions).filter(a => a.customerId === c.id && ['todo', 'progress'].includes(a.status)).length;
      return `<tr><td><button class="text-link customer-name" data-action="customer" data-id="${e(c.id)}">${avatar(c.name)}<span><strong>${e(c.name)}</strong><small>${e((c.contacts.find(p => p.primary) || c.contacts[0])?.value || 'Brak kontaktu')}</small></span></button></td><td>${e(c.town || 'Nie podano')}<small>${e(L.country(c.country))}</small></td><td>${v ? `${date(v.start)}<small>${time(v.start)} ${v.moved ? '· Przełożona' : ''}</small>` : '<span class="muted">Nie zaplanowano</span>'}</td><td>${user().role === 'manager' ? e(personName(c.owner)) : `<span class="count" style="margin:0">${count}</span>`}</td><td>${iconButton(`Otwórz: ${c.name}`, 'customer', c.id, 'chevron')}</td></tr>`;
    }).join('')}</tbody></table></div><div class="table-foot"><span>Liczba klientów: ${rows.length}${query ? ' pasujących do wyszukiwania' : ''}</span><span>${user().role === 'manager' ? 'Rejestr klientów zespołu' : 'Widoczni są tylko Twoi klienci'}</span></div>`;
  }
  function visitsView() {
    const rows = visits();
    return `${heading('Zaplanuj dobre spotkania.', 'Planuj wizyty, zmieniaj terminy i dbaj o kontakt.', button('Zaplanuj wizytę', 'new-visit', '', 'primary', 'plus'))}<div class="toolbar between"><div class="row">${icon('calendar')}<strong>19–23 października 2026</strong><span class="muted" style="font-size:12px">Europe/Warsaw</span></div><div class="segments">${['week', 'list'].map(layout => `<button data-action="visit-layout" data-id="${layout}" class="${visitLayout === layout ? 'active' : ''}" aria-pressed="${visitLayout === layout}">${layout === 'week' ? 'Tydzień' : 'Wszystkie wizyty'}</button>`).join('')}</div></div>
      ${visitLayout === 'week' ? `<div class="board-scroll" tabindex="0" role="region" aria-label="Wizyty w tygodniu"><div class="week-board">${days.map(d => { const vs = rows.filter(v => D.dayOf(v.start) === d); return `<section class="week-column ${d === D.TODAY ? 'today' : ''}"><h3>${date(d, { weekday: 'short' })}${d === D.TODAY ? '<small class="muted" style="display:block;margin-top:6px">Dzisiaj</small>' : ''}</h3>${vs.length ? vs.map(v => `<button class="week-event is-${D.stateOf(v)}" data-action="visit-detail" data-id="${e(v.id)}"><span>${time(v.start)}–${time(v.end)}</span><strong>${e(cName(v.customerId))}</strong><small>${e(v.purpose || 'Wizyta u klienta')}</small>${visitFlags(v)}</button>`).join('') : '<p class="muted" style="font-size:12px;text-align:center">Brak wizyt</p>'}</section>`; }).join('')}</div></div>` : rows.length ? rows.reduce((html, v, i) => { const day = D.dayOf(v.start); return html + (i === 0 || D.dayOf(rows[i-1].start) !== day ? `${i ? '</div>' : ''}<h2 style="margin-top:24px">${date(day, { weekday: 'long' })}</h2><div class="agenda">` : '') + agendaRow(v) + (i === rows.length - 1 ? '</div>' : ''); }, '') : empty('Twój kalendarz jest pusty', 'Zaplanuj pierwszą wizytę u klienta.')}
      <p class="spec">Zmiana początku wizyty dodaje znacznik „Przełożona”. Status „Odbyta” jest automatyczny. Wizyty cykliczne pojawią się później.</p>`;
  }
  function actionCard(a) {
    const available = D.transitions[a.status].filter(s => a.owner === persona || user().role !== 'manager' || ['done', 'cancelled'].includes(s));
    return `<article class="action-card"><h3>${e(a.title)}</h3><button class="text-link" style="font-size:12px" data-action="customer" data-id="${e(a.customerId)}">${e(cName(a.customerId))}</button><div class="task-due ${D.overdue(a) ? 'late' : ''}">${icon('clock')}${dueLabel(a)}</div>${D.person(state, a.author)?.role === 'manager' ? `<div class="attribution">Autor: ${e(personName(a.author))} · Kierownik</div>` : ''}${D.person(state, a.changedBy)?.role === 'manager' ? `<div class="attribution">Status zmieniony przez: ${e(personName(a.changedBy))} · Kierownik</div>` : ''}<label><span class="sr-only">Status zadania: ${e(a.title)}</span><select data-action-status="${e(a.id)}"><option value="${a.status}">${U.actionLabel(a.status)}</option>${available.map(s => `<option value="${s}">${U.actionLabel(s)}</option>`).join('')}</select></label><button class="text-link" style="font-size:11px;margin-top:12px" data-action="source-note" data-id="${e(a.noteId)}">Otwórz notatkę źródłową</button></article>`;
  }
  function actionsView() {
    let rows = own(state.actions);
    if (actionFilter === 'due') rows = rows.filter(a => a.due && a.due <= D.TODAY && ['todo', 'progress'].includes(a.status));
    return `${heading('Zadbaj o ciąg dalszy rozmowy.', 'Kolejne kroki powiązane z notatkami ze spotkań.')}
      <div class="toolbar between"><div class="segments">${[['open', 'Wszystkie zadania'], ['due', 'Na dziś i zaległe']].map(([key, label]) => `<button class="${actionFilter === key ? 'active' : ''}" data-action="action-filter" data-id="${key}" aria-pressed="${actionFilter === key}">${label}</button>`).join('')}</div><span class="muted" style="font-size:12px">Dodawaj zadania z notatki z wizyty lub karty klienta.</span></div>
      <div class="action-board">${[['todo', 'Do zrobienia'], ['progress', 'W toku'], ['closed', 'Zamknięte']].map(([key, title]) => { const list = rows.filter(a => key === 'closed' ? ['done', 'cancelled'].includes(a.status) : a.status === key); return `<section class="action-column"><h2>${title}<span class="count">${list.length}</span></h2>${list.length ? list.map(actionCard).join('') : empty(key === 'todo' ? 'Brak zadań do wykonania' : key === 'progress' ? 'Możesz zaczynać' : 'Brak zamkniętych zadań', key === 'progress' ? 'Przenieś tutaj zadanie, gdy zaczniesz je realizować.' : 'Zadania pojawią się tutaj po zmianie statusu.')}</section>`; }).join('')}</div>`;
  }
  function teamView() {
    if (user().role !== 'manager') return empty('Widok kierownika', 'Wybierz kierownika jako użytkownika demo, aby zobaczyć podsumowanie zespołu.');
    const rows = ownerFilter === 'all' ? state.visits : state.visits.filter(v => v.owner === ownerFilter);
    const m = D.metrics(rows, periodFrom, periodTo);
    return `${heading('Zespół pod dobrą opieką.', 'Podsumowanie wizyt bez ręcznego raportowania.')}<div class="notice notice-info">${icon('info')}<p><strong>Podgląd kolejnego etapu</strong>Panel zespołu powstanie po MVP. Te statystyki korzystają z danych prototypu.</p></div>
      <div class="toolbar">${ownerSelect()}<label class="row gap-small">Od <input type="date" id="period-from" value="${periodFrom}"></label><label class="row gap-small">Do <input type="date" id="period-to" value="${periodTo}"></label>${button('Ten tydzień', 'this-week')}</div>
      <div class="metrics">${[['planned', 'Zaplanowane', 'Obejmuje wizyty odbyte'], ['held', 'Odbyte', 'Termin zakończenia minął'], ['moved', 'Przełożone', 'Liczone raz dla każdej wizyty'], ['cancelled', 'Odwołane', 'Wizyty jawnie odwołane']].map(([key, label, detail]) => `<div class="metric"><span>${label}</span><strong>${m[key]}</strong><small>${detail}</small></div>`).join('')}</div>
      <div class="table-wrap"><table><thead><tr><th>Handlowiec</th><th>Zaplanowane</th><th>Odbyte</th><th>Przełożone</th><th>Odwołane</th><th>Odbyte / zaplanowane</th></tr></thead><tbody>${state.users.filter(u => ownerFilter === 'all' || u.id === ownerFilter).map(p => { const a = D.metrics(state.visits.filter(v => v.owner === p.id), periodFrom, periodTo); return `<tr><td><div class="row">${avatar(p.name, 'avatar-person')}<strong>${e(p.name)}</strong></div></td><td>${a.planned}</td><td>${a.held}</td><td>${a.moved}</td><td>${a.cancelled}</td><td><div class="bar" role="img" aria-label="Odbyte wizyty: ${a.held} z ${a.planned}"><span style="width:${a.planned ? a.held / a.planned * 100 : 0}%"></span></div></td></tr>`; }).join('')}</tbody></table></div><p class="spec">Wizyty oczekujące na decyzję: ${m.decision} (liczone osobno). Zakres obejmuje oba wskazane dni w strefie Europe/Warsaw. Wcześniejsze wizyty pozostają przypisane pierwotnemu opiekunowi.</p>`;
  }
  function calendarView() {
    const connected = state.connections[persona] === 'connected';
    const pending = state.visits.filter(v => v.owner === persona && v.unsynced);
    return `${heading('Jeden kalendarz. Wszystko pod kontrolą.', 'Wizyty u klientów obok pozostałych planów na dzień.')}<div class="settings-grid"><div><section class="panel"><div class="row"><span class="sync-icon">${icon('calendar')}</span><div><h2 style="margin-bottom:3px">Kalendarz Google</h2><span class="sync-status">${connected ? 'Połączono w demo' : 'Połączenie wygasło w demo'}</span></div></div><p style="margin-top:20px">Prywatne konto Google · kalendarz główny<br>Ten podgląd symuluje połączenie. Nie łączy się z Google.</p><div class="setting-line"><div><strong>Wizyty utworzone w Eko CRM</strong><small class="muted">Data, godzina i usunięcie synchronizują się w obie strony.</small></div>${icon('check')}</div><div class="setting-line"><div><strong>Pozostałe wydarzenia w kalendarzu</strong><small class="muted">Pozostają prywatne. Nie są importowane ani zmieniane.</small></div>${icon('check')}</div><div class="setting-line"><div><strong>Bez zaproszeń dla klientów</strong><small class="muted">Klient nie jest dodawany jako uczestnik wydarzenia.</small></div>${icon('check')}</div>${button(connected ? 'Rozłącz (demo)' : 'Połącz ponownie (demo)', connected ? 'disconnect' : 'reconnect', '', connected ? 'secondary' : 'primary', 'link')}</section><section class="panel"><h2>Oczekuje na synchronizację <span class="count">${pending.length}</span></h2>${pending.length ? pending.map(v => `<div class="setting-line"><div><strong>${e(cName(v.customerId))}</strong><small class="muted">${date(v.start)} o ${time(v.start)}</small></div>${badge('unsynced')}</div>`).join('') : '<p>Brak oczekujących zmian.</p>'}${connected && pending.length ? button('Ponów synchronizację (demo)', 'reconnect', '', 'primary', 'refresh') : ''}</section></div><section class="panel"><h2>Sprawdź scenariusze synchronizacji</h2><p>Te przyciski zmieniają lokalne dane demo, aby pokazać obsługę problemów z synchronizacją.</p><div class="setting-line"><div><strong>Dostęp do kalendarza wygasa</strong><p>Wizyty zachowują status. Pojawia się prośba o ponowne połączenie.</p>${button('Symuluj wygaśnięcie dostępu', 'disconnect')}</div></div><div class="setting-line"><div><strong>Wizyta zostaje usunięta w Google</strong><p>Opiekun wizyty musi wybrać nowy termin lub ją odwołać. Żadna wizyta nie znika bez decyzji.</p><label class="field"><span>Wybierz swoją wizytę</span><select id="delete-demo-visit">${state.visits.filter(v => v.owner === persona && D.stateOf(v) !== 'cancelled').map(v => `<option value="${e(v.id)}">${e(cName(v.customerId))} · ${date(v.start)}</option>`).join('')}</select></label>${button('Symuluj usunięcie', 'simulate-delete')}</div></div></section></div>`;
  }
  function componentsView() {
    return `${heading('Z czego powstaje interfejs.', 'Komponenty, tokeny i stany używane w prototypie.')}
      <div class="catalogue-grid"><section class="panel"><h2>Paleta inspirowana naturą</h2><div class="swatches">${[['Las', '#244b3b'], ['Młody liść', '#d8e8b3'], ['Mgła', '#f3f6f3'], ['Papier', '#ffffff'], ['Atrament', '#253b35'], ['Żniwa', '#a36518']].map(([label, color]) => `<div class="swatch"><i style="background:${color}"></i><strong>${label}</strong><br>${color}</div>`).join('')}</div><p class="spec">styles/tokens.css · semantyczne zmienne kolorów i układu</p></section>
      <section class="panel"><h2>Typografia z zadaniem</h2><h1 style="margin:16px 0">Bliżej Twoich klientów.</h1><h3>Zadbaj o kontekst kolejnej rozmowy.</h3><p class="muted">Nagłówki: Bahnschrift. Tekst: Segoe UI. Zastępcze fonty systemowe pozwalają uruchomić demo bez pobierania zasobów.</p><p class="spec">32 / 28 / 20 / 16 / 14 / 12px · nagłówki wyrównane do lewej</p></section>
      <section class="panel"><h2>Działania i hierarchia</h2><div class="row wrap">${button('Zaplanuj wizytę', 'new-visit', '', 'primary', 'plus')}${button('Dodaj klienta', 'new-customer', '', 'secondary', 'users')}${button('Pokaż komunikat', 'sample-toast', '', 'ghost') }<button class="button" disabled>Niedostępne</button></div><p class="spec">Button · IconButton · widoczny fokus klawiatury · natywny stan nieaktywny</p></section>
      <section class="panel"><h2>Stan to nie tylko kolor</h2><div class="row wrap">${['planned', 'held', 'decision', 'cancelled', 'moved', 'unsynced', 'todo', 'progress', 'done'].map(s => badge(s)).join('')}</div><p class="spec">StatusBadge · przełożenie i brak synchronizacji to znaczniki, nie statusy</p></section>
      <section class="panel"><h2>Czytelne formularze</h2>${field('Nazwa klienta', 'sample-name', '', 'text', 'placeholder="Np. Gospodarstwo Pod Wierzbą"') }<div class="form-error">Podaj polski kod pocztowy w formacie 00-000.</div><p class="spec">Field · powiązane etykiety · błędy przy formularzu · etykiety niezależne od tekstu zastępczego</p></section>
      <section class="panel"><h2>Pomocny pusty widok</h2>${empty('Czas na rozmowę', 'Nie ma zaplanowanych wizyt. Wybierz klienta, z którym chcesz się spotkać.', button('Zaplanuj wizytę', 'new-visit', '', 'primary', 'plus'))}</section>
      <section class="panel"><h2>Zestaw ikon</h2><div class="row wrap">${['sun', 'users', 'calendar', 'task', 'chart', 'pin', 'note', 'leaf', 'warning', 'refresh', 'archive', 'phone'].map(i => `<span title="${U.iconLabels[i]}" style="padding:10px">${icon(i)}</span>`).join('')}</div><p class="spec">Autorskie ikony SVG · viewBox 24px · linia 1,6px · ikony dekoracyjne ukryte przed czytnikami ekranu</p></section>
      <section class="panel"><h2>Materiały do wdrożenia</h2><p class="muted">Demo i biblioteka korzystają z tych samych komponentów i reguł. Dokumentacja techniczna opisuje kontrakty, scenariusze i pokrycie wymagań.</p><div class="row wrap"><a href="HANDOFF.md" class="button">Dokumentacja wdrożenia (EN)</a><a href="REQUIREMENTS.md" class="button">Mapa wymagań (EN)</a></div><p class="spec">src/components.js · src/domain.js · src/contracts.d.ts</p></section></div>`;
  }
  function openModal(title, subtitle, body, footer = '', form = '') {
    modal.innerHTML = `<div class="dialog-header"><div><h2 id="dialog-title">${e(title)}</h2><p>${e(subtitle)}</p></div>${iconButton('Zamknij okno', 'close-modal', '', 'close')}</div>${form ? `<form id="${form}">` : ''}<div class="dialog-body"><div class="form-error" role="alert" tabindex="-1"></div>${body}</div>${footer ? `<div class="dialog-footer">${footer}</div>` : ''}${form ? '</form>' : ''}`;
    if (!modal.open) modal.showModal();
  }
  function saveFooter(label) { return `${button('Anuluj', 'close-modal')}<button class="button button-primary" type="submit">${e(label)}</button>`; }
  function showVisit(visitId) {
    const v = state.visits.find(v => v.id === visitId);
    if (!D.canRead(v, user())) return toast('Ta wizyta nie jest dostępna.');
    const c = D.customer(state, v.customerId);
    const status = D.stateOf(v);
    const editable = v.owner === persona;
    const notes = state.notes.filter(n => n.visitId === v.id);
    openModal(c.name, `${date(v.start, { weekday: 'long' })} · ${time(v.start)}–${time(v.end)}`, `
      ${visitFlags(v)}
      ${status === 'decision' ? '<div class="notice" style="margin-top:18px"><p><strong>Usunięto z Kalendarza Google</strong>Wybierz nowy termin lub odwołaj wizytę. Zamknięcie tego okna nie usuwa przypomnienia.</p></div>' : ''}
      <dl class="detail-grid"><div><dt>Cel wizyty</dt><dd>${e(v.purpose || 'Wizyta u klienta')}</dd></div><div><dt>Opiekun wizyty</dt><dd>${e(personName(v.owner))}</dd></div><div><dt>Adres spotkania</dt><dd>${e(v.location || `${c.street}, ${c.town}`)}</dd></div><div><dt>Kontakt główny</dt><dd>${e((c.contacts.find(p => p.primary) || c.contacts[0])?.value || 'Nie podano')}</dd></div></dl>
      <div class="row wrap">${button('Karta klienta', 'customer', c.id, 'secondary', 'users')}${button('Dodaj notatkę', 'visit-note', v.id, 'secondary', 'note')}</div>
      ${notes.length ? `<h3 style="margin-top:24px">Notatki z wizyty</h3>${notes.map(noteCard).join('')}` : '<p class="spec">Nie ma jeszcze notatek. Zapisz ustalenia i dodaj zadanie.</p>'}
      ${!editable ? '<p class="spec">Tylko opiekun wizyty może zmienić jej termin lub ją odwołać.</p>' : ''}`,
      editable && status !== 'cancelled' ? `${button(status === 'held' ? 'Wizyta nie odbyła się' : 'Odwołaj wizytę', 'cancel-visit', v.id, 'danger')}${status !== 'held' ? button(status === 'decision' ? 'Wybierz nowy termin' : 'Przełóż wizytę', 'move-visit', v.id, 'primary', 'calendar') : button('Dodaj notatkę', 'visit-note', v.id, 'primary', 'note')}` : button('Zamknij', 'close-modal'));
  }
  function visitForm(visitId = '', customerId = '') {
    const v = state.visits.find(v => v.id === visitId);
    const eligible = state.customers.filter(c => c.owner === persona && !c.archived);
    if (!eligible.length) return openModal('Zacznij od klienta', 'Możesz planować wizyty u swoich aktywnych klientów.', empty('Brak aktywnych klientów', 'Dodaj klienta lub wybierz handlowca jako użytkownika demo.'), button('Dodaj klienta', 'new-customer', '', 'primary'));
    const start = v ? D.localParts(v.start) : `${selectedDay >= D.TODAY ? selectedDay : D.TODAY}T16:00`;
    const end = v ? D.localParts(v.end) : `${selectedDay >= D.TODAY ? selectedDay : D.TODAY}T17:00`;
    openModal(v ? 'Przełóż wizytę' : 'Zaplanuj wizytę', 'Wszystkie godziny podano w strefie Europe/Warsaw.', `<input type="hidden" name="id" value="${e(visitId)}"><label class="field"><span>Klient *</span><select name="customerId" required ${v ? 'disabled' : ''}>${eligible.map(c => `<option value="${e(c.id)}" ${c.id === (v?.customerId || customerId) ? 'selected' : ''}>${e(c.name)} · ${e(c.town)}</option>`).join('')}</select></label><div class="form-grid">${field('Początek *', 'start', start, 'datetime-local', 'required')}${field('Koniec *', 'end', end, 'datetime-local', 'required')}</div>${field('Cel wizyty', 'purpose', v?.purpose || '', 'text', 'maxlength="160" placeholder="Co chcesz omówić?"')}${field('Inny adres spotkania', 'location', v?.location || '', 'text', 'maxlength="200" placeholder="Pozostaw puste, aby użyć adresu klienta"')}<p class="spec">${v ? 'Zmiana początku wizyty dodaje znacznik „Przełożona”. Zmiana samego czasu trwania lub adresu nie dodaje tego znacznika.' : 'Wizyta zostanie zapisana także bez dostępu do Kalendarza Google. Klient nie otrzyma zaproszenia.'}</p>`, saveFooter(v ? 'Zapisz nowy termin' : 'Zaplanuj wizytę'), 'visit-form');
  }
  function noteCard(n) {
    const manager = D.person(state, n.author)?.role === 'manager';
    return `<article class="note-card"><div class="row between"><strong style="font-size:12px">${e(personName(n.author))} ${manager ? '<span class="manager-label">Kierownik</span>' : ''}</strong>${n.author === persona ? iconButton('Edytuj swoją notatkę', 'edit-note', n.id, 'edit') : ''}</div><small>${date(n.created)} · ${time(n.created)}${n.visitId ? ' · Notatka z wizyty' : ' · Notatka o kliencie'}</small><p>${e(n.body)}</p>${state.actions.filter(a => a.noteId === n.id && D.canRead(a, user())).map(a => `<div style="padding-top:10px;border-top:1px solid var(--color-line)"><div class="row between"><span style="font-size:12px">${e(a.title)}</span>${badge(a.status, U.actionLabel(a.status))}</div>${actionAttribution(a)}</div>`).join('')}</article>`;
  }
  function showCustomer(customerId, tab = 'overview') {
    const c = D.customer(state, customerId);
    if (!D.canRead(c, user())) { sheet.close(); openCustomer = null; return toast('Ten klient nie jest dostępny w tym widoku.'); }
    modal.close(); openCustomer = c.id; customerTab = tab;
    const vs = own(state.visits).filter(v => v.customerId === c.id).sort((a, b) => b.start.localeCompare(a.start));
    const notes = state.notes.filter(n => n.customerId === c.id).slice().reverse();
    sheet.innerHTML = `<div class="dialog-header"><div><h2 id="sheet-title">Karta klienta</h2><p>${c.archived ? 'Klient zarchiwizowany' : 'Klient aktywny'}</p></div>${iconButton('Zamknij kartę klienta', 'close-sheet', '', 'close')}</div><div class="dialog-body"><div class="record-heading">${avatar(c.name)}<div><h3>${e(c.name)}</h3><p>${e(c.town)}, ${e(L.country(c.country))}</p></div></div><div class="row wrap">${button('Edytuj dane', 'edit-customer', c.id, 'secondary', 'edit')}${!c.archived && c.owner === persona ? button('Zaplanuj wizytę', 'customer-visit', c.id, 'primary', 'plus') : ''}${user().role === 'manager' ? button('Zmień opiekuna', 'reassign', c.id) : ''}</div>
      <div class="record-tabs" aria-label="Sekcje karty klienta">${[['overview', 'Podsumowanie'], ['visits', `Wizyty (${vs.length})`], ['notes', `Notatki (${notes.length})`]].map(([key, label]) => `<button data-action="customer-tab" data-id="${key}" class="${tab === key ? 'active' : ''}" aria-pressed="${tab === key}">${label}</button>`).join('')}</div>
      ${tab === 'overview' ? `<dl class="detail-grid"><div><dt>Adres</dt><dd>${e(c.street || 'Nie podano')}<br>${e(c.postcode)} ${e(c.town)}</dd></div><div><dt>Opiekun</dt><dd>${e(personName(c.owner))}</dd></div><div><dt>NIP / identyfikator podatkowy</dt><dd>${e(c.nip || 'Nie podano')}</dd></div><div><dt>Kraj</dt><dd>${e(L.country(c.country))}</dd></div></dl><h3>Kontakty</h3>${c.contacts.length ? c.contacts.map(p => `<div class="setting-line"><div class="row">${icon(p.kind === 'phone' ? 'phone' : 'mail')}<div><strong>${e(p.value)}</strong><small class="muted">${e(p.label || (p.kind === 'phone' ? 'Telefon' : 'E-mail'))}${p.primary ? ' · Główny' : ''}</small></div></div></div>`).join('') : '<p class="muted">Nie dodano danych kontaktowych.</p>'}<h3 style="margin-top:24px">Ostatnia rozmowa</h3>${notes[0] ? noteCard(notes[0]) : empty('Zacznij rozmowę', 'Dodaj pierwszą notatkę do wizyty.')}${!c.archived ? button('Archiwizuj klienta', 'archive', c.id, 'danger', 'archive') : button('Przywróć klienta', 'restore', c.id, 'primary', 'refresh')}` : tab === 'visits' ? (vs.length ? `<div class="agenda">${vs.map(agendaRow).join('')}</div>` : empty('Nie ma jeszcze wizyt', 'Zaplanuj wizytę, aby rozpocząć historię kontaktów z klientem.')) : `<div class="row between"><p class="muted" style="font-size:12px;margin:0">Notatki pozostają w historii klienta.</p>${(user().role === 'manager' || vs.length) ? button('Dodaj notatkę', 'customer-note', c.id, 'secondary', 'plus') : ''}</div>${notes.length ? notes.map(noteCard).join('') : empty('Początek nowej relacji', 'Tutaj pojawią się notatki dodane do wizyt.')}`}</div>`;
    if (!sheet.open) sheet.showModal();
  }
  function contactEditor(c = {}, i = 0) {
    return `<div class="contact-edit"><div class="form-grid"><label class="field"><span>Rodzaj kontaktu</span><select name="contactKind"><option value="phone" ${c.kind !== 'email' ? 'selected' : ''}>Telefon</option><option value="email" ${c.kind === 'email' ? 'selected' : ''}>E-mail</option></select></label>${field('Numer telefonu lub adres e-mail', 'contactValue', c.value || '', 'text', 'maxlength="150"')}</div>${field('Opis kontaktu', 'contactLabel', c.label || '', 'text', 'maxlength="120" placeholder="Do kogo prowadzi ten kontakt?"')}<div class="row between"><label class="row gap-small"><input type="radio" name="primaryContact" value="${i}" ${c.primary ? 'checked' : ''}>Kontakt główny</label>${button('Usuń', 'remove-contact', '', 'ghost')}</div></div>`;
  }
  function customerForm(customerId = '') {
    const c = D.customer(state, customerId);
    openModal(c ? 'Edytuj klienta' : 'Dodaj klienta', 'Używaj wyłącznie fikcyjnych danych. Pola z * są wymagane.', `<input type="hidden" name="id" value="${e(customerId)}">${field('Nazwa klienta *', 'name', c?.name || '', 'text', 'required maxlength="120" placeholder="Np. Gospodarstwo Pod Wierzbą"')}<div class="form-grid">${field('Kraj *', 'country', L.country(c?.country || 'Poland'), 'text', 'required maxlength="80"')}${field('NIP / identyfikator podatkowy', 'nip', c?.nip || '', 'text', 'maxlength="40"')}</div>${field('Ulica i numer', 'street', c?.street || '', 'text', 'maxlength="160"')}<div class="form-grid">${field('Kod pocztowy', 'postcode', c?.postcode || '', 'text', 'maxlength="20"')}${field('Miejscowość / poczta', 'town', c?.town || '', 'text', 'maxlength="100"')}</div><h3>Dane kontaktowe</h3><div id="contact-editors">${(c?.contacts.length ? c.contacts : [{}]).map(contactEditor).join('')}</div>${button('Dodaj kolejny kontakt', 'add-contact', '', 'secondary', 'plus')}<p class="spec">Numery dziewięciocyfrowe otrzymają prefiks +48. Pola województwa i powiatu opisano w dokumentacji wdrożenia; nie są dostępne w demo.</p>`, saveFooter(c ? 'Zapisz klienta' : 'Dodaj klienta'), 'customer-form');
  }
  function noteForm(customerId, visitId = '', noteId = '') {
    const c = D.customer(state, customerId);
    const existing = state.notes.find(n => n.id === noteId);
    const availableVisits = own(state.visits).filter(v => v.customerId === c.id);
    openModal(existing ? 'Edytuj swoją notatkę' : 'Zapisz ustalenia', c.name, `<input type="hidden" name="id" value="${e(noteId)}"><input type="hidden" name="customerId" value="${e(customerId)}">${!existing ? `<label class="field"><span>${user().role === 'manager' ? 'Powiąż z wizytą (opcjonalnie)' : 'Wizyta *'}</span><select name="visitId" ${user().role !== 'manager' ? 'required' : ''}>${user().role === 'manager' ? '<option value="">Notatka o kliencie</option>' : ''}${availableVisits.map(v => `<option value="${e(v.id)}" ${v.id === visitId ? 'selected' : ''}>${date(v.start)} · ${time(v.start)} · ${U.labels[D.stateOf(v)]}</option>`).join('')}</select></label>` : ''}<label class="field"><span>Notatka *</span><textarea name="body" required maxlength="4000" rows="5" placeholder="Co ustalono? O czym warto pamiętać przy kolejnej wizycie?">${e(existing?.body || '')}</textarea></label>${!existing ? `<div style="border-top:1px solid var(--color-line);padding-top:20px"><h3>Od notatki do działania</h3><p class="muted" style="font-size:12px">Opcjonalnie. Zadanie pozostanie powiązane z tą notatką.</p>${field('Opis zadania', 'action', '', 'text', 'maxlength="200" placeholder="Co trzeba zrobić?"')}${field('Termin (opcjonalnie)', 'due', '', 'date')}</div>` : ''}${user().role === 'manager' ? '<p class="spec">Notatka i zadanie będą oznaczone Twoim imieniem i rolą kierownika. Zadanie zostanie przypisane opiekunowi klienta.</p>' : ''}`, saveFooter(existing ? 'Zapisz notatkę' : 'Zapisz notatkę i zadanie'), 'note-form');
  }
  function confirmAction(title, subtitle, message, action, target, label, danger = false) {
    openModal(title, subtitle, `<p>${e(message)}</p>`, `${button('Wróć', 'close-modal')}${button(label, action, target, danger ? 'danger' : 'primary')}`);
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
      case 'complete-action': mutate(() => D.changeAction(state, id, 'done', user()), 'Zadanie wykonane.'); break;
      case 'cancel-visit': confirmAction('Odwołać tę wizytę?', cName(state.visits.find(v => v.id === id).customerId), 'Wizyta zostanie odwołana i usunięta z kalendarza demo. Notatki pozostaną w historii klienta. Aby zachować wizytę, wróć i wybierz „Przełóż wizytę”.', 'confirm-cancel', id, 'Odwołaj wizytę', true); break;
      case 'confirm-cancel': mutate(() => D.cancelVisit(state, id, user()), 'Wizyta odwołana. Notatki zostały zachowane.'); break;
      case 'archive': {
        const future = state.visits.filter(v => v.customerId === id && Date.parse(v.start) > Date.parse(D.NOW) && v.status !== 'cancelled').length;
        const actions = state.actions.filter(a => a.customerId === id && ['todo', 'progress'].includes(a.status)).length;
        confirmAction('Zarchiwizować tego klienta?', cName(id), `Zaplanowane wizyty do odwołania: ${future}. Otwarte zadania do anulowania: ${actions}. Wcześniejsze wizyty i notatki pozostaną dostępne. Możesz przywrócić klienta, ale odwołane wizyty i anulowane zadania nie zostaną wznowione.`, 'confirm-archive', id, 'Archiwizuj klienta', true); break;
      }
      case 'confirm-archive': mutate(() => D.archiveCustomer(state, id, user()), 'Klient zarchiwizowany. Historia została zachowana.'); break;
      case 'restore': mutate(() => D.restoreCustomer(state, id, user()), 'Klient przywrócony. Odwołane wizyty nie zostały wznowione.'); break;
      case 'reassign': openModal('Zmień opiekuna klienta', cName(id), `<input type="hidden" name="customerId" value="${e(id)}"><label class="field"><span>Nowy opiekun</span><select name="owner">${state.users.filter(p => p.role === 'rep').map(p => `<option value="${p.id}" ${D.customer(state, id).owner === p.id ? 'selected' : ''}>${e(p.name)}</option>`).join('')}</select></label><p class="muted">Klient, jego przyszłe wizyty i otwarte zadania zostaną przekazane nowemu opiekunowi. Wcześniejsze wizyty i autorzy notatek pozostaną bez zmian. Przekazanie nie jest liczone jako przełożenie ani odwołanie wizyty.</p>`, saveFooter('Zmień opiekuna klienta'), 'reassign-form'); break;
      case 'visit-note': { const v = state.visits.find(v => v.id === id); noteForm(v.customerId, v.id); break; }
      case 'customer-note': noteForm(id); break;
      case 'edit-note': { const n = state.notes.find(n => n.id === id); noteForm(n.customerId, n.visitId, n.id); break; }
      case 'source-note': { const n = state.notes.find(n => n.id === id); if (n) showCustomer(n.customerId, 'notes'); break; }
      case 'add-contact': { const container = modal.querySelector('#contact-editors'); const indices = [...container.querySelectorAll('[name="primaryContact"]')].map(el => Number(el.value)); container.insertAdjacentHTML('beforeend', contactEditor({}, Math.max(-1, ...indices) + 1)); break; }
      case 'remove-contact': trigger.closest('.contact-edit').remove(); break;
      case 'disconnect': mutate(() => D.setConnection(state, user(), false), 'Dostęp do kalendarza wygasł w demo. Statusy wizyt pozostały bez zmian.'); break;
      case 'reconnect': mutate(() => D.setConnection(state, user(), true), 'Kalendarz demo połączony. Oczekujące zmiany zostały zsynchronizowane.'); break;
      case 'simulate-delete': {
        const visitId = document.querySelector('#delete-demo-visit')?.value;
        if (!visitId) return toast('Brak wizyt dostępnych dla tego scenariusza.');
        mutate(() => D.googleDelete(state, visitId, user()), 'Zasymulowano usunięcie w Google. Wizyta oczekuje na Twoją decyzję.'); break;
      }
      case 'search':
        query = ''; customerFilter = 'active'; ownerFilter = 'all';
        if (view !== 'customers') { history.replaceState(null, '', '#customers'); navigate('customers'); } else render();
        document.querySelector('#customer-search')?.focus(); break;
      case 'this-week': periodFrom = '2026-10-19'; periodTo = '2026-10-25'; render(); break;
      case 'sample-toast': toast('Tak wygląda komunikat potwierdzający wykonanie działania.'); break;
      case 'reset': confirmAction('Przywrócić początkowy stan demo?', 'Zmiana dotyczy wyłącznie danych demo P2.', 'Wszystkie zmiany w demo P2 w tej przeglądarce zostaną zastąpione początkowymi fikcyjnymi danymi. Inne aplikacje i prototypy pozostaną bez zmian.', 'confirm-reset', '', 'Przywróć demo', true); break;
      case 'confirm-reset': state = L.localizeFixtures(D.copy(window.EkoFixtures)); persona = 'alex'; selectedDay = D.TODAY; query = ''; ownerFilter = 'all'; customerFilter = 'active'; periodFrom = '2026-10-19'; periodTo = '2026-10-25'; actionFilter = 'open'; persist(); history.replaceState(null, '', '#today'); navigate('today'); toast('Przywrócono dane demo. Możesz zacząć od nowa.'); break;
    }
  });
  document.addEventListener('input', event => {
    if (event.target.id === 'customer-search') { query = event.target.value; document.querySelector('#customer-results').innerHTML = customerResults(); }
  });
  document.addEventListener('change', event => {
    const target = event.target;
    if (target.id === 'persona') { persona = target.value; query = ''; ownerFilter = 'all'; navigate(view); toast(`Widok demo: ${user().name}.`); }
    if (target.id === 'owner-filter') { ownerFilter = target.value; render(); }
    if (target.id === 'period-from' || target.id === 'period-to') {
      const from = document.querySelector('#period-from').value;
      const to = document.querySelector('#period-to').value;
      if (from && to && from <= to) { periodFrom = from; periodTo = to; render(); }
      else { toast('Wybierz poprawny zakres. Data końcowa nie może być wcześniejsza niż początkowa.'); render(); }
    }
    if (target.dataset.actionStatus) mutate(() => D.changeAction(state, target.dataset.actionStatus, target.value, user()), 'Status zadania zaktualizowany.');
  });
  document.addEventListener('submit', event => {
    if (!event.target.matches('#visit-form, #customer-form, #note-form, #reassign-form')) return;
    event.preventDefault();
    const form = event.target;
    const formId = form.getAttribute('id');
    const input = Object.fromEntries(new FormData(form));
    if (formId === 'visit-form') {
      const result = mutate(() => D.saveVisit(state, { ...input, start: D.toInstant(input.start), end: D.toInstant(input.end) }, user()), 'Wizyta zapisana.');
      if (result) { selectedDay = D.dayOf(result.start); if (!days.includes(selectedDay)) { visitLayout = 'list'; history.replaceState(null, '', '#visits'); navigate('visits'); } else render(); }
    }
    if (formId === 'customer-form') {
      input.country = L.countryValue(input.country);
      input.contacts = [...form.querySelectorAll('.contact-edit')].map(el => ({ kind: el.querySelector('[name="contactKind"]').value, value: el.querySelector('[name="contactValue"]').value, label: el.querySelector('[name="contactLabel"]').value, primary: el.querySelector('[name="primaryContact"]').checked }));
      const result = mutate(() => D.saveCustomer(state, input, user()), '');
      if (result) { showCustomer(result.record.id); if (result.duplicate) openModal('Klient zapisany — możliwy duplikat', result.record.name, '<p>W dostępnych dla Ciebie rekordach istnieje już taka sama nazwa i miejscowość, numer telefonu lub adres e-mail. Sprawdź listę klientów przed dodaniem kolejnych danych.</p>', button('Rozumiem', 'close-modal', '', 'primary')); else toast('Klient zapisany.'); }
    }
    if (formId === 'note-form') mutate(() => input.id ? D.editNote(state, input.id, input.body, user()) : D.addNote(state, input, user()), input.id ? 'Notatka zaktualizowana.' : input.action?.trim() ? 'Notatka i zadanie zapisane.' : 'Notatka zapisana.');
    if (formId === 'reassign-form') mutate(() => D.reassignCustomer(state, input.customerId, input.owner, user()), 'Opiekun klienta zmieniony. Historyczne przypisania zostały zachowane.');
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
