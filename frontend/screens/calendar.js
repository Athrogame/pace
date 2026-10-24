// Read-only Google Calendar import. The browser asks Google for a short-lived, read-only token,
// reads the next two weeks of events, sends Pace only the times (and titles, if the person
// chose to keep them), then gives the token back. The Pace server never sees a token.
import { api, session } from "../api.js";
import { busy, fmtDue, fmtTime, h, icon, toast, fill } from "../ui.js";
import { googleConfig, loadGsi } from "./parts.js";

const SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly";
const DAYS_AHEAD = 14;
const KEEP_TITLES_KEY = "pace_calendar_titles";

function getToken(clientId) {
  return new Promise((resolve, reject) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPE,
      callback: (resp) => (resp.error ? reject(new Error(friendly(resp.error))) : resolve(resp.access_token)),
      error_callback: (err) => reject(new Error(friendly(err && err.type))),
    });
    client.requestAccessToken({ prompt: "" });
  });
}

function friendly(code) {
  if (code === "popup_closed" || code === "access_denied") return "Calendar import canceled. Nothing was read.";
  if (code === "popup_failed_to_open") return "Your browser blocked Google's window. Allow pop-ups for Pace and try again.";
  return "Google didn't allow the calendar import. Try again.";
}

/** "2026-10-26T17:00:00-04:00" -> "2026-10-26T17:00:00" (already in the person's time zone). */
const local = (dt) => dt.slice(0, 19);

async function readEvents(token, timeZone) {
  const now = new Date();
  const until = new Date(now.getTime() + DAYS_AHEAD * 86400000);
  const params = new URLSearchParams({
    timeMin: now.toISOString(), timeMax: until.toISOString(), singleEvents: "true", orderBy: "startTime",
    maxResults: "250", timeZone,
    fields: "items(summary,status,transparency,start,end,attendees(self,responseStatus))",
  });
  const res = await fetch(`https://www.googleapis.com/calendar/v3/calendars/primary/events?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    if (res.status === 403) throw new Error("Google Calendar isn't turned on for this app yet (see the README).");
    throw new Error("Couldn't read your calendar. Try again in a moment.");
  }
  return (await res.json()).items || [];
}

function toPace(items, keepTitles) {
  return items
    .filter((e) => e.status !== "cancelled")
    .filter((e) => e.transparency !== "transparent")                 // marked "free"
    .filter((e) => e.start && e.start.dateTime && e.end && e.end.dateTime)   // skip all-day events
    .filter((e) => !(e.attendees || []).some((a) => a.self && a.responseStatus === "declined"))
    .map((e) => ({ title: keepTitles ? (e.summary || "Busy").slice(0, 120) : "Busy",
      start: local(e.start.dateTime), end: local(e.end.dateTime) }));
}

export async function importFromGoogle({ keepTitles, timeZone }) {
  const cfg = await googleConfig();
  if (!cfg.google_client_id) throw new Error("Google isn't set up on this server yet (add GOOGLE_CLIENT_ID).");
  const google = await loadGsi();
  if (!google.accounts.oauth2) throw new Error("Couldn't load Google's sign-in. Check your connection.");
  const token = await getToken(cfg.google_client_id);
  try {
    const items = await readEvents(token, timeZone);
    return await api.calendarImport(toPace(items, keepTitles));
  } finally {
    google.accounts.oauth2.revoke(token, () => {});   // Pace doesn't keep access to your calendar
  }
}

/** The Settings card. */
export async function calendarSection(settings, onChange) {
  const wrap = h("div");
  if (session.isChild()) return h("section", { class: "card" }, h("h2", {}, "Google Calendar"),
    h("p", { class: "small muted" }, "Google imports are unavailable for under-13 plans."));
  if (session.onDemo()) {
    fill(wrap, h("p", { class: "small muted" },
      "Calendar import is turned off on the shared demo plan, so nobody's real calendar ends up in it. Tap \"Leave the demo\" at the top, then sign in or set up your own plan to import yours."));
    return h("section", { class: "card" }, h("h2", {}, "Google Calendar"), wrap);
  }
  let status = { imported: 0, synced_at: null };
  try { status = await api.calendarStatus(); } catch (_) { /* show the empty state */ }

  let keep = false;
  try { keep = localStorage.getItem(KEEP_TITLES_KEY) === "1"; } catch (_) { /* default: Busy */ }
  const keepBox = h("input", { type: "checkbox", class: "check-input" });
  keepBox.checked = keep;
  keepBox.addEventListener("change", () => {
    try { localStorage.setItem(KEEP_TITLES_KEY, keepBox.checked ? "1" : "0"); } catch (_) { /* fine */ }
  });

  const go = h("button", { type: "button", class: "btn btn-primary" }, icon("week", 18),
    status.imported ? "Import again" : "Import from Google Calendar");
  go.addEventListener("click", busy(go, async () => {
    const r = await importFromGoogle({ keepTitles: keepBox.checked, timeZone: settings.timezone || "America/New_York" });
    toast(r.imported ? `Imported ${r.imported} event${r.imported === 1 ? "" : "s"}. Your week is replanned.`
      : "No timed events in the next 2 weeks.");
    onChange();
  }));
  const remove = h("button", { type: "button", class: "btn btn-ghost" }, "Remove imported events");
  remove.addEventListener("click", busy(remove, async () => {
    const r = await api.calendarRemove();
    toast(`Removed ${r.removed} imported event${r.removed === 1 ? "" : "s"}.`);
    onChange();
  }));

  fill(wrap,
    h("p", { class: "small muted" }, "Pace reads the next 2 weeks of your Google Calendar once, so it can plan around appointments, practices and plans you already have. It's read-only: Pace can't change your calendar, and it gives Google's permission back right after reading."),
    status.synced_at ? h("p", { class: "small" }, icon("check", 16),
      ` ${status.imported} event${status.imported === 1 ? "" : "s"} imported ${fmtDue(status.synced_at).split(" ")[0]} at ${fmtTime(status.synced_at)}. Import again any time to refresh.`) : null,
    h("label", { class: "check-row" }, keepBox,
      h("span", {}, h("strong", {}, "Keep event names"),
        h("span", { class: "sub" }, "Off: imported events just say \"Busy\". Calendars can hold personal things, so this is up to you."))),
    h("div", { class: "row" }, go, status.imported ? remove : null),
    h("p", { class: "hint" }, "Skips all-day events, events marked free, and events you declined."));
  return h("section", { class: "card" }, h("h2", {}, "Google Calendar"), wrap);
}
