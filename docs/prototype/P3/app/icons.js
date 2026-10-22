/*
 * Eko_CRM prototype P3 — icons. 24-unit grid, 2px stroke, square caps: the look of stamped
 * metal signage on machinery. Paths carry over unchanged into an <Icon name> component.
 */
const PATHS = {
  week: '<rect x="3" y="5" width="18" height="16"/><path d="M3 10h18M8 3v4M16 3v4M7 14h3M7 18h3M14 14h3"/>',
  customers: '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6"/><path d="M16 5a3 3 0 0 1 0 6M18 14c2 .8 3 2.8 3 6"/>',
  visits: '<rect x="3" y="5" width="18" height="16"/><path d="M3 10h18M8 3v4M16 3v4M9 15l2 2 4-4"/>',
  tasks: '<rect x="3" y="4" width="18" height="16"/><path d="M7 9h2M12 9h5M7 13h2M12 13h5M7 17h2M12 17h3"/>',
  team: '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
  dashboard: '<path d="M4 20V11M10 20V4M16 20v-6M22 20H2"/>',
  account: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="10" r="3"/><path d="M6.5 18.5c1.2-2.5 3.2-3.5 5.5-3.5s4.3 1 5.5 3.5"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a10 10 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1Z"/>',
  pin: '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><circle cx="12" cy="10" r="2.2"/>',
  mail: '<rect x="3" y="6" width="18" height="12"/><path d="M3 7l9 6 9-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  close: '<path d="M5 5l14 14M19 5 5 19"/>',
  back: '<path d="M15 4l-8 8 8 8"/>',
  prev: '<path d="M14 6l-6 6 6 6"/>',
  next: '<path d="M10 6l6 6-6 6"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16v4Z"/><path d="M13 7l4 4"/>',
  archive: '<rect x="3" y="4" width="18" height="4"/><path d="M5 8v12h14V8M10 12h4"/>',
  restore: '<path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.6"/><path d="M4 4v5h5"/>',
  cloudOff: '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 7 9a4.5 4.5 0 0 0 0 9Z"/><path d="M4 4l16 16"/>',
  cloud: '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 7 9a4.5 4.5 0 0 0 0 9Z"/>',
  moved: '<path d="M4 12h14M13 7l5 5-5 5"/><path d="M4 7v10" stroke-dasharray="2 3"/>',
  alert: '<path d="M12 3 2 21h20L12 3Z"/><path d="M12 10v5M12 17.5v.5"/>',
  note: '<path d="M5 3h9l5 5v13H5V3Z"/><path d="M14 3v5h5M8 12h8M8 16h5"/>',
  logout: '<path d="M14 4h5v16h-5M10 16l4-4-4-4M14 12H3"/>',
  copy: '<rect x="8" y="8" width="12" height="12"/><path d="M16 8V4H4v12h4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  demo: '<path d="M9 3h6M10 3v5L4 19a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2l-6-11V3"/><path d="M7 15h10"/>',
};

export function icon(name, size) {
  return `<svg class="icon" ${size ? `data-size="${size}"` : ""} viewBox="0 0 24 24" aria-hidden="true">${PATHS[name] ?? ""}</svg>`;
}
export const iconNames = Object.keys(PATHS);

/* Brand mark: three furrows across a square field and the red dot of the rep on the road. */
export const brandMark = `<svg class="brand__mark" viewBox="0 0 26 26" aria-hidden="true">
  <rect x="1" y="1" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2"/>
  <path d="M5 20 20 5M5 13 13 5M12 21l9-9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"/>
  <circle cx="19" cy="19" r="3" fill="#c0202a"/>
</svg>`;
