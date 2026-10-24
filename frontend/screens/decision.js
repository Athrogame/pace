import { api } from "../api.js";
import { busy, combine, dateKey, field, fmtDay, fmtDue, fmtMinutes, fmtRange, h, icon, sleepBar, statusWord, timePicker, toast, fill } from "../ui.js";
import { looksLikeWork, workCheckbox } from "./parts.js";

export async function render(main, { app, settings }) {
  let isWork = true, touched = false, start = "17:00", end = "22:00";
  let previewedEvent = null;
  const result = h("div", { "aria-live": "polite" });

  const optionA = h("input", { type: "text", maxlength: 120, placeholder: "e.g. Take the extra shift" });
  const optionB = h("input", { type: "text", maxlength: 120, placeholder: "e.g. Keep my evening free" });
  const question = h("textarea", { rows: 3, maxlength: 600, placeholder: "What are you trying to decide?" });
  const chatLog = h("div", { class: "decision-chat-log", role: "log", "aria-live": "polite", "aria-label": "Decide coach conversation" });
  const scenarioNote = h("p", { class: "small muted" }, "Preview a shift above for a measured sleep comparison, or enter any two options here.");
  const chatSection = h("section", { class: "card decision-chat" },
    h("h2", {}, "Ask the coach"),
    h("p", { class: "small muted" }, "Talk through a choice. Pace uses your sleep outlook and latest energy check-in. This chat does not save your messages."),
    scenarioNote, chatLog,
    h("div", { class: "two-col" }, field("Option A (optional)", optionA), field("Option B (optional)", optionB)),
    field("Your question", question));
  const ask = h("button", { type: "button", class: "btn btn-primary" }, icon("sparkle", 18), "Ask coach");
  chatSection.append(ask);
  ask.addEventListener("click", busy(ask, async () => {
    const a = optionA.value.trim(), b = optionB.value.trim(), message = question.value.trim();
    if (!message) { toast("Write a question for the coach", "error"); return; }
    if (Boolean(a) !== Boolean(b)) { toast("Add both options to compare them", "error"); return; }
    const response = await api.decisionCoach({ message, option_a: a || null, option_b: b || null,
      event: previewedEvent });
    if (response.flagged) { app.go("safety"); return; }
    chatLog.append(h("p", { class: "chat-turn chat-user" }, h("strong", {}, "You"), message),
      h("p", { class: "chat-turn chat-coach" }, h("strong", {}, "Pace coach"),
        h("span", { class: "small muted" }, `Sleep outlook: ${response.sleep_outlook}. Latest energy: ${response.energy_band}.`),
        h("span", { class: "chat-answer" }, response.text)));
    question.value = "";
    chatLog.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }));

  const title = h("input", { type: "text", maxlength: 80, value: "Extra shift", placeholder: "e.g. Extra shift, concert, game" });
  const workSlot = h("div");
  const drawWork = () => fill(workSlot, workCheckbox(isWork, (v) => { isWork = v; touched = true; }));
  drawWork();
  title.addEventListener("input", () => { if (!touched) { isWork = looksLikeWork(title.value); drawWork(); } });
  const wanted = new URLSearchParams(location.hash.split("?")[1] || "").get("date");
  const date = h("input", { type: "date", value: wanted || settings.now.slice(0, 10), min: settings.now.slice(0, 10) });

  const event = () => {
    let endD = date.value;
    if (end <= start) { const d = new Date(date.value + "T12:00:00"); d.setDate(d.getDate() + 1); endD = dateKey(d); }
    return { kind: isWork ? "shift" : "activity", title: title.value.trim() || "Extra shift",
      start: combine(date.value, start), end: combine(endD, end) };
  };

  const check = h("button", { type: "button", class: "btn btn-primary btn-block" }, icon("scale", 18), "Show me what changes");
  check.addEventListener("click", busy(check, async () => {
    const ev = event();
    const flag = await api.safetyCheck(ev.title);
    if (flag.flagged) { app.go("safety"); return; }
    const r = await api.decision(ev);
    if (r.flagged) { app.go("safety"); return; }
    drawResult(ev, r);
  }));

  function drawResult(ev, r) {
    previewedEvent = ev;
    optionA.value = `Take ${ev.title}`;
    optionB.value = `Pass on ${ev.title}`;
    scenarioNote.textContent = `Using the ${ev.title} preview above for exact sleep and homework effects.`;
    const goal = settings.sleep_goal_min;
    const changed = r.sleep_change;
    const worse = changed.filter((c) => c.after_min < c.before_min);
    const verdictBad = r.newly_at_risk.length || changed.some((c) => c.after_status === "red");

    const yes = h("button", { type: "button", class: "btn btn-primary" }, icon("check", 18), "Add it to my week");
    yes.addEventListener("click", busy(yes, async () => {
      await api.addEvent(ev);
      toast("Added. Your week is replanned.");
      app.go("week");
    }));

    const nightsCompare = changed.length
      ? h("div", {}, ...changed.map((c) => {
          const b = r.before.nights.find((n) => n.date === c.date), a = r.after.nights.find((n) => n.date === c.date);
          return h("div", { style: { marginBottom: "14px" } },
            h("h3", {}, `${fmtDay(c.date)} night`),
            h("div", { class: "compare" },
              h("div", {}, h("p", { class: "col-h" }, "Now"), sleepBar(b, goal)),
              h("div", {}, h("p", { class: "col-h" }, `With ${ev.title.toLowerCase()}`), sleepBar(a, goal))));
        }))
      : h("p", {}, "Your sleep doesn't change. Every night stays the same.");

    result.replaceChildren(h("section", { class: "card" },
      h("p", { class: "eyebrow" }, `${fmtDue(ev.start).split(" ")[0]} · ${fmtRange(ev.start, ev.end)}`),
      h("h2", {}, verdictBad ? "Here's what it would cost" : "This one fits"),
      h("div", { class: `banner ${verdictBad ? "banner-red" : worse.length ? "banner-yellow" : "banner-green"}` },
        icon(verdictBad ? "alert" : "check"),
        h("div", {},
          h("p", {}, worse.length
            ? `Your shortest night would be ${fmtMinutes(r.summary_facts.worst_night_sleep_min)} of sleep (${statusWord(r.after.nights.find((n) => n.sleep_min === r.summary_facts.worst_night_sleep_min).status).toLowerCase()}).`
            : "No night loses sleep."),
          h("p", { class: "small" }, `Work this week: ${r.before.work_hours} hr now, ${r.work_hours_after} hr with this${r.summary_facts.over_15_hours ? " (over 15)" : ""}.`))),
      nightsCompare,
      r.newly_at_risk.length ? h("div", {}, h("h3", {}, "Would stop fitting"),
        ...r.newly_at_risk.map((t) => h("p", { class: "small" }, icon("alert", 16), ` ${t.title}, due ${fmtDue(t.due)} (${fmtMinutes(t.short_by_min)} short)`))) : null,
      h("p", { class: "small muted" }, "Nothing is saved until you say yes. It's your call."),
      h("button", { type: "button", class: "btn btn-ghost", onClick: () => {
        chatSection.scrollIntoView({ behavior: "smooth", block: "start" });
        question.focus({ preventScroll: true });
      } }, icon("sparkle", 18), "Talk it through with the coach"),
      h("div", { class: "row" }, yes,
        h("button", { type: "button", class: "btn btn-ghost", onClick: () => { result.replaceChildren(); toast("Okay, nothing changed"); } }, "Not this time"))));
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  fill(main, 
    h("div", { class: "page-head" }, h("h1", {}, "I'm thinking about…"),
      h("p", {}, "See exactly what an extra shift or plan would do to your sleep and homework before you say yes.")),
    h("section", { class: "card" },
      field("What is it?", title),
      workSlot,
      field("Day", date),
      h("div", { class: "two-col" },
        field("Starts", timePicker({ value: start, label: "Starts", onChange: (v) => { start = v; } })),
        field("Ends", timePicker({ value: end, label: "Ends", onChange: (v) => { end = v; } }))),
      check),
    result,
    chatSection);
}
