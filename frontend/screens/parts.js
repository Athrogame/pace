// Pieces shared by first-time setup and Settings.
import { api, googlePhotoFrom, session } from "../api.js";
import { busy, chips, combine, dateKey, field, fmtRange, h, icon, timePicker, toast, WEEKDAY_LABEL, WEEKDAYS, fill } from "../ui.js";

export function mondayOfThisWeek(nowIso) {
  const d = nowIso ? new Date(nowIso.slice(0, 10) + "T00:00:00") : new Date();
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return dateKey(d);
}

/**
 * "This is a work shift" checkbox. Work counts toward weekly work hours and gets 30 minutes of
 * rest after it; anything else (prayer, practice, family time) is just time Pace plans around.
 */
export function workCheckbox(checked, onChange) {
  const input = h("input", { type: "checkbox", class: "check-input" });
  input.checked = checked;
  input.addEventListener("change", () => onChange(input.checked));
  return h("label", { class: "check-row" }, input,
    h("span", {}, h("strong", {}, "This is a work shift"),
      h("span", { class: "sub" }, "Counts toward your work hours, with 30 minutes to rest after.")));
}

/** Guess work vs. not from the name, so the checkbox usually starts right. */
export function looksLikeWork(name) {
  return /\b(shift|work|job|cashier|server|barista|babysit|tutor(ing)?|lifeguard)\b/i.test(name || "");
}

const QUICK_PICKS = [
  ["Work shift", true], ["Prayer", false], ["Practice", false], ["Religious service", false],
  ["Family time", false], ["Tutoring", false],
];

/**
 * Weekly shifts and activities. With saveNow, changes hit the API right away (Settings);
 * without it they collect in `pending` until setup finishes.
 */
export function recurringEditor({ existing = [], saveNow = false, nowIso }) {
  const pending = [];
  let saved = existing.filter((e) => e.recurring);
  const list = h("div");

  const draw = () => {
    const rows = [...saved.map((e) => ({ ...e, saved: true })), ...pending];
    fill(list, rows.length
      ? rows.map((e) => h("div", { class: "list-row" },
          h("span", { class: `pill-icon pill-${e.kind}` }, icon(e.kind === "shift" ? "briefcase" : "heart", 18)),
          h("div", { class: "grow" }, h("strong", {}, e.title),
            h("div", { class: "small muted" }, `${e.recurring.days.map((d) => WEEKDAY_LABEL[d]).join(", ")} · ${fmtRange(e.start, e.end)}`)),
          h("button", { type: "button", class: "icon-btn", "aria-label": `Remove ${e.title}`,
            onClick: async () => {
              if (e.saved) { await api.deleteEvent(e.id); saved = saved.filter((x) => x.id !== e.id); toast("Removed"); }
              else pending.splice(pending.indexOf(pending.find((p) => p === e || (p.title === e.title && p.start === e.start))), 1);
              draw();
            } }, icon("trash", 18))))
      : h("p", { class: "muted small empty-note" }, "Nothing yet. Add regular work shifts, practices, or anything else that repeats each week."));
  };

  let isWork = true, start = "17:00", end = "21:00";
  const startPick = timePicker({ value: start, label: "Starts", onChange: (v) => { start = v; } });
  const endPick = timePicker({ value: end, label: "Ends", onChange: (v) => { end = v; } });
  const title = h("input", { type: "text", maxlength: 80, placeholder: "e.g. Work at the cafe, Prayer, Soccer practice" });
  const workSlot = h("div");
  let touched = false;   // once the person sets the checkbox, stop guessing from the name
  const drawWork = () => fill(workSlot, workCheckbox(isWork, (v) => { isWork = v; touched = true; }));
  drawWork();
  title.addEventListener("input", () => { if (!touched) { isWork = looksLikeWork(title.value); drawWork(); } });

  const makeDays = (selected) => chips(WEEKDAYS.map((d) => [d, WEEKDAY_LABEL[d]]), selected, null, { label: "Repeats on" });
  let days = makeDays([]);
  const daysWrap = h("div", {}, days);
  const setDays = (selected) => { days = makeDays(selected); fill(daysWrap, days); };
  const everyDay = h("button", { type: "button", class: "btn btn-ghost btn-sm", onClick: () => setDays(WEEKDAYS) }, "Every day");
  const weekdays = h("button", { type: "button", class: "btn btn-ghost btn-sm",
    onClick: () => setDays(["mon", "tue", "wed", "thu", "fri"]) }, "Weekdays");

  const picks = h("div", { class: "chips", role: "group", "aria-label": "Quick picks" },
    QUICK_PICKS.map(([name, work]) => h("button", { type: "button", class: "chip chip-sm", onClick: () => {
      title.value = name;
      isWork = work;
      drawWork();
      if (name === "Prayer") {   // short by default; people set their own times
        start = "13:00"; end = "13:15"; startPick.setValue(start); endPick.setValue(end);
        setDays(WEEKDAYS);
      }
      title.focus();
    } }, name)));

  const add = h("button", { type: "button", class: "btn btn-ghost btn-block" }, icon("plus", 18), "Add it");
  add.addEventListener("click", busy(add, async () => {
    const picked = days.getValue();
    if (!title.value.trim()) { toast("Give it a name", "error"); title.focus(); return; }
    if (!picked.length) { toast("Pick at least one day", "error"); return; }
    if (end <= start) { toast("End time must be after the start time", "error"); return; }
    const monday = mondayOfThisWeek(nowIso);
    const ev = { kind: isWork ? "shift" : "activity", title: title.value.trim(), start: combine(monday, start),
      end: combine(monday, end), recurring: { days: picked } };
    if (saveNow) { const r = await api.addEvent(ev); saved.push({ ...ev, id: r.id }); toast("Added"); }
    else pending.push(ev);
    title.value = "";
    touched = false;
    setDays([]);
    draw();
  }));

  draw();
  const el = h("div", {},
    list,
    h("div", { class: "card soft", style: { marginTop: "12px", marginBottom: 0 } },
      field("What is it?", title),
      h("div", { class: "field" }, h("span", { class: "label" }, "Quick picks"), picks),
      workSlot,
      h("div", { class: "field" },
        h("div", { class: "row between", style: { marginBottom: "6px" } }, h("span", { class: "label", style: { margin: 0 } }, "Repeats on"),
          h("div", { class: "row", style: { gap: "6px" } }, weekdays, everyDay)),
        daysWrap),
      h("div", { class: "two-col" }, field("Starts", startPick), field("Ends", endPick)),
      h("p", { class: "hint" }, "Pray more than once a day? Add each time separately. Short ones are fine."),
      add));
  return { el, pending };
}

// ---------- Sign in with Google ----------

let configPromise = null;
let gsiPromise = null;
const GOOGLE_G = `<svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.8 6C12.4 13.6 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 6.9l7.4 5.8c4.3-4 6.9-9.9 6.9-17.2z"/><path fill="#FBBC05" d="M10.5 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.8-4.7l-7.8-6A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.7l7.9-6z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.8c-2.1 1.4-4.8 2.3-8.5 2.3-6.3 0-11.6-4.2-13.5-9.9l-7.9 6C6.6 42.6 14.6 48 24 48z"/></svg>`;

export function googleConfig() {
  configPromise = configPromise || api.authConfig().catch(() => ({ google_client_id: null }));
  return configPromise;
}

export function loadGsi() {
  gsiPromise = gsiPromise || new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve(window.google);
    s.onerror = () => { gsiPromise = null; reject(new Error("Couldn't load Google sign-in. Check your connection.")); };
    document.head.append(s);
  });
  return gsiPromise;
}

/**
 * "Continue with Google". Calls onSignedIn(result) with {user_id, has_settings, created}.
 * Shows Google's own button when the server has a client id, and an explanatory stand-in when not.
 */
export function googleButton({ onSignedIn, text = "continue_with" }) {
  if (session.isChild()) return h("span", { hidden: true });
  const slot = h("div", { class: "google-slot" });
  const err = h("p", { class: "form-error", role: "alert" });
  const wrap = h("div", { class: "google-wrap" }, slot, err);

  const handle = async (response) => {
    err.textContent = "";
    try {
      const r = await api.google(response.credential);
      session.start(r);
      session.setPhoto(googlePhotoFrom(response.credential));   // stays in this browser only
      await onSignedIn(r);
    } catch (e) { err.textContent = e.message; }
  };

  const standIn = (message) => {
    const b = h("button", { type: "button", class: "btn btn-google btn-block", html: `${GOOGLE_G}<span>Continue with Google</span>` });
    b.addEventListener("click", () => { err.textContent = message; });
    fill(slot, b);
  };
  standIn("");   // shown immediately so the layout doesn't jump

  googleConfig().then(async (cfg) => {
    if (!cfg.google_client_id) {
      standIn("Google sign-in isn't set up on this server yet. Add a GOOGLE_CLIENT_ID to turn it on (see the README).");
      return;
    }
    try {
      const google = await loadGsi();
      google.accounts.id.initialize({ client_id: cfg.google_client_id, callback: handle, ux_mode: "popup" });
      slot.replaceChildren();
      // Google's white "outline" button reads clearly on both the light and dark themes.
      google.accounts.id.renderButton(slot, {
        theme: "outline", size: "large", shape: "pill", text,
        width: Math.min(400, Math.max(240, Math.floor(slot.getBoundingClientRect().width || 320))),
      });
    } catch (e) { standIn(e.message); }
  });
  return wrap;
}

export function orDivider() {
  return h("div", { class: "or-divider", role: "separator" }, h("span", {}, "or"));
}

/** Username + password with a show/hide toggle. mode: "signup" | "login". */
export function accountFields(mode) {
  const username = h("input", { type: "text", maxlength: 24, autocomplete: "username", autocapitalize: "none",
    spellcheck: "false", placeholder: mode === "signup" ? "e.g. nightowl_27" : "Your username" });
  const password = h("input", { type: "password", maxlength: 128,
    autocomplete: mode === "signup" ? "new-password" : "current-password",
    placeholder: mode === "signup" ? "At least 8 characters; avoid common passwords" : "Your password" });
  const toggle = h("button", { type: "button", class: "reveal", "aria-label": "Show password", "aria-pressed": "false" }, "Show");
  toggle.addEventListener("click", () => {
    const show = password.type === "password";
    password.type = show ? "text" : "password";
    toggle.textContent = show ? "Hide" : "Show";
    toggle.setAttribute("aria-pressed", String(show));
    toggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
  const el = h("div", {},
    field("Username", username, mode === "signup" ? "3 to 24 letters, numbers or underscores. Don't use your real name." : null),
    field("Password", h("div", { class: "password-wrap" }, password, toggle),
      mode === "signup" ? "There's no email, so write it down somewhere safe. Pace can't reset it." : null),
    take9Tip());
  return { el, username, password, values: () => ({ username: username.value.trim(), password: password.value }) };
}

/** Take9: pause before you share. Shown wherever someone types a password. */
export function take9Tip() {
  return h("aside", { class: "take9", "aria-label": "Safety tip" }, icon("shield", 18),
    h("p", { style: { margin: 0 } }, h("strong", {}, "Pause before you share. "),
      "Only type your Pace password on this page. Pace will never email, text or message you asking for it. ",
      h("a", { href: "#/privacy" }, "What Pace stores")));
}

/** Create an account for the plan this browser already has. Calls onDone(username). */
export function signupForm({ onDone, buttonText = "Create account" }) {
  const f = accountFields("signup");
  const btn = h("button", { type: "button", class: "btn btn-primary btn-block" }, buttonText);
  const err = h("p", { class: "form-error", role: "alert" });
  btn.addEventListener("click", busy(btn, async () => {
    err.textContent = "";
    const { username, password } = f.values();
    if (!username || !password) { err.textContent = "Pick a username and a password."; return; }
    try {
      const r = await api.signup(username, password);
      session.start(r);
      onDone(r.username);
    } catch (e) { err.textContent = e.message; }
  }));
  return h("div", {}, f.el, err, btn);
}
