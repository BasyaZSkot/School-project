const list = document.querySelector("#history-list");
const note = document.querySelector("#page-message");
const title = document.querySelector("#history-title");
const selectedId = new URLSearchParams(location.search).get("monitor_id");
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
function showNote(text) {
  note.hidden = !text;
  note.querySelector("p").textContent = text || "";
}
function formatPrice(value, currency) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency", currency: currency || "RUB", maximumFractionDigits: 2
  }).format(value);
}
function chart(points) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 600 120");
  svg.setAttribute("class", "history-chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "График изменения цены");
  if (points.length < 2) return svg;
  const values = points.map(point => Number(point.price));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const coords = values.map((value, index) => {
    const x = 8 + index * 584 / (values.length - 1);
    const y = 108 - (value - min) * 96 / span;
    return x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", coords);
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", "#6558e8");
  line.setAttribute("stroke-width", "3");
  line.setAttribute("stroke-linecap", "round");
  line.setAttribute("stroke-linejoin", "round");
  svg.append(line);
  return svg;
}
function renderHistory(monitor, points) {
  const card = el("article", "history-card");
  const head = el("div", "history-card-head");
  const info = el("div", "");
  info.append(el("h3", "", monitor.title));
  info.append(el("p", "muted", monitor.marketplace + " · " + points.length + " проверок"));
  head.append(info);
  const open = el("a", "button button-secondary", "Открыть товар ↗");
  open.href = monitor.product_url;
  open.target = "_blank";
  open.rel = "noopener noreferrer";
  head.append(open);
  card.append(head);
  if (points.length >= 2) card.append(chart(points));
  if (!points.length) {
    card.append(el("div", "empty-panel", "История появится после успешной проверки источника."));
  } else {
    const table = document.createElement("div");
    table.className = "history-table";
    points.slice().reverse().slice(0, 12).forEach(point => {
      const row = el("div", "history-row");
      row.append(
        el("span", "", new Date(point.captured_at).toLocaleString("ru-RU")),
        el("strong", "", formatPrice(point.price, point.currency))
      );
      table.append(row);
    });
    card.append(table);
  }
  return card;
}
async function loadHistory() {
  try {
    const monitorsResponse = await fetch("/api/monitors");
    const monitorData = await monitorsResponse.json();
    if (!monitorsResponse.ok) throw new Error(monitorData.detail || "Не удалось загрузить товары.");
    let monitors = monitorData.monitors || [];
    if (selectedId) monitors = monitors.filter(monitor => monitor.id === selectedId);
    title.textContent = selectedId && monitors.length ? monitors[0].title : "История всех товаров";
    if (!monitors.length) {
      const empty = el("div", "empty-panel");
      empty.append(el("strong", "", "История начинается с первого товара"),
        el("span", "", "Добавьте товар из поиска. Его цена сохранится после успешной проверки."));
      const search = el("a", "button button-primary", "Найти товар");
      search.href = "/";
      empty.append(search);
      list.replaceChildren(empty);
      return;
    }
    const histories = await Promise.all(monitors.map(async monitor => {
      const response = await fetch("/api/monitors/" + monitor.id + "/history?limit=200");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Не удалось загрузить историю товара.");
      return renderHistory(monitor, data.points || []);
    }));
    list.replaceChildren(...histories);
  } catch (error) {
    showNote(error.message || "Не удалось загрузить историю.");
  }
}
document.querySelector("#refresh-history").addEventListener("click", loadHistory);
loadHistory();
