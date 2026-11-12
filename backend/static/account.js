let csrfToken = "";
const message = document.querySelector("#account-message");
function showMessage(text) {
  message.textContent = text;
  message.hidden = !text;
}
function dateText(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : date.toLocaleDateString("ru-RU");
}

window.MultiMarketSession.ready
  .then(data => {
    if (!data.authenticated || !data.user) {
      window.location.replace("/login?next=/account");
      return;
    }
    const user = data.user;
    csrfToken = data.csrf_token || "";
    document.querySelector("#account-name").textContent = user.name || "Пользователь";
    document.querySelector("#account-email").textContent = user.email || "Email не передан провайдером";
    document.querySelector("#account-provider").textContent = ({ google: "Google", yandex: "Яндекс", local: "Почта и пароль" })[user.provider] || user.provider;
    document.querySelector("#account-role").textContent = user.role === "admin" ? "Администратор" : "Пользователь";
    document.querySelector("#account-created").textContent = dateText(user.created_at);
    document.querySelector("#account-verified").textContent=user.email_verified?"Подтверждена":"Не подтверждена";
    document.querySelector("#email-verification").hidden=!!user.email_verified || !user.email;
    loadNotificationSettings();
    if (user.picture_url && user.picture_url.startsWith("https://")) {
      const image = document.querySelector("#account-picture");
      image.src = user.picture_url;
      image.alt = "Фото профиля";
      image.hidden = false;
    }
    if (user.role === "admin") document.querySelector("#admin-link").hidden = false;
  })
  .catch(() => showMessage("Не удалось загрузить профиль. Обновите страницу."));

document.querySelector("#logout-button").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await fetch("/auth/logout", {
      method: "POST",
      headers: { "X-CSRF-Token": csrfToken }
    });
    if (!response.ok) throw new Error("Не удалось завершить сеанс.");
    window.MultiMarketPreferences?.logout();
    window.location.replace("/");
  } catch (error) {
    showMessage(error.message);
    button.disabled = false;
  }
});

document.querySelector("#verify-email").addEventListener("click",async event=>{
  const button=event.currentTarget;button.disabled=true;
  try{const data=await window.MultiMarketSession.request("/api/auth/email/request","POST");document.querySelector("#verify-message").textContent=data.message;}
  catch(e){document.querySelector("#verify-message").textContent=e.message;}
  finally{button.disabled=false;}
});
async function loadNotificationSettings(){
  try{
    const data=await window.MultiMarketSession.request("/api/notification-settings");
    const email=document.querySelector("#notification-email"),telegram=document.querySelector("#notification-telegram");
    email.checked=data.email_enabled;email.disabled=!data.email_available;
    telegram.checked=data.telegram_enabled;telegram.disabled=!data.telegram_connected;
    document.querySelector("#notification-email-status").textContent=data.email_available?"Письма будут приходить на почту аккаунта.":"Для писем нужна подтверждённая почта и доступная отправка писем.";
    document.querySelector("#notification-telegram-status").textContent=data.telegram_connected?"Подключён: "+data.telegram_name:data.telegram_available?"Подключите личный чат с ботом.":"Уведомления Telegram пока недоступны.";
    document.querySelector("#telegram-connect").disabled=!data.telegram_available;
    document.querySelector("#telegram-disconnect").hidden=!data.telegram_connected;
  }catch(e){document.querySelector("#notification-message").textContent=e.message;}
}
document.querySelector("#notification-form").addEventListener("submit",async e=>{
  e.preventDefault();try{await window.MultiMarketSession.request("/api/notification-settings","PATCH",{email_enabled:document.querySelector("#notification-email").checked,telegram_enabled:document.querySelector("#notification-telegram").checked});document.querySelector("#notification-message").textContent="Каналы уведомлений сохранены.";}catch(error){document.querySelector("#notification-message").textContent=error.message;}
});
document.querySelector("#telegram-connect").addEventListener("click",async()=>{
  try{const data=await window.MultiMarketSession.request("/api/notification-settings/telegram","POST");const link=document.querySelector("#telegram-connect-link");link.href=data.url;link.hidden=false;document.querySelector("#notification-message").textContent="Откройте бота, нажмите «Начать», затем проверьте подключение. Ссылка действует 10 минут.";}catch(e){document.querySelector("#notification-message").textContent=e.message;}
});
document.querySelector("#telegram-disconnect").addEventListener("click",async()=>{try{await window.MultiMarketSession.request("/api/notification-settings/telegram","DELETE");document.querySelector("#telegram-connect-link").hidden=true;await loadNotificationSettings();}catch(e){document.querySelector("#notification-message").textContent=e.message;}});
document.querySelector("#notification-refresh").addEventListener("click",loadNotificationSettings);
