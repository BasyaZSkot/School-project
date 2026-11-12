let monitorCsrfToken = "";
let channelSettings={};
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
    const authResponse = await fetch("/api/auth/me");
    if (!authResponse.ok) throw new Error("Не удалось проверить вход.");
    const auth = await authResponse.json();
    if (!auth.authenticated) { location.replace("/login?next=/monitoring"); return; }
    monitorCsrfToken = auth.csrf_token;
    channelSettings=await window.MultiMarketSession.request("/api/notification-settings");
    const response = await fetch("/api/monitors");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось загрузить мониторинг.");
    list.replaceChildren();
    if (!data.monitors.length) {
      const empty = el("div", "empty-panel");
      empty.append(el("strong", "", "Сохраните первый товар"),
        el("span", "", "Найдите товар и нажмите «Следить за ценой». Здесь появятся его цена и история."));
      const search = el("a", "button button-primary", "Найти товар");
      search.href = "/";
      empty.append(search);
      list.append(empty);
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
        await changeMonitor(monitor.id, "PATCH", { active: !monitor.active });
      });
      const remove = el("button", "button button-danger", "Удалить");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        await changeMonitor(monitor.id, "DELETE");
      });
      const productLink = el("a", "button button-primary", "Открыть товар ↗");
      productLink.href = monitor.product_url;
      productLink.target = "_blank";
      productLink.rel = "noopener noreferrer";
      controls.append(history, toggle, remove, productLink);
      card.append(info, controls);
      const settings=el("details","monitor-settings"),summary=el("summary","","Цена и уведомления");settings.append(summary);
      const form=el("form","monitor-settings-form"),mode=el("select"),target=el("input"),currency=el("select"),percent=el("input"),direction=el("select"),interval=el("select");
      mode.append(new Option("Изменение на процент","percent"),new Option("Цена не выше заданной","target"));mode.value=monitor.target_price!=null?"target":"percent";
      target.type="number";target.min="0.01";target.max="1000000000000";target.step="0.01";target.value=monitor.target_price??"";
      for(const c of [...new Set(["RUB","USD","EUR","BYN","KZT",monitor.target_currency||"RUB"])])currency.append(new Option(c,c));currency.value=monitor.target_currency||"RUB";
      percent.type="number";percent.min="0.1";percent.max="100";percent.step="0.1";percent.value=monitor.threshold_percent;
      direction.append(new Option("Только снижение","drop"),new Option("Снижение и рост","any"));direction.value=monitor.alert_direction;
      for(const [seconds,label] of [[900,"15 минут"],[3600,"1 час"],[21600,"6 часов"],[86400,"1 день"],[604800,"1 неделя"]])interval.append(new Option(label,seconds));if(![900,3600,21600,86400,604800].includes(monitor.interval_seconds))interval.append(new Option(monitor.interval_seconds+" секунд",monitor.interval_seconds));interval.value=String(monitor.interval_seconds);
      function field(label,input){const node=el("label","",label);node.append(input);return node;}
      const targetField=field("Целевая цена",target),currencyField=field("Валюта цели",currency),percentField=field("Изменение, %",percent),directionField=field("Когда сообщать",direction);
      const fields=el("div","monitor-rule-fields");fields.append(field("Условие",mode),targetField,currencyField,percentField,directionField,field("Проверять каждые",interval));
      function rule(){const isTarget=mode.value==="target";targetField.hidden=currencyField.hidden=!isTarget;percentField.hidden=directionField.hidden=isTarget;target.required=isTarget;percent.required=!isTarget;}mode.addEventListener("change",rule);rule();form.append(fields);
      const checkboxes={};for(const [key,label,enabled] of [["notify_in_app","На сайте",true],["notify_email","Email",channelSettings.email_available],["notify_telegram","Telegram",channelSettings.telegram_connected]]){const check=el("input");check.type="checkbox";check.checked=!!monitor[key];check.disabled=!enabled&&!monitor[key];checkboxes[key]=check;const labelNode=el("label","check-label");labelNode.append(check,document.createTextNode(label));form.append(labelNode);}
      const help=el("a","text-button","Подключить почту или Telegram");help.href="/account#notification-settings";form.append(help);
      const save=el("button","button button-primary","Сохранить настройки"),feedback=el("p","muted");save.type="submit";feedback.role="status";form.append(save,feedback);
      form.addEventListener("submit",async e=>{e.preventDefault();save.disabled=true;try{const updated=await window.MultiMarketSession.request("/api/monitors/"+monitor.id,"PATCH",{target_price:mode.value==="target"?Number(target.value):null,target_currency:currency.value,threshold_percent:Number(percent.value),alert_direction:direction.value,interval_seconds:Number(interval.value),...Object.fromEntries(Object.entries(checkboxes).filter(([key,input])=>input.checked!==!!monitor[key]).map(([key,input])=>[key,input.checked]))});Object.assign(monitor,updated);feedback.textContent="Настройки сохранены.";}catch(error){feedback.textContent=error.message;}finally{save.disabled=false;}});settings.append(form);card.append(settings);
      list.append(card);
    });
  } catch (error) {
    showNote(error.message || "Не удалось загрузить мониторинг.");
  }
}
document.querySelector("#refresh-monitors").addEventListener("click", loadMonitors);
loadMonitors();

async function changeMonitor(id, method, body) {
  try {
    const response = await fetch("/api/monitors/" + id, {
      method, headers: { "Content-Type": "application/json", "X-CSRF-Token": monitorCsrfToken },
      body: body ? JSON.stringify(body) : undefined
    });
    if (response.status === 401) { location.replace("/login?next=/monitoring"); return; }
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось изменить товар.");
    showNote("");
    await loadMonitors();
  } catch (error) { showNote(error.message); }
}
