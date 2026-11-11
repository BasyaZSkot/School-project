let csrfToken = "";
const usersList = document.querySelector("#users-list");
const message = document.querySelector("#admin-message");
function showMessage(text) {
  message.textContent = text;
  message.hidden = !text;
}
function node(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
}

async function loadUsers() {
  showMessage("");
  usersList.replaceChildren(node("p", "muted", "Загружаем пользователей…"));
  try {
    const [meResponse, usersResponse] = await Promise.all([
      fetch("/api/auth/me", { headers: { Accept: "application/json" } }),
      fetch("/api/admin/users", { headers: { Accept: "application/json" } })
    ]);
    if (meResponse.status === 401 || usersResponse.status === 401) {
      window.location.replace("/login?next=/admin");
      return;
    }
    if (usersResponse.status === 403) throw new Error("Эта страница доступна только администратору.");
    const me = await meResponse.json();
    const data = await usersResponse.json();
    if (!meResponse.ok || !usersResponse.ok) throw new Error(data.detail || "Не удалось загрузить список.");
    csrfToken = me.csrf_token || "";
    const users = Array.isArray(data.users) ? data.users : [];
    document.querySelector("#admin-count").textContent = users.length + (users.length === 1 ? " аккаунт" : " аккаунтов");
    usersList.replaceChildren();
    for (const user of users) {
      const row = node("article", "admin-user-row");
      const identity = node("div", "admin-user-identity");
      identity.append(node("strong", "", user.name || "Пользователь"));
      identity.append(node("span", "", user.email || "Email не указан"));
      identity.append(node("small", "", user.provider === "google" ? "Google" : "Яндекс"));
      const role = document.createElement("select");
      role.className = "admin-role-select";
      role.setAttribute("aria-label", "Роль пользователя " + (user.name || ""));
      for (const [value, label] of [["user", "Пользователь"], ["admin", "Администратор"]]) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        role.append(option);
      }
      role.value = user.role;
      const save = node("button", "button button-secondary", "Сохранить роль");
      save.type = "button";
      save.addEventListener("click", async () => {
        save.disabled = true;
        try {
          const response = await fetch("/api/admin/users/" + encodeURIComponent(user.id), {
            method: "PATCH",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
            body: JSON.stringify({ role: role.value })
          });
          const result = await response.json();
          if (!response.ok) throw new Error(result.detail || "Не удалось изменить роль.");
          showMessage("Роль пользователя обновлена.");
          await loadUsers();
        } catch (error) {
          showMessage(error.message);
          save.disabled = false;
        }
      });
      row.append(identity, role, save);
      usersList.append(row);
    }
    if (!users.length) usersList.append(node("p", "empty-panel", "Пока нет аккаунтов."));
  } catch (error) {
    usersList.replaceChildren();
    showMessage(error.message || "Не удалось загрузить список пользователей.");
  }
}

document.querySelector("#refresh-users").addEventListener("click", loadUsers);
loadUsers();

