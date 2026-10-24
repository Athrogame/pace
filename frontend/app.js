import { api, session } from "./api.js";
import { ensureAge } from "./age.js";
import { beginLoading } from "./loading.js";
import { h, icon, fill } from "./ui.js";
import * as setup from "./screens/setup.js";
import * as onboarding from "./screens/onboarding.js";
import * as signin from "./screens/signin.js";
import * as week from "./screens/week.js";
import * as add from "./screens/add.js";
import * as today from "./screens/today.js";
import * as checkin from "./screens/checkin.js";
import * as decision from "./screens/decision.js";
import * as cameUp from "./screens/came-up.js";
import * as safety from "./screens/safety.js";
import * as privacy from "./screens/privacy.js";
import * as day from "./screens/day.js";

const ROUTES = {
  today, week, add, decision, checkin, "came-up": cameUp, safety, signin, privacy, day,
  welcome: onboarding,
  settings: { render: (main, ctx) => setup.render(main, { ...ctx, editing: true }) },
};

// Screens that work before setup is finished, and screens that hide the nav and red button.
const OPEN_ROUTES = new Set(["welcome", "signin", "safety", "privacy"]);
const FULLSCREEN = new Set(["welcome", "signin", "checkin"]);
const SELF_FOCUS = new Set(["welcome", "signin"]);

const NAV = [
  ["today", "Today", "today"],
  ["week", "Week", "week"],
  ["add", "Add", "plus"],
  ["decision", "Decide", "scale"],
  ["settings", "Settings", "settings"],
];

const state = { settings: undefined, checkedIn: {} };

export const app = {
  go(name) {
    if (location.hash === `#/${name}`) route(); else location.hash = `#/${name}`;
  },
  async refreshSettings() {
    try { state.settings = await api.getSettings(); }
    catch (e) {
      if (e.status === 404) state.settings = null;
      else if (e.status === 401) state.settings = null;
      else throw e;
    }
    return state.settings;
  },
  markCheckedIn(day) { state.checkedIn[day] = true; },
  get settings() { return state.settings; },
};

function skipKey(day) { return `pace_checkin_skip_${day}`; }
export function skipCheckin(day) {
  state.checkedIn[day] = true;
  try { sessionStorage.setItem(skipKey(day), "1"); } catch (_) { /* fine */ }
}

window.addEventListener("pace:needs-signin", () => {
  state.settings = undefined;
  try { sessionStorage.setItem("pace_signin_reason", "You've been signed out. Sign in again to see your plan."); } catch (_) { /* fine */ }
  if (!location.hash.startsWith("#/signin")) location.hash = "#/signin";
});

function renderDemoBar() {
  const bar = document.getElementById("demoBar");
  if (!session.onDemo()) { bar.hidden = true; return; }
  const leave = h("button", { type: "button", class: "btn btn-sm demo-leave" }, "Leave the demo");
  leave.addEventListener("click", async () => {
    session.end();                     // fresh, empty plan for this browser
    await app.refreshSettings();
    app.go("welcome");                 // set up, sign in, or continue with Google from here
  });
  fill(bar, h("span", {}, icon("today", 16), " This is the shared demo plan."), leave);
  bar.hidden = false;
}

function renderNav(current) {
  const nav = document.getElementById("bottomNav");
  fill(nav, NAV.map(([route, label, ic]) => h("a", {
    href: `#/${route}`, "aria-current": current === route ? "page" : null,
  }, icon(ic, 22), label)));
}

async function route() {
  const main = document.getElementById("main");
  const rawName = location.hash.replace(/^#\/?/, "").split("?")[0] || "today";
  const stopLoading = beginLoading(main, rawName);
  try { await showRoute(main); }
  finally { stopLoading(); }
}

async function showRoute(main) {
  document.body.classList.add("no-fab");
  if (!await ensureAge(main, route)) return;
  try { await session.bootstrap(); }
  catch (e) { fill(main, h("div", { class: "card" }, h("h2", {}, "Can't check your sign-in"),
    h("p", { class: "muted" }, "Check your connection and reload."))); return; }
  let name = location.hash.replace(/^#\/?/, "").split("?")[0] || "today";
  if (!ROUTES[name]) name = "today";

  const startHash = location.hash;
  try {
    if (state.settings === undefined) await app.refreshSettings();
  } catch (e) {
    fill(main, h("div", { class: "card" }, h("h2", {}, "Can't reach Pace"),
      h("p", { class: "muted" }, "Check your connection and reload the page.")));
    return;
  }
  if (location.hash !== startHash) return;   // a redirect (e.g. to sign-in) is already rendering

  // No plan yet: first-time setup (sign-in and the safety screen are always reachable).
  if (!state.settings && !OPEN_ROUTES.has(name)) name = "welcome";
  if (state.settings && name === "welcome") name = "today";

  // Daily check-in on the first open of the day.
  if (state.settings && (name === "today" || name === "week")) {
    const day = state.settings.now.slice(0, 10);
    let skipped = false;
    try { skipped = sessionStorage.getItem(skipKey(day)) === "1"; } catch (_) { /* fine */ }
    if (!state.checkedIn[day] && !skipped) {
      try {
        const c = await api.checkins();
        if (c.needed) { name = "checkin"; } else { state.checkedIn[day] = true; }
      } catch (_) { /* never block the app on this */ }
    }
  }

  document.body.classList.toggle("no-chrome", FULLSCREEN.has(name) || !state.settings);
  document.querySelector(".policy-links")?.classList.toggle("hide-on-settings", name === "settings");
  main.classList.toggle("wide", name === "week");
  main.classList.toggle("narrow", FULLSCREEN.has(name));
  renderNav(name === "day" ? "week" : name);
  renderDemoBar();
  let ready = false;
  try {
    await ROUTES[name].render(main, { app, settings: state.settings });
    ready = true;
  } catch (e) {
    console.error(e);
    fill(main, h("div", { class: "card" }, h("h2", {}, "Something went wrong"),
      h("p", { class: "muted" }, e.message || "Try again in a moment.")));
  }
  document.body.classList.toggle("no-fab", !ready || name === "safety");
  if (!SELF_FOCUS.has(name)) {
    main.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
  document.body.classList.remove("scrolling-down");
}

// Shrink the red button to its icon while scrolling down; bring the label back on the way up.
let lastY = 0;
window.addEventListener("scroll", () => {
  const y = window.scrollY;
  if (Math.abs(y - lastY) < 8) return;
  document.body.classList.toggle("scrolling-down", y > lastY && y > 80);
  lastY = y;
}, { passive: true });

window.addEventListener("hashchange", route);
route();
