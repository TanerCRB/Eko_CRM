/*
 * Icon set for the prototype: 24x24 stroke icons (1.8 stroke, round caps), drawn for this project.
 * In frontend/src these become one <Icon name> component; the paths carry over unchanged.
 */
(function (global) {
  "use strict";
  const P = {
    today: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/><circle cx="12" cy="15" r="1.6"/>',
    customers: '<circle cx="9" cy="8.5" r="3.2"/><path d="M3.5 19c.6-3.2 2.9-5 5.5-5s4.9 1.8 5.5 5"/><path d="M15.5 5.6a3 3 0 0 1 0 5.8M17.5 14.4c1.6.6 2.7 2.2 3 4.6"/>',
    visits: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4M8 14h3M8 17h6"/>',
    actions: '<rect x="4" y="4" width="16" height="16" rx="2.5"/><path d="m8.5 12.2 2.4 2.4 4.8-5.2"/>',
    team: '<path d="M7 7h11l-3-3M17 17H6l3 3"/>',
    dashboard: '<path d="M4 20V10M10 20V4M16 20v-7M21 20H3"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.4M12 18.8v2.4M4.2 7.5l2 1.2M17.8 15.3l2 1.2M4.2 16.5l2-1.2M17.8 8.7l2-1.2"/>',
    phone: '<path d="M6.6 3.5h2.6l1.4 4-2 1.3a11 11 0 0 0 6.6 6.6l1.3-2 4 1.4v2.6a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 4.6 5.7a2 2 0 0 1 2-2.2Z"/>',
    mail: '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="m3.5 7 8.5 6 8.5-6"/>',
    pin: '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z"/><circle cx="12" cy="10" r="2.4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    cloudOff: '<path d="M7.5 18.5h9.8a3.7 3.7 0 0 0 1.2-7.2A6 6 0 0 0 7.6 9.2 4.7 4.7 0 0 0 7.5 18.5Z"/><path d="M4 4l16 16"/>',
    cloud: '<path d="M7.5 18.5h9.8a3.7 3.7 0 0 0 1.2-7.2A6 6 0 0 0 7.6 9.2 4.7 4.7 0 0 0 7.5 18.5Z"/>',
    moved: '<path d="M4 12h13M13 7l5 5-5 5"/><path d="M4 7v10" stroke-dasharray="2 2.5"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    alert: '<path d="M12 4 2.8 19.5h18.4L12 4Z"/><path d="M12 10v4.2M12 17.2v.1"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    back: '<path d="M15 5l-7 7 7 7"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/>',
    archive: '<rect x="3.5" y="4.5" width="17" height="4" rx="1"/><path d="M5 8.5V19a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8.5M10 12.5h4"/>',
    restore: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3L4.5 9"/><path d="M4.5 4.5V9H9"/>',
    note: '<path d="M5 3.5h10l4 4V20a.5.5 0 0 1-.5.5h-13A.5.5 0 0 1 5 20V3.5Z"/><path d="M15 3.5V8h4M8.5 12h7M8.5 15.5h5"/>',
    logout: '<path d="M14 4h4.5a1.5 1.5 0 0 1 1.5 1.5v13a1.5 1.5 0 0 1-1.5 1.5H14M10 16l4-4-4-4M14 12H4"/>',
    more: '<circle cx="5.5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="18.5" cy="12" r="1.3"/>',
    demo: '<path d="M9 3.5h6M10 3.5v5.2L4.8 18a1.6 1.6 0 0 0 1.4 2.5h11.6a1.6 1.6 0 0 0 1.4-2.5L14 8.7V3.5"/><path d="M7.5 14.5h9"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>',
  };
  function icon(name, extra = "") {
    return `<svg class="ek-icon ${extra}" viewBox="0 0 24 24" aria-hidden="true">${P[name] || ""}</svg>`;
  }
  // Brand mark: a rapeseed flower — four petals, the crucifer shape.
  const brandMark = '<svg class="brand__mark" viewBox="0 0 32 32" aria-hidden="true">' +
    '<g fill="#e6c21b"><ellipse cx="16" cy="8.5" rx="5" ry="6.5"/><ellipse cx="16" cy="23.5" rx="5" ry="6.5"/>' +
    '<ellipse cx="8.5" cy="16" rx="6.5" ry="5"/><ellipse cx="23.5" cy="16" rx="6.5" ry="5"/></g>' +
    '<circle cx="16" cy="16" r="3.6" fill="#241c15"/></svg>';
  global.EkoIcons = { paths: P, icon, brandMark };
})(window);
