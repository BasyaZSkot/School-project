(function(root,factory){const api=factory();if(typeof module==="object"&&module.exports)module.exports=api;else root.MultiMarketLibraryData=api;})(typeof window==="undefined"?globalThis:window,function(){
  "use strict";
  const KEY="multimarket.compare.v1",hosts={Ozon:["ozon.ru"],Wildberries:["wildberries.ru","wildberries.by","wildberries.kz"],"Яндекс Маркет":["market.yandex.ru"]};
  const norm=v=>String(v||"").toLocaleLowerCase("ru").replace(/ё/g,"е").replace(/\s+/g," ").trim();
  const canonical=v=>String(v||"").normalize("NFKC").toLowerCase().replace(/ё/g,"е").replace(/[^0-9a-zа-я]+/g," ").trim();
  const colors={"черный":"чёрный",black:"чёрный","белый":"белый",white:"белый",silver:"серебристый","серебристый":"серебристый",gray:"серый",grey:"серый","серый":"серый",blue:"синий","синий":"синий","голубой":"голубой",green:"зелёный","зеленый":"зелёный",red:"красный","красный":"красный",pink:"розовый","розовый":"розовый",purple:"фиолетовый","фиолетовый":"фиолетовый",gold:"золотой","золотой":"золотой",graphite:"графитовый","графитовый":"графитовый",beige:"бежевый","бежевый":"бежевый"};
  function capacity(value){const m=String(value).toLowerCase().match(/(?:^|[^0-9])(\d+(?:[.,]\d+)?)\s*(тб|tb|гб|gb|мб|mb)(?=$|[^0-9a-zа-я])/);if(!m)return null;const n=Number(m[1].replace(",","."))*(["tb","тб"].includes(m[2])?1024:["mb","мб"].includes(m[2])?1/1024:1);return n+" ГБ";}
  function variants(o){
    const result={};for(const key of ["storage","ram","color","package","condition","version"]){const value=o.variants?.[key];if(typeof value==="string"&&value)result[key]=["storage","ram"].includes(key)?capacity(value):canonical(value);}
    for(const spec of (o.specifications||[]).slice(0,100)){if(!spec?.name||!spec.value)continue;const name=canonical(spec.name);let key;
      if(["цвет","цвет товара","color"].includes(name))key="color";
      else if(name.includes("оперативн")||name==="ram")key="ram";
      else if(["память","объем памяти","storage","storage capacity"].includes(name)||(name.includes("встроенн")&&name.includes("памят")))key="storage";
      else if(["комплектация","комплект поставки","package"].includes(name))key="package";
      else if(["состояние","condition"].includes(name))key="condition";
      else if(["версия","региональная версия"].includes(name))key="version";
      if(key)result[key]=["storage","ram"].includes(key)?capacity(spec.value):canonical(spec.value);
    }
    let rest=canonical(o.title);for(const value of [o.brand,o.model])if(value)rest=rest.split(canonical(value)).join(" ");
    const pair=String(o.title||"").toLowerCase().match(/(?:^|[^0-9a-zа-я])(\d{1,3})\s*[/+]\s*(\d{2,4})\s*(?:gb|гб)(?=$|[^0-9a-zа-я])/);
    if(pair){result.ram??=pair[1]+" ГБ";result.storage??=pair[2]+" ГБ";}
    else if(!result.storage){const found=[...String(o.title||"").toLowerCase().matchAll(/(?:^|[^0-9a-zа-я])(\d+(?:[.,]\d+)?\s*(?:gb|гб|tb|тб))(?=$|[^0-9a-zа-я])/g)];if(found.length===1)result.storage=capacity(found[0][1]);}
    const tokens=new Set(rest.split(/\s+/)),matches=new Set(Object.entries(colors).filter(([word])=>tokens.has(word)).map(([,color])=>color));if(matches.size===1&&!result.color)result.color=[...matches][0];
    if(result.color)result.color=colors[canonical(result.color)]||canonical(result.color);
    const state=" "+(canonical(o.condition)||result.condition||canonical(o.title))+" ";
    if(["восстановленный","восстановлен","refurbished","refurb"].some(word=>state.includes(" "+word+" ")))result.condition="восстановленный";
    else if(["б у","бу","used","бывший в употреблении"].some(word=>state.includes(" "+word+" ")))result.condition="б/у";
    else if(["новый","новое","new"].some(word=>state.includes(" "+word+" ")))result.condition="новый";
    else if(o.condition)result.condition=canonical(o.condition);
    return Object.fromEntries(Object.entries(result).filter(([,v])=>v).sort(([a],[b])=>a<b?-1:a>b?1:0));
  }
  function validUrl(market,value){try{const u=new URL(value);return u.protocol==="https:"&&!u.username&&!u.password&&(!u.port||u.port==="443")&&(hosts[market]||[]).some(h=>u.hostname===h||u.hostname.endsWith("."+h));}catch{return false;}}
  function identity(product){return [...new Set(product.offers.map(o=>{const url=new URL(o.url),params=[...url.searchParams].filter(([k])=>!["lr","yclid","gclid","_openstat"].includes(k.toLowerCase())&&!k.toLowerCase().startsWith("utm_")).sort(([a,av],[b,bv])=>a<b?-1:a>b?1:av<bv?-1:av>bv?1:0),query=new URLSearchParams(params).toString();return JSON.stringify([o.marketplace,url.pathname.replace(/\/$/,"")+(query?"?"+query:""),String(o.external_id||""),variants(o)]);} ))].sort().join("|");}
  function locator(o){const u=new URL(o.url),params=[...u.searchParams].filter(([k])=>!["lr","yclid","gclid","_openstat"].includes(k.toLowerCase())&&!k.toLowerCase().startsWith("utm_")).sort(([a,av],[b,bv])=>a<b?-1:a>b?1:av<bv?-1:av>bv?1:0),query=new URLSearchParams(params).toString();return o.marketplace+":"+u.pathname.replace(/\/$/,"")+(query?"?"+query:"");}
  function sameProduct(left,right){return left.offers.some(a=>right.offers.some(b=>{if(locator(a)!==locator(b)||(a.external_id&&b.external_id&&a.external_id!==b.external_id))return false;const av=a.variants||variants(a),bv=b.variants||variants(b);return Object.keys(av).every(k=>!(k in bv)||av[k]===bv[k]);}));}
  function snapshot(product){
    if(!product||typeof product.title!=="string"||!Array.isArray(product.offers))return null;
    const offers=product.offers.filter(o=>o&&validUrl(o.marketplace,o.url)&&typeof o.price==="number"&&Number.isFinite(o.price)&&o.price>0&&/^[A-Z]{3}$/.test(o.currency||"RUB")).slice(0,12).map(o=>{
      const images=[o.image_url,...(Array.isArray(o.image_urls)?o.image_urls:[])].filter(v=>{try{const u=new URL(v);return u.protocol==="https:"&&!u.username&&!u.password;}catch{return false;}}).slice(0,20);
      return {marketplace:o.marketplace,url:o.url,title:String(o.title||product.title).slice(0,300),price:o.price,currency:o.currency||"RUB",external_id:String(o.external_id||"").slice(0,200),brand:String(o.brand||"").slice(0,200),model:String(o.model||"").slice(0,200),seller:String(o.seller||"").slice(0,200),condition:String(o.condition||"").slice(0,160),in_stock:typeof o.in_stock==="boolean"?o.in_stock:null,image_url:images[0],image_urls:images,variants:variants({...o,title:o.title||product.title}),specifications:(Array.isArray(o.specifications)?o.specifications:[]).filter(s=>s&&s.name&&s.value).slice(0,100).map(s=>({name:String(s.name).slice(0,160),value:String(s.value).slice(0,500)}))};
    });
    if(!offers.length)return null;const value={title:product.title.slice(0,300),offers};value.identity=identity(value);return value;
  }
  function read(storage){try{const raw=JSON.parse(storage.getItem(KEY)||"[]");return Array.isArray(raw)?raw.map(snapshot).filter(Boolean).filter((p,i,all)=>all.findIndex(x=>sameProduct(x,p))===i).slice(0,4):[];}catch{return [];}}
  function toggle(storage,product){const item=snapshot(product);if(!item)throw Error("Нет данных для сравнения");const list=read(storage),index=list.findIndex(p=>sameProduct(p,item));if(index>=0)list.splice(index,1);else{if(list.length>=4)throw Error("Можно сравнить до четырёх товаров. Удалите один на странице сравнения.");list.push(item);}storage.setItem(KEY,JSON.stringify(list));return list;}
  function best(product){const available=product.offers.filter(o=>o.in_stock!==false),list=available.length?available:product.offers,cur=list.some(o=>o.currency==="RUB")?"RUB":list[0]?.currency;return list.filter(o=>o.currency===cur).reduce((a,b)=>!a||b.price<a.price?b:a,null);}
  function rows(offers){
    const definitions=[["brand","Бренд"],["model","Модель"],["seller","Продавец"],["condition","Состояние"],["storage","Встроенная память"],["ram","Оперативная память"],["color","Цвет"],["package","Комплектация"],["version","Версия"]];
    const names=new Map(definitions),maps=offers.map(o=>{
      const data=new Map();for(const [key] of definitions){const value=o?.variants?.[key]||o?.[key];if(value)data.set(key,String(value));}
      for(const spec of o?.specifications||[]){const normalized=norm(spec.name),alias={"цвет товара":"color","цвет":"color","встроенная память":"storage","объем встроенной памяти":"storage","оперативная память":"ram","комплектация":"package","состояние":"condition","версия":"version","бренд":"brand","модель":"model"}[normalized],key=alias||"spec:"+normalized;if(!names.has(key))names.set(key,spec.name);if(!data.has(key))data.set(key,spec.value);}return data;
    });
    return [...names].filter(([key])=>maps.some(m=>m.has(key))).map(([key,name])=>{const values=maps.map(m=>m.get(key)||"Нет данных");return {key,name,values,different:new Set(values.map(norm)).size>1};});
  }
  return {KEY,norm,validUrl,identity,snapshot,read,toggle,best,rows,variants,locator,sameProduct};
});
