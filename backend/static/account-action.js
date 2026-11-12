(function(){
  "use strict";const S=window.MultiMarketSession,$=s=>document.querySelector(s),mode=location.pathname,token=new URLSearchParams(location.hash.slice(1)).get("token")||"";
  history.replaceState(null,"",location.pathname);const reset=mode==="/reset-password",verify=mode==="/confirm-email",forgot=!reset&&!verify;
  $("#action-title").textContent=forgot?"Восстановить пароль":reset?"Новый пароль":"Подтвердить почту";document.title=$("#action-title").textContent+" — MultiMarket";
  $("#action-intro").textContent=forgot?"Укажите почту аккаунта. Мы пришлём ссылку для смены пароля.":reset?"Придумайте пароль от 8 до 128 символов. После изменения потребуется войти заново.":"Нажмите кнопку, чтобы подтвердить, что этот адрес почты принадлежит вам.";
  $("#action-email-field").hidden=!forgot;$("#action-email").required=forgot;
  for(const id of ["password","repeat"]){$("#action-"+id+"-field").hidden=!reset;$("#action-"+id).required=reset;}
  $("#action-submit").textContent=forgot?"Отправить ссылку":reset?"Сохранить новый пароль":"Подтвердить почту";
  function note(text){$("#action-message").hidden=false;$("#action-message").textContent=text;}
  if(!forgot&&!/^[A-Za-z0-9_-]{40,100}$/.test(token)){$("#action-submit").disabled=true;note("В ссылке нет действительного кода. Запросите новое письмо.");$("#action-next").href=verify?"/account":"/forgot-password";$("#action-next").textContent=verify?"Перейти в аккаунт":"Запросить новую ссылку";}
  $("#action-form").addEventListener("submit",async e=>{
    e.preventDefault();const button=$("#action-submit");button.disabled=true;
    try{
      if(reset&&$("#action-password").value!==$("#action-repeat").value)throw Error("Пароли не совпадают.");
      const url=forgot?"/api/auth/password-reset/request":reset?"/api/auth/password-reset/confirm":"/api/auth/email/confirm";
      const payload=forgot?{email:$("#action-email").value}:reset?{token,password:$("#action-password").value}:{token};
      const result=await S.request(url,"POST",payload);note(result.message);$("#action-form").hidden=true;
      if(verify){$("#action-next").href="/account";$("#action-next").textContent="Перейти в аккаунт";}
    }catch(error){note(error.message);button.disabled=false;}
  });
})();
