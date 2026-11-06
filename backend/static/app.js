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
const monitorList = document.querySelector("#monitor-list");
const monitorNotice = document.querySelector("#monitor-notice");

const providerMeta = {
  "Ozon": { logo: "O", className: "ozon-logo" },
  "Wildberries": { logo: "WB", className: "wb-logo" },
  "Яндекс Маркет": { logo: "Я", className: "ym-logo" }
};
const statusMeta = {
  access_required: { label: "Нет данных", className: "status-warn" },
  policy_restricted: { label: "Нет данных", className: "status-warn" },
  ready: { label: "Карточки найдены", className: "status-good" },
  no_results: { label: "Нет карточек", className: "status-warn" },
  error: { label: "Не ответил", className: "status-error" }
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
function showMessage(node, message) {
  node.hidden = !message;
  node.querySelector("p").textContent = message || "";
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
    card.append(top, makeElement("h3", "", provider.marketplace));
    if (provider.message) card.append(makeElement("p", "provider-message", provider.message));
    if (provider.search_url) {
      const link = makeElement("a", "provider-link", "Открыть поиск на сайте ↗");
      link.href = provider.search_url; link.target = "_blank"; link.rel = "noopener noreferrer"; card.append(link);
    }
    providerGrid.append(card);
  }
  count.textContent = `${providers.length} площадки`;
}
async function addMonitor(offer, query) {
  const response = await fetch("/api/monitors", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, product_url: offer.url, marketplace: offer.marketplace, title: offer.title, interval_seconds: 3600 })
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Не удалось добавить монитор.");
  await loadMonitors();
  showMessage(monitorNotice, "Товар добавлен в мониторинг.");
}
function renderOffers(products = [], query = "") {
  offersList.replaceChildren();
  if (!products.length) { offersWrap.hidden = true; return; }
  offersWrap.hidden = false;
  let offerCount = 0;
  for (const product of products) {
    const card = makeElement("article", "offer-card");
    const heading = makeElement("div", "offer-product-head");
    const firstImage = (product.offers || []).find(item => item.image_url)?.image_url;
    if (firstImage && firstImage.startsWith("https://")) {
      const image = makeElement("img", "offer-product-image");
      image.src = firstImage; image.alt = product.title || "Фото товара"; image.loading = "lazy";
      image.referrerPolicy = "no-referrer"; heading.append(image);
    }
    heading.append(makeElement("h4", "", product.title || "Товар"));
    card.append(heading);
    const list = makeElement("div", "offer-rows");
    for (const offer of product.offers || []) {
      offerCount += 1;
      const row = makeElement("div", "offer-row");
      const info = makeElement("div", "offer-info");
      info.append(makeElement("strong", "", offer.marketplace), makeElement("span", "", offer.title));
      const price = makeElement("strong", "offer-price",
        new Intl.NumberFormat("ru-RU", { style: "currency", currency: offer.currency || "RUB", maximumFractionDigits: 0 }).format(offer.price));
      row.append(info, price);
      const actions = makeElement("div", "offer-actions");
      if (offer.url) {
        const link = makeElement("a", "offer-open", "К товару ↗");
        link.href = offer.url; link.target = "_blank"; link.rel = "noopener noreferrer"; actions.append(link);
        const watch = makeElement("button", "watch-button", "Следить за ценой");
        watch.type = "button";
        watch.addEventListener("click", async () => {
          watch.disabled = true; watch.textContent = "Добавляем…";
          try { await addMonitor(offer, query); watch.textContent = "Добавлено"; }
          catch (error) { watch.disabled = false; watch.textContent = "Следить за ценой"; showMessage(monitorNotice, error.message); }
        });
        actions.append(watch);
      }
      row.append(actions); list.append(row);
    }
    card.append(list); offersList.append(card);
  }
  offersCaption.textContent = `${offerCount} предложений`;
}
async function runSearch(query) {
  const cleanQuery = query.trim();
  if (!cleanQuery) { input.focus(); return; }
  input.value = cleanQuery; setLoading(true);
  title.textContent = `Ищем «${cleanQuery}»`;
  emptyState.hidden = true; offersWrap.hidden = true; showMessage(notice, "");
  providerGrid.replaceChildren(makeElement("div", "loading-card", "Ищем товары на Ozon, Wildberries и Яндекс Маркете…"));
  try {
    const response = await fetch(`/api/search?${new URLSearchParams({ q: cleanQuery, limit: "20" })}`, { headers: { "Accept": "application/json" } });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось выполнить поиск.");
    title.textContent = `Результаты для «${data.query}»`;
    renderProviders(data.providers || []); renderOffers(data.products || [], cleanQuery);
    emptyState.hidden = Boolean((data.products || []).length);
    if (!(data.products || []).length) {
      emptyState.querySelector("strong").textContent = "Товары пока не найдены";
      emptyState.querySelector("span").textContent = "Площадки не вернули карточки для этого запроса. Попробуй другое название.";
    }
    showMessage(notice, data.notice);
  } catch (error) {
    title.textContent = "Не удалось выполнить поиск"; providerGrid.replaceChildren();
    emptyState.hidden = false; emptyState.querySelector("strong").textContent = "Поиск временно недоступен";
    emptyState.querySelector("span").textContent = error.message || "Сервер пока не отвечает.";
    showMessage(notice, "Попробуй повторить поиск позже.");
  } finally { setLoading(false); }
}
async function loadMonitors() {
  try {
    const response = await fetch("/api/monitors");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось загрузить мониторы.");
    monitorList.replaceChildren();
    if (!data.monitors.length) {
      monitorList.append(makeElement("div", "monitor-empty", "Пока нет отслеживаемых товаров. Добавь товар из результатов поиска."));
      return;
    }
    for (const monitor of data.monitors) {
      const card = makeElement("article", "monitor-card");
      const info = makeElement("div", "monitor-info");
      info.append(makeElement("strong", "", monitor.title));
      const priceText = monitor.current_price == null ? "Цена ещё не получена" :
        new Intl.NumberFormat("ru-RU", { style: "currency", currency: monitor.currency || "RUB", maximumFractionDigits: 2 }).format(monitor.current_price);
      info.append(makeElement("span", "", `${monitor.marketplace} · ${priceText} · ${monitor.last_status}`));
      card.append(info);
      const controls = makeElement("div", "monitor-controls");
      const toggle = makeElement("button", "small-button", monitor.active ? "Пауза" : "Продолжить");
      toggle.type = "button";
      toggle.addEventListener("click", async () => {
        await fetch(`/api/monitors/${monitor.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active: !monitor.active }) });
        await loadMonitors();
      });
      const history = makeElement("button", "small-button", "История");
      history.type = "button";
      history.addEventListener("click", async () => {
        const res = await fetch(`/api/monitors/${monitor.id}/history`);
        const payload = await res.json();
        const points = payload.points || [];
        showMessage(monitorNotice, points.length ? "История: " + points.map(p => new Date(p.captured_at).toLocaleString("ru-RU") + " — " + p.price + " " + p.currency).join(" · ") : "История пока пуста. Она появится после успешной проверки источника.");
      });
      const remove = makeElement("button", "small-button danger-button", "Удалить");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        await fetch(`/api/monitors/${monitor.id}`, { method: "DELETE" }); await loadMonitors();
      });
      controls.append(toggle, history, remove); card.append(controls); monitorList.append(card);
    }
  } catch (error) { showMessage(monitorNotice, error.message); }
}
form.addEventListener("submit", event => { event.preventDefault(); runSearch(input.value); });
document.querySelectorAll(".example-query").forEach(button => button.addEventListener("click", () => runSearch(button.textContent)));
document.querySelector("#refresh-monitors").addEventListener("click", loadMonitors);
loadMonitors();
