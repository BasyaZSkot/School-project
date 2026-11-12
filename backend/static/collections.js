(function(){
  "use strict";
  const S=window.MultiMarketSession,D=window.MultiMarketLibraryData;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const $=s=>document.querySelector(s);let favorites=[],favoritePromise,compareRun=0;const details=new Map(),selected=new Map();
  const controlProducts=new WeakMap();let updateQueued=false;
  function scheduleUpdate(){if(updateQueued)return;updateQueued=true;queueMicrotask(()=>{updateQueued=false;update();});}
  const quick=el("nav",undefined,"library-nav");quick.setAttribute("aria-label","Личная коллекция");
  for(const [href,label] of [["/favorites","Избранное"],["/compare","Сравнение"],["/notifications","Уведомления"]]){const a=el("a",label);a.href=href;if(location.pathname===href)a.setAttribute("aria-current","page");if(href==="/compare")a.dataset.compareLink="";quick.append(a);}
  $(".topbar")?.insertAdjacentElement("afterend",quick);
  const feedback=el("p",undefined,"library-feedback");feedback.id="library-feedback";feedback.role="status";feedback.hidden=true;quick.insertAdjacentElement("afterend",feedback);
  function say(text){feedback.textContent=text;feedback.hidden=!text;}
  function compareList(){try{return D.read(localStorage);}catch{return [];}}
  async function loadFavorites(force=false){
    if(force)favoritePromise=null;
    if(!favoritePromise)favoritePromise=S.ready.then(async auth=>{if(!auth.authenticated)return [];const data=await S.request("/api/favorites");favorites=data.favorites||[];return favorites;}).catch(error=>{favoritePromise=null;throw error;});
    return favoritePromise;
  }
  function update(){
    const list=compareList();document.querySelectorAll("[data-compare-link]").forEach(a=>a.textContent="Сравнение"+(list.length?" ("+list.length+")":""));
    document.querySelectorAll(".compare-button").forEach(b=>{const p=controlProducts.get(b),yes=!!p&&list.some(item=>D.sameProduct(item,p));b.setAttribute("aria-pressed",String(yes));b.textContent=yes?"В сравнении":"Сравнить";});
    document.querySelectorAll(".favorite-button").forEach(b=>{const p=controlProducts.get(b),yes=!!p&&favorites.some(item=>D.sameProduct(item,p));b.setAttribute("aria-pressed",String(yes));b.textContent=yes?"В избранном":"В избранное";});
  }
  function href(product){
    const p=D.snapshot(product),key="multimarket.product."+(crypto.randomUUID?.()||Date.now()+Math.random());
    try{sessionStorage.setItem(key,JSON.stringify(p));}catch{}
    const best=D.best(p),summary={title:p.title,offers:[{marketplace:best.marketplace,title:best.title,price:best.price,currency:best.currency,url:best.url,image_url:best.image_url}]};
    return "/product?key="+encodeURIComponent(key)+"&data="+encodeURIComponent(JSON.stringify(summary));
  }
  function controls(product){
    const p=D.snapshot(product),box=el("div",undefined,"collection-controls");if(!p)return box;
    const favorite=el("button","В избранное","text-button favorite-button"),compare=el("button","Сравнить","text-button compare-button");
    for(const b of [favorite,compare]){b.type="button";b.dataset.identity=p.identity;b.setAttribute("aria-pressed","false");controlProducts.set(b,p);}
    favorite.addEventListener("click",async()=>{
      favorite.disabled=true;
      try{
        const auth=await S.ready;if(!auth.authenticated){location.assign("/login?next="+encodeURIComponent(location.pathname+location.search));return;}
        await loadFavorites();const existing=favorites.find(x=>D.sameProduct(x,p));
        if(existing){await S.request("/api/favorites/"+existing.id,"DELETE");favorites=favorites.filter(f=>f.id!==existing.id);say("Товар удалён из избранного.");}
        else{const saved=await S.request("/api/favorites","PUT",p);favorites.unshift(saved);say("Товар сохранён в избранном аккаунта.");}
        update();document.dispatchEvent(new CustomEvent("multimarket:favoriteschange"));
      }catch(e){say(e.message);}finally{favorite.disabled=false;}
    });
    compare.addEventListener("click",()=>{try{const list=D.toggle(localStorage,p);update();say(list.some(x=>D.sameProduct(x,p))?"Товар добавлен. Откройте «Сравнение», чтобы сопоставить характеристики.":"Товар убран из сравнения.");if($("#comparison-table"))renderCompare();}catch(e){say(e.message);}});
    box.append(favorite,compare);loadFavorites().then(scheduleUpdate).catch(()=>{});scheduleUpdate();return box;
  }
  function money(o){try{return new Intl.NumberFormat("ru-RU",{style:"currency",currency:o.currency,maximumFractionDigits:2}).format(o.price);}catch{return o.price+" "+o.currency;}}
  async function renderFavorites(force=false){
    const wrap=$("#favorites-list");if(!wrap)return;
    const auth=await S.ready;if(!auth.authenticated){location.replace("/login?next=/favorites");return;}
    try{
      const list=await loadFavorites(force);wrap.replaceChildren();
      if(!list.length){wrap.append(el("p","Сохраняйте понравившиеся товары кнопкой «В избранное» в поиске или карточке.","empty-panel"));return;}
      for(const item of list){const card=el("article",undefined,"favorite-card"),offer=D.best(item),a=el("a",item.title,"favorite-title");a.href=href(item);
        if(offer.image_url){const img=el("img");img.src=offer.image_url;img.alt="";img.loading="lazy";img.referrerPolicy="no-referrer";card.append(img);}
        card.append(a,el("p",money(offer)+" · "+offer.marketplace),el("p","Сохранённая цена. Обновлённые условия — в карточке и магазине.","muted"),controls(item));wrap.append(card);
      }update();
    }catch(e){wrap.replaceChildren(el("p",e.message,"notice"));}
  }
  async function enrich(product,offer){
    const key=offer.marketplace+":"+offer.url;if(details.has(key))return details.get(key);
    const promise=(async()=>{try{await window.MultiMarketRegion?.ready;const params=new URLSearchParams({marketplace:offer.marketplace,product_url:offer.url});const region=window.MultiMarketRegion?.getId();if(region)params.set("region_id",region);const r=await fetch("/api/product-details?"+params);const data=await r.json();if(!r.ok||!data.details_available)return offer;return D.snapshot({title:product.title,offers:[{...offer,...data}]})?.offers[0]||offer;}catch{return offer;}})();details.set(key,promise);return promise;
  }
  async function renderCompare(){
    const wrap=$("#comparison-table");if(!wrap)return;const run=++compareRun,list=compareList();wrap.replaceChildren();update();
    $("#compare-differences").disabled=list.length<2;
    if(!list.length){wrap.append(el("p","Добавьте от двух до четырёх товаров кнопкой «Сравнить» в поиске, карточке или избранном.","empty-panel"));return;}
    const offers=list.map(p=>p.offers.find(o=>o.url===selected.get(p.identity))||D.best(p));
    function draw(current){
      if(run!==compareRun)return;const table=el("table",undefined,"comparison-table"),caption=el("caption","Сравнение товаров и характеристик");table.style.setProperty("--compare-count",String(list.length));caption.className="sr-only";table.append(caption);
      const thead=el("thead"),head=el("tr");head.append(el("th","Характеристика"));
      list.forEach((p,i)=>{const th=el("th");th.scope="col";const a=el("a",p.title);a.href=href(p);th.append(a);
        if(current[i].image_url){const img=el("img");img.src=current[i].image_url;img.alt="";img.referrerPolicy="no-referrer";th.append(img);}
        const select=el("select");select.setAttribute("aria-label","Предложение для "+p.title);p.offers.forEach((o,index)=>select.append(new Option(o.marketplace+(o.seller?" · "+o.seller:""),String(index))));select.value=String(p.offers.indexOf(offers[i]));select.addEventListener("change",()=>{selected.set(p.identity,p.offers[Number(select.value)].url);renderCompare();});th.append(select);
        th.append(el("strong",money(current[i])),el("p",current[i].in_stock===false?"Нет в наличии":current[i].in_stock===true?"В наличии":"Наличие уточняйте в магазине","muted"));
        const remove=el("button","Убрать","text-button");remove.type="button";remove.addEventListener("click",()=>{D.toggle(localStorage,p);renderCompare();});th.append(remove);head.append(th);
      });thead.append(head);table.append(thead);const body=el("tbody");
      const rows=D.rows(current).filter(r=>!$("#compare-differences").checked||r.different);
      for(const row of rows){const tr=el("tr");if(row.different)tr.className="comparison-different";const label=el("th",row.name);label.scope="row";tr.append(label);row.values.forEach(v=>tr.append(el("td",v)));body.append(tr);}
      if(!rows.length){const tr=el("tr"),td=el("td",list.length<2?"Добавьте ещё один товар для сравнения.":"Различий в доступных характеристиках не найдено.");td.colSpan=list.length+1;tr.append(td);body.append(tr);}table.append(body);wrap.replaceChildren(table);
    }
    draw(offers);const enriched=await Promise.all(list.map((p,i)=>enrich(p,offers[i])));draw(enriched);
  }
  $("#compare-differences")?.addEventListener("change",renderCompare);
  $("#compare-clear")?.addEventListener("click",()=>{localStorage.removeItem(D.KEY);renderCompare();});
  document.addEventListener("multimarket:favoriteschange",()=>renderFavorites(true));window.addEventListener("storage",e=>{if(e.key===D.KEY){update();renderCompare();}});
  window.MultiMarketLibrary={controls,href,refresh:update};update();renderFavorites();renderCompare();
})();
