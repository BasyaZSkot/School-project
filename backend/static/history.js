const H = window.MultiMarketHistory;
const list = document.querySelector("#history-list");
const note = document.querySelector("#page-message");
const title = document.querySelector("#history-title");
const selectedId = new URLSearchParams(location.search).get("monitor_id");
let loadRun = 0;
const chartObservers = new Set();
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
function money(value, currency) {
  return new Intl.NumberFormat("ru-RU", {style: "currency", currency, maximumFractionDigits: 2}).format(value);
}
function date(value) { return new Date(value).toLocaleString("ru-RU", {day:"numeric", month:"short", year:"numeric", hour:"2-digit", minute:"2-digit"}); }
function changeText(change) {
  if (!change) return "Недостаточно данных";
  if (change.amount === 0) return "Без изменений · 0 %";
  const sign = change.amount < 0 ? "−" : "+";
  const percent = new Intl.NumberFormat("ru-RU", {maximumFractionDigits: 2}).format(Math.abs(change.percent));
  return (change.amount < 0 ? "↓ " : "↑ ") + sign + money(Math.abs(change.amount), change.currency) + " (" + sign + percent + " %)";
}
function changeClass(change) { return change?.amount < 0 ? "price-down" : change?.amount > 0 ? "price-up" : "price-neutral"; }
function svgNode(tag, attrs = {}, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function priceChart(points, allPoints, currency, host) {
  const wrap = el("div", "history-plot"), readout = el("div", "history-point-readout");
  readout.setAttribute("aria-live", "polite");
  const graphic = el("div", "history-graphic");
  const sliderLabel = el("label", "history-slider-label", "Выбрать проверку на графике");
  const slider = el("input", "history-slider");
  slider.type = "range"; slider.min = "0"; slider.max = String(points.length - 1); slider.step = "1";
  slider.value = slider.max; sliderLabel.append(slider);
  wrap.append(readout, graphic, sliderLabel, el("p", "history-help", "Наведите на линию или выберите проверку ползунком. Между проверками цена могла меняться."));
  host.append(wrap);
  let active = points.length - 1, cursor, dot, svg, geometry;
  function choose(index) {
    active = index; slider.value = String(index);
    const point = points[index], previous = allPoints[allPoints.indexOf(point) - 1];
    const change = H.change(previous, point), text = !previous ? "Первая доступная проверка" : previous.currency !== currency ? "Валюта изменилась" : "К предыдущей проверке: " + changeText(change);
    readout.replaceChildren(el("span", "muted", date(point.time)), el("strong", "", money(point.price, currency)), el("span", changeClass(change), text));
    slider.setAttribute("aria-valuetext", date(point.time) + ", " + money(point.price, currency) + ", " + text);
    if (geometry && cursor) {
      const pos = geometry.coordinates[index];
      cursor.setAttribute("x1", pos.x); cursor.setAttribute("x2", pos.x);
      dot.setAttribute("cx", pos.x); dot.setAttribute("cy", pos.y);
    }
  }
  function draw() {
    const width = Math.max(300, Math.round(graphic.clientWidth || 760));
    geometry = H.layout(points, width);
    const g = geometry;
    svg = svgNode("svg", {viewBox: `0 0 ${width} 270`, class:"history-chart", role:"img",
      "aria-label":`История цены в ${currency}: от ${money(points[0].price, currency)} до ${money(points.at(-1).price, currency)}. ${changeText(H.summary(points).change)}`});
    for (const value of g.ticks) {
      const y = g.y(value);
      svg.append(svgNode("line", {x1:g.left, x2:g.right, y1:y, y2:y, class:"history-grid"}),
        svgNode("text", {x:g.left - 10, y:y + 4, "text-anchor":"end", class:"history-axis"},
          new Intl.NumberFormat("ru-RU", {notation:value >= 1e7 ? "compact" : "standard", maximumFractionDigits: 2}).format(value)));
    }
    svg.append(svgNode("text", {x:g.left - 10, y:12, "text-anchor":"end", class:"history-axis"}, currency));
    const tickCount = width < 500 ? 2 : 4;
    const sameDay = new Date(g.start).toDateString() === new Date(g.end).toDateString();
    for (let i = 0; i < (g.start === g.end ? 1 : tickCount); i++) {
      const time = g.start + (g.end - g.start) * i / (tickCount - 1);
      svg.append(svgNode("text", {x:g.x(time), y:250, "text-anchor":i===0?"start":i===tickCount-1?"end":"middle", class:"history-axis"},
        new Date(time).toLocaleString("ru-RU", sameDay ? {hour:"2-digit", minute:"2-digit"} : {day:"numeric", month:"short"})));
    }
    svg.append(svgNode("polyline", {points:g.coordinates.map(p => `${p.x},${p.y}`).join(" "), class:"history-line"}));
    if (points.length <= 80) for (const pos of g.coordinates) svg.append(svgNode("circle", {cx:pos.x, cy:pos.y, r:3, class:"history-dot"}));
    cursor = svgNode("line", {y1:g.top, y2:g.bottom, class:"history-cursor"});
    dot = svgNode("circle", {r:6, class:"history-selected-dot"});
    svg.append(cursor, dot); graphic.replaceChildren(svg); choose(active);
    function pointAt(event) {
      const rect = svg.getBoundingClientRect(), x = (event.clientX - rect.left) * width / rect.width;
      let nearest = 0;
      for (let i = 1; i < points.length; i++) if (Math.abs(g.coordinates[i].x - x) < Math.abs(g.coordinates[nearest].x - x)) nearest = i;
      choose(nearest);
    }
    svg.addEventListener("pointermove", event => { if (event.pointerType === "mouse" || event.buttons) pointAt(event); });
    svg.addEventListener("pointerdown", pointAt);
  }
  slider.addEventListener("input", () => choose(Number(slider.value)));
  draw();
  const observer = new ResizeObserver(draw); observer.observe(graphic); chartObservers.add(observer);
  return observer;
}
function renderHistory(monitor, rawPoints) {
  const points = H.normalize(rawPoints), card = el("article", "history-card");
  const head = el("div", "history-card-head"), info = el("div");
  info.append(el("h3", "", monitor.title), el("p", "muted", monitor.marketplace)); head.append(info);
  const open = el("a", "button button-secondary", "Открыть товар ↗");
  open.href = monitor.product_url; open.target = "_blank"; open.rel = "noopener noreferrer"; head.append(open); card.append(head);
  if (!points.length) { card.append(el("div", "empty-panel", "История появится после успешной проверки источника.")); return card; }
  const toolbar = el("div", "history-filters");
  const periodLabel = el("label", "", "Период"), period = el("select");
  for (const [value, label] of [["7","7 дней"],["30","30 дней"],["90","90 дней"],["0","Вся доступная история"]]) period.append(new Option(label, value));
  period.value = "0"; periodLabel.append(period); toolbar.append(periodLabel);
  const currencies = [...new Set(points.map(p => p.currency))], currency = el("select");
  currencies.forEach(c => currency.append(new Option(c, c))); currency.value = points.at(-1).currency;
  if (currencies.length > 1) { const label = el("label", "", "Валюта"); label.append(currency); toolbar.append(label); }
  card.append(toolbar);
  const body = el("div"); card.append(body); let observer;
  function update() {
    if (observer) { observer.disconnect(); chartObservers.delete(observer); }
    body.replaceChildren();
    const visible = H.select(points, currency.value, Number(period.value)), stats = H.summary(visible);
    if (!stats) { body.append(el("p", "empty-panel", "За этот период нет проверок. Выберите другой период.")); return; }
    const summary = el("div", "history-summary");
    function metric(label, value, cls = "") { const box = el("div"); box.append(el("span", "muted", label), el("strong", cls, value)); summary.append(box); }
    metric("Последняя цена в периоде", money(stats.last.price, currency.value));
    metric("Изменение за период", changeText(stats.change), changeClass(stats.change));
    metric("Минимум", money(stats.min, currency.value)); metric("Максимум", money(stats.max, currency.value));
    body.append(summary, el("p", "history-range", `${date(stats.first.time)} — ${date(stats.last.time)} · Проверок: ${visible.length}`));
    if (visible.length > 1) observer = priceChart(visible, points, currency.value, body);
    else body.append(el("p", "empty-panel", "Пока одна проверка. Изменение и график появятся после следующей успешной проверки."));
    const details = el("details", "history-records"); details.open = true;
    details.append(el("summary", "", "Все проверки и изменения"));
    const scroll = el("div", "history-table-scroll"), table = el("table", "history-table");
    const caption = el("caption", "sr-only", "Цена и изменение относительно предыдущей успешной проверки");
    const thead = el("thead"), header = el("tr");
    for (const label of ["Дата проверки", "Цена", "К предыдущей проверке"]) { const th = el("th", "", label); th.scope = "col"; header.append(th); }
    thead.append(header); const tbody = el("tbody"); table.append(caption, thead, tbody); scroll.append(table); details.append(scroll);
    let shown = 0;
    const more = el("button", "text-button history-more", "Показать ещё проверки"); more.type = "button";
    function appendRows() {
      const end = Math.min(visible.length, shown + 12);
      for (; shown < end; shown++) {
        const point = visible[visible.length - 1 - shown], previous = points[points.indexOf(point) - 1], change = H.change(previous, point);
        const row = el("tr");
        row.append(el("td", "", date(point.time)), el("td", "", money(point.price, currency.value)),
          el("td", changeClass(change), previous ? (previous.currency !== point.currency ? "Валюта изменилась" : changeText(change)) : "Первая доступная проверка"));
        tbody.append(row);
      }
      more.hidden = shown >= visible.length;
    }
    more.addEventListener("click", appendRows); details.append(more); appendRows(); body.append(details);
    body.append(el("p", "history-help", "Изменение за период — от первой до последней цены в выбранном периоде и валюте. В таблице — относительно предыдущей успешной проверки."));
    if (rawPoints.length >= 500) body.append(el("p", "history-help", "Показаны последние 500 проверок. Более ранние записи не включены в график и расчёт изменения."));
  }
  period.addEventListener("change", update); currency.addEventListener("change", update); update();
  return card;
}
async function loadHistory() {
  const run = ++loadRun, refresh = document.querySelector("#refresh-history"); refresh.disabled = true; showNote("");
  try {
    const auth = await window.MultiMarketSession.ready;
    if (auth.error) throw Error("Не удалось проверить вход. Обновите страницу.");
    if (!auth.authenticated) { location.replace("/login?next=" + encodeURIComponent(location.pathname + location.search)); return; }
    const data = await window.MultiMarketSession.request("/api/monitors");
    let monitors = data.monitors || [];
    if (selectedId) monitors = monitors.filter(m => m.id === selectedId);
    title.textContent = selectedId && monitors.length ? monitors[0].title : "История всех товаров";
    const histories = await Promise.all(monitors.map(async monitor => {
      try { const data = await window.MultiMarketSession.request("/api/monitors/" + monitor.id + "/history?limit=500"); return {monitor, points:data.points || []}; }
      catch { return {monitor, error:true}; }
    }));
    if (run !== loadRun) return;
    for (const observer of chartObservers) observer.disconnect(); chartObservers.clear(); list.replaceChildren();
    if (!monitors.length) {
      const empty = el("div", "empty-panel"); empty.append(el("strong", "", selectedId ? "Товар не найден" : "История начинается с первого товара"), el("span", "", "Добавьте товар из поиска, чтобы следить за ценой."));
      const search = el("a", "button button-primary", "Найти товар"); search.href = "/"; empty.append(search); list.append(empty);
    }
    for (const item of histories) {
      if (item.error) { const card = el("article", "history-card"); card.append(el("h3", "", item.monitor.title), el("p", "", "Не удалось загрузить историю. Нажмите «Обновить».")); list.append(card); }
      else list.append(renderHistory(item.monitor, item.points));
    }
  } catch (error) { if (run === loadRun) showNote(error.message || "Не удалось загрузить историю."); }
  finally { if (run === loadRun) refresh.disabled = false; }
}
document.querySelector("#refresh-history").addEventListener("click", loadHistory);
loadHistory();
