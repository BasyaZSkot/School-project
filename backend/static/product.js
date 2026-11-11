const marketplaceHosts = {
  Ozon: ["ozon.ru"],
  Wildberries: ["wildberries.ru", "wildberries.by", "wildberries.kz"],
  "Яндекс Маркет": ["market.yandex.ru"]
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function validProductUrl(marketplace, value) {
  try {
    const url = new URL(value);
    const hosts = marketplaceHosts[marketplace] || [];
    return url.protocol === "https:" && (!url.port || url.port === "443") &&
      hosts.some(host => url.hostname === host || url.hostname.endsWith("." + host));
  } catch {
    return false;
  }
}
function money(value, currency) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) return "Цена не указана";
  try {
    return new Intl.NumberFormat("ru-RU", {
      style: "currency", currency: currency || "RUB", maximumFractionDigits: 2
    }).format(amount);
  } catch {
    return amount.toLocaleString("ru-RU") + " " + (currency || "RUB");
  }
}
function showSpecs(items) {
  const list = document.querySelector("#product-specs");
  list.replaceChildren();
  for (const item of Array.isArray(items) ? items : []) {
    if (!item || !item.name || !item.value) continue;
    list.append(element("dt", "", item.name), element("dd", "", item.value));
  }
  if (!list.childElementCount) {
    list.append(element("dt", "detail-muted", "Сведения"), element("dd", "detail-muted", "Характеристики не опубликованы."));
  }
}
function showReviews(items) {
  const list = document.querySelector("#product-reviews");
  list.replaceChildren();
  for (const review of Array.isArray(items) ? items.slice(0, 10) : []) {
    if (!review || !review.body) continue;
    const card = element("article", "detail-review");
    const header = element("div", "detail-review-head");
    header.append(element("strong", "", review.author || "Покупатель"));
    const meta = [review.rating ? `★ ${review.rating}` : "", review.date || ""].filter(Boolean).join(" · ");
    if (meta) header.append(element("span", "", meta));
    card.append(header, element("p", "", review.body));
    list.append(card);
  }
  if (!list.childElementCount) list.append(element("p", "detail-muted", "Публичные тексты отзывов не найдены."));
}
function showDetails(details) {
  document.querySelector("#product-description").textContent =
    details.description || "Описание не опубликовано в доступной разметке карточки.";
  const rating = Number(details.rating);
  document.querySelector("#product-rating").textContent =
    Number.isFinite(rating) && rating > 0
      ? rating.toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + " из 5"
      : "Нет данных";
  const hasReviewCount = details.review_count !== null && details.review_count !== undefined && details.review_count !== "";
  const reviewCount = Number(details.review_count);
  document.querySelector("#product-review-count").textContent =
    hasReviewCount && Number.isFinite(reviewCount) && reviewCount >= 0
      ? reviewCount.toLocaleString("ru-RU") + " отзывов и оценок"
      : "Количество отзывов не указано";
  showSpecs(details.specifications);
  showReviews(details.reviews);
}

function readProduct() {
  const raw = new URLSearchParams(window.location.search).get("data");
  if (!raw || raw.length > 16000) return null;
  try {
    const product = JSON.parse(raw);
    if (!product || typeof product.title !== "string" || !Array.isArray(product.offers)) return null;
    const offers = product.offers.filter(offer =>
      offer && typeof offer.marketplace === "string" && validProductUrl(offer.marketplace, offer.url)
    ).slice(0, 12);
    return offers.length ? { title: product.title.slice(0, 300), offers } : null;
  } catch {
    return null;
  }
}

async function loadProduct() {
  const product = readProduct();
  const title = document.querySelector("#product-title");
  const status = document.querySelector("#product-status");
  if (!product) {
    title.textContent = "Карточка товара недоступна";
    status.textContent = "Вернитесь к поиску и откройте страницу товара из списка результатов.";
    document.querySelector("#product-description").textContent = "Нет данных.";
    showSpecs([]);
    showReviews([]);
    return;
  }

  document.title = product.title + " — MultiMarket";
  title.textContent = product.title;
  const marketplaces = [...new Set(product.offers.map(offer => offer.marketplace))];
  const chips = document.querySelector("#product-marketplaces");
  for (const marketplace of marketplaces) chips.append(element("span", "marketplace-chip", marketplace));
  const imageUrl = product.offers.find(offer => typeof offer.image_url === "string" && offer.image_url.startsWith("https://"))?.image_url;
  if (imageUrl) {
    const image = document.querySelector("#product-image");
    image.src = imageUrl;
    image.alt = product.title;
    document.querySelector("#product-image-wrap").hidden = false;
  } else {
    document.querySelector(".product-detail-hero").classList.add("no-product-image");
  }
  const bestByCurrency = new Map();
  for (const offer of product.offers) {
    const amount = Number(offer.price);
    if (!Number.isFinite(amount) || amount <= 0) continue;
    const currency = offer.currency || "RUB";
    bestByCurrency.set(currency, Math.min(bestByCurrency.get(currency) ?? amount, amount));
  }
  if (bestByCurrency.size) {
    document.querySelector("#product-best-price").textContent = "Лучшая доступная цена — " +
      [...bestByCurrency].map(([currency, amount]) => money(amount, currency)).join(" · ");
    document.querySelector("#product-best-price").hidden = false;
  }

  const offerList = document.querySelector("#product-offers");
  offerList.replaceChildren();
  for (const offer of product.offers) {
    const card = element("article", "product-offer-card");
    const info = element("div", "product-offer-info");
    info.append(element("strong", "", offer.marketplace));
    if (offer.title && offer.title !== product.title) info.append(element("span", "", offer.title));
    if (offer.in_stock === true) info.append(element("span", "stock-badge", "В наличии"));
    if (offer.in_stock === false) info.append(element("span", "stock-badge stock-badge-empty", "Нет в наличии"));
    const controls = element("div", "product-offer-controls");
    controls.append(element("strong", "product-offer-price", money(offer.price, offer.currency)));
    const link = element("a", "button button-primary", "Открыть на площадке ↗");
    link.href = offer.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    controls.append(link);
    card.append(info, controls);
    offerList.append(card);
  }

  showDetails({});
  status.textContent = "Загружаем описания, характеристики и оценки из доступных карточек…";
  const detailResults = await Promise.all(product.offers.map(async offer => {
    const params = new URLSearchParams({ marketplace: offer.marketplace, product_url: offer.url });
    try {
      const response = await fetch("/api/product-details?" + params, { headers: { Accept: "application/json" } });
      const data = await response.json();
      return response.ok && data.details_available ? { marketplace: offer.marketplace, data } : null;
    } catch {
      return null;
    }
  }));
  const result = detailResults.find(Boolean);
  if (result) {
    showDetails(result.data);
    status.textContent = "Подробности прочитаны из доступной публичной карточки на площадке «" + result.marketplace + "».";
  } else {
    status.textContent = "Площадки не опубликовали дополнительные сведения в доступной разметке. Цены и ссылки остаются доступными.";
  }
}

loadProduct();

