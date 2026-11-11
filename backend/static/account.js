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

fetch("/api/auth/me", { headers: { Accept: "application/json" } })
  .then(response => response.json())
  .then(data => {
    if (!data.authenticated || !data.user) {
      window.location.replace("/login?next=/account");
      return;
    }
    const user = data.user;
    csrfToken = data.csrf_token || "";
    document.querySelector("#account-name").textContent = user.name || "Пользователь";
    document.querySelector("#account-email").textContent = user.email || "Email не передан провайдером";
    document.querySelector("#account-provider").textContent = user.provider === "google" ? "Google" : "Яндекс";
    document.querySelector("#account-role").textContent = user.role === "admin" ? "Администратор" : "Пользователь";
    document.querySelector("#account-created").textContent = dateText(user.created_at);
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
    window.location.replace("/");
  } catch (error) {
    showMessage(error.message);
    button.disabled = false;
  }
});

