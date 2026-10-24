// One-time, read-only Google Tasks import. The browser holds the OAuth token only while
// reading Google; Pace receives selected task details, never the token.
import { api, session } from "../api.js";
import { busy, dateKey, field, h, icon, timePicker, toast, fill } from "../ui.js";
import { googleConfig, loadGsi } from "./parts.js";

const SCOPE = "https://www.googleapis.com/auth/tasks.readonly";
const MAX_PREVIEW = 300;

function getToken(clientId) {
  return new Promise((resolve, reject) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: clientId, scope: SCOPE,
      callback: (resp) => resp.error ? reject(new Error("Google Tasks access was canceled.")) : resolve(resp.access_token),
      error_callback: () => reject(new Error("Google's window did not open. Allow pop-ups for Pace and try again.")),
    });
    client.requestAccessToken({ prompt: "" });
  });
}

async function googlePage(url, token) {
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) {
    if (response.status === 403) throw new Error("Google denied Tasks access. In the Google Cloud project for Pace, enable Google Tasks API and add the tasks.readonly scope under Data Access, then try again.");
    throw new Error("Couldn't read Google Tasks. Try again in a moment.");
  }
  return response.json();
}

async function pagedItems(url, token, limit) {
  const items = [];
  let next = null;
  do {
    const pageUrl = new URL(url);
    if (next) pageUrl.searchParams.set("pageToken", next);
    const page = await googlePage(pageUrl, token);
    items.push(...(page.items || []));
    next = page.nextPageToken || null;
  } while (next && items.length < limit);
  return items.slice(0, limit);
}

async function readGoogleTasks(token) {
  const lists = await pagedItems("https://tasks.googleapis.com/tasks/v1/users/@me/lists?maxResults=100", token, 100);
  const tasks = [];
  for (const list of lists) {
    if (tasks.length >= MAX_PREVIEW) break;
    const url = `https://tasks.googleapis.com/tasks/v1/lists/${encodeURIComponent(list.id)}/tasks?maxResults=100&showCompleted=false&showHidden=false`;
    const items = await pagedItems(url, token, MAX_PREVIEW - tasks.length);
    for (const task of items) {
      if (task.status === "completed" || task.deleted || !task.title?.trim()) continue;
      tasks.push({ external_id: `${list.id}:${task.id}`, title: task.title.trim().slice(0, 120),
        list: list.title || "My Tasks", date: task.due?.slice(0, 10) || "" });
    }
  }
  return tasks;
}

async function getPreview() {
  const cfg = await googleConfig();
  if (!cfg.google_client_id) throw new Error("Google isn't set up on this server yet. Add GOOGLE_CLIENT_ID.");
  const google = await loadGsi();
  if (!google.accounts.oauth2) throw new Error("Couldn't load Google's sign-in. Check your connection.");
  const token = await getToken(cfg.google_client_id);
  try { return await readGoogleTasks(token); }
  finally { google.accounts.oauth2.revoke(token, () => {}); }
}

export function googleTasksSection(onChange) {
  const wrap = h("div");
  if (session.isChild()) return h("section", { class: "card" }, h("h2", {}, "Google Tasks"),
    h("p", { class: "small muted" }, "Google imports are unavailable for under-13 plans."));
  if (session.onDemo()) {
    fill(wrap, h("p", { class: "small muted" }, "Leave the shared demo before importing your personal Google Tasks."));
    return h("section", { class: "card" }, h("h2", {}, "Google Tasks"), wrap);
  }

  const chooseAI = h("button", { type: "button", class: "btn btn-primary" }, icon("sparkle", 18), "Choose with AI suggestions");
  const chooseLocal = h("button", { type: "button", class: "btn btn-ghost" }, "Choose without AI");
  const actions = h("div", { class: "row" }, chooseAI, chooseLocal);
  const start = async (useAI) => {
    const [googleTasks, paceTasks] = await Promise.all([getPreview(), api.tasks(true)]);
    const imported = new Set(paceTasks.filter((t) => t.source === "google_tasks").map((t) => t.external_id));
    const toSuggest = googleTasks.filter((t) => !imported.has(t.external_id)).slice(0, 40);
    const guesses = toSuggest.length ? await api.googleTasksSuggest(toSuggest.map((t) => ({
      title: t.title, list_title: t.list,
    })), useAI).catch(() => null) : null;
    const suggestions = new Map(toSuggest.map((t, i) => [t.external_id, guesses?.suggestions?.[i]]));
    drawPreview(googleTasks, imported, suggestions);
  };
  chooseAI.addEventListener("click", busy(chooseAI, () => start(true)));
  chooseLocal.addEventListener("click", busy(chooseLocal, () => start(false)));

  function drawPreview(tasks, imported, suggestions) {
    if (!tasks.length) {
      fill(wrap, h("p", {}, "No unfinished Google Tasks found."), actions);
      return;
    }
    const rows = tasks.map((task) => {
      const exists = imported.has(task.external_id);
      const guess = suggestions.get(task.external_id);
      const selected = h("input", { type: "checkbox", class: "check-input" });
      selected.checked = Boolean(task.date && task.date >= dateKey(new Date())) && !exists;
      selected.disabled = exists;
      const dueDate = h("input", { type: "date", value: task.date });
      const subject = h("input", { type: "text", maxlength: 40, value: guess?.subject || "general", placeholder: "e.g. math" });
      const taskType = h("select", { "aria-label": `Assignment type for ${task.title}` },
        [["homework", "Homework"], ["essay", "Essay"], ["test_study", "Test study"], ["project", "Project"]]
          .map(([value, label]) => h("option", { value }, label)));
      taskType.value = guess?.task_type || "homework";
      const minutes = h("select", { "aria-label": `Estimated time for ${task.title}` },
        [...Array.from({ length: 12 }, (_, i) => (i + 1) * 15), 240].map((n) => h("option", { value: n }, `${n} minutes`)));
      minutes.value = String(guess?.guess_min || 30);
      let dueTime = "23:59";
      const clock = timePicker({ value: dueTime, step: 1, label: `Due time for ${task.title}`, onChange: (v) => { dueTime = v; } });
      const card = h("div", { class: "card soft", style: { margin: "10px 0" } },
        h("label", { class: "check-row" }, selected,
          h("span", {}, h("strong", {}, task.title), h("span", { class: "sub" }, `Google list: ${task.list}`))),
        exists ? h("p", { class: "small muted" }, "Already imported. Edit it in Pace if needed.") :
          h("div", {},
            guess ? h("p", { class: "small muted" }, guess.source === "ai"
              ? "AI suggested the subject, type and time below. Check them before importing."
              : "Pace made a quick estimate. Check it before importing.") : null,
            h("div", { class: "two-col" },
            field("Date to finish by", dueDate, task.date ? "From Google; change it if this isn't the deadline." : "No date in Google. Choose one to import."),
            field("Time to finish by", clock, "Google Tasks does not provide a due time."),
            field("Subject", subject), field("Type", taskType),
            field("How long will it take?", minutes))));
      return { task, selected, dueDate, subject, taskType, minutes, dueTime: () => dueTime, card, exists };
    });

    const save = h("button", { type: "button", class: "btn btn-primary" }, "Import selected into Pace");
    save.addEventListener("click", busy(save, async () => {
      const chosen = rows.filter((r) => r.selected.checked && !r.exists);
      if (!chosen.length) { toast("Select at least one task", "error"); return; }
      if (chosen.some((r) => !r.dueDate.value || !r.subject.value.trim())) {
        toast("Give every selected task a date and subject", "error"); return;
      }
      const payload = chosen.map((r) => ({ external_id: r.task.external_id, title: r.task.title,
        subject: r.subject.value.trim(), task_type: r.taskType.value,
        due: `${r.dueDate.value}T${r.dueTime()}:00`, guess_min: Number(r.minutes.value) }));
      const result = await api.googleTasksImport(payload);
      toast(`Imported ${result.imported} task${result.imported === 1 ? "" : "s"}. Your week is replanned.`);
      onChange();
    }));
    fill(wrap,
      h("p", { class: "small muted" }, `${tasks.length} unfinished Google Task${tasks.length === 1 ? "" : "s"} found. Review the date, time, subject and estimate before importing. Undated tasks are unchecked.`),
      ...rows.map((r) => r.card),
      h("div", { class: "row" }, save, h("button", { type: "button", class: "btn btn-ghost", onClick: () => fill(wrap, intro, actions) }, "Cancel")));
  }

  const intro = h("p", { class: "small muted" },
    "Read unfinished items from Google Tasks and choose which become Pace assignments. If you choose AI suggestions, Pace sends task titles and Google list names to Claude for subject, type and time guesses; the other option keeps them on Pace's server. You can edit every suggestion. Google only provides a scheduled date, so you set the actual deadline before import. Pace revokes Google's read-only access after reading.");
  fill(wrap, intro, actions);
  return h("section", { class: "card" }, h("h2", {}, "Google Tasks"), wrap);
}
