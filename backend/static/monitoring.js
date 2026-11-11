const list = document.querySelector("#monitor-list");
const note = document.querySelector("#page-message");
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
function priceText(value, currency) {
  if (value == null) return "Цена ещё не получена";
  return new Intl.NumberFormat("ru-RU", {
    style: "currency", currency: currency || "RUB", maximumFractionDigits: 2
  }).format(value);
}
async function loadMonitors() {
  try {
    const response = await fetch("/api/monitors");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось загрузить мониторинг.");
    list.replaceChildren();
    if (!data.monitors.length) {
      list.append(el("div", "empty-panel", "Пока нет отслеживаемых товаров. Добавь товар из поиска."));
      return;
    }
    data.monitors.forEach(monitor => {
      const card = el("article", "monitor-card");
      const info = el("div", "monitor-info");
      info.append(el("h3", "", monitor.title));
      info.append(el("p", "", monitor.marketplace + " · " + priceText(monitor.current_price, monitor.currency)));
      const status = el("span", "monitor-status", "Статус: " + monitor.last_status);
      info.append(status);
      const controls = el("div", "monitor-controls");
      const history = el("a", "button button-secondary", "История");
      history.href = "/history?monitor_id=" + encodeURIComponent(monitor.id);
      const toggle = el("button", "button button-secondary", monitor.active ? "Пауза" : "Продолжить");
      toggle.type = "button";
      toggle.addEventListener("click", async () => {
        await fetch("/api/monitors/" + monitor.id, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active: !monitor.active })
        });
        await loadMonitors();
      });
      const remove = el("button", "button button-danger", "Удалить");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        await fetch("/api/monitors/" + monitor.id, { method: "DELETE" });
        await loadMonitors();
      });
      const productLink = el("a", "button button-primary", "Открыть товар ↗");
      productLink.href = monitor.product_url;
      productLink.target = "_blank";
      productLink.rel = "noopener noreferrer";
      controls.append(history, toggle, remove, productLink);
      card.append(info, controls);
      list.append(card);
    });
  } catch (error) {
    showNote(error.message || "Не удалось загрузить мониторинг.");
  }
}
document.querySelector("#refresh-monitors").addEventListener("click", loadMonitors);
loadMonitors();
