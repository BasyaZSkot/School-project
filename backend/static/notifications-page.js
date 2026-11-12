(function(){
  "use strict";const S=window.MultiMarketSession,$=s=>document.querySelector(s),el=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
  async function load(){try{
    const auth=await S.ready;if(!auth.authenticated){location.replace("/login?next=/notifications");return;}
    const [data,monitors]=await Promise.all([S.request("/api/alerts"),S.request("/api/monitors")]);const names=new Map(monitors.monitors.map(m=>[m.id,m]));$("#alerts-list").replaceChildren();
    if(!data.alerts.length){$("#alerts-list").append(el("p","Уведомлений пока нет. В «Моих товарах» задайте целевую цену или процент изменения.","empty-panel"));return;}
    for(const alert of data.alerts){const monitor=names.get(alert.monitor_id),card=el("article","","notification-card"+(alert.read_at?"":" notification-unread"));card.append(el("h2",alert.reason==="target"?"Достигнута целевая цена":alert.change_percent<0?"Цена снизилась":"Цена выросла"),el("p",monitor?.title||"Товар"));card.append(el("strong",new Intl.NumberFormat("ru-RU",{style:"currency",currency:alert.currency}).format(alert.new_price)),el("p",new Date(alert.created_at).toLocaleString("ru-RU"),"muted"));
      const deliveryLabels={sent:"отправлено",pending:"ожидает отправки",sending:"отправляется",failed:"не удалось отправить",cancelled:"отменено"};const statuses=Object.entries(alert.deliveries||{}).map(([channel,status])=>(channel==="email"?"Email":"Telegram")+": "+(deliveryLabels[status]||status));if(statuses.length)card.append(el("p",statuses.join(" · "),"muted"));
      const actions=el("div","","toolbar-actions"),history=el("a","История цены","button button-secondary");history.href="/history?monitor_id="+encodeURIComponent(alert.monitor_id);actions.append(history);
      if(!alert.read_at){const button=el("button","Прочитано","text-button");button.type="button";button.addEventListener("click",async()=>{try{await S.request("/api/alerts/"+alert.id+"/read","PATCH");await load();}catch(e){$("#alerts-message").textContent=e.message;}});actions.append(button);}card.append(actions);$("#alerts-list").append(card);
    }
  }catch(e){$("#alerts-message").textContent=e.message;}}
  $("#alerts-refresh").addEventListener("click",load);load();
})();
