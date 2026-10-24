// Loading states: content stays put for a moment; if a screen is slow, a placeholder in the
// shape of that screen shimmers in, with a thin progress bar across the top.
import { fill, h } from "./ui.js";

const DELAY_MS = 150;   // loads faster than this never flash a placeholder
let latest = 0;
let pendingTimer = null;
let barEl = null;

const line = (width, cls = "") => h("div", { class: `sk sk-line ${cls}`, style: { width } });
const block = (height, cls = "") => h("div", { class: `sk sk-block ${cls}`, style: { height } });
const card = (...rows) => h("div", { class: "card sk-card" }, ...rows);
const head = (withTabs) => h("div", { class: "sk-head" }, line("46%", "sk-title"), line("64%"), withTabs ? block("44px", "sk-tabs") : null);

function dayCard() {
  return card(line("38%", "sk-day"), block("46px"), block("46px"), line("90%"), block("40px"));
}

const LAYOUTS = {
  week: () => [head(true), h("div", { class: "week-grid" }, [1, 2, 3, 4].map(dayCard))],
  today: () => [head(), card(line("30%"), line("92%"), line("70%")), card(line("40%", "sk-title"), line("55%")),
    card(line("28%", "sk-day"), block("54px"), block("54px"))],
  day: () => [head(), h("div", { class: "day-stats" }, [1, 2, 3].map(() => block("64px"))),
    card(line("30%", "sk-day"), [1, 2, 3, 4, 5].map(() => line("100%", "sk-row")))],
  generic: () => [head(), card(line("40%", "sk-day"), block("48px"), block("48px"), block("48px")), card(line("55%"), line("85%"))],
};
const ALIASES = { "came-up": "generic", add: "generic", decision: "generic", settings: "generic", privacy: "generic" };

function placeholder(name) {
  const make = LAYOUTS[name] || LAYOUTS[ALIASES[name]] || LAYOUTS.generic;
  return h("div", { class: "sk-wrap", "aria-hidden": "true" }, make());
}

function bar() {
  if (!barEl) {
    barEl = h("div", { class: "load-bar", role: "progressbar", "aria-label": "Loading", hidden: true }, h("span"));
    document.body.append(barEl);
  }
  return barEl;
}

/** Call at the start of a screen change. Returns stop(): call it once the screen is ready. */
export function beginLoading(main, name) {
  const current = ++latest;
  clearTimeout(pendingTimer);
  pendingTimer = setTimeout(() => {
    if (current !== latest) return;
    main.setAttribute("aria-busy", "true");
    bar().hidden = false;
    fill(main, placeholder(name));
  }, DELAY_MS);
  return () => {
    if (current !== latest) return;
    clearTimeout(pendingTimer);
    pendingTimer = null;
    main.removeAttribute("aria-busy");
    if (barEl) barEl.hidden = true;
  };
}
