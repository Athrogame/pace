import { api, session } from "../api.js";
import { busy, h, icon, fill } from "../ui.js";
import { accountFields, googleButton, orDivider } from "./parts.js";

export async function render(main, { app, settings }) {
  const f = accountFields("login");
  const err = h("p", { class: "form-error", role: "alert" });
  const btn = h("button", { type: "submit", class: "btn btn-primary btn-block btn-lg" }, "Sign in");
  const expired = sessionStorage.getItem("pace_signin_reason");
  try { sessionStorage.removeItem("pace_signin_reason"); } catch (_) { /* fine */ }

  const submit = busy(btn, async () => {
    err.textContent = "";
    const { username, password } = f.values();
    if (!username || !password) { err.textContent = "Enter your username and password."; return; }
    try {
      const r = await api.login(username, password);
      session.start(r);
      await app.refreshSettings();
      app.go(r.has_settings ? "today" : "welcome");
    } catch (e) {
      err.textContent = e.message;
      f.password.select();
    }
  });
  const google = googleButton({
    text: "signin_with",
    onSignedIn: async (r) => { await app.refreshSettings(); app.go(r.has_settings ? "today" : "welcome"); },
  });
  const form = h("form", { class: "card step-card", novalidate: true, onSubmit: (e) => { e.preventDefault(); submit(); } },
    google, orDivider(), f.el, err, btn);

  fill(main, h("div", { class: "onboard step-enter" },
    h("div", { class: "signin-badge", "aria-hidden": "true" }, icon("today", 30)),
    h("h1", { tabindex: "-1" }, "Welcome back"),
    h("p", { class: "lead" }, "Sign in with Google or your Pace username to pick up your plan on this device."),
    expired ? h("div", { class: "banner banner-yellow", role: "status" }, icon("clock"), h("p", {}, expired)) : null,
    settings && !session.signedIn() ? h("div", { class: "banner banner-info" }, icon("alert"),
      h("p", { class: "small" }, "This device already has a plan without an account. Signing in switches to your account's plan instead.")) : null,
    form,
    h("p", { class: "center small" }, "New to Pace? ", h("a", { href: settings ? "#/settings" : "#/welcome" },
      settings ? "Create an account in Settings" : "Set up your plan")),
    h("p", { class: "fine-print center" }, "Forgot your Pace password? Pace doesn't collect emails, so it can't send a reset link. You can set up a fresh plan instead. With Google, Pace only keeps Google's account number, never your email or name.")));
  main.querySelector("h1").focus({ preventScroll: true });
}
