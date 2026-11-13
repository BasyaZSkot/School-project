(function () {
  'use strict';
  const root = document.documentElement, themeKey = 'multimarket.theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  const themes = ['system', 'light', 'dark'], views = ['tiles', 'compact', 'list'];
  const paths = {
    search: '<circle cx="10.8" cy="10.8" r="7.2"/><path d="m16 16 4.5 4.5"/>',
    heart: '<path d="M20.5 5.5a5 5 0 0 0-7 0L12 7l-1.5-1.5a5 5 0 0 0-7 7L12 21l8.5-8.5a5 5 0 0 0 0-7Z"/>',
    compare: '<rect x="3" y="8" width="6" height="12" rx="2"/><rect x="15" y="4" width="6" height="16" rx="2"/>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
    chart: '<path d="M4 3v17h17M8 14l4-5 4 3 5-7"/>',
    pin: '<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5"/>',
    moon: '<path d="M21 13a9 9 0 0 1-10-10A9 9 0 1 0 21 13Z"/>',
    system: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    compact: '<path d="M3 3h4v4H3zm7 0h4v4h-4zm7 0h4v4h-4zM3 10h4v4H3zm7 0h4v4h-4zm7 0h4v4h-4zM3 17h4v4H3zm7 0h4v4h-4zm7 0h4v4h-4z"/>',
    list: '<rect x="3" y="4" width="5" height="6" rx="1"/><rect x="3" y="14" width="5" height="6" rx="1"/><path d="M12 5h9m-9 4h6m-6 6h9m-9 4h6"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    filter: '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
    bag: '<rect x="4" y="7" width="16" height="14" rx="3"/><path d="M8 8V6a4 4 0 0 1 8 0v2"/>',
    truck: '<path d="M3 5h11v12H3zm11 5h4l3 4v3h-7"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
    star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    chevron: '<path d="m7 10 5 5 5-5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.01"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>'
  };
  function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    for (const [key, value] of Object.entries({viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':'1.7', 'stroke-linecap':'round', 'stroke-linejoin':'round', 'aria-hidden':'true', focusable:'false', class:'ui-icon'})) svg.setAttribute(key, value);
    // Fixed application assets; user content is never inserted into SVG markup.
    svg.innerHTML = paths[name] || paths.info;
    return svg;
  }
  window.MultiMarketUI = {icon};
  function read(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } }
  function save(key, value) { try { localStorage.setItem(key, value); } catch {} }
  function theme(value) {
    const preference = themes.includes(value) ? value : 'system';
    root.dataset.themePreference = preference;
    root.dataset.theme = preference === 'system' ? (system.matches ? 'dark' : 'light') : preference;
    document.querySelectorAll('[data-theme-choice]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === preference)));
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = root.dataset.theme === 'dark' ? '#171a20' : '#f6f7f9';
  }
  theme(read(themeKey, 'system'));
  system.addEventListener('change', () => { if (root.dataset.themePreference === 'system') theme('system'); });
  function view(scope, value) { root.dataset[scope + 'View'] = views.includes(value) ? value : 'tiles'; }
  for (const scope of ['search', 'product']) view(scope, read('multimarket.view.' + scope, 'tiles'));
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-icon]').forEach(node => node.replaceChildren(icon(node.dataset.icon)));
    document.querySelectorAll('.main-nav a, .mobile-nav a, .menu-links a').forEach(link => {
      const href = link.getAttribute('href');
      if (location.pathname === href || (href === '/account' && ['/login','/forgot-password','/reset-password','/verify-email','/admin'].includes(location.pathname))) link.setAttribute('aria-current', 'page');
    });
    const toggle = document.querySelector('#theme-toggle'), menu = document.querySelector('#theme-menu');
    function closeTheme(focus) { if (!menu) return; menu.hidden = true; toggle.setAttribute('aria-expanded', 'false'); if (focus) toggle.focus(); }
    if (toggle && menu) {
      toggle.addEventListener('click', () => { const open = menu.hidden; menu.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); if (open) menu.querySelector('[aria-pressed="true"]')?.focus(); });
      menu.querySelectorAll('button').forEach(button => button.addEventListener('click', () => { theme(button.dataset.themeChoice); save(themeKey, button.dataset.themeChoice); closeTheme(true); }));
      document.addEventListener('click', event => { if (!event.target.closest('.theme-control')) closeTheme(false); });
      document.addEventListener('keydown', event => { if (event.key === 'Escape' && !menu.hidden) closeTheme(true); });
    }
    theme(root.dataset.themePreference);
    for (const [opener, target] of [['menu-toggle','navigation-dialog'], ['open-filters','filter-dialog']]) {
      const button = document.getElementById(opener), dialog = document.getElementById(target);
      if (!button || !dialog) continue;
      button.addEventListener('click', () => dialog.showModal());
      dialog.querySelectorAll('[data-close-dialog]').forEach(close => close.addEventListener('click', () => dialog.close()));
      dialog.addEventListener('click', event => { if (event.target === dialog && event.clientX < dialog.getBoundingClientRect().left) dialog.close(); });
    }
    for (const [scope, selector] of [['search','#offers-list'], ['product','#product-offers']]) {
      const target = document.querySelector(selector); if (!target) continue;
      const wrap = document.createElement('div'); wrap.className = 'view-switch'; wrap.setAttribute('role','group'); wrap.setAttribute('aria-label',scope === 'search' ? 'Вид товаров' : 'Вид предложений');
      for (const [value,name,title] of [['tiles','grid','Крупные карточки'],['compact','compact','Компактные карточки'],['list','list','Список']]) {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'view-option'; button.dataset.view = value; button.dataset.scope = scope; button.append(icon(name)); button.setAttribute('aria-label',title); button.title = title;
        button.setAttribute('aria-pressed',String(root.dataset[scope + 'View'] === value));
        button.addEventListener('click', () => { view(scope,value); save('multimarket.view.' + scope,value); wrap.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed',String(item.dataset.view === value))); }); wrap.append(button);
      }
      if (scope === 'search') document.querySelector('.results-toolbar')?.append(wrap); else target.before(wrap);
    }
    const filters = document.querySelector('#catalog-filters'), filterButton = document.querySelector('#open-filters');
    if (filters && filterButton) { const sync = () => { filterButton.hidden = filters.hidden; }; new MutationObserver(sync).observe(filters,{attributes:true,attributeFilter:['hidden']}); sync(); }
    const syncDialogs = () => root.classList.toggle('has-modal',!!document.querySelector('dialog[open]'));
    document.querySelectorAll('dialog').forEach(dialog => new MutationObserver(syncDialogs).observe(dialog,{attributes:true,attributeFilter:['open']}));
  });
  window.addEventListener('storage', event => {
    if (event.key === themeKey) theme(event.newValue || 'system');
    for (const scope of ['search','product']) if (event.key === 'multimarket.view.' + scope) {
      view(scope,event.newValue || 'tiles'); document.querySelectorAll('.view-option[data-scope="' + scope + '"]').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.view === root.dataset[scope + 'View'])));
    }
  });
})();
