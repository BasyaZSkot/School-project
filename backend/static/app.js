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
  access_required: { label: "Нужен источник", className: "status-warn" },
  disabled: { label: "Временно выключен", className: "status-neutral" },
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
    const productPage = element("a", "details-button", "Подробнее о товаре →");
    const productSummary = {
      title: product.title || "Товар",
      offers: offers.map(offer => ({
        marketplace: offer.marketplace,
        title: offer.title,
        price: offer.price,
        currency: offer.currency,
        url: offer.url,
        image_url: offer.image_url,
        external_id: offer.external_id,
        in_stock: offer.in_stock
      }))
    };
    productPage.href = "/product?data=" + encodeURIComponent(JSON.stringify(productSummary));
    card.append(productPage);
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
function updateMoreButton() {
  const remaining = Math.max(0, bufferedProducts.length - displayedProductCount);
  moreButton.hidden = remaining === 0;
  if (remaining > 0) {
    const nextBatch = Math.min(DISPLAY_BATCH_SIZE, remaining);
    moreButton.textContent = "Показать ещё " + nextBatch + " " + productsWord(nextBatch);
  }
}
function revealNextProducts() {
  const start = displayedProductCount;
  const end = Math.min(start + DISPLAY_BATCH_SIZE, bufferedProducts.length);
  if (end <= start) {
    updateMoreButton();
    return 0;
  }
  const batch = bufferedProducts.slice(start, end);
  const rendered = renderOffers(batch, activeQuery, start > 0);
  displayedProductCount = end;
  updateMoreButton();
  return rendered;
}
async function fetchSearchResults(sequence = searchSequence) {
  const params = new URLSearchParams({
    q: activeQuery,
    limit: String(MAX_BUFFERED_RESULTS),
    offset: "0"
  });
  const response = await fetch("/api/search?" + params, {
    headers: { Accept: "application/json" }
  });
  const data = await response.json();
  if (sequence !== searchSequence) return null;
  if (!response.ok) throw new Error(data.detail || "Не удалось выполнить поиск.");

  bufferedProducts = Array.isArray(data.products) ? data.products : [];
  displayedProductCount = 0;
  title.textContent = "Результаты для «" + data.query + "»";
  renderProviders(data.providers);
  const firstBatch = bufferedProducts.slice(0, DISPLAY_BATCH_SIZE);
  renderOffers(firstBatch, activeQuery, false);
  displayedProductCount = firstBatch.length;
  emptyState.hidden = Boolean(bufferedProducts.length);
  if (!bufferedProducts.length) {
    emptyState.querySelector("strong").textContent = "Товары не найдены";
    emptyState.querySelector("span").textContent = "Открой площадку или подключи разрешённый источник данных.";
  }

  if ((data.total_products ?? 0) >= MAX_BUFFERED_RESULTS && !data.exact_total) {
    message(notice, "Яндекс Маркет вернул первые 200 доступных карточек. Возможно, у запроса есть следующие страницы.");
  } else {
    message(notice, data.notice);
  }
  updateMoreButton();
  return data;
}
async function runSearch(query) {
  activeQuery = query.trim();
  if (!activeQuery) return;
  bufferedProducts = [];
  displayedProductCount = 0;
  const sequence = ++searchSequence;
  input.value = activeQuery;
  button.disabled = true;
  button.textContent = "Ищем…";
  title.textContent = "Ищем «" + activeQuery + "»";
  emptyState.hidden = true;
  offersWrap.hidden = true;
  moreButton.hidden = true;
  message(notice, "");
  providerGrid.replaceChildren(element("div", "loading-card", "Ищем до 200 товаров на Яндекс Маркете…"));
  try {
    await fetchSearchResults(sequence);
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
moreButton.addEventListener("click", () => {
  if (moreButton.hidden) return;
  moreButton.disabled = true;
  moreButton.textContent = "Показываем…";
  revealNextProducts();
  moreButton.disabled = false;
});

