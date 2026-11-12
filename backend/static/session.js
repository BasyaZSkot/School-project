(function(){
  "use strict";
  let state={authenticated:false,user:null,csrf_token:"",error:false};
  async function refresh(){
    try{const r=await fetch("/api/auth/me",{headers:{Accept:"application/json"},cache:"no-store"});if(!r.ok)throw Error();state={...await r.json(),error:false};}
    catch{state={authenticated:false,user:null,csrf_token:"",error:true};}
    return state;
  }
  const ready=refresh();
  async function request(url,method="GET",body){
    await ready;
    const response=await fetch(url,{method,headers:{Accept:"application/json",...(body!==undefined?{"Content-Type":"application/json"}:{}),...(method!=="GET"?{"X-CSRF-Token":state.csrf_token}:{})},body:body===undefined?undefined:JSON.stringify(body),cache:"no-store"});
    let data;try{data=await response.json();}catch{throw Error("Сервис временно недоступен.");}
    if(!response.ok){const error=Error(typeof data.detail==="string"?data.detail:"Проверьте заполнение полей и повторите.");error.status=response.status;throw error;}
    return data;
  }
  window.MultiMarketSession={ready,refresh,request,get:()=>state};
})();
