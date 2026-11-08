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
let activeQuery = "";
let activeSearchId = "";
let nextOffset = 0;
let productCount = 0;
let offerCount = 0;
let searchSequence = 0;
let detailRequestSequence = 0;
const loadedProductIds = new Set();
const DEFAULT_PAGE_SIZE = 20;
const INITIAL_PAGE_FILL_RETRY_MS = 1000;
const MAX_PAGE_FILL_RETRY_MS = 10000;
const productDialog = document.querySelector("#product-dialog");

const providerMeta = {
  "Ozon": { logo: "O", className: "ozon-logo" },
  "Wildberries": { logo: "WB", className: "wb-logo" },
  "Яндекс Маркет": { logo: "Я", className: "ym-logo" }
};
const statusMeta = {
  access_required: { label: "Нужен источник", className: "status-warn" },
  policy_restricted: { label: "Доступ ограничен", className: "status-warn" },
  ready: { label: "Есть карточки", className: "status-good" },
  no_results: { label: "Нет карточек", className: "status-warn" },
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
function newSearchSessionId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return "search-" + Date.now().toString(36) + Math.random().toString(36).slice(2);
}
function money(value, currency) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency", currency: currency || "RUB", maximumFractionDigits: 2
  }).format(value);
}
function renderProviders(providers) {
  providerGrid.replaceChildren();
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
      const setup = element("a", "provider-setup", "Как подключить источник");
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
    const imageUrl = offers.find(item => item.image_url && item.image_url.startsWith("https://"))?.image_url;
    if (imageUrl) {
      const image = element("img", "offer-product-image");
      image.src = imageUrl;
      image.alt = product.title || "Фото товара";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      head.append(image);
    }
    head.append(element("h3", "", product.title || "Товар"));
    card.append(head);
    const rows = element("div", "offer-rows");
    const minima = new Map();
    offers.forEach(offer => {
      const price = Number(offer.price);
      const currency = offer.currency || "RUB";
      if (Number.isFinite(price) && price > 0) {
        minima.set(currency, Math.min(minima.get(currency) ?? price, price));
      }
    });
    offers.forEach(offer => {
      offerCount += 1;
      const row = element("div", "offer-row");
      const info = element("div", "offer-info");
      info.append(element("strong", "", offer.marketplace));
      // Offers of the same product usually repeat the product's own title;
      // showing it again under every row just clutters the card, so only
      // add it when it actually differs (e.g. a seller-specific variant).
      const offerTitle = (offer.title || "").trim();
      const productTitle = (product.title || "").trim();
      if (offerTitle && offerTitle !== productTitle) {
        info.append(element("span", "", offerTitle));
      }
      if (offers.length > 1 && Number(offer.price) === minima.get(offer.currency || "RUB")) {
        info.append(element("span", "best-price-badge", "Лучшая цена"));
      }
      const right = element("div", "offer-right");
      right.append(element("strong", "offer-price", money(offer.price, offer.currency)));
      const actions = element("div", "offer-actions");
      const detailsButton = element("button", "details-button", "Подробнее");
      detailsButton.type = "button";
      detailsButton.addEventListener("click", () => openProductDetails(offer));
      actions.append(detailsButton);
      const link = element("a", "offer-open", "К товару ↗");
      link.href = offer.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      actions.append(link);
      const watch = element("button", "watch-button", "Следить");
      watch.type = "button";
      watch.addEventListener("click", async () => {
        watch.disabled = true;
        try {
          const response = await fetch("/api/monitors", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              query, product_url: offer.url, marketplace: offer.marketplace,
              title: offer.title, interval_seconds: 3600
            })
          });
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || "Не удалось добавить товар.");
          watch.textContent = "Добавлен";
        } catch (error) {
          watch.disabled = false;
          message(notice, error.message);
        }
      });
      actions.append(watch);
      right.append(actions);
      row.append(info, right);
      rows.append(row);
    });
    card.append(rows);
    offersList.append(card);
    productCount += 1;
    renderedCount += 1;
  }
  offersCaption.textContent = productCount + " товаров · " + offerCount + " предложений";
  count.textContent = productCount + " товаров";
  return renderedCount;
}
function renderDetailFields(data, fallbackOffer) {
  const details = data || fallbackOffer || {};
  const description = details.description || "Описание не опубликовано в доступной разметке карточки.";
  document.querySelector("#detail-description").textContent = description;
  const rating = Number(details.rating);
  document.querySelector("#detail-rating").textContent =
    Number.isFinite(rating) && rating > 0 ? rating.toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + " из 5" : "Нет данных";
  const hasReviewCount = details.review_count !== null && details.review_count !== undefined && details.review_count !== "";
  const reviews = Number(details.review_count);
  document.querySelector("#detail-reviews").textContent =
    hasReviewCount && Number.isFinite(reviews) && reviews >= 0 ? reviews.toLocaleString("ru-RU") : "Нет данных";

  const specs = document.querySelector("#detail-specs");
  specs.replaceChildren();
  for (const item of Array.isArray(details.specifications) ? details.specifications : []) {
    if (!item || !item.name || !item.value) continue;
    specs.append(element("dt", "", item.name), element("dd", "", item.value));
  }
  if (!specs.childElementCount) specs.append(
    element("dt", "detail-muted", "Сведения"),
    element("dd", "detail-muted", "Характеристики не опубликованы.")
  );

  const reviewList = document.querySelector("#detail-review-list");
  reviewList.replaceChildren();
  const reviewEntries = Array.isArray(details.reviews) ? details.reviews.slice(0, 10) : [];
  for (const review of reviewEntries) {
    if (!review || !review.body) continue;
    const card = element("article", "detail-review");
    const header = element("div", "detail-review-head");
    header.append(element("strong", "", review.author || "Покупатель"));
    const meta = [review.rating ? `★ ${review.rating}` : "", review.date || ""].filter(Boolean).join(" · ");
    if (meta) header.append(element("span", "", meta));
    card.append(header, element("p", "", review.body));
    reviewList.append(card);
  }
  if (!reviewList.childElementCount) {
    reviewList.append(element("p", "detail-muted", "Публичные тексты отзывов не найдены."));
  }
}

async function openProductDetails(offer) {
  const requestSequence = ++detailRequestSequence;
  const title = offer.title || "Товар";
  document.querySelector("#detail-market").textContent = offer.marketplace || "Маркетплейс";
  document.querySelector("#detail-title").textContent = title;
  document.querySelector("#detail-price-value").textContent = money(offer.price, offer.currency);
  const link = document.querySelector("#detail-link");
  link.href = offer.url;
  const image = document.querySelector("#detail-image");
  image.hidden = !offer.image_url;
  if (offer.image_url) image.src = offer.image_url;
  else image.removeAttribute("src");
  image.alt = title;
  document.querySelector("#detail-status").textContent = "Загружаем доступные сведения о товаре…";
  renderDetailFields(offer, offer);
  productDialog.showModal();

  const params = new URLSearchParams({ marketplace: offer.marketplace, product_url: offer.url });
  try {
    const response = await fetch("/api/product-details?" + params, {
      headers: { Accept: "application/json" }
    });
    const data = await response.json();
    if (requestSequence !== detailRequestSequence) return;
    if (!response.ok) throw new Error(data.detail || "Не удалось загрузить подробности.");
    renderDetailFields(data.details_available ? data : offer, offer);
    document.querySelector("#detail-status").textContent = data.details_available
      ? "Данные прочитаны из доступной публичной разметки карточки."
      : (data.message || "Подробные поля не найдены на публичной странице.");
  } catch (error) {
    if (requestSequence !== detailRequestSequence) return;
    renderDetailFields(offer, offer);
    document.querySelector("#detail-status").textContent = error.message || "Не удалось загрузить подробности.";
  }
}

document.querySelector("#detail-close").addEventListener("click", () => productDialog.close());

async function fetchPage(offset, append, sequence = searchSequence, displayLimit = DEFAULT_PAGE_SIZE) {
  const query = activeQuery;
  const params = new URLSearchParams({
    q: query, limit: "20", offset: String(offset), session_id: activeSearchId
  });
  const response = await fetch("/api/search?" + params, { headers: { Accept: "application/json" } });
  const data = await response.json();
  if (sequence !== searchSequence) return null;
  if (!response.ok) throw new Error(data.detail || "Не удалось выполнить поиск.");
  const responseProducts = data.products || [];
  const pageProducts = responseProducts.slice(0, displayLimit);
  let renderedCount = 0;
  if (!append) {
    title.textContent = "Результаты для «" + data.query + "»";
    renderProviders(data.providers);
    renderedCount = renderOffers(pageProducts, activeQuery, false);
    emptyState.hidden = Boolean(responseProducts.length);
    if (!responseProducts.length) {
      emptyState.querySelector("strong").textContent = "Товары не найдены";
      emptyState.querySelector("span").textContent = "Открой площадку или подключи разрешённый источник данных.";
    }
    message(notice, data.notice);
  } else {
    renderedCount = renderOffers(pageProducts, activeQuery, true);
  }
  // Advance by consumed results, even if the browser skipped a duplicate card.
  nextOffset = data.offset + pageProducts.length;
  const hasBufferedProducts = responseProducts.length > pageProducts.length;
  const retryableEmptyPage = data.retryable && !responseProducts.length;
  moreButton.hidden = retryableEmptyPage
    ? false
    : (!pageProducts.length || (!hasBufferedProducts && !data.has_more));
  if (append) {
    message(notice, data.retryable
      ? "Источник временно не ответил. Найденные товары сохранены — нажмите кнопку ещё раз, чтобы повторить загрузку."
      : "");
  }
  // total_products only reflects every product that exists once every
  // provider has run dry; otherwise the backend only probed one item past
  // the current page, so DEFAULT_PAGE_SIZE is the only honest guess.
  const remaining = data.exact_total ? Math.max(0, (data.total_products ?? 0) - nextOffset) : 0;
  const nextBatch = remaining > 0 ? Math.min(DEFAULT_PAGE_SIZE, remaining) : DEFAULT_PAGE_SIZE;
  moreButton.textContent = data.retryable
    ? "Повторить загрузку"
    : `Показать ещё ${nextBatch} ${productsWord(nextBatch)}`;
  return {
    loaded: renderedCount,
    consumed: pageProducts.length,
    moreAvailable: !moreButton.hidden
  };
}
async function topUpPage(firstPage, sequence) {
  let loaded = firstPage?.loaded || 0;
  let moreAvailable = Boolean(firstPage?.moreAvailable);
  let retryDelay = INITIAL_PAGE_FILL_RETRY_MS;
  while (
    loaded < DEFAULT_PAGE_SIZE
    && moreAvailable
    && sequence === searchSequence
  ) {
    moreButton.textContent = "Жду товары…";
    message(notice, `Добавлено ${loaded} из ${DEFAULT_PAGE_SIZE}. Жду следующие карточки…`);
    await new Promise(resolve => setTimeout(resolve, retryDelay));
    if (sequence !== searchSequence) break;

    try {
      moreButton.textContent = "Загружаем…";
      const page = await fetchPage(nextOffset, true, sequence, DEFAULT_PAGE_SIZE - loaded);
      if (!page) break;
      moreAvailable = page.moreAvailable;
      if (page.loaded > 0) {
        loaded += page.loaded;
        retryDelay = INITIAL_PAGE_FILL_RETRY_MS;
      } else {
        retryDelay = Math.min(retryDelay * 2, MAX_PAGE_FILL_RETRY_MS);
      }
    } catch (error) {
      message(notice, `Добавлено ${loaded} из ${DEFAULT_PAGE_SIZE}. ${error.message} Повторяю запрос…`);
      retryDelay = Math.min(retryDelay * 2, MAX_PAGE_FILL_RETRY_MS);
    }
  }
  if (sequence === searchSequence && loaded > 0 && loaded < DEFAULT_PAGE_SIZE && !moreAvailable) {
    message(notice, `Площадки вернули ${loaded} из ${DEFAULT_PAGE_SIZE} доступных карточек.`);
  }
}
async function runSearch(query) {
  activeQuery = query.trim();
  if (!activeQuery) return;
  activeSearchId = newSearchSessionId();
  nextOffset = 0;
  const sequence = ++searchSequence;
  input.value = activeQuery;
  button.disabled = true;
  button.textContent = "Ищем…";
  title.textContent = "Ищем «" + activeQuery + "»";
  emptyState.hidden = true;
  offersWrap.hidden = true;
  moreButton.hidden = true;
  message(notice, "");
  providerGrid.replaceChildren(element("div", "loading-card", "Ищем на трёх площадках…"));
  try {
    const firstPage = await fetchPage(0, false, sequence);
    if (firstPage) await topUpPage(firstPage, sequence);
  } catch (error) {
    providerGrid.replaceChildren();
    title.textContent = "Поиск не выполнен";
    emptyState.hidden = false;
    emptyState.querySelector("strong").textContent = "Не удалось выполнить поиск";
    emptyState.querySelector("span").textContent = error.message || "Попробуй ещё раз.";
  } finally {
    if (sequence === searchSequence) {
      button.disabled = false;
      button.textContent = "Найти →";
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
moreButton.addEventListener("click", async () => {
  moreButton.disabled = true;
  const labelBeforeClick = moreButton.textContent;
  moreButton.textContent = "Загружаем…";
  const sequence = searchSequence;
  try {
    const firstPage = await fetchPage(nextOffset, true, sequence);
    if (firstPage) await topUpPage(firstPage, sequence);
  } catch (error) {
    message(notice, error.message);
    moreButton.textContent = labelBeforeClick;
  } finally {
    moreButton.disabled = false;
  }
});
