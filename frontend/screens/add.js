import { api } from "../api.js";
import { busy, combine, dateKey, field, fmtDue, fmtMinutes, fmtRange, h, icon, minutesSelect, timePicker, toast, fill } from "../ui.js";
import { looksLikeWork, recurringEditor, workCheckbox } from "./parts.js";

const TYPES = [["homework", "Homework"], ["essay", "Essay"], ["test_study", "Test study"], ["project", "Project"]];
const SUBJECTS = ["math", "english", "history", "chemistry", "biology", "physics", "spanish", "computer science"];

function tomorrow(nowIso) {
  const d = new Date(nowIso.slice(0, 10) + "T12:00:00");
  d.setDate(d.getDate() + 1);
  return dateKey(d);
}

function nextDay(dateStr) {
  const d = new Date(dateStr + "T12:00:00");
  d.setDate(d.getDate() + 1);
  return dateKey(d);
}

export async function render(main, { app, settings }) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  let tab = ["shift", "weekly"].includes(params.get("tab")) ? params.get("tab") : "task";
  let editing = null;   // the task or event being edited, or null when adding
  const [tasks, events] = await Promise.all([api.tasks(), api.events()]);
  const known = [...new Set([...SUBJECTS, ...tasks.map((t) => t.subject)])];
  const rerender = () => render(main, { app, settings });

  const body = h("div");
  const seg = h("div", { class: "seg", role: "group", "aria-label": "What are you adding?" });
  const drawSeg = () => fill(seg, [["task", "Assignment"], ["shift", "One time"], ["weekly", "Every week"]].map(([k, t]) =>
    h("button", { type: "button", "aria-pressed": String(tab === k), onClick: () => { tab = k; editing = null; drawSeg(); drawBody(); } }, t)));

  function editHeader(what) {
    return h("div", { class: "edit-head" },
      h("span", {}, icon("edit", 16), ` Editing ${what}`),
      h("button", { type: "button", class: "btn btn-ghost btn-sm", onClick: () => { editing = null; drawSeg(); drawBody(); } }, "Cancel"));
  }

  // ---------- task form (add or edit) ----------
  function taskForm(t) {
    const title = h("input", { type: "text", maxlength: 120, placeholder: "e.g. Chem lab report", value: t ? t.title : "" });
    const subject = h("input", { type: "text", list: "subjects", maxlength: 40, placeholder: "e.g. math", autocapitalize: "none",
      value: t ? t.subject : "" });
    const datalist = h("datalist", { id: "subjects" }, known.map((s) => h("option", { value: s })));
    const type = h("select", {}, TYPES.map(([v, label]) => h("option", { value: v }, label)));
    if (t) type.value = t.task_type;
    const dueDate = h("input", { type: "date", value: t ? t.due.slice(0, 10) : (params.get("due") || tomorrow(settings.now)),
      min: t ? null : settings.now.slice(0, 10) });
    let dueTime = t ? t.due.slice(11, 16) : "08:00";
    const duePick = timePicker({ value: dueTime, label: "Due time", onChange: (v) => { dueTime = v; } });

    // Adding: your guess (Pace may adjust it). Editing: the total time Pace plans for.
    const startMinutes = t ? t.planned_min : 30;
    const guess = minutesSelect(Math.max(15, Math.round(startMinutes / 15) * 15), { min: 15, max: 600, step: 15,
      label: t ? "Total time it needs" : "Your guess" });
    const preview = h("div", { "aria-live": "polite" });
    let planned = null, useGuess = false;

    const refresh = async () => {
      if (t) return;
      planned = null;
      const sub = subject.value.trim().toLowerCase();
      if (!sub) { fill(preview); return; }
      try {
        const r = await api.estimates(sub, Number(guess.value));
        const p = r.preview;
        if (p && p.multiplier && p.planned_min !== p.guess_min) {
          planned = p.planned_min;
          const toggle = h("button", { type: "button", class: "btn btn-ghost btn-sm" }, useGuess ? "Use Pace's estimate" : "Use my guess instead");
          toggle.addEventListener("click", () => { useGuess = !useGuess; refresh(); });
          fill(preview, h("div", { class: "banner banner-info" }, icon("sparkle"),
            h("div", { class: "grow" },
              h("p", {}, useGuess ? `Planning your guess: ${fmtMinutes(p.guess_min)}.`
                : `You guessed ${fmtMinutes(p.guess_min)}. Planning ${fmtMinutes(p.planned_min)} based on your past ${sub} work.`),
              h("div", { style: { marginTop: "8px" } }, toggle))));
        } else fill(preview);
      } catch (_) { fill(preview); }
    };
    subject.addEventListener("change", refresh);
    subject.addEventListener("blur", refresh);
    guess.addEventListener("change", refresh);

    const save = h("button", { type: "button", class: "btn btn-primary btn-block" },
      icon(t ? "check" : "plus", 18), t ? "Save changes" : "Add assignment");
    save.addEventListener("click", busy(save, async () => {
      if (!title.value.trim()) { toast("What's the assignment called?", "error"); title.focus(); return; }
      if (!subject.value.trim()) { toast("Add a subject so Pace can learn your timing", "error"); subject.focus(); return; }
      if (!dueDate.value) { toast("When is it due?", "error"); return; }
      const g = Number(guess.value);
      if (t) {
        const r = await api.editTask(t.id, { title: title.value.trim(), subject: subject.value.trim(), task_type: type.value,
          due: combine(dueDate.value, dueTime), planned_min: g });
        if (r.safety_flagged) { app.go("safety"); return; }
        toast("Saved. Your week is replanned.");
        app.go("week");
        return;
      }
      const r = await api.addTask({ title: title.value.trim(), subject: subject.value.trim(), task_type: type.value,
        due: combine(dueDate.value, dueTime), guess_min: g, planned_min: planned && !useGuess ? planned : (useGuess ? g : null) });
      if (r.safety_flagged) { app.go("safety"); return; }
      toast(`Added. Planning ${fmtMinutes(r.planned_min)}.`);
      app.go("week");
    }));

    return h("section", { class: `card${t ? " card-editing" : ""}` },
      t ? editHeader(`"${t.title}"`) : null,
      field("Assignment", title),
      h("div", { class: "two-col" }, field("Subject", subject), field("Type", type)), datalist,
      h("div", { class: "two-col" }, field("Due date", dueDate), field("Due time", duePick, "If it's due in class, Pace finishes it the night before.")),
      field(t ? "Total time it needs" : "How long do you think it'll take?", guess,
        t && t.done_min ? `You've done ${fmtMinutes(t.done_min)} so far. Pace plans the rest.` : null),
      preview,
      save);
  }

  // ---------- shift / activity form (add or edit) ----------
  function shiftForm(e) {
    let isWork = e ? e.kind === "shift" : true, touched = Boolean(e);
    let start = e ? e.start.slice(11, 16) : "17:00";
    let end = e ? e.end.slice(11, 16) : "21:00";
    const title = h("input", { type: "text", maxlength: 80, value: e ? e.title : "Shift",
      placeholder: "e.g. Extra shift, Game, Eid prayer" });
    const workSlot = h("div");
    const drawWork = () => fill(workSlot, workCheckbox(isWork, (v) => { isWork = v; touched = true; }));
    drawWork();
    title.addEventListener("input", () => { if (!touched) { isWork = looksLikeWork(title.value); drawWork(); } });
    const date = h("input", { type: "date", value: e ? e.start.slice(0, 10) : (params.get("date") || settings.now.slice(0, 10)),
      min: e ? null : settings.now.slice(0, 10) });
    const save = h("button", { type: "button", class: "btn btn-primary btn-block" },
      icon(e ? "check" : "plus", 18), e ? "Save changes" : "Add to my week");
    save.addEventListener("click", busy(save, async () => {
      if (!title.value.trim()) { toast("Give it a name", "error"); return; }
      if (!date.value) { toast("Pick a date", "error"); return; }
      const body = { kind: isWork ? "shift" : "activity", title: title.value.trim(), start: combine(date.value, start),
        end: combine(end <= start ? nextDay(date.value) : date.value, end) };
      const r = e ? await api.editEvent(e.id, body) : await api.addEvent(body);
      if (r.safety_flagged) { app.go("safety"); return; }
      toast(e ? "Saved. Your week is replanned." : "Added. Your week is replanned.");
      app.go("week");
    }));
    return h("div", {},
      h("section", { class: `card${e ? " card-editing" : ""}` },
        e ? editHeader(`"${e.title}"`) : null,
        field("What is it?", title),
        workSlot,
        field("Date", date),
        h("div", { class: "two-col" },
          field("Starts", timePicker({ value: start, label: "Starts", onChange: (v) => { start = v; } })),
          field("Ends", timePicker({ value: end, label: "Ends", onChange: (v) => { end = v; } }), "Ends after midnight? Pick an earlier end time and Pace counts it as the next day.")),
        save),
      e ? null : h("div", { class: "banner banner-info" }, icon("scale"),
        h("div", { class: "grow" }, h("p", {}, "Not sure yet? See what an extra shift would cost first."),
          h("a", { class: "btn btn-ghost btn-sm", href: "#/decision", style: { marginTop: "8px" } }, "Try it in Decide"))));
  }

  // ---------- current items ----------
  function rowActions(label, onEdit, onDelete) {
    return h("div", { class: "row-actions" },
      h("button", { type: "button", class: "icon-btn icon-btn-edit", "aria-label": `Edit ${label}`, onClick: onEdit }, icon("edit", 18)),
      h("button", { type: "button", class: "icon-btn", "aria-label": `Delete ${label}`, onClick: onDelete }, icon("trash", 18)));
  }

  const startEdit = (kind, item) => {
    tab = kind;
    editing = item;
    drawSeg();
    drawBody();
    main.scrollIntoView({ behavior: "smooth", block: "start" });
    body.querySelector("input")?.focus({ preventScroll: true });
  };

  function lists() {
    const oneOff = events.filter((e) => !e.recurring && e.end >= settings.now);
    return h("section", { class: "card" },
      h("h2", {}, "Coming up"),
      tasks.length ? h("div", {}, tasks.map((t) => h("div", { class: "list-row" }, icon("book", 18),
        h("div", { class: "grow" }, h("strong", {}, t.title),
          h("div", { class: "small muted" }, `${t.subject} · due ${fmtDue(t.due)} · ${fmtMinutes(Math.max(0, t.planned_min - t.done_min))} left`)),
        rowActions(t.title, () => startEdit("task", t),
          async () => { await api.deleteTask(t.id); toast("Deleted"); rerender(); }))))
        : h("p", { class: "muted small" }, "No assignments yet."),
      oneOff.length ? h("div", { style: { marginTop: "12px" } }, h("h3", {}, "One-time shifts and activities"),
        oneOff.map((e) => h("div", { class: "list-row" }, icon(e.kind === "shift" ? "briefcase" : "heart", 18),
          h("div", { class: "grow" }, h("strong", {}, e.title), h("div", { class: "small muted" }, `${fmtDue(e.start).split(" ")[0]} · ${fmtRange(e.start, e.end)}`)),
          rowActions(e.title, () => startEdit("shift", e),
            async () => { await api.deleteEvent(e.id); toast("Deleted"); rerender(); })))) : null,
      h("p", { class: "hint" }, "Shifts and activities that repeat are under Every week."));
  }

  // ---------- every week: work, prayer, practice (saves right away) ----------
  function weeklyForm() {
    return h("section", { class: "card" },
      h("h2", {}, "Every week"),
      h("p", { class: "muted small" }, "Work, prayer, practice: anything at the same time each week. Pace plans around it from now on. Changes save right away."),
      recurringEditor({ existing: events, saveNow: true, nowIso: settings.now }).el);
  }

  const drawBody = () => fill(body, tab === "task" ? taskForm(editing) : tab === "weekly" ? weeklyForm() : shiftForm(editing));
  drawSeg();
  drawBody();
  fill(main, h("div", { class: "page-head" }, h("h1", {}, "Add"), h("p", {}, "Pace fits it into your week and protects your sleep.")),
    seg, body, lists());
}
