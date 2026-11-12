(function(){
  "use strict";
  const S=window.MultiMarketSession,D=window.MultiMarketPickupData;
  const REGION="multimarket.region.v1",OWNER="multimarket.preferences.owner",GUEST="multimarket.preferences.guest";
  let currentUser=null,pending=null,saving=false,message="Сохраняется в этом браузере";
  function show(text){message=text;document.querySelectorAll("[data-preferences-status]").forEach(n=>n.textContent=text);document.dispatchEvent(new CustomEvent("multimarket:preferencestatus",{detail:{message:text}}));}
  function raw(){return {region:localStorage.getItem(REGION),pickup:localStorage.getItem(D.KEY)};}
  function restore(data){for(const [key,value] of [[REGION,data?.region],[D.KEY,data?.pickup]]){if(value===null||value===undefined)localStorage.removeItem(key);else localStorage.setItem(key,value);}}
  const ready=(async()=>{
    const auth=await S.ready;
    try{
      const owner=localStorage.getItem(OWNER);
      if(!auth.authenticated){if(owner){restore(JSON.parse(localStorage.getItem(GUEST)||"null"));localStorage.removeItem(OWNER);}show("Сохраняется в этом браузере. Войдите, чтобы синхронизировать выбор.");return;}
      currentUser=auth.user.id;if(!owner)localStorage.setItem(GUEST,JSON.stringify(raw()));
      const data=await S.request("/api/preferences/delivery");
      if(data.delivery){localStorage.setItem(REGION,JSON.stringify({version:1,id:data.delivery.region_id}));localStorage.setItem(D.KEY,JSON.stringify({version:1,choices:data.delivery.choices}));}
      else if(owner && owner!==currentUser)restore(null);
      else{const region=JSON.parse(localStorage.getItem(REGION)||"null");await S.request("/api/preferences/delivery","PUT",{region_id:region?.id??null,choices:D.read(localStorage)});}
      localStorage.setItem(OWNER,currentUser);show("Город и ПВЗ синхронизируются с аккаунтом");
    }catch{show("Не удалось загрузить настройки аккаунта. Обновите страницу.");currentUser=null;}
  })();
  async function save(){
    await ready;if(!currentUser)return;
    try{const region=JSON.parse(localStorage.getItem(REGION)||"null");pending={region_id:region?.id??null,choices:D.read(localStorage)};}catch{return;}
    if(saving)return;saving=true;
    while(pending){const data=pending;pending=null;show("Сохраняем в аккаунте…");try{await S.request("/api/preferences/delivery","PUT",data);show("Сохранено в аккаунте");}catch{show("Выбор сохранён в браузере. Не удалось синхронизировать — повторите изменение позже.");}}
    saving=false;
  }
  function logout(){try{restore(JSON.parse(localStorage.getItem(GUEST)||"null"));localStorage.removeItem(OWNER);}catch{}currentUser=null;}
  document.addEventListener("multimarket:regionchange",save);document.addEventListener("multimarket:pickupchange",save);
  window.MultiMarketPreferences={ready,save,logout,getMessage:()=>message};
})();
