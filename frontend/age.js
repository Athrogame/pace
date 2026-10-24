// Neutral age screen shown before any plan ID or personal information is collected.
import { session } from "./api.js";
import { fill, h } from "./ui.js";

let verified = false;
let status = null;

async function json(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  // A local server started before this update may still be serving the older backend.
  if (path === "/age/status" && res.status === 404) return { required: false, verified: true, child: false };
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Please try again.");
  return data;
}

export async function ensureAge(main, continueApp) {
  const leaveAgeScreen = () => {
    document.body.classList.remove("no-chrome", "age-screen");
    main.classList.remove("age-main");
  };
  if (verified) { leaveAgeScreen(); return true; }
  try { status = await json("/age/status"); }
  catch (_) { fill(main, h("p", {}, "Can't reach Pace. Check your connection and reload.")); return false; }
  if (!status.required || status.verified) {
    verified = true;
    session.setAgeStatus(status);
    leaveAgeScreen();
    return true;
  }
  document.body.classList.add("no-chrome", "age-screen");
  main.classList.add("age-main");
  const error = h("p", { class: "form-error", role: "alert", "aria-live": "polite" });
  const wrap = h("section", { class: "age-card", "aria-labelledby": "age-title" });
  const heading = (eyebrow, title, description) => h("div", { class: "age-intro" },
    h("span", { class: "age-mark", "aria-hidden": "true" }, "✦"),
    h("p", { class: "age-eyebrow" }, eyebrow),
    h("h1", { id: "age-title" }, title),
    h("p", { class: "age-lead" }, description));
  const showPending = (awaitingParent = false) => {
    if (awaitingParent) {
      const cancel = h("button", { type: "button", class: "btn btn-ghost btn-block" }, "Cancel this request");
      cancel.addEventListener("click", async () => {
        error.textContent = "";
        try {
          const res = await fetch("/age/pending", { method: "DELETE" });
          if (!res.ok) throw new Error("Could not cancel the request. Please try again.");
          location.reload();
        } catch (e) { error.textContent = e.message; }
      });
      fill(wrap, heading("Parent approval", "Waiting for your parent", "We emailed your parent or guardian a consent request."),
        h("div", { class: "age-content" },
          h("p", { class: "age-note" }, "After they approve, return in a day and check again for the follow-up confirmation. Your plan stays locked until both steps are finished."),
          h("button", { type: "button", class: "btn btn-primary btn-block age-action", onClick: () => location.reload() }, "Check again"),
          cancel, error));
      return;
    }
    const email = h("input", { id: "parent-email", type: "email", autocomplete: "email", placeholder: "name@example.com", required: true });
    const send = h("button", { type: "submit", class: "btn btn-primary btn-block age-action" }, "Email my parent");
    const form = h("form", { class: "age-content" },
      h("label", { class: "label", for: "parent-email" }, "Parent or guardian email"), email,
      h("p", { class: "hint" }, "We'll send the privacy details and a consent link to this address."),
      send, error);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      error.textContent = "";
      send.disabled = true;
      try {
        await json("/age/request-parent", { parent_email: email.value.trim() });
        showPending(true);
      } catch (e) { error.textContent = e.message; send.disabled = false; }
    });
    fill(wrap, heading("Parent approval", "Ask your parent or guardian", "To keep your plan private, a parent or guardian needs to approve it first."), form);
  };
  if (status.pending) showPending(status.awaiting_parent);
  else {
    const month = h("select", { id: "birth-month", required: true },
      [h("option", { value: "" }, "Select month"), ...Array.from({ length: 12 }, (_, i) =>
        h("option", { value: i + 1 }, new Date(2020, i, 1).toLocaleString(undefined, { month: "long" })))]) ;
    const year = h("input", { id: "birth-year", type: "text", inputmode: "numeric", pattern: "[0-9]{4}", maxlength: "4",
      placeholder: "YYYY", autocomplete: "off", required: true });
    const go = h("button", { type: "submit", class: "btn btn-primary btn-block age-action" }, "Continue");
    const form = h("form", { class: "age-content" },
      h("div", { class: "age-fields" },
        h("div", { class: "age-field" }, h("label", { class: "label", for: "birth-month" }, "Birth month"), month),
        h("div", { class: "age-field" }, h("label", { class: "label", for: "birth-year" }, "Birth year"), year)),
      error, go,
      h("p", { class: "age-privacy" }, "Your birth month and year aren't saved."));
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      error.textContent = "";
      const birthYear = Number(year.value);
      if (!Number.isInteger(birthYear) || birthYear < 1900 || birthYear > new Date().getFullYear()) {
        error.textContent = "Enter a valid four-digit birth year.";
        year.focus();
        return;
      }
      go.disabled = true;
      try {
        const result = await json("/age/start", { birth_month: Number(month.value), birth_year: birthYear });
        if (result.verified) { verified = true; session.setAgeStatus(result); continueApp(); }
        else showPending();
      } catch (e) { error.textContent = e.message; go.disabled = false; }
    });
    fill(wrap, heading("A quick privacy check", "First, when were you born?", "Your birth month and year help us choose the right privacy setup for you."), form);
  }
  fill(main, wrap);
  return false;
}
