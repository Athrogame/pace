import { api } from "../api.js";
import { busy, fmtDay, fmtDue, fmtMinutes, fmtRange, fmtTime, h, icon, lastNightNote, toast, fill } from "../ui.js";

const BREAK_AFTER_MIN = 45;
const TIMER_KEY = "pace_timer";

function loadTimer() {
  try { return JSON.parse(localStorage.getItem(TIMER_KEY) || "null"); } catch (_) { return null; }
}
function saveTimer(t) {
  try { t ? localStorage.setItem(TIMER_KEY, JSON.stringify(t)) : localStorage.removeItem(TIMER_KEY); } catch (_) { /* fine */ }
}
function clock(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  return (hh ? `${hh}:${String(mm).padStart(2, "0")}` : `${mm}`) + `:${String(ss).padStart(2, "0")}`;
}

function suggestionCard(s, onDone) {
  const accept = h("button", { type: "button", class: "btn btn-primary btn-sm" }, "Use that");
  accept.addEventListener("click", busy(accept, async () => {
    await api.acceptEstimate(s.subject);
    toast(`New ${s.subject} tasks will plan ${s.suggestion.multiplier}× your guess`);
    onDone();
  }));
  return h("div", { class: "banner banner-info" }, icon("sparkle"),
    h("div", { class: "grow" }, h("p", {}, s.suggestion.text),
      h("p", { class: "small muted" }, "Based on your own past work. Weighted averages, not guesses."),
      h("div", { class: "row", style: { marginTop: "8px" } }, accept,
        h("button", { type: "button", class: "btn btn-ghost btn-sm", onClick: (e) => e.target.closest(".banner").remove() }, "Not now"))));
}

export async function render(main, { app, settings }) {
  const [plan, est, checks] = await Promise.all([api.plan(), api.estimates(), api.checkins().catch(() => null)]);
  const todaysCheckin = checks && checks.checkins.find((c) => c.date === checks.today);
  const todayKey = plan.generated_at.slice(0, 10);
  const tonight = plan.blocks.filter((b) => b.start.slice(0, 10) === todayKey);
  const todayInfo = plan.days[0];
  const tonightNight = plan.nights[0];
  let timer = loadTimer();
  let tick = null;

  // ----- coach (loads separately so a slow AI never blocks the page) -----
  // Shimmering lines while the coach thinks; replaced (textContent) when the message arrives.
  const coachBody = h("p", { class: "coach-text muted" },
    h("span", { class: "visually-hidden" }, "Thinking about tonight…"),
    h("span", { class: "sk sk-line", style: { display: "block", width: "94%" } }),
    h("span", { class: "sk sk-line", style: { display: "block", width: "62%", marginBottom: 0 } }));
  const modeBadge = h("span", { class: `badge badge-mode-${plan.mode}` }, { push: "Ahead", steady: "Steady", recovery: "Recovery", safety: "Support" }[plan.mode]);
  const coachCard = h("section", { class: "card coach", "aria-live": "polite" },
    h("div", { class: "row between" }, h("span", { class: "badge badge-ai" }, icon("sparkle", 14), "AI coach"), modeBadge),
    coachBody);
  api.coach().then((c) => {
    if (c.mode === "safety") { app.go("safety"); return; }
    coachBody.className = "coach-text";
    coachBody.textContent = c.text;
  }).catch(() => { coachBody.textContent = `Stop by ${fmtTime(plan.stop_time)} to protect your sleep.`; });

  // ----- tonight's blocks -----
  const list = h("div");
  const breakNote = h("div", { "aria-live": "polite" });

  function drawBlocks() {
    if (tick) { clearInterval(tick); tick = null; }
    if (!tonight.length) {
      list.replaceChildren(h("p", { class: "muted" }, plan.mode === "recovery"
        ? "Nothing urgent tonight. Rest is the plan."
        : "Nothing planned for tonight."));
      return;
    }
    list.replaceChildren(...tonight.map((b) => {
      const key = `${b.task_id}|${b.start}`;
      const running = timer && timer.key === key;
      const time = h("span", { class: "timer", "aria-label": "Elapsed time" }, running ? clock(Date.now() - timer.started) : fmtMinutes(b.minutes));
      const btn = h("button", { type: "button", class: running ? "btn btn-danger btn-sm" : "btn btn-primary btn-sm",
        "aria-label": running ? `Stop ${b.title}` : `Start ${b.title}` },
        icon(running ? "stop" : "play", 16), running ? "Stop" : "Start");
      const row = h("div", { class: "block-row" },
        h("div", { class: "grow" }, h("strong", {}, b.title), h("div", { class: "small muted" }, fmtRange(b.start, b.end))),
        time, btn);
      btn.addEventListener("click", () => {
        if (running) {
          const mins = Math.max(1, Math.round((Date.now() - timer.started) / 60000));
          if (tick) { clearInterval(tick); tick = null; }   // stop the clock before the timer goes away
          timer = null; saveTimer(null); askActual(row, b, mins);
        }
        else {
          if (timer) { toast("Stop the other timer first", "error"); return; }
          timer = { key, started: Date.now() }; saveTimer(timer); drawBlocks();
        }
      });
      if (running) {
        tick = setInterval(() => {
          if (!timer) return;
          const ms = Date.now() - timer.started;
          time.textContent = clock(ms);
          if (ms >= BREAK_AFTER_MIN * 60000 && !breakNote.childElementCount) {
            breakNote.replaceChildren(h("div", { class: "banner break-note" }, icon("clock"),
              h("div", {}, h("strong", {}, `${BREAK_AFTER_MIN} minutes in. Take a short break.`),
                h("p", { class: "small" }, "Stand up, get water, look away from the screen for 5 minutes."))));
          }
        }, 1000);
      }
      return row;
    }));
  }

  function askActual(row, block, mins) {
    const input = h("input", { type: "number", min: 1, max: 600, value: mins, inputmode: "numeric", style: { maxWidth: "110px" } });
    const logBtn = h("button", { type: "button", class: "btn btn-ghost btn-sm" }, "Save time");
    const doneBtn = h("button", { type: "button", class: "btn btn-primary btn-sm" }, icon("check", 16), "Finished the task");
    const result = h("div", { "aria-live": "polite" });
    logBtn.addEventListener("click", busy(logBtn, async () => {
      await api.logTask(block.task_id, Number(input.value) || 0);
      toast(`Saved ${fmtMinutes(Number(input.value) || 0)}`);
      render(main, { app, settings });
    }));
    doneBtn.addEventListener("click", busy(doneBtn, async () => {
      const r = await api.finishTask(block.task_id, Number(input.value) || 0);
      const e = r.estimate;
      const bits = [h("div", { class: "banner banner-green" }, icon("check"), h("div", {}, h("strong", {}, `${block.title} done.`),
        h("p", { class: "small" }, `${fmtMinutes(r.actual_min)} total.`)))];
      if (e.note) bits.push(h("div", { class: "banner banner-info" }, icon("sparkle"), h("p", {}, e.note)));
      if (e.suggestion) bits.push(suggestionCard(e, () => render(main, { app, settings })));
      bits.push(h("button", { type: "button", class: "btn btn-ghost btn-sm", onClick: () => render(main, { app, settings }) }, "Back to tonight"));
      result.replaceChildren(...bits);
      inner.replaceChildren(result);
    }));
    const inner = h("div", { class: "card soft", style: { margin: "8px 0 0" } },
      h("label", { class: "label", for: "actualMin" }, "How long did that really take?"),
      h("div", { class: "row" }, Object.assign(input, { id: "actualMin" }), h("span", { class: "muted" }, "minutes")),
      h("div", { class: "row", style: { marginTop: "10px" } }, logBtn, doneBtn));
    row.after(inner);
    row.querySelector("button").disabled = true;
    input.focus();
  }

  drawBlocks();

  const suggestions = est.subjects.filter((s) => s.suggestion);
  const soon = plan.at_risk;
  const hello = settings.nickname ? `Hi, ${settings.nickname}` : "Tonight";

  fill(main, 
    h("div", { class: "page-head" }, h("p", { class: "eyebrow" }, fmtDay(todayKey, true)), h("h1", {}, hello)),
    checks ? lastNightNote(todaysCheckin, settings.sleep_goal_min) : null,
    plan.mode === "recovery" ? h("div", { class: "banner banner-yellow" }, icon("moon"),
      h("div", {}, h("strong", {}, "Recovery mode"),
        h("p", { class: "small" }, "You've been running low. Tonight is only what's due soon. The rest moved later."))) : null,
    coachCard,
    h("section", { class: "card" },
      h("div", { class: "row between" },
        h("div", {}, h("p", { class: "eyebrow" }, "Stop working by"), h("div", { class: "stop-time" }, fmtTime(plan.stop_time))),
        h("div", { style: { textAlign: "right" } }, h("p", { class: "eyebrow" }, "Tonight's plan"),
          h("strong", {}, `Bed by ${fmtTime(tonightNight.sleep_start)}`),
          h("div", { class: "small muted" }, `${fmtMinutes(tonightNight.sleep_min)} of sleep planned`))),
      todayInfo.events.some((e) => e.kind === "shift") ? h("p", { class: "small muted", style: { margin: "8px 0 0" } },
        `Work today: ${todayInfo.events.filter((e) => e.kind === "shift").map((e) => fmtRange(e.start, e.end)).join(", ")}`) : null),
    breakNote,
    h("section", { class: "card" }, h("h2", {}, "Tonight"), list),
    ...suggestions.map((s) => suggestionCard(s, () => render(main, { app, settings }))),
    soon.length ? h("div", { class: "banner banner-red" }, icon("alert"), h("div", {},
      h("strong", {}, "Heads up"),
      ...soon.map((r) => h("p", { class: "small" }, r.overdue
        ? `${r.title} was due ${fmtDue(r.due)} and is past due. Talk to your teacher about turning it in late.`
        : `${r.title} (due ${fmtDue(r.due)}) is ${fmtMinutes(r.short_by_min)} short. Consider asking your teacher for an extension.`)),
      h("a", { href: "#/week", class: "small" }, "See your week"))) : null,
    h("p", { class: "small", style: { textAlign: "center", marginTop: "18px" } },
      h("a", { href: "#/checkin" }, "Update today's check-in")),
  );

  const stop = () => { if (tick) clearInterval(tick); window.removeEventListener("hashchange", stop); };
  window.addEventListener("hashchange", stop);
}
