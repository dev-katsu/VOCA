const usernameEl = document.getElementById("username");
const passwordEl = document.getElementById("password");
const showPwEl   = document.getElementById("showPw");
const errorEl    = document.getElementById("errorMsg");
const loginBtn   = document.getElementById("loginBtn");

showPwEl.addEventListener("change", () => {
  passwordEl.type = showPwEl.checked ? "text" : "password";
});

async function doLogin() {
  const username = usernameEl.value.trim();
  const password = passwordEl.value;

  errorEl.textContent = "";

  if (!username || !password) {
    errorEl.textContent = "Please fill in all fields.";
    return;
  }

  loginBtn.disabled = true;
  loginBtn.textContent = "LOGGING IN...";

  try {
    // Calls the Python function exposed in app.py — same check_login()
    // logic as the original Tkinter app, unchanged.
    const result = await eel.try_login(username, password)();

    if (result.ok) {
      errorEl.style.color = "#15803d";
      errorEl.textContent = "Success! Opening dashboard...";
      // Carry the logged-in user's info to the dashboard page.
      sessionStorage.setItem("voca_user", JSON.stringify({
        fullname: result.fullname,
        role: result.role
      }));
      setTimeout(() => { window.location.href = "dashboard.html"; }, 500);
    } else {
      errorEl.style.color = "#b91c1c";
      errorEl.textContent = "Invalid credentials. Access denied.";
      passwordEl.value = "";
      passwordEl.focus();
      loginBtn.disabled = false;
      loginBtn.textContent = "LOG IN";
    }
  } catch (err) {
    errorEl.style.color = "#b91c1c";
    errorEl.textContent = "Could not reach the application backend.";
    loginBtn.disabled = false;
    loginBtn.textContent = "LOG IN";
    console.error(err);
  }
}

loginBtn.addEventListener("click", doLogin);

[usernameEl, passwordEl].forEach(el => {
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doLogin();
  });
});

usernameEl.focus();