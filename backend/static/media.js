(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.MultiMarketMedia=api;})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const placeholder='data:image/svg+xml;charset=utf-8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200" viewBox="0 0 320 200"><rect width="320" height="200" fill="#f5f5f7"/><text x="160" y="105" text-anchor="middle" font-family="Arial,sans-serif" font-size="32" fill="#73737c">Фото недоступно</text></svg>');
  function candidates(offer,urls){
    const raw=urls||[offer?.image_url,...(Array.isArray(offer?.image_urls)?offer.image_urls:[])],result=[];
    for(const value of raw){
      let url;try{url=new URL(String(value||'').replace(/\u200b/g,''));}catch{continue;}
      if(url.protocol!=='https:'||url.username||url.password)continue;
      const match=url.pathname.match(/^\/vol\d+\/part\d+\/([1-9]\d{0,14})\/images\/(?:big|c246x328|c516x688|tm)\/(\d{1,2})\.(?:webp|jpg)$/);
      const expected=String(offer?.external_id||'').match(/^[1-9]\d{0,14}$/)?.[0]||String(offer?.url||'').match(/\/catalog\/([1-9]\d{0,14})\/detail\.aspx/)?.[1];
      if(offer?.marketplace==='Wildberries'&&/^basket-\d{2,3}\.wbbasket\.ru$/.test(url.hostname)&&match&&Number(match[2])>=1&&Number(match[2])<=20&&(!expected||expected===match[1])){
        result.push('/api/media/wb/'+match[1]+'/'+Number(match[2]));
      }
      result.push(url.href);
    }
    return [...new Set(result)].slice(0,6);
  }
  function set(img,offer,options={}){
    const urls=candidates(offer,options.urls);let index=0;
    img.referrerPolicy='no-referrer';img.decoding='async';
    if(options.lazy)img.loading='lazy';
    const next=()=>{if(index<urls.length){img.src=urls[index++];}else{img.onerror=null;img.src=placeholder;img.alt='Фото недоступно';img.dataset.photoUnavailable='true';}};
    img.onerror=next;img.onload=()=>{if(img.src!==placeholder)delete img.dataset.photoUnavailable;};
    next();return img;
  }
  return {candidates,set,placeholder};
});
