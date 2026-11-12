(function () {
  "use strict";
  const KEY = "multimarket.region.v1";
  let cities = [], selected = null, automaticName = "";
  const $ = selector => document.querySelector(selector);
  const normalize = text => String(text || "").toLocaleLowerCase("ru").replace(/ё/g,"е").replace(/[^a-zа-я0-9]/g,"");
  function readChoice() {
    try {
      const data = JSON.parse(localStorage.getItem(KEY) || "null");
      return data && data.version === 1 ? {exists:true,id:data.id} : {exists:false,id:null};
    } catch { return {exists:false,id:null}; }
  }
  function valid(id) { return id === null || cities.some(c => c.id === id); }
  function name() { return cities.find(c => c.id === selected)?.name || (automaticName ? automaticName + " (площадка)" : "Регион площадки"); }
  function updateLabels() { document.querySelectorAll("[data-region-label]").forEach(node => node.textContent = name()); }
  function renderCities() {
    const list = $("#region-list"); if (!list) return;
    const term = normalize($("#region-search").value);
    const matches = cities.filter(c => normalize(c.name).includes(term));
    list.replaceChildren();
    matches.forEach(city => {
      const item = document.createElement("li"), button = document.createElement("button");
      button.type = "button"; button.className = "region-option"; button.textContent = city.name;
      button.setAttribute("aria-pressed",String(city.id === selected));
      button.addEventListener("click", () => choose(city.id)); item.append(button); list.append(item);
    });
    $("#region-auto").setAttribute("aria-pressed",String(selected === null));
    $("#region-feedback").textContent = matches.length ? "" : "Город не найден. Попробуйте другое написание.";
  }
  function choose(id) {
    if (!valid(id)) return;
    const previous = selected; selected = id;
    try { localStorage.setItem(KEY,JSON.stringify({version:1,id})); } catch {}
    updateLabels(); $("#region-dialog")?.close();
    if (previous !== id) document.dispatchEvent(new CustomEvent("multimarket:regionchange",{detail:{id}}));
  }
  function observeOffers(offers) {
    if (selected === null) {
      automaticName = offers.find(o => o.delivery?.destination)?.delivery.destination || "";
      updateLabels();
    }
  }
  function scopeDelivery(delivery) {
    if (selected === null) return delivery || {};
    const d = delivery || {}, city = cities.find(c => c.id === selected);
    const confirmed = d.region_confirmed !== false && (Number(d.region_id) === selected || normalize(d.destination) === normalize(city?.name));
    return confirmed ? {...d,requested_region_id:selected,region_confirmed:true}
      : {text:"Площадка не подтвердила срок для выбранного города",destination:city?.name,requested_region_id:selected,region_confirmed:false};
  }
  const ready = fetch("/api/regions",{headers:{Accept:"application/json"}}).then(async response => {
    if (!response.ok) throw new Error("Не удалось загрузить города");
    const data = await response.json(); cities = Array.isArray(data.regions) ? data.regions : [];
    if (!cities.length) throw new Error("Города временно недоступны");
    const stored = readChoice();
    const fromUrl = new URLSearchParams(location.search).get("region_id");
    selected = stored.exists ? stored.id : fromUrl ? Number(fromUrl) : null;
    if (!valid(selected)) selected = null;
    updateLabels();
    if ($("#region-open")) $("#region-open").disabled = false;
    if (location.hash === "#delivery-region" && $("#region-dialog")) {renderCities();$("#region-dialog").showModal();$("#region-search").focus();}
  }).catch(() => {
    if ($("#region-open")) {$("#region-open").disabled=true;$("#region-open").title="Выбор города временно недоступен. Обновите страницу.";}
  });
  $("#region-open")?.addEventListener("click", () => {$("#region-search").value="";renderCities();$("#region-dialog").showModal();$("#region-search").focus();});
  $("#region-close")?.addEventListener("click", () => $("#region-dialog").close());
  $("#region-auto")?.addEventListener("click", () => choose(null));
  $("#region-search")?.addEventListener("input",renderCities);
  $("#region-dialog")?.addEventListener("close", () => {if(location.hash === "#delivery-region") history.replaceState(null,"",location.pathname+location.search);});
  window.addEventListener("storage", async event => {
    if (event.key !== KEY) return;
    await ready; const id = readChoice().id;
    if (valid(id) && id !== selected) {selected=id;updateLabels();document.dispatchEvent(new CustomEvent("multimarket:regionchange",{detail:{id}}));}
  });
  window.MultiMarketRegion = {ready,getId:()=>selected,getName:name,observeOffers,scopeDelivery};
})();
