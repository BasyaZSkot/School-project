(function () {
  "use strict";
  const D = window.MultiMarketPickupData, Region = window.MultiMarketRegion;
  const $ = s => document.querySelector(s);
  const node = (tag, text, cls) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n; };
  let city=null, market=D.markets[0], points=[], candidate=null, suggestions=[], active=-1, limit=20;
  let pointSequence=0, suggestSequence=0, pointAbort, suggestAbort, timer, map, origin, mapPromise, mapConfig={};
  let mapMode=!matchMedia("(max-width: 700px)").matches;
  const host=$("#pickup-page");
  if(!host){
    Region.ready.then(updateSummary);document.addEventListener("multimarket:regionchange",updateSummary);
    $("#product-source")?.addEventListener("change",updateSummary);
    window.addEventListener("storage",e=>{if(e.key===D.KEY)updateSummary();});
    window.MultiMarketPickup={refresh:updateSummary,open:market=>location.assign(deliveryUrl(market))};
    return;
  }
  const editor=node("section",undefined,"pickup-editor");editor.id="pickup-editor";editor.setAttribute("aria-labelledby","pickup-title");
  editor.innerHTML=`<div class="pickup-header"><h2 id="pickup-title">Найти пункт выдачи</h2></div>
    <div class="pickup-fields"><label>Город<select id="pickup-city"><option value="">Выберите город</option></select></label><label>Маркетплейс<select id="pickup-market"></select></label></div>
    <div class="pickup-search-wrap"><label for="pickup-address">Адрес или название пункта</label><input id="pickup-address" type="search" maxlength="160" placeholder="Начните вводить улицу и дом" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="pickup-suggestions" aria-describedby="pickup-search-help"><ul id="pickup-suggestions" class="pickup-suggestions" role="listbox" aria-label="Подсказки адресов и пунктов выдачи" hidden></ul></div>
    <div class="pickup-view-bar"><p id="pickup-search-help">От 3 букв — адресные подсказки. Выберите адрес, чтобы найти ПВЗ рядом.</p><div class="pickup-view" role="group" aria-label="Способ выбора"><button id="pickup-list-view" type="button">Списком</button><button id="pickup-map-view" type="button">На карте</button></div></div>
    <p id="pickup-status" class="pickup-status" role="status" aria-live="polite"></p>
    <div id="pickup-layout" class="pickup-layout"><div class="pickup-results"><ul id="pickup-list" aria-label="Пункты выдачи"></ul><button id="pickup-more" type="button" class="secondary-button" hidden>Показать ещё</button></div><div id="pickup-map-panel" class="pickup-map-panel"><div id="pickup-map" aria-label="Карта пунктов выдачи"></div><button id="pickup-map-search" class="secondary-button pickup-map-search" type="button" disabled>Найти в этой области</button><p id="pickup-map-error" class="pickup-map-error" role="status" hidden></p></div></div>
    <div class="pickup-footer"><div><strong id="pickup-choice">Пункт не выбран</strong><p id="pickup-choice-market" class="muted"></p></div><div class="pickup-footer-actions"><button id="pickup-remove" class="text-button" type="button" hidden>Удалить сохранённый</button><button id="pickup-confirm" type="button" disabled>Выбрать этот пункт</button></div></div>
    <p class="pickup-disclaimer">Выбор сохранится в MultiMarket. Доступность товара и доставку в этот пункт подтвердит маркетплейс при оформлении. Список может быть неполным. Пункты: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap</a>. <span id="pickup-suggest-credit" hidden>Адресные подсказки: <a href="https://yandex.ru/maps/" target="_blank" rel="noopener noreferrer">Яндекс Карты</a>.</span></p>`;
  host.append(editor);
  $("#delivery-city-slot").replaceChildren($("#pickup-city").parentElement);
  document.querySelectorAll(".secondary-button").forEach(b=>{b.classList.remove("secondary-button");b.classList.add("button","button-secondary");});
  $("#pickup-confirm").classList.add("button","button-primary");
  D.markets.forEach(m => $("#pickup-market").append(new Option(m,m)));
  function saved() {return D.read(localStorage)[D.key(city,market)] || null;}
  function broadcast() {updateSummary();renderSaved();document.dispatchEvent(new CustomEvent("multimarket:pickupchange"));}
  function deliveryUrl(marketplace, hash="") {
    const url=new URL("/delivery",location.origin);
    url.searchParams.set("return_to",location.pathname+location.search);
    if(D.markets.includes(marketplace))url.searchParams.set("marketplace",marketplace);
    url.hash=hash;return url.pathname+url.search+url.hash;
  }
  function updateSummary() {
    const id=Region.getEffectiveId();
    const source=$("#product-source"), selectedMarket=source?.selectedOptions[0]?.textContent;
    document.querySelectorAll("[data-delivery-link]").forEach(link=>{link.href=deliveryUrl(selectedMarket,new URL(link.href).hash);});
    document.querySelectorAll("[data-pickup-summary]").forEach(el => {
      const choices=Object.values(D.read(localStorage)).filter(p=>p.region_id===id && (!selectedMarket || p.marketplace===selectedMarket));
      el.textContent=choices.length ? choices.map(p=>p.marketplace+": "+p.address).join(" · ") : "Отдельно для каждого маркетплейса";
    });
  }
  function renderSaved() {
    const list=$("#delivery-saved-list");list.replaceChildren();const choices=D.read(localStorage);
    D.markets.forEach(m=>{
      const point=choices[D.key(city,m)],li=node("li"),copy=node("div");
      copy.append(node("strong",m),node("p",point?.address || (city ? "Пункт пока не выбран" : "Сначала выберите город"),"muted"));
      const button=node("button",point ? "Изменить" : "Выбрать","text-button");button.type="button";button.disabled=!city;
      button.setAttribute("aria-label",(point ? "Изменить" : "Выбрать")+" пункт "+m);
      button.addEventListener("click",()=>{market=m;$("#pickup-market").value=m;$("#pickup-address").value="";loadPoints(point ? {lat:point.lat,lon:point.lon} : null);editor.scrollIntoView({behavior:"smooth",block:"start"});$("#pickup-address").focus({preventScroll:true});});
      li.append(copy,button);list.append(li);
    });
  }
  function status(text) {$("#pickup-status").textContent=text;}
  function closeSuggestions() {suggestions=[];active=-1;$("#pickup-suggestions").hidden=true;$("#pickup-address").setAttribute("aria-expanded","false");$("#pickup-address").removeAttribute("aria-activedescendant");}
  function cancelSuggestions() {clearTimeout(timer);suggestSequence++;suggestAbort?.abort();closeSuggestions();}
  function renderSuggestions(items) {
    suggestions=items;active=-1;const list=$("#pickup-suggestions");list.replaceChildren();
    items.forEach((item,i) => {const li=node("li");li.id="pickup-suggest-"+i;li.role="option";li.setAttribute("aria-selected","false");li.append(node("strong",item.label),node("span",item.point ? "Пункт выдачи · "+market : "Адрес · найти пункты рядом"));li.addEventListener("pointerdown",e=>e.preventDefault());li.addEventListener("click",()=>chooseSuggestion(item));list.append(li);});
    list.hidden=!items.length;$("#pickup-address").setAttribute("aria-expanded",String(!!items.length));$("#pickup-address").removeAttribute("aria-activedescendant");
  }
  function localSuggestions(query) {return D.matches(points,query).slice(0,4).map(point=>({label:point.address,point}));}
  async function request(url, signal) {
    const r=await fetch(url,{signal,headers:{Accept:"application/json"}});const data=await r.json();
    if(!r.ok)throw new Error(typeof data.detail==="string" ? data.detail : "Не удалось загрузить данные. Попробуйте позже.");return data;
  }
  function choice() {
    const previous=saved(), current=candidate || previous;
    $("#pickup-choice").textContent=current ? current.address : "Пункт не выбран";
    const unchanged=candidate?.id===previous?.id && !!candidate;
    $("#pickup-choice-market").textContent=current ? market+(candidate && !unchanged ? " · Выберите этот пункт для сохранения" : " · Сохранён") : "Нажмите на пункт в списке или на карте";
    $("#pickup-confirm").textContent=unchanged ? "Готово" : "Выбрать этот пункт";
    $("#pickup-confirm").disabled=!candidate;$("#pickup-remove").hidden=!previous;
  }
  function select(point, pan=true) {
    candidate=point;choice();renderList();drawMarkers();
    if(map && pan)map.setCenter([point.lat,point.lon],16);
  }
  function renderList() {
    const list=$("#pickup-list");list.replaceChildren();const selectedId=candidate?.id || saved()?.id;
    points.slice(0,limit).forEach(point=> {
      const li=node("li"),button=node("button",undefined,"pickup-point");button.type="button";button.setAttribute("aria-pressed",String(point.id===selectedId));
      button.append(node("strong",point.address),node("span",point.kind+" · "+(point.distance_km<1 ? Math.round(point.distance_km*1000)+" м" : point.distance_km.toLocaleString("ru-RU")+" км")+" от центра поиска"));
      if(!point.address_complete)button.append(node("small","Номер дома не указан — проверьте точку на карте"));
      button.addEventListener("click",()=>select(point));li.append(button);list.append(li);
    });
    $("#pickup-more").hidden=limit>=points.length;
  }
  async function loadPoints(center) {
    const sequence=++pointSequence;pointAbort?.abort();pointAbort=new AbortController();candidate=null;points=[];limit=20;
    cancelSuggestions();renderList();drawMarkers();choice();
    $("#pickup-map-search").disabled=true;
    if(!city){status("Выберите город, чтобы увидеть пункты выдачи.");return;}
    status("Ищем пункты выдачи…");
    const params=new URLSearchParams({region_id:city,marketplace:market});
    if(center){params.set("lat",center.lat);params.set("lon",center.lon);params.set("radius",3);}
    try {
      const data=await request("/api/pickup-points?"+params,pointAbort.signal);if(sequence!==pointSequence)return;
      points=(data.points || []).filter(p=>D.valid(p) && p.region_id===city && p.marketplace===market);origin=data.center;
      const previous=saved();candidate=points.find(p=>p.id===previous?.id) || null;
      status(points.length ? "Найдено пунктов: "+points.length+(data.limited ? ". Уточните адрес или область карты — показаны не все пункты." : ". Выберите удобный.") : "В этой области пунктов не найдено. Попробуйте другой адрес или переместите карту.");
      renderList();choice();if(mapMode){await ensureMap();if(sequence!==pointSequence)return;map?.setCenter([origin.lat,origin.lon],13);}drawMarkers();
    } catch(e){if(e.name!=="AbortError" && sequence===pointSequence)status(e.message);}
    finally {if(sequence===pointSequence)$("#pickup-map-search").disabled=!origin || !map;}
  }
  async function chooseSuggestion(item) {
    cancelSuggestions();const sequence=suggestSequence;$("#pickup-address").value=item.label;
    if(item.point){select(item.point);$("#pickup-address").blur();return;}
    if(item.provider==="yandex"){
      status("Находим адрес на карте…");
      try {
        await ensureYandex();
        const result=await window.ymaps.geocode(item.label,{results:1});
        if(sequence!==suggestSequence)return;
        const geo=result.geoObjects.get(0), coords=geo?.geometry.getCoordinates();
        if(!coords)throw new Error("Адрес не найден. Уточните номер дома.");
        item={...item,lat:coords[0],lon:coords[1]};
      }catch(e){if(sequence===suggestSequence)status("Не удалось найти адрес на карте. Выберите другой вариант или пункт в списке.");return;}
    }
    origin={lat:item.lat,lon:item.lon};if(map)map.setCenter([item.lat,item.lon],14);await loadPoints(origin);
  }
  function addressInput() {
    cancelSuggestions();const q=$("#pickup-address").value.trim();if(!city || q.length<3)return;
    renderSuggestions(localSuggestions(q));const sequence=suggestSequence;
    timer=setTimeout(async()=> {
      suggestAbort=new AbortController();
      try {
        const data=await request("/api/address-suggestions?"+new URLSearchParams({region_id:city,q}),suggestAbort.signal);
        if(sequence!==suggestSequence)return;
        const local=localSuggestions(q),seen=new Set(local.map(x=>x.label));
        renderSuggestions([...local,...(data.suggestions || []).filter(x=>!seen.has(x.label)).map(x=>({...x,label:String(x.label)}))]);
        if(!suggestions.length)status("Адрес не найден. Уточните улицу и номер дома или воспользуйтесь картой.");
      }catch(e){if(e.name!=="AbortError" && sequence===suggestSequence)status("Адресные подсказки недоступны. Можно выбрать ПВЗ из списка или на карте.");}
    },650);
  }
  function drawMarkers() {
    if(!map)return;map.geoObjects.removeAll();
    const selectedId=candidate?.id || saved()?.id;
    points.forEach(p=> {
      const selected=p.id===selectedId;
      const marker=new window.ymaps.Placemark([p.lat,p.lon],{iconContent:market==="Яндекс Маркет" ? "Я" : market==="Ozon" ? "O" : "WB"},{preset:"islands#circleIcon",iconColor:selected ? "#231243" : "#5a52dc"});
      marker.events.add("click",()=>select(p,false));map.geoObjects.add(marker);
    });
  }
  async function ensureYandex() {
    if(!mapConfig.api_key)throw new Error("Карта пока недоступна. Выберите пункт из списка.");
    if(!mapPromise)mapPromise=new Promise((resolve,reject)=> {
      const script=node("script");const params=new URLSearchParams({apikey:mapConfig.api_key,lang:"ru_RU"});
      const timeout=setTimeout(()=>reject(new Error("Карта не загрузилась. Выберите пункт из списка.")),15000);
      script.src="https://api-maps.yandex.ru/2.1/?"+params;
      script.onload=()=>{if(!window.ymaps){clearTimeout(timeout);reject(new Error("Карта недоступна."));return;}window.ymaps.ready(()=>{clearTimeout(timeout);resolve();},()=>{clearTimeout(timeout);reject(new Error("Карта недоступна."));});};
      script.onerror=()=>{clearTimeout(timeout);reject(new Error("Карта не загрузилась. Выберите пункт из списка."));};document.head.append(script);
    });
    return mapPromise;
  }
  async function ensureMap() {
    if(map){map.container.fitToViewport();return;}
    try {
      await ensureYandex();if(map || !mapMode)return;
      map=new window.ymaps.Map("pickup-map",{center:origin ? [origin.lat,origin.lon] : [55.75,37.62],zoom:13,controls:["zoomControl"]});
      $("#pickup-map-error").hidden=true;
      map.events.add("boundschange",()=>{$("#pickup-map-search").disabled=!city;});drawMarkers();
    }catch(e){$("#pickup-map-error").hidden=false;$("#pickup-map-error").textContent=e.message;}
  }
  function view(mode) {
    mapMode=mode;$("#pickup-map-panel").hidden=!mode;$("#pickup-layout").classList.toggle("pickup-layout-list",!mode);
    $("#pickup-map-view").setAttribute("aria-pressed",String(mode));$("#pickup-list-view").setAttribute("aria-pressed",String(!mode));
    if(mode && city && origin)ensureMap();
  }
  async function open() {
    await Region.ready;const cities=Region.getCities();
    if(!cities.length){$("#delivery-city-slot").textContent="Города временно недоступны. Обновите страницу.";status("Не удалось загрузить города.");renderSaved();return;}
    try{mapConfig=await request("/api/map-config");}catch{mapConfig={};}
    $("#pickup-suggest-credit").hidden=!mapConfig.yandex_suggest;
    $("#pickup-city").replaceChildren(new Option("Регион площадки автоматически",""),...cities.map(c=>new Option(c.name,c.id)));
    const params=new URLSearchParams(location.search),marketplace=params.get("marketplace");
    city=Region.getId();market=D.markets.includes(marketplace) ? marketplace : D.markets[0];
    $("#pickup-city").value=city || "";$("#pickup-market").value=market;$("#pickup-address").value="";origin=null;
    renderSaved();view(mapMode);
    // Accept return links only to pages that can initiate delivery changes.
    const target=params.get("return_to");
    try {const url=new URL(target || "/",location.origin);if(url.origin===location.origin && ["/","/product"].includes(url.pathname))document.querySelectorAll("[data-delivery-back]").forEach(link=>{link.href=url.pathname+url.search;link.textContent=url.pathname==="/product" ? "← Вернуться к товару" : "← Вернуться к поиску";});}catch{}
    if(location.hash==="#city")$("#pickup-city").focus();
    const previous=saved();await loadPoints(previous ? {lat:previous.lat,lon:previous.lon} : null);
  }
  document.addEventListener("click",e=> {if(!e.target.closest(".pickup-search-wrap"))closeSuggestions();});
  $("#pickup-city").addEventListener("change",()=>Region.select(Number($("#pickup-city").value)||null));
  $("#pickup-market").addEventListener("change",()=>{market=$("#pickup-market").value;$("#pickup-address").value="";loadPoints(origin);});
  $("#pickup-address").addEventListener("input",addressInput);
  $("#pickup-address").addEventListener("keydown",e=> {
    if(e.key==="Escape" && suggestions.length){e.preventDefault();e.stopPropagation();closeSuggestions();return;}
    if(["ArrowDown","ArrowUp"].includes(e.key) && suggestions.length){e.preventDefault();active=(active+(e.key==="ArrowDown"?1:-1)+suggestions.length)%suggestions.length;[...$("#pickup-suggestions").children].forEach((li,i)=>li.setAttribute("aria-selected",String(i===active)));$("#pickup-address").setAttribute("aria-activedescendant","pickup-suggest-"+active);$("#pickup-suggest-"+active).scrollIntoView({block:"nearest"});}
    if(e.key==="Enter"){e.preventDefault();if(suggestions.length)chooseSuggestion(suggestions[Math.max(0,active)]);else addressInput();}
  });
  $("#pickup-list-view").addEventListener("click",()=>view(false));$("#pickup-map-view").addEventListener("click",()=>view(true));
  $("#pickup-more").addEventListener("click",()=>{limit+=20;renderList();});
  $("#pickup-map-search").addEventListener("click",()=>{if(map){$("#pickup-address").value="";const c=map.getCenter();loadPoints({lat:c[0],lon:c[1]});}});
  $("#pickup-confirm").addEventListener("click",()=> {
    if(!candidate)return;
    try {D.save(localStorage,candidate);}catch {status("Не удалось сохранить выбор. Разрешите сохранение данных в браузере и повторите.");return;}
    Region.select(city);choice();broadcast();status("Пункт выдачи сохранён. Можно выбрать пункт другой площадки или вернуться к покупкам.");
  });
  $("#pickup-remove").addEventListener("click",()=> {
    try {D.remove(localStorage,city,market);}catch{status("Не удалось удалить сохранённый пункт.");return;}
    candidate=null;choice();renderList();drawMarkers();broadcast();status("Сохранённый пункт удалён.");
  });
  document.addEventListener("multimarket:regionchange",()=>{city=Region.getId();$("#pickup-city").value=city || "";origin=null;$("#pickup-address").value="";$("#delivery-city-status").textContent="Город сохранён.";renderSaved();const previous=saved();loadPoints(previous ? {lat:previous.lat,lon:previous.lon} : null);});
  window.addEventListener("storage",e=>{if(e.key===D.KEY){renderSaved();choice();renderList();drawMarkers();}});
  open();window.MultiMarketPickup={refresh:renderSaved};
})();
