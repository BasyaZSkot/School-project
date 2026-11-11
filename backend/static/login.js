const providerStatus = document.querySelector("#provider-status");
const errorBox = document.querySelector("#login-error");
const query = new URLSearchParams(window.location.search);
const next = query.get("next") || "/account";

const errors = {
  cancelled: "Вход отменён. Вы можете попробовать ещё раз.",
  provider: "Не удалось подтвердить аккаунт. Проверьте настройки OAuth и повторите вход."
};
if (errors[query.get("error")]) {
  errorBox.textContent = errors[query.get("error")];
  errorBox.hidden = false;
}

for (const provider of ["google", "yandex"]) {
  const link = document.querySelector(`#${provider}-login`);
  link.href = "/auth/" + provider + "?next=" + encodeURIComponent(next);
}

fetch("/api/auth/config", { headers: { Accept: "application/json" } })
  .then(response => response.json())
  .then(data => {
    if (data.authenticated) {
      window.location.replace("/account");
      return;
    }
    const enabled = [];
    for (const provider of ["google", "yandex"]) {
      if (data.providers?.[provider]) {
        document.querySelector(`#${provider}-login`).hidden = false;
        enabled.push(provider);
      }
    }
    providerStatus.textContent = enabled.length
      ? "Выберите провайдера, чтобы продолжить."
      : "Вход пока не настроен. Добавьте OAuth client ID, client secret и redirect URI в backend/.env.";
  })
  .catch(() => {
    providerStatus.textContent = "Не удалось проверить настройки входа. Попробуйте обновить страницу.";
  });

