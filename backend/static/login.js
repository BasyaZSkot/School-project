const providerStatus = document.querySelector("#provider-status");
const errorBox = document.querySelector("#login-error");
const query = new URLSearchParams(window.location.search);
const requestedNext = query.get("next") || "/account";
const target = new URL(requestedNext, location.origin);
const next = target.origin === location.origin && !requestedNext.includes("\\") ? target.pathname + target.search : "/account";
let registering = false;
const passwordForm = document.querySelector("#password-form");
const passwordInput = document.querySelector("#login-password");
const submitButton = document.querySelector("#password-submit");
document.querySelector("#switch-mode").addEventListener("click", event => {
  registering = !registering;
  document.querySelector("#name-field").hidden = !registering;
  document.querySelector("#login-name").required = registering;
  document.querySelector("#password-hint").hidden = !registering;
  passwordInput.minLength = registering ? 8 : 1;
  passwordInput.autocomplete = registering ? "new-password" : "current-password";
  submitButton.textContent = registering ? "Зарегистрироваться" : "Войти";
  document.querySelector("h1").textContent = registering ? "Создать аккаунт" : "Вход в аккаунт";
  event.currentTarget.textContent = registering ? "Уже есть аккаунт? Войти" : "Нет аккаунта? Зарегистрироваться";
  errorBox.hidden = true;
});
passwordForm.addEventListener("submit", async event => {
  event.preventDefault();
  submitButton.disabled = true;
  errorBox.hidden = true;
  try {
    const meResponse = await fetch("/api/auth/me");
    if (!meResponse.ok) throw new Error("Не удалось начать вход. Попробуйте ещё раз.");
    const me = await meResponse.json();
    const response = await fetch(registering ? "/api/auth/register" : "/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": me.csrf_token },
      body: JSON.stringify({ email: document.querySelector("#login-email").value,
        password: passwordInput.value, name: document.querySelector("#login-name").value })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Проверьте заполнение полей.");
    location.assign(next);
  } catch (error) {
    errorBox.textContent = error.message || "Не удалось войти. Попробуйте ещё раз.";
    errorBox.hidden = false;
  } finally { submitButton.disabled = false; }
});

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
      window.location.replace(next);
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
      ? "Или войдите через другой сервис."
      : "Ваши товары будут доступны только вам.";
  })
  .catch(() => {
    providerStatus.textContent = "Не удалось проверить настройки входа. Попробуйте обновить страницу.";
  });
