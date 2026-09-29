const fullnameEl = document.getElementById("fullname");
const facultyIdEl = document.getElementById("facultyId");
const passwordEl = document.getElementById("password");
const confirmEl = document.getElementById("confirmPassword");
const showPw1El = document.getElementById("showPw1");
const showPw2El = document.getElementById("showPw2");
const errorEl = document.getElementById("errorMsg");
const successEl = document.getElementById("successMsg");
const createBtn = document.getElementById("createBtn");

showPw1El.addEventListener("change", () => {
  passwordEl.type = showPw1El.checked ? "text" : "password";
});
showPw2El.addEventListener("change", () => {
  confirmEl.type = showPw2El.checked ? "text" : "password";
});

function setError(msg) {
  successEl.textContent = "";
  errorEl.textContent = msg;
}

function setSuccess(msg) {
  errorEl.textContent = "";
  successEl.textContent = msg;
}

async function doSignup() {
  const fullname = fullnameEl.value.trim();
  const facultyId = facultyIdEl.value.trim();
  const password = passwordEl.value;
  const confirmPassword = confirmEl.value;

  errorEl.textContent = "";
  successEl.textContent = "";

  // Same validation rules as the original sign-up form.
  if (!fullname || !facultyId || !password || !confirmPassword) {
    setError("Please fill in all fields.");
    return;
  }
  if (facultyId.length < 4) {
    setError("Faculty ID must be at least 4 characters.");
    return;
  }
  if (password.length < 6) {
    setError("Password must be at least 6 characters.");
    return;
  }
  if (password !== confirmPassword) {
    setError("Passwords do not match.");
    return;
  }

  createBtn.disabled = true;
  createBtn.textContent = "CREATING...";

  try {
    // Calls the Python function exposed in app.py, which uses the
    // same register_user() logic as the original app.
    const result = await eel.try_signup(fullname, facultyId, password)();

    if (result.ok) {
      setSuccess(result.message || "Account created successfully.");
      // Same behavior as the original: return to the login screen
      // shortly after a successful sign-up.
      setTimeout(() => { window.location.href = "login.html"; }, 1500);
    } else {
      setError(result.message || "Could not create account.");
      createBtn.disabled = false;
      createBtn.textContent = "CREATE ACCOUNT";
    }
  } catch (err) {
    setError("Could not reach the application backend.");
    createBtn.disabled = false;
    createBtn.textContent = "CREATE ACCOUNT";
    console.error(err);
  }
}

createBtn.addEventListener("click", doSignup);

[fullnameEl, facultyIdEl, passwordEl, confirmEl].forEach(el => {
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSignup();
  });
});

fullnameEl.focus();
