const Catalog = window.MultiMarketCatalog;
const Region = window.MultiMarketRegion;
const marketplaceHosts = { Ozon:["ozon.ru"], Wildberries:["wildberries.ru","wildberries.by","wildberries.kz"], "Яндекс Маркет":["market.yandex.ru"] };
const $ = selector => document.querySelector(selector);
let sources = [], selectedSource = 0, galleryImages = [], imageIndex = 0;
let reviewLimit = 5, specsExpanded = false;
let activeVariant="";
const variantKey=o=>JSON.stringify(Object.fromEntries(Object.entries(o.variants||{}).sort(([a],[b])=>a.localeCompare(b))));
const variantLabel=o=>Object.values(o.variants||{}).join(" · ") || "Вариант не указан";
function updateVariants(){
  const options=new Map(sources.map(o=>[variantKey(o),variantLabel(o)]));
  if(!options.has(activeVariant))activeVariant=variantKey(sources[selectedSource]);
  const select=$("#product-variant");select.replaceChildren(...[...options].map(([key,label])=>new Option(label,key)));select.value=activeVariant;
  $("#product-variant-toolbar").hidden=options.size<=1;
  if(variantKey(sources[selectedSource])!==activeVariant)selectedSource=sources.findIndex(o=>variantKey(o)===activeVariant);
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function validProductUrl(marketplace, value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password && (!url.port || url.port === "443") &&
      (marketplaceHosts[marketplace] || []).some(host => url.hostname === host || url.hostname.endsWith("." + host));
  } catch { return false; }
}
function money(value, currency = "RUB") {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return "Не указана";
  try { return new Intl.NumberFormat("ru-RU", {style:"currency", currency, minimumFractionDigits:0, maximumFractionDigits:2}).format(amount); }
  catch { return amount.toLocaleString("ru-RU") + " " + currency; }
}
function readProduct() {
  const params = new URLSearchParams(location.search);
  let product;
  try {
    const key = params.get("key");
    if (key?.startsWith("multimarket.product.")) product = JSON.parse(sessionStorage.getItem(key) || "null");
  } catch {}
  if (!product) {
    const raw = params.get("data");
    if (!raw || raw.length > 16000) return null;
    try { product = JSON.parse(raw); } catch { return null; }
  }
  if (typeof product?.title !== "string" || !Array.isArray(product.offers)) return null;
  const offers = product.offers.filter(o => o && validProductUrl(o.marketplace,o.url) && Catalog.validPrice(o)).slice(0,12)
    .map(o => ({...o, specifications:Array.isArray(o.specifications) ? o.specifications : [],
      reviews:Array.isArray(o.reviews) ? o.reviews : [], delivery:o.delivery && typeof o.delivery === "object" ? o.delivery : {}}));
  return offers.length ? {title:product.title.slice(0,300), offers} : null;
}
function showImage(index) {
  if (!galleryImages.length) return;
  imageIndex = (index + galleryImages.length) % galleryImages.length;
  for (const image of [$("#product-image"), $("#gallery-dialog-image")]) {
    image.src = galleryImages[imageIndex]; image.referrerPolicy = "no-referrer";
    image.alt = $("#product-title").textContent + " — фото " + (imageIndex + 1);
  }
  const count = (imageIndex + 1) + " из " + galleryImages.length;
  $("#gallery-count").textContent = count;
  $("#gallery-dialog-count").textContent = count;
  [...$("#gallery-thumbs").children].forEach((button,i) => button.setAttribute("aria-pressed", String(i === imageIndex)));
}
function showGallery(offer) {
  galleryImages = Catalog.images(offer);
  $("#product-image-wrap").hidden = !galleryImages.length;
  $(".product-detail-hero").classList.toggle("no-product-image", !galleryImages.length);
  $("#gallery-controls").hidden = galleryImages.length < 2;
  $("#gallery-thumbs").replaceChildren();
  $("#gallery-thumbs").hidden = galleryImages.length < 2;
  $("#gallery-dialog-prev").disabled = galleryImages.length < 2;
  $("#gallery-dialog-next").disabled = galleryImages.length < 2;
  galleryImages.forEach((url,index) => {
    const button = element("button", "gallery-thumb"); button.type = "button";
    button.setAttribute("aria-label", "Фото " + (index + 1));
    const image = element("img"); image.src = url; image.alt = ""; image.loading = "lazy"; image.referrerPolicy = "no-referrer";
    button.append(image); button.addEventListener("click", () => showImage(index));
    $("#gallery-thumbs").append(button);
  });
  showImage(0);
}
function showSpecs() {
  $("#spec-search").hidden = !specsExpanded;
  const term = $("#spec-search").value.trim().toLocaleLowerCase("ru");
  const items = (sources[selectedSource]?.specifications || []).filter(s => s?.name && s?.value).slice(0,100);
  const matches = items.filter(s => (s.name + " " + s.value).toLocaleLowerCase("ru").includes(term));
  const visible = term || specsExpanded ? matches : matches.slice(0,10);
  $("#product-specs").replaceChildren();
  visible.forEach(s => {
    const row = element("div","spec-row");
    row.append(element("dt","",s.name),element("dd","",s.value));
    $("#product-specs").append(row);
  });
  if (!matches.length) $("#product-specs").append(element("dd","detail-muted",term ? "Такая характеристика не найдена." : "Магазин не передал характеристики."));
  $("#spec-more").hidden = items.length <= 10;
  $("#spec-more").textContent = specsExpanded ? "Свернуть характеристики" : "Все характеристики (" + items.length + ")";
  $("#spec-more").setAttribute("aria-expanded", String(specsExpanded));
}
function reviewItems(offer) {
  const seen = new Set();
  return (Array.isArray(offer?.reviews) ? offer.reviews : []).filter(r => {
    if (!r?.body || typeof r.body !== "string") return false;
    const key = JSON.stringify([r.body.trim(),r.author,r.date]);
    if (seen.has(key)) return false;
    seen.add(key); return true;
  }).slice(0,100);
}
function reviewsWord(n) {
  if (n % 10 === 1 && n % 100 !== 11) return "отзыв";
  if ([2,3,4].includes(n % 10) && ![12,13,14].includes(n % 100)) return "отзыва";
  return "отзывов";
}
function showReviews() {
  const offer = sources[selectedSource] || {};
  const available = reviewItems(offer);
  const score = $("#review-rating").value;
  const items = available.filter(r => !score || Number(r.rating) === Number(score));
  const order = $("#review-sort").value;
  if (order === "newest") items.sort((a,b) => (Date.parse(b.date) || 0) - (Date.parse(a.date) || 0));
  if (order === "highest" || order === "lowest") items.sort((a,b) => {
    const ar = Number(a.rating), br = Number(b.rating);
    if (!(ar > 0) || !(br > 0)) return (br > 0 ? 1 : 0) - (ar > 0 ? 1 : 0);
    return (br - ar) * (order === "lowest" ? -1 : 1);
  });
  $("#product-reviews").replaceChildren();
  items.slice(0,reviewLimit).forEach(review => {
    const card = element("article", "detail-review");
    const head = element("div","detail-review-head");
    head.append(element("strong","",review.author || "Покупатель"));
    const score = Number(review.rating);
    const date = Date.parse(review.date);
    const meta = [score > 0 && score <= 5 ? "★ " + score : "", Number.isFinite(date) ? new Date(date).toLocaleDateString("ru-RU") : ""].filter(Boolean);
    head.append(element("span","",meta.join(" · ")));
    const body = element("p","review-text",review.body);
    card.append(head,body);
    if (review.body.length > 420) {
      body.classList.add("review-text-collapsed");
      const more = element("button","text-button","Читать полностью"); more.type = "button"; more.setAttribute("aria-expanded","false");
      more.addEventListener("click", () => {
        const collapsed = body.classList.toggle("review-text-collapsed");
        more.textContent = collapsed ? "Читать полностью" : "Свернуть"; more.setAttribute("aria-expanded",String(!collapsed));
      });
      card.append(more);
    }
    $("#product-reviews").append(card);
  });
  if (!items.length) $("#product-reviews").append(element("p","detail-muted",score ? "Отзывов с такой оценкой среди доступных нет." : "Магазин не передал тексты отзывов. Их можно посмотреть на странице товара."));
  $("#review-feedback").textContent = items.length ? "Показано " + Math.min(reviewLimit,items.length) + " из " + items.length + " доступных отзывов" : "";
  $("#review-more").hidden = reviewLimit >= items.length;
  const nextBatch = Math.min(5,Math.max(0,items.length-reviewLimit));
  $("#review-more").textContent = "Показать ещё " + nextBatch + " " + reviewsWord(nextBatch);
  $("#review-availability").textContent = Number(offer.review_count) > available.length
    ? "У магазина больше оценок и отзывов, чем доступно здесь. Полный список — на его странице товара." : "";
  const link = $("#review-store-link"); link.hidden = !offer.url; if (offer.url) link.href = offer.url;
}
function showSource(index) {
  selectedSource = index; reviewLimit = 5; specsExpanded = false;
  $("#spec-search").value = ""; $("#review-rating").value = "";
  const offer = sources[index]; if (!offer) return;
  activeVariant=variantKey(offer);$("#product-variant").value=activeVariant;
  $("#product-title").textContent=offer.title;renderOffers();
  $("#product-description").textContent = offer.description || "Магазин не передал описание товара.";
  const rating = Number(offer.rating);
  $("#product-rating").textContent = rating > 0 && rating <= 5 ? rating.toLocaleString("ru-RU") + " из 5" : "Оценка не указана";
  $("#product-review-count").textContent = offer.review_count != null ? "Оценок и отзывов: " + Number(offer.review_count).toLocaleString("ru-RU") : "Количество оценок не указано";
  showGallery(offer); showSpecs(); showReviews();
}
function renderOffers() {
  const visible=sources.filter(o=>variantKey(o)===activeVariant);
  const best = Catalog.bestOffers(visible);
  $("#product-offers").replaceChildren();
  for (const offer of visible) {
    const card = element("article", "product-offer-card" + (best.has(offer) ? " recommended-offer" : ""));
    const info = element("div","product-offer-info");
    const badgeList = element("div","offer-badges");
    Catalog.badges(offer,best).forEach(badge => badgeList.append(element("span","best-price-badge",badge)));
    if (badgeList.childElementCount) info.append(badgeList);
    info.append(element("strong","",offer.marketplace));
    if(offer.seller)info.append(element("span","","Продавец: "+offer.seller));
    if(variantLabel(offer)!=="Вариант не указан")info.append(element("span","variant-summary",variantLabel(offer)));
    if (offer.in_stock != null) info.append(element("span","stock-badge" + (offer.in_stock ? "" : " stock-badge-empty"),offer.in_stock ? "В наличии" : "Нет в наличии"));
    info.append(element("span","offer-delivery",Catalog.deliveryLabel(offer)));
    if (offer.delivery?.cost != null) info.append(element("span","", "Стоимость доставки: " + (Number(offer.delivery.cost) === 0 ? "бесплатно" : money(offer.delivery.cost,offer.delivery.currency))));
    const controls = element("div","product-offer-controls");
    controls.append(element("strong","product-offer-price",money(offer.price,offer.currency)));
    const link = element("a","button " + (best.has(offer) || visible.length === 1 ? "button-primary" : "button-secondary"),"В магазин ↗");
    link.href = offer.url; link.target = "_blank"; link.rel = "noopener noreferrer";
    controls.append(link); card.append(info,controls); $("#product-offers").append(card);
  }
  const choices = [...best];
  const recommendation = choices.find(o => Catalog.currency(o) === "RUB") || choices[0];
  const hero = $("#product-best-price"); hero.replaceChildren(); hero.hidden = !visible.length;
  if (recommendation) {
    hero.append(element("strong","","Лучшее предложение · " + money(recommendation.price,recommendation.currency)),element("span","",recommendation.marketplace + " · " + Catalog.deliveryLabel(recommendation)));
  } else {
    const prices = new Map();
    visible.filter(o => o.in_stock !== false).forEach(o => prices.set(Catalog.currency(o),Math.min(prices.get(Catalog.currency(o)) ?? Infinity,Number(o.price))));
    hero.textContent = prices.size ? "Цена: " + [...prices].map(([c,p]) => money(p,c)).join(" · ") : "Нет предложений в наличии";
  }
  if(visible.length)$("#product-collection-actions").replaceChildren(window.MultiMarketLibrary.controls({title:sources[selectedSource]?.title||visible[0].title,offers:visible}));
}
function updateSourceSelect() {
  const select = $("#product-source"); select.replaceChildren();
  sources.forEach((o,i) => {const option=new Option(o.marketplace+(o.seller?" · "+o.seller:""),String(i));option.dataset.marketplace=o.marketplace;select.append(option);});
  select.value = String(selectedSource); $("#product-source-toolbar").hidden = !sources.length;
  window.MultiMarketPickup?.refresh();
}
async function loadProduct() {
  const product = readProduct();
  if (!product) {
    $("#product-title").textContent = "Карточка товара недоступна";
    $("#product-status").textContent = "Вернитесь к поиску и откройте товар из результатов.";
    $("#product-description").textContent = "Нет данных."; showSpecs(); showReviews(); return;
  }
  sources = product.offers.map(o => ({...o,delivery:Region.scopeDelivery(o.delivery)}));
  Region.observeOffers(sources);
  document.title = product.title + " — MultiMarket"; $("#product-title").textContent = product.title;
  [...new Set(sources.map(o => o.marketplace))].forEach(m => $("#product-marketplaces").append(element("span","marketplace-chip",m)));
  const richness = o => Catalog.images(o).length + (o.specifications?.length || 0) + (o.reviews?.length || 0) + (o.description ? 1 : 0);
  selectedSource = sources.reduce((best,o,i) => richness(o) > richness(sources[best]) ? i : best,0);
  updateVariants(); renderOffers(); updateSourceSelect(); showSource(selectedSource);
  $("#product-status").textContent = "Обновляем фотографии, характеристики, отзывы и доставку…";
  let userSelected = false;
  $("#product-source").addEventListener("change", event => {userSelected = true; showSource(Number(event.target.value));});
  const results = await Promise.all(sources.map(async offer => {
    try {
      const params = new URLSearchParams({marketplace:offer.marketplace,product_url:offer.url});
      if (Region.getId() !== null) params.set("region_id",String(Region.getId()));
      const response = await fetch("/api/product-details?" + params,{headers:{Accept:"application/json"}});
      const data = await response.json();
      if (!response.ok || !data.details_available) return null;
      return data;
    } catch { return null; }
  }));
  sources = sources.map((offer,i) => {
    const detail = results[i]; if (!detail) return offer;
    const next = {...offer};
    for (const key of ["description","rating","review_count","in_stock","brand","model","seller","condition"]) if (detail[key] != null && detail[key] !== "") next[key] = detail[key];
    next.variants=Object.keys(detail.variants||{}).length?detail.variants:offer.variants;
    next.image_urls = [...new Set([...Catalog.images(detail),...Catalog.images(offer)])].slice(0,20); next.image_url = next.image_urls[0];
    next.specifications = detail.specifications?.length ? detail.specifications : offer.specifications;
    next.reviews = reviewItems({reviews:[...(detail.reviews || []),...(offer.reviews || [])]});
    next.delivery = Object.keys(detail.delivery || {}).length ? detail.delivery : offer.delivery;
    return next;
  });
  if (!userSelected) selectedSource = sources.reduce((best,o,i) => richness(o) > richness(sources[best]) ? i : best,0);
  Region.observeOffers(sources);
  updateVariants(); renderOffers(); updateSourceSelect(); showSource(selectedSource);
  $("#product-status").textContent = sources.some(o => o.delivery?.region_confirmed === false)
    ? "Магазин не подтвердил выбранный город. Срок доставки уточните в магазине."
    : results.some(Boolean) ? "Сведения обновлены из доступных карточек магазинов." : "Показаны доступные сведения из поиска. Остальные подробности можно уточнить в магазине.";
}
$("#spec-search").addEventListener("input",showSpecs);
$("#product-variant").addEventListener("change",()=>{activeVariant=$("#product-variant").value;selectedSource=sources.findIndex(o=>variantKey(o)===activeVariant);updateSourceSelect();showSource(selectedSource);});
function selectAboutTab(name, focus = false) {
  for (const key of ["description", "specs"]) {
    const active = key === name;
    const tab = $("#about-" + key + "-tab");
    tab.setAttribute("aria-selected",String(active));
    tab.tabIndex = active ? 0 : -1;
    tab.classList.toggle("active",active);
    $("#about-" + key + "-panel").hidden = !active;
    if (active && focus) tab.focus();
  }
}
for (const key of ["description", "specs"]) {
  $("#about-" + key + "-tab").addEventListener("click",() => selectAboutTab(key));
  $("#about-" + key + "-tab").addEventListener("keydown",event => {
    if (["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) {
      event.preventDefault();
      selectAboutTab(event.key === "Home" ? "description" : event.key === "End" ? "specs" : key === "specs" ? "description" : "specs",true);
    }
  });
}
$("#spec-more").addEventListener("click", () => {specsExpanded = !specsExpanded; if (!specsExpanded) $("#spec-search").value=""; showSpecs();});
$("#review-more").addEventListener("click", () => {reviewLimit += 5; showReviews();});
for (const id of ["#review-rating","#review-sort"]) $(id).addEventListener("change", () => {reviewLimit=5; showReviews();});
for (const id of ["#gallery-prev","#gallery-dialog-prev"]) $(id).addEventListener("click", () => showImage(imageIndex-1));
for (const id of ["#gallery-next","#gallery-dialog-next"]) $(id).addEventListener("click", () => showImage(imageIndex+1));
$("#gallery-open").addEventListener("click", () => $("#gallery-dialog").showModal());
$("#gallery-close").addEventListener("click", () => $("#gallery-dialog").close());
for (const id of ["#product-image-wrap","#gallery-dialog"]) $(id).addEventListener("keydown", event => {
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {event.preventDefault(); showImage(imageIndex+(event.key === "ArrowRight" ? 1 : -1));}
});
document.addEventListener("multimarket:regionchange", () => location.reload());
Region.ready.then(loadProduct);
