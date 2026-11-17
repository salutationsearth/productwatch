(() => {
  const form = document.getElementById("customer-login");
  if (!form) return;
  const errEl = document.getElementById("login-error");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errEl.hidden = true;
    const body = new FormData(form);
    const res = await fetch("/auth/customer/login", { method: "POST", body });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      errEl.textContent = err.detail || "Sign in failed";
      errEl.hidden = false;
      return;
    }
    window.location.href = "/account";
  });
})();
