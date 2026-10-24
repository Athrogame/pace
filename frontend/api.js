// Without an account, a random plan id lives in localStorage. Signed-in sessions
// use an HttpOnly cookie set by the server, so JavaScript cannot read the token.

const ID_KEY = "pace_user_id";
const TOKEN_KEY = "pace_token"; // legacy only; removed after one-time migration
const PHOTO_KEY = "pace_google_photo";   // only ever kept in this browser, never sent to the server
const memory = {};   // fallback when localStorage is blocked (private mode)
let childPlan = false;
let signedIn = false;
let bootstrapped = false;

function read(key) {
  try { return localStorage.getItem(key); } catch (_) { return memory[key] || null; }
}
function write(key, value) {
  memory[key] = value;
  try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (_) { /* memory only */ }
}

function makeId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  if (window.crypto && crypto.getRandomValues) {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return "u-" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  throw new Error("Pace needs a secure browser connection to protect your plan.");
}

export const DEMO_ID = "demo";

// Only ?as=demo may switch plans. Accepting arbitrary IDs here would expose anonymous plans
// whenever somebody knew or guessed an ID.
const as = new URLSearchParams(location.search).get("as");

export function userId() {
  let id = read(ID_KEY);
  if (!id) { id = makeId(); write(ID_KEY, id); }
  return id;
}

export const session = {
  isChild: () => childPlan,
  async bootstrap() {
    if (bootstrapped) return;
    if (childPlan) { write(TOKEN_KEY, null); return; }
    const oldToken = read(TOKEN_KEY);
    if (oldToken) {
      const migrated = await fetch("/auth/migrate", { method: "POST", headers: { Authorization: `Bearer ${oldToken}` } });
      if (!migrated.ok && migrated.status !== 401) throw new Error("Can't update your sign-in. Please reload.");
      write(TOKEN_KEY, null);
    }
    const response = await fetch("/auth/me", { headers: { "X-User-Id": userId() } });
    if (response.status === 401) {
      write(ID_KEY, makeId());
      signedIn = false;
      bootstrapped = true;
      return;
    }
    if (!response.ok) throw new Error("Can't check your sign-in. Please reload.");
    signedIn = Boolean((await response.json()).signed_in);
    bootstrapped = true;
  },
  setAgeStatus(status) {
    childPlan = Boolean(status.child && status.verified);
    if (childPlan && status.user_id) { write(TOKEN_KEY, null); signedIn = false; write(ID_KEY, status.user_id); }
    if (!childPlan && status.verified && as === "demo") {
      write(ID_KEY, DEMO_ID);
      write(TOKEN_KEY, null);
      signedIn = false;
      history.replaceState(null, "", location.pathname + location.hash);
    }
  },
  signedIn: () => signedIn,
  /** Viewing the shared demo plan (opened with ?as=demo). */
  onDemo: () => !signedIn && read(ID_KEY) === DEMO_ID,
  /** After sign-up or sign-in: this browser now follows the account's plan. */
  start(result) { write(ID_KEY, result.user_id); write(TOKEN_KEY, null); signedIn = true; },
  /** Sign out: forget browser hints and start a fresh, empty anonymous plan. */
  end() { write(TOKEN_KEY, null); write(PHOTO_KEY, null); write(ID_KEY, makeId()); signedIn = false; },
  photo: () => read(PHOTO_KEY),
  setPhoto(url) { write(PHOTO_KEY, url); },
};

/**
 * The profile photo link inside Google's sign-in token, read here in the browser. Only a
 * googleusercontent.com https link is accepted; anything else is ignored.
 */
export function googlePhotoFrom(credential) {
  try {
    const part = credential.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = JSON.parse(decodeURIComponent(escape(atob(part + "===".slice((part.length + 3) % 4)))));
    const url = new URL(json.picture);
    return url.protocol === "https:" && url.hostname.endsWith(".googleusercontent.com") ? url.href : null;
  } catch (_) {
    return null;
  }
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: {
      "X-User-Id": userId(),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    // Session expired, or this id belongs to an account: drop to a fresh anonymous id
    // (so nothing keeps failing) and ask the person to sign in.
    session.end();
    window.dispatchEvent(new CustomEvent("pace:needs-signin"));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail
        : Array.isArray(j.detail) ? j.detail.map((d) => d.msg).join("; ") : detail;
    } catch (_) { /* not json */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export const api = {
  getSettings: () => request("GET", "/settings"),
  putSettings: (s) => request("PUT", "/settings", s),
  events: () => request("GET", "/events"),
  addEvent: (e) => request("POST", "/events", e),
  deleteEvent: (id) => request("DELETE", `/events/${id}`),
  editEvent: (id, changes) => request("PATCH", `/events/${id}`, changes),
  editTask: (id, changes) => request("PATCH", `/tasks/${id}`, changes),
  tasks: (all = false) => request("GET", `/tasks${all ? "?include_completed=true" : ""}`),
  addTask: (t) => request("POST", "/tasks", t),
  googleTasksImport: (tasks) => request("POST", "/tasks/google/import", { tasks }),
  googleTasksSuggest: (tasks, useAI = true) => request("POST", "/tasks/google/suggest", { tasks, use_ai: useAI }),
  deleteTask: (id) => request("DELETE", `/tasks/${id}`),
  logTask: (id, minutes) => request("POST", `/tasks/${id}/log`, { minutes }),
  finishTask: (id, minutes) => request("POST", `/tasks/${id}/finish`, { minutes }),
  plan: (days = 7) => request("GET", `/plan?days=${days}`),
  /** This Monday through next Sunday. Past days (with reported sleep) are merged in front. */
  planWeeks: async () => {
    const p = await request("GET", "/plan?weeks=true");
    p.days = [...(p.past_days || []), ...p.days];
    p.nights = [...(p.past_nights || []), ...p.nights];
    return p;
  },
  rebalance: () => request("POST", "/plan/rebalance"),
  undoRebalance: () => request("DELETE", "/plan/rebalance"),
  checkins: () => request("GET", "/checkins"),
  checkin: (c) => request("POST", "/checkins", c),
  mode: () => request("GET", "/mode"),
  coach: (refresh = false) => request("GET", `/coach${refresh ? "?refresh=true" : ""}`),
  decision: (e) => request("POST", "/decision", e),
  decisionCoach: (body) => request("POST", "/decision/coach", body),
  cameUp: (b) => request("POST", "/came-up", b),
  cameUpList: () => request("GET", "/came-up"),
  undoCameUp: (id) => request("DELETE", `/came-up/${id}`),
  estimates: (subject, guess) => request("GET", subject ? `/estimates?subject=${encodeURIComponent(subject)}&guess_min=${guess}` : "/estimates"),
  acceptEstimate: (subject) => request("POST", `/estimates/${encodeURIComponent(subject)}/accept`),
  safetyCheck: (text) => request("POST", "/safety/check", { text }),
  me: () => request("GET", "/auth/me"),
  signup: (username, password) => request("POST", "/auth/signup", { username, password }),
  login: (username, password) => request("POST", "/auth/login", { username, password }),
  logout: () => request("POST", "/auth/logout"),
  logoutAll: () => request("POST", "/auth/logout-all"),
  authConfig: () => request("GET", "/auth/config"),
  calendarStatus: () => request("GET", "/calendar/status"),
  calendarImport: (events) => request("POST", "/calendar/import", { events }),
  calendarRemove: () => request("DELETE", "/calendar/import"),
  google: (credential) => request("POST", "/auth/google", { credential }),
  deleteMe: () => request("DELETE", "/me"),
};
