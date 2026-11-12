const form = document.querySelector("#search-form");
const input = document.querySelector("#search-input");
const button = document.querySelector("#search-button");
const title = document.querySelector("#results-title");
const count = document.querySelector("#result-count");
const providerGrid = document.querySelector("#provider-grid");
const emptyState = document.querySelector("#empty-state");
const notice = document.querySelector("#notice");
const offersWrap = document.querySelector("#offers-wrap");
const offersList = document.querySelector("#offers-list");
const offersCaption = document.querySelector("#offers-caption");
const moreButton = document.querySelector("#load-more-button");
const results = document.querySelector("#results");
const providerDetails = document.querySelector("#provider-details");
const loading = document.querySelector("#search-loading");
const searchGuide = document.querySelector("#search-guide");
const Catalog = window.MultiMarketCatalog;
const Region = window.MultiMarketRegion;
const filterForm = document.querySelector("#catalog-filters");
let filteredProducts = [];
let savedResponse = null;
const SEARCH_STATE_KEY = "multimarket.search.v1";
let activeQuery = "";
let bufferedProducts = [];
let displayedProductCount = 0;
let productCount = 0;
let offerCount = 0;
let searchSequence = 0;
const loadedProductIds = new Set();
const MAX_BUFFERED_RESULTS = 200;
const DISPLAY_BATCH_SIZE = 20;

const providerMeta = {
  "Ozon": { logo: "O", className: "ozon-logo" },
  "Wildberries": { logo: "WB", className: "wb-logo" },
  "Яндекс Маркет": { logo: "Я", className: "ym-logo" }
};
const statusMeta = {
  access_required: { label: "Поиск недоступен", className: "status-warn" },
  disabled: { label: "Временно выключен", className: "status-neutral" },
  policy_restricted: { label: "Доступ ограничен", className: "status-warn" },
  ready: { label: "Товары найдены", className: "status-good" },
  no_results: { label: "Товары не найдены", className: "status-neutral" },
  error: { label: "Ошибка запроса", className: "status-error" }
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function message(node, text) {
  node.hidden = !text;
  node.querySelector("p").textContent = text || "";
}
function productsWord(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "товар";
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return "товара";
  return "товаров";
}
function money(value, currency) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency", currency: currency || "RUB", minimumFractionDigits: 0, maximumFractionDigits: 2
  }).format(value);
}
function renderProviders(providers) {
  providerGrid.replaceChildren();
  providerDetails.hidden = !providers?.length;
  for (const provider of providers || []) {
    const meta = providerMeta[provider.marketplace] || { logo: "?", className: "" };
    const info = statusMeta[provider.status] || statusMeta.error;
    const card = element("article", "provider-card");
    const top = element("div", "provider-top");
    top.append(element("span", "provider-logo " + meta.className, meta.logo));
    top.append(element("span", "status " + info.className, info.label));
    card.append(top, element("h3", "", provider.marketplace));
    if (provider.message) card.append(element("p", "provider-message", provider.message));
    const links = element("div", "provider-links");
    if (provider.search_url) {
      const link = element("a", "provider-link", "Открыть поиск ↗");
      link.href = provider.search_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      links.append(link);
    }
    if (provider.status === "policy_restricted" || provider.status === "access_required") {
      const setup = element("a", "provider-setup", "Почему поиск недоступен");
      setup.href = "/sources";
      links.append(setup);
    }
    if (links.childElementCount) card.append(links);
    providerGrid.append(card);
  }
}
function renderOffers(products, query, append) {
  if (!append) {
    offersList.replaceChildren();
    productCount = 0;
    offerCount = 0;
    loadedProductIds.clear();
  }
  if (!products.length && !append) {
    offersWrap.hidden = true;
    count.textContent = "";
    return 0;
  }
  offersWrap.hidden = false;
  let renderedCount = 0;
  for (const product of products) {
    const productId = product.product_id || product.match_key;
    if (append && productId && loadedProductIds.has(productId)) continue;
    if (productId) loadedProductIds.add(productId);
    const offers = Array.isArray(product.offers) ? product.offers : [];
    if (!offers.length) continue;
    const card = element("article", "offer-card");
    const head = element("div", "offer-product-head");
    const imageUrl = offers.flatMap(Catalog.images)[0];
    if (imageUrl) {
      const image = element("img", "offer-product-image");
      image.src = imageUrl;
      image.alt = product.title || "Фото товара";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      head.append(image);
    }
    card.append(head);
    const productPage = element("a", "details-button", product.title || "Товар");
    const productSummary = {
      title: product.title || "Товар",
      region_id: Region.getId(),
      offers: (product.sourceOffers || offers).map(offer => ({
        marketplace: offer.marketplace,
        title: offer.title,
        price: offer.price,
        currency: offer.currency,
        url: offer.url,
        image_url: offer.image_url,
        external_id: offer.external_id,
        in_stock: offer.in_stock,
        brand: offer.brand,
        model: offer.model, seller:offer.seller, condition:offer.condition, variants:offer.variants,
        rating: offer.rating,
        review_count: offer.review_count,
        delivery: offer.delivery
      }))
    };
    const storageKey = "multimarket.product." + (globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2));
    productPage.href = "/product?data=" + encodeURIComponent(JSON.stringify(productSummary)) + "&key=" + encodeURIComponent(storageKey);
    if (Region.getId() !== null) productPage.href += "&region_id=" + Region.getId();
    const saveProduct = () => {
      try { sessionStorage.setItem(storageKey, JSON.stringify({title:product.title, offers:product.sourceOffers || offers,region_id:Region.getId()})); } catch {}
    };
    productPage.addEventListener("click", saveProduct);
    productPage.addEventListener("auxclick", saveProduct);
    const productHeading = element("h3");
    productHeading.append(productPage);
    head.append(productHeading);
    card.append(window.MultiMarketLibrary.controls({title:product.title,offers:product.sourceOffers || offers}));
    const rows = element("div", "offer-rows");
    const best = Catalog.bestOffers(offers);
    offers.forEach(offer => {
      offerCount += 1;
      const row = element("div", "offer-row");
      const info = element("div", "offer-info");
      info.append(element("strong", "", offer.marketplace));
      if(offer.seller)info.append(element("span","","Продавец: "+offer.seller));
      if(Object.keys(offer.variants||{}).length)info.append(element("span","variant-summary",Object.values(offer.variants).join(" · ")));
      if (offer.in_stock === false) info.append(element("span", "stock-badge-empty", "Нет в наличии"));
      // Offers of the same product usually repeat the product's own title;
      // showing it again under every row just clutters the card, so only
      // add it when it actually differs (e.g. a seller-specific variant).
      const offerTitle = (offer.title || "").trim();
      const productTitle = (product.title || "").trim();
      if (offerTitle && offerTitle !== productTitle) {
        info.append(element("span", "", offerTitle));
      }
      for (const badge of Catalog.badges(offer, best)) {
        const label = element("span", "best-price-badge", badge);
        label.title = badge === "Лучшее предложение"
          ? "Минимальная цена товара среди доступных предложений в этой валюте. Приоритет у товаров в наличии. Доставка не включена."
          : badge === "Высокая оценка" ? "Оценка от 4,5 при наличии не менее 10 оценок." : "Опубликованный срок доставки — до 2 дней. Уточните его для своего адреса.";
        info.append(label);
      }
      if (Number(offer.rating) > 0) info.append(element("span", "offer-rating", "★ " + offer.rating + (offer.review_count != null ? " · оценок: " + offer.review_count : "")));
      const delivery = element("p", "offer-delivery", Catalog.deliveryLabel(offer));
      const right = element("div", "offer-right");
      right.append(element("strong", "offer-price", money(offer.price, offer.currency)));
      const actions = element("div", "offer-actions");
      const link = element("a", "offer-open", "В магазин ↗");
      link.href = offer.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      actions.append(link);
      const watch = element("button", "watch-button", "Следить за ценой");
      watch.type = "button";
      watch.addEventListener("click", async () => {
        watch.disabled = true;
        watch.textContent = "Добавляем…";
        try {
          const authResponse = await fetch("/api/auth/me");
          if (!authResponse.ok) throw new Error("Не удалось проверить вход.");
          const auth = await authResponse.json();
          if (!auth.authenticated) {
            saveSearchState();
            location.assign("/login?next=/");
            return;
          }
          const response = await fetch("/api/monitors", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": auth.csrf_token },
            body: JSON.stringify({
              query, product_url: offer.url, marketplace: offer.marketplace,
              title: offer.title, interval_seconds: 3600
            })
          });
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || "Не удалось добавить товар.");
          watch.textContent = "Отслеживается";
          message(notice, "Товар добавлен. Его цена и история доступны в разделе «Мои товары».");
        } catch (error) {
          watch.disabled = false;
          watch.textContent = "Следить за ценой";
          message(notice, error.message);
        }
      });
      actions.append(watch);
      right.append(actions);
      row.append(info, delivery, right);
      rows.append(row);
    });
    card.append(rows);
    offersList.append(card);
    productCount += 1;
    renderedCount += 1;
  }
  offersCaption.textContent = "Предложений: " + offerCount + ". Итоговую цену проверьте в магазине.";
  count.textContent = "Показано " + productCount + " из " + filteredProducts.length;
  return renderedCount;
}
function updateMoreButton() {
  const remaining = Math.max(0, filteredProducts.length - displayedProductCount);
  moreButton.hidden = remaining === 0;
  if (remaining > 0) {
    const nextBatch = Math.min(DISPLAY_BATCH_SIZE, remaining);
    moreButton.textContent = "Показать ещё " + nextBatch + " " + productsWord(nextBatch);
  }
}
function revealNextProducts() {
  const start = displayedProductCount;
  const end = Math.min(start + DISPLAY_BATCH_SIZE, filteredProducts.length);
  if (end <= start) {
    updateMoreButton();
    return 0;
  }
  const batch = filteredProducts.slice(start, end);
  const rendered = renderOffers(batch, activeQuery, start > 0);
  displayedProductCount = end;
  updateMoreButton();
  return rendered;
}
function readFilters() {
  const values = {};
  for (const key of ["min", "max", "currency", "sort", "marketplace", "brand", "rating", "delivery"]) {
    values[key] = document.querySelector("#filter-" + key).value;
  }
  values.stock = document.querySelector("#filter-stock").checked;
  return values;
}
function populateFilters(saved = {}) {
  const offers = bufferedProducts.flatMap(p => p.offers || []);
  for (const [key, values, label] of [
    ["marketplace", offers.map(o => o.marketplace), "Все площадки"],
    ["brand", offers.map(o => o.brand), "Все бренды"],
    ["currency", offers.map(Catalog.currency), null]
  ]) {
    const select = document.querySelector("#filter-" + key);
    select.replaceChildren();
    if (label) select.append(new Option(label, ""));
    [...new Set(values.filter(Boolean))].sort().forEach(value => select.append(new Option(value, value)));
    if (key === "currency") select.value = offers.some(o => Catalog.currency(o) === "RUB") ? "RUB" : select.options[0]?.value || "RUB";
  }
  for (const [key, value] of Object.entries(saved)) {
    const control = document.querySelector("#filter-" + key);
    if (!control) continue;
    if (key === "stock") control.checked = Boolean(value);
    else if (control.tagName !== "SELECT" || [...control.options].some(o => o.value === value)) control.value = value;
  }
  filterForm.hidden = !bufferedProducts.length;
}
function applyFilters(displayed = DISPLAY_BATCH_SIZE) {
  const filters = readFilters();
  const feedback = document.querySelector("#filter-feedback");
  if (filters.min !== "" && filters.max !== "" && Number(filters.min) > Number(filters.max)) {
    feedback.textContent = "Цена «до» должна быть не меньше цены «от».";
    return;
  }
  filteredProducts = Catalog.sortProducts(Catalog.filterProducts(bufferedProducts, filters), filters.sort, filters.currency);
  displayedProductCount = Math.min(Math.max(DISPLAY_BATCH_SIZE, displayed), filteredProducts.length);
  renderOffers(filteredProducts.slice(0, displayedProductCount), activeQuery, false);
  updateMoreButton();
  emptyState.hidden = Boolean(filteredProducts.length);
  document.querySelector("#retry-search").textContent = bufferedProducts.length ? "Сбросить фильтры" : "Повторить поиск";
  if (bufferedProducts.length && !filteredProducts.length) {
    emptyState.querySelector("strong").textContent = "Нет подходящих товаров";
    emptyState.querySelector("span").textContent = "Измените условия или сбросьте фильтры, чтобы увидеть все предложения.";
    count.textContent = "Найдено: 0";
  }
  const active = [filters.min,filters.max,filters.brand,filters.marketplace,filters.rating,filters.delivery,filters.stock].filter(Boolean).length;
  document.querySelector("#filter-active-count").textContent = active ? "· " + active : "";
  feedback.textContent = "Подходит " + filteredProducts.length + " из " + bufferedProducts.length + " загруженных товаров. Сроки доставки зависят от адреса.";
  saveSearchState();
}
function resetFilters() {
  filterForm.reset();
  populateFilters();
  applyFilters();
}
filterForm.addEventListener("submit", event => event.preventDefault());
filterForm.addEventListener("input", () => applyFilters());
document.querySelector("#reset-filters").addEventListener("click", resetFilters);
async function fetchSearchResults(sequence = searchSequence) {
  const params = new URLSearchParams({
    q: activeQuery,
    limit: String(MAX_BUFFERED_RESULTS),
    offset: "0"
  });
  if (Region.getId() !== null) params.set("region_id",String(Region.getId()));
  const response = await fetch("/api/search?" + params, {
    headers: { Accept: "application/json" }
  });
  const data = await response.json();
  if (sequence !== searchSequence) return null;
  if (!response.ok) throw new Error(data.detail || "Не удалось выполнить поиск.");

  savedResponse = data;
  bufferedProducts = Array.isArray(data.products) ? data.products : [];
  Region.observeOffers(bufferedProducts.flatMap(p => p.offers || []));
  displayedProductCount = 0;
  title.textContent = "Результаты для «" + data.query + "»";
  renderProviders(data.providers);
  filterForm.reset();
  populateFilters();
  applyFilters();
  providerDetails.open = !bufferedProducts.length;
  if (!bufferedProducts.length) {
    emptyState.querySelector("strong").textContent = "Товары не найдены";
    emptyState.querySelector("span").textContent = "Уточните бренд и модель или откройте поиск на площадке ниже.";
  }

  if ((data.total_products ?? 0) >= MAX_BUFFERED_RESULTS && !data.exact_total) {
    message(notice, "Показаны первые 200 доступных товаров. Уточните запрос, чтобы найти нужную модель.");
  } else {
    message(notice, data.notice);
  }
  updateMoreButton();
  saveSearchState();
  return data;
}
async function runSearch(query) {
  await Region.ready;
  activeQuery = query.trim();
  if (!activeQuery) return;
  savedResponse = null;
  try { sessionStorage.removeItem(SEARCH_STATE_KEY); } catch {}
  bufferedProducts = [];
  filteredProducts = [];
  document.querySelector("#retry-search").textContent = "Повторить поиск";
  displayedProductCount = 0;
  const sequence = ++searchSequence;
  results.hidden = false;
  results.setAttribute("aria-busy", "true");
  searchGuide.hidden = true;
  loading.hidden = false;
  providerDetails.hidden = true;
  filterForm.hidden = true;
  providerDetails.open = false;
  count.textContent = "";
  input.value = activeQuery;
  button.disabled = true;
  button.textContent = "Ищем…";
  title.textContent = "Ищем «" + activeQuery + "»";
  emptyState.hidden = true;
  offersWrap.hidden = true;
  moreButton.hidden = true;
  message(notice, "");
  try {
    await fetchSearchResults(sequence);
  } catch (error) {
    if (sequence !== searchSequence) return;
    providerGrid.replaceChildren();
    title.textContent = "Поиск не выполнен";
    emptyState.hidden = false;
    emptyState.querySelector("strong").textContent = "Не удалось выполнить поиск";
    emptyState.querySelector("span").textContent = error.message || "Проверьте соединение и попробуйте ещё раз.";
  } finally {
    if (sequence === searchSequence) {
      loading.hidden = true;
      results.setAttribute("aria-busy", "false");
      button.disabled = false;
      button.textContent = "Найти";
    }
  }
}
form.addEventListener("submit", event => {
  event.preventDefault();
  runSearch(input.value);
});
document.querySelectorAll(".example-query").forEach(item =>
  item.addEventListener("click", () => runSearch(item.textContent))
);
moreButton.addEventListener("click", () => {
  if (moreButton.hidden) return;
  moreButton.disabled = true;
  moreButton.textContent = "Показываем…";
  revealNextProducts();
  moreButton.disabled = false;
  saveSearchState();
});
document.querySelector("#retry-search").addEventListener("click", () => bufferedProducts.length ? resetFilters() : runSearch(activeQuery));

function saveSearchState() {
  if (!savedResponse) return;
  if ((savedResponse.region?.id ?? null) !== Region.getId()) return;
  try {
    sessionStorage.setItem(SEARCH_STATE_KEY, JSON.stringify({
      version: 4, query: activeQuery, data: savedResponse, region_id:Region.getId(),
      displayed: displayedProductCount, scrollY: window.scrollY, filters:readFilters()
    }));
  } catch { /* Browsing also works when storage is unavailable or full. */ }
}
function restoreSearchState() {
  try {
    const state = JSON.parse(sessionStorage.getItem(SEARCH_STATE_KEY) || "null");
    if (!state || ![1,2,3].includes(state.version) || typeof state.query !== "string" ||
        !Array.isArray(state.data?.products) || !Number.isInteger(state.displayed)) return;
    if (state.version < 4 || (state.region_id ?? null) !== Region.getId()) {
      runSearch(state.query).then(() => {
        if (savedResponse) {populateFilters(state.filters); applyFilters(state.displayed);}
      });
      return;
    }
    savedResponse = state.data;
    activeQuery = state.query;
    input.value = activeQuery;
    bufferedProducts = state.data.products;
    Region.observeOffers(bufferedProducts.flatMap(p => p.offers || []));
    results.hidden = false;
    searchGuide.hidden = true;
    title.textContent = "Результаты для «" + activeQuery + "»";
    renderProviders(state.data.providers);
    populateFilters(state.filters);
    applyFilters(state.displayed);
    providerDetails.open = !bufferedProducts.length;
    if (!bufferedProducts.length) {
      emptyState.querySelector("strong").textContent = "Товары не найдены";
      emptyState.querySelector("span").textContent = "Уточните бренд и модель или откройте поиск на площадке ниже.";
    }
    message(notice, state.data.notice);
    updateMoreButton();
    requestAnimationFrame(() => window.scrollTo(0, Number(state.scrollY) || 0));
  } catch { /* Ignore an outdated or incomplete saved search. */ }
}
window.addEventListener("pagehide", saveSearchState);
document.addEventListener("click", event => {
  if (event.target.closest("a")) saveSearchState();
});
document.addEventListener("multimarket:regionchange", () => {
  if (!activeQuery) return;
  const filters = readFilters(), requestedRegion = Region.getId();
  runSearch(activeQuery).then(() => {if (savedResponse && Region.getId() === requestedRegion) {populateFilters(filters);applyFilters();}});
});
Region.ready.then(restoreSearchState);
