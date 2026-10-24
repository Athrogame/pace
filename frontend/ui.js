// Small UI toolkit: element builder, 12-hour time formatting and pickers, icons, toasts.
// Rule for this app: a person never sees 24-hour time. Times are "HH:MM" only inside data.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "style" && typeof v === "object") {
      for (const [prop, val] of Object.entries(v)) {
        if (prop.startsWith("--")) el.style.setProperty(prop, val); else el.style[prop] = val;
      }
    }
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

/** replaceChildren that skips null/false, so optional sections never render as "null". */
export function fill(el, ...children) {
  el.replaceChildren(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
  return el;
}

// ---------- time ----------

export function parseISO(s) {
  // Naive local ISO "2026-10-20T19:30:00" -> Date in local time.
  const [d, t = "00:00:00"] = s.split("T");
  const [y, mo, da] = d.split("-").map(Number);
  const [hh, mm] = t.split(":").map(Number);
  return new Date(y, mo - 1, da, hh, mm);
}

export function toISO(date) {
  const p = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}:00`;
}

export function dateKey(date) {
  return toISO(date).slice(0, 10);
}

export function combine(dateStr, hm) {
  return `${dateStr}T${hm}:00`;
}

/** "19:30" | ISO | Date -> "7:30 PM" */
export function fmtTime(v) {
  let hh, mm;
  if (v instanceof Date) { hh = v.getHours(); mm = v.getMinutes(); }
  else if (typeof v === "string" && v.includes("T")) { const d = parseISO(v); hh = d.getHours(); mm = d.getMinutes(); }
  else { [hh, mm] = v.split(":").map(Number); }
  const suffix = hh < 12 ? "AM" : "PM";
  return `${hh % 12 || 12}:${String(mm).padStart(2, "0")} ${suffix}`;
}

/** "7:00 – 9:30 PM", or "11:00 AM – 1:00 PM" when the halves differ */
export function fmtRange(a, b) {
  const s = fmtTime(a), e = fmtTime(b);
  const [sTime, sSuf] = s.split(" "), [, eSuf] = e.split(" ");
  return sSuf === eSuf ? `${sTime} – ${e}` : `${s} – ${e}`;
}

export function fmtMinutes(total) {
  total = Math.round(total);
  const hrs = Math.floor(total / 60), m = total % 60;
  if (hrs && m) return `${hrs} hr ${m} min`;
  if (hrs) return `${hrs} hr`;
  return `${m} min`;
}

const DAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAY_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function fmtDay(v, long = false) {
  const d = typeof v === "string" ? parseISO(v.includes("T") ? v : v + "T00:00:00") : v;
  return `${(long ? DAY_LONG : DAY_SHORT)[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

export function fmtDue(iso) {
  return `${DAY_SHORT[parseISO(iso).getDay()]} ${fmtTime(iso)}`;
}

export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
export const WEEKDAY_LABEL = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };

/**
 * 12-hour time picker: hour (1–12), minute (5-minute steps), AM/PM.
 * value / onChange use "HH:MM" (24-hour) internally only.
 */
export function timePicker({ value = "18:00", onChange, label, id, step = 5 }) {
  let [hh, mm] = value.split(":").map(Number);
  mm = Math.round(mm / step) * step % 60;
  const hourSel = h("select", { "aria-label": `${label} hour`, id });
  for (let i = 1; i <= 12; i++) hourSel.append(h("option", { value: i }, i));
  const minSel = h("select", { "aria-label": `${label} minute` });
  for (let i = 0; i < 60; i += step) minSel.append(h("option", { value: i }, String(i).padStart(2, "0")));
  const apSel = h("select", { "aria-label": `${label} AM or PM` },
    h("option", { value: "AM" }, "AM"), h("option", { value: "PM" }, "PM"));
  const wrap = h("div", { class: "time-picker", role: "group", "aria-label": label },
    hourSel, h("span", { class: "colon", "aria-hidden": "true" }, ":"), minSel, apSel);

  const set = (v) => {
    let [H, M] = v.split(":").map(Number);
    M = Math.round(M / step) * step;
    if (M === 60) { M = 0; H = (H + 1) % 24; }
    hourSel.value = H % 12 || 12;
    minSel.value = M;
    apSel.value = H < 12 ? "AM" : "PM";
  };
  const get = () => {
    let H = Number(hourSel.value) % 12;
    if (apSel.value === "PM") H += 12;
    return `${String(H).padStart(2, "0")}:${String(Number(minSel.value)).padStart(2, "0")}`;
  };
  set(`${hh}:${mm}`);
  for (const s of [hourSel, minSel, apSel]) s.addEventListener("change", () => onChange && onChange(get()));
  wrap.getValue = get;
  wrap.setValue = set;
  return wrap;
}

export function field(labelText, control, hint) {
  const id = control.id || `f${Math.random().toString(36).slice(2, 8)}`;
  if (!control.id && control.tagName !== "DIV") control.id = id;
  const lab = control.tagName === "DIV"
    ? h("span", { class: "label", id: `${id}-l` }, labelText)
    : h("label", { class: "label", for: control.id }, labelText);
  if (control.tagName === "DIV") control.setAttribute("aria-labelledby", `${id}-l`);
  return h("div", { class: "field" }, lab, control, hint ? h("p", { class: "hint" }, hint) : null);
}

export function chips(options, selected, onChange, { multi = true, label } = {}) {
  const set = new Set(selected);
  const wrap = h("div", { class: "chips", role: "group", "aria-label": label });
  const render = () => {
    wrap.replaceChildren(...options.map(([value, text]) => h("button", {
      type: "button", class: "chip", "aria-pressed": String(set.has(value)),
      onClick: () => {
        if (multi) { set.has(value) ? set.delete(value) : set.add(value); }
        else { set.clear(); set.add(value); }
        render(); onChange && onChange(multi ? [...set] : value);
      },
    }, text)));
  };
  render();
  wrap.getValue = () => (multi ? [...set] : [...set][0]);
  return wrap;
}

// ---------- icons (Lucide paths, stroke icons) ----------

const ICONS = {
  today: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  week: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  scale: '<path d="M16 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1zM2 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1zM7 21h10M12 3v18M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
  settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>',
  phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
  message: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  stop: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  trash: '<path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
  undo: '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
  sparkle: '<path d="M9.94 14.06 4 20M12 2l1.9 5.8L20 10l-6.1 2.2L12 18l-1.9-5.8L4 10l6.1-2.2z"/>',
  heart: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7z"/>',
  briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
  book: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
  school: '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  edit: '<path d="M12 20h9"/><path d="M16.38 3.62a1 1 0 0 1 3 3L7.37 18.64a2 2 0 0 1-.86.5l-2.87.84a.5.5 0 0 1-.62-.62l.84-2.87a2 2 0 0 1 .5-.86z"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
};

export function icon(name, size = 20) {
  const span = h("span", { class: "icon", "aria-hidden": "true" });
  span.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
  return span;
}

// ---------- feedback ----------

export function toast(message, kind = "info") {
  const region = document.getElementById("toasts");
  const t = h("div", { class: `toast toast-${kind}`, role: kind === "error" ? "alert" : "status" }, message);
  region.append(t);
  setTimeout(() => t.classList.add("leaving"), 3200);
  setTimeout(() => t.remove(), 3600);
}

export function busy(button, fn) {
  return async (...args) => {
    if (button.disabled) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try { return await fn(...args); }
    catch (e) { toast(e.message || "Something went wrong", "error"); }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); }
  };
}

export function statusWord(status) {
  return { green: "On track", yellow: "A bit short", red: "Short on sleep" }[status] || status;
}

/** A night in the plan (a forecast, not what happened): when you'll be in bed and how much sleep that leaves. */
export function sleepBar(night, goal) {
  const pct = Math.max(4, Math.min(100, (night.sleep_min / goal) * 100));
  const summary = `Planned: in bed by ${fmtTime(night.sleep_start)}, ${fmtMinutes(night.sleep_min)} of sleep, ${statusWord(night.status)}`;
  return h("div", { class: `sleep sleep-${night.status}`, title: "Pace's plan for this night" },
    h("div", { class: "sleep-top" },
      h("span", { class: "sleep-label" }, icon("moon", 16), ` Bed by ${fmtTime(night.sleep_start)}`),
      h("span", { class: "sleep-amount" }, `${fmtMinutes(night.sleep_min)} planned · ${statusWord(night.status)}`)),
    h("div", { class: "sleep-track", role: "img", "aria-label": summary },
      h("div", { class: "sleep-fill", style: { width: `${pct}%` } })),
    night.reason ? h("p", { class: "sleep-reason" }, night.reason) : null);
}

/** A night that already happened: the sleep from the next morning's check-in, not a plan. */
export function reportedSleepBar(night, goal) {
  if (night.sleep_min == null) {
    return h("div", { class: "sleep sleep-unknown" },
      h("div", { class: "sleep-top" },
        h("span", { class: "sleep-label" }, icon("moon", 16), " No check-in"),
        h("span", { class: "sleep-amount" }, "Sleep not reported")));
  }
  const pct = Math.max(4, Math.min(100, (night.sleep_min / goal) * 100));
  return h("div", { class: `sleep sleep-${night.status} sleep-reported`, title: "From your check-in" },
    h("div", { class: "sleep-top" },
      h("span", { class: "sleep-label" }, icon("moon", 16), ` Slept ${fmtMinutes(night.sleep_min)}`),
      h("span", { class: "sleep-amount" }, `your check-in · ${statusWord(night.status)}`)),
    h("div", { class: "sleep-track", role: "img", "aria-label": `You reported ${fmtMinutes(night.sleep_min)} of sleep` },
      h("div", { class: "sleep-fill", style: { width: `${pct}%` } })));
}

/**
 * What the person reported this morning, so it's never confused with the plan.
 * checkin: today's row from GET /checkins, or undefined.
 */
export function lastNightNote(checkin, goal) {
  if (!checkin || checkin.sleep_min == null) {
    return h("p", { class: "last-night muted" }, icon("moon", 16), " No check-in yet today. ",
      h("a", { href: "#/checkin" }, "Tell Pace how you slept"));
  }
  const short = goal - checkin.sleep_min;
  return h("p", { class: `last-night${short > 60 ? " last-night-short" : ""}` }, icon("moon", 16),
    " Last night you slept ", h("strong", {}, fmtMinutes(checkin.sleep_min)),
    short > 0 ? ` (${fmtMinutes(short)} under your goal).` : " (you hit your goal).",
    " ", h("a", { href: "#/checkin" }, "Change"));
}

/**
 * Back-to-back study blocks for the same task (only the 10-minute break between them) read as one
 * session: "History essay 3:05 – 4:45 PM · 1 hr 30 min". The break is still kept in the plan.
 */
export function mergeBlocks(blocks) {
  const sorted = [...blocks].sort((a, b) => a.start.localeCompare(b.start));
  const out = [];
  for (const b of sorted) {
    const last = out[out.length - 1];
    const gap = last ? (parseISO(b.start) - parseISO(last.end)) / 60000 : Infinity;
    if (last && last.task_id === b.task_id && gap <= 15) {
      last.end = b.end;
      last.minutes += b.minutes;
      last.parts += 1;
    } else {
      out.push({ ...b, parts: 1 });
    }
  }
  return out;
}

export function minutesSelect(value, { min = 15, max = 360, step = 15, label } = {}) {
  const sel = h("select", { "aria-label": label });
  for (let m = min; m <= max; m += step) sel.append(h("option", { value: m }, fmtMinutes(m)));
  sel.value = value;
  return sel;
}
