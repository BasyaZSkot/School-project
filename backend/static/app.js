const form = document.querySelector("#search-form");
const input = document.querySelector("#search-input");
const searchButton = document.querySelector("#search-button");
const title = document.querySelector("#results-title");
const count = document.querySelector("#result-count");
const providerGrid = document.querySelector("#provider-grid");
const emptyState = document.querySelector("#empty-state");
const notice = document.querySelector("#notice");
const offersWrap = document.querySelector("#offers-wrap");
const offersList = document.querySelector("#offers-list");
const offersCaption = document.querySelector("#offers-caption");

const providerMeta = {
  "Ozon": { logo: "O", className: "ozon-logo" },
  "Wildberries": { logo: "WB", className: "wb-logo" },
  "Яндекс Маркет": { logo: "Я", className: "ym-logo" }
};

const statusMeta = {
  access_required: { label: "Нужен доступ", className: "status-warn" },
  policy_restricted: { label: "Ограничен правилами", className: "status-warn" },
  ready: { label: "Подключён", className: "status-good" },
  error: { label: "Временно недоступен", className: "status-error" }
};

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function setLoading(loading) {
  searchButton.disabled = loading;
  searchButton.innerHTML = loading ? '<span class="spinner"></span><span>Ищем…</span>' : '<span>Найти</span><span aria-hidden="true">→</span>';
  input.disabled = loading;
}

function renderProviders(providers = []) {
  providerGrid.replaceChildren();
  for (const provider of providers) {
    const meta = providerMeta[provider.marketplace] || { logo: "?", className: "" };
    const status = statusMeta[provider.status] || statusMeta.error;
    const card = makeElement("article", "provider-card");
    const top = makeElement("div", "provider-top");
    top.append(makeElement("span", `provider-logo ${meta.className}`, meta.logo));
    top.append(makeElement("span", `status ${status.className}`, status.label));
    card.append(top);
    card.append(makeElement("h3", "", provider.marketplace));
    card.append(makeElement("p", "", provider.message || "Источник проверен."));
    if (provider.search_url) {
      const link = makeElement("a", "provider-link", "Открыть поиск на сайте ↗");
      link.href = provider.search_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      card.append(link);
    }
    providerGrid.append(card);
  }
  count.textContent = `${providers.length} площадки`;
}

function renderOffers(products = []) {
  offersList.replaceChildren();
  if (!products.length) {
    offersWrap.hidden = true;
    return;
  }
  offersWrap.hidden = false;
  let offerCount = 0;
  for (const product of products) {
    const card = makeElement("article", "offer-card");
    card.append(makeElement("h4", "", product.title || "Товар"));
    const list = makeElement("div", "offer-rows");
    for (const offer of product.offers || []) {
      offerCount += 1;
      const row = makeElement("div", "offer-row");
      const info = makeElement("div", "offer-info");
      info.append(makeElement("strong", "", offer.marketplace));
      info.append(makeElement("span", "", offer.title));
      const price = makeElement("strong", "offer-price",
        new Intl.NumberFormat("ru-RU", { style: "currency", currency: offer.currency || "RUB", maximumFractionDigits: 0 }).format(offer.price));
      row.append(info, price);
      if (offer.url) {
        const link = makeElement("a", "offer-open", "К товару ↗");
        link.href = offer.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        row.append(link);
      }
      list.append(row);
    }
    card.append(list);
    offersList.append(card);
  }
  offersCaption.textContent = `${offerCount} предложений`;
}

function showNotice(message) {
  notice.hidden = !message;
  notice.querySelector("p").textContent = message || "";
}

async function runSearch(query) {
  const cleanQuery = query.trim();
  if (!cleanQuery) {
    input.focus();
    return;
  }
  input.value = cleanQuery;
  setLoading(true);
  title.textContent = `Ищем «${cleanQuery}»`;
  emptyState.hidden = true;
  offersWrap.hidden = true;
  showNotice("");
  providerGrid.replaceChildren(makeElement("div", "loading-card", "Проверяем площадки…"));
  try {
    const response = await fetch(`/api/search?${new URLSearchParams({ q: cleanQuery, limit: "20" })}`, {
      headers: { "Accept": "application/json" }
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось выполнить поиск.");
    title.textContent = `Результаты для «${data.query}»`;
    renderProviders(data.providers || []);
    renderOffers(data.products || []);
    emptyState.hidden = Boolean((data.products || []).length);
    if (!(data.products || []).length) {
      emptyState.querySelector("strong").textContent = "Пока нет объединённых предложений";
      emptyState.querySelector("span").textContent = "Открой поиск на нужной площадке по ссылке выше.";
    }
    showNotice(data.notice);
  } catch (error) {
    title.textContent = "Не удалось выполнить поиск";
    providerGrid.replaceChildren();
    emptyState.hidden = false;
    emptyState.querySelector("strong").textContent = "Сервер пока не отвечает";
    emptyState.querySelector("span").textContent = error.message || "Проверь, запущен ли Backend.";
    showNotice("Запусти Backend командой из инструкции в README.");
  } finally {
    setLoading(false);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch(input.value);
});

document.querySelectorAll(".example-query").forEach((button) => {
  button.addEventListener("click", () => runSearch(button.textContent));
});
