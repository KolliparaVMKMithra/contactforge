const form = document.getElementById("login-form");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const loginBtn = document.getElementById("login-btn");
const btnLabel = loginBtn.querySelector(".btn-label");
const btnSpinner = loginBtn.querySelector(".btn-spinner");
const errorEl = document.getElementById("login-error");

function setLoading(loading) {
  loginBtn.disabled = loading;
  btnSpinner.hidden = !loading;
  btnLabel.textContent = loading ? "Signing in…" : "Sign in";
}

function showError(message) {
  errorEl.hidden = false;
  errorEl.textContent = message;
}

function hideError() {
  errorEl.hidden = true;
  errorEl.textContent = "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideError();
  setLoading(true);

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        email: emailInput.value.trim(),
        password: passwordInput.value,
      }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showError(data.detail || "Invalid email or password.");
      return;
    }

    window.location.href = "/";
  } catch (_) {
    showError("Could not reach the server. Try again.");
  } finally {
    setLoading(false);
  }
});
