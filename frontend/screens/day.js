// One day in full: a timeline from wake-up to bedtime, what's due, and shortcuts to add things.
import { api } from "../api.js";
import { fmtDay, fmtMinutes, fmtRange, fmtTime, h, icon, mergeBlocks, reportedSleepBar, sleepBar, fill } from "../ui.js";

function row(at, kind, ic, title, detail, extra) {
  return { at, el: h("li", { class: `tl-row tl-${kind}` },
    h("span", { class: "tl-time" }, fmtTime(at)),
    h("span", { class: "tl-dot", "aria-hidden": "true" }, icon(ic, 14)),
    h("div", { class: "tl-body" }, h("strong", {}, title), detail ? h("span", { class: "tl-detail" }, detail) : null, extra || null)) };
}

export async function render(main, { settings }) {
  const date = new URLSearchParams(location.hash.split("?")[1] || "").get("d");
  const [plan, tasks] = await Promise.all([api.planWeeks(), api.tasks()]);
  const day = plan.days.find((d) => d.date === date);
  const index = plan.days.indexOf(day);
  const backHref = index >= 7 ? "#/week?w=next" : "#/week";

  if (!day) {
    fill(main, h("div", { class: "page-head" }, h("h1", {}, "That day isn't in your plan"),
      h("p", {}, "Pace shows this week and next week. Pick a day from your week.")),
      h("a", { class: "btn btn-ghost", href: "#/week" }, "Back to my week"));
    return;
  }

  const night = plan.nights.find((n) => n.date === date);
  const blocks = plan.blocks.filter((b) => b.start.slice(0, 10) === date);
  const dueToday = tasks.filter((t) => t.due.slice(0, 10) === date);
  const isToday = date === plan.generated_at.slice(0, 10);
  const commute = settings.commute_min || 0;

  const items = [row(day.wake, "wake", "today", "Wake up", null)];
  if (day.school) {
    items.push(row(day.school[0], "school", "school", "School", fmtRange(day.school[0], day.school[1]),
      commute ? h("span", { class: "tl-detail" }, `Plus ${fmtMinutes(commute)} commute each way`) : null));
  }
  for (const e of day.events) {
    const what = e.source === "google" ? "From Google Calendar" : e.kind === "shift" ? "Work shift · 30 min to rest after" : "Activity";
    items.push(row(e.start, e.kind === "shift" ? "shift" : "activity",
      e.source === "google" ? "week" : e.kind === "shift" ? "briefcase" : "heart", e.title, fmtRange(e.start, e.end),
      h("span", { class: "tl-detail" }, what)));
  }
  for (const b of day.blocked) {
    const starts = b.start.slice(0, 10) === date ? b.start : `${date}T00:00:00`;
    items.push(row(starts, "blocked", "alert", "Time off (something came up)",
      b.start.slice(0, 10) === date ? `From ${fmtTime(b.start)}` : "All day"));
  }
  for (const b of mergeBlocks(blocks)) {
    items.push(row(b.start, "study", "book", b.title,
      `${fmtRange(b.start, b.end)} · ${fmtMinutes(b.minutes)}${b.parts > 1 ? " with a 10-minute break" : ""}`,
      b.subject ? h("span", { class: "tl-detail" }, b.subject) : null));
  }
  if (day.past) {
    // Already happened: show the bedtime goal and what the next morning's check-in said.
    items.push(row(day.bedtime, "bed", "moon", "Bedtime goal",
      night.sleep_min == null ? "No check-in the next morning" : `You slept ${fmtMinutes(night.sleep_min)} (your check-in)`));
  } else {
    items.push(row(day.cutoff, "stop", "clock", "Stop homework", "30 minutes to wind down before bed"));
    items.push(row(night.sleep_start, "bed", "moon", "Bed", `${fmtMinutes(night.sleep_min)} of sleep planned`,
      night.reason ? h("span", { class: "tl-detail" }, night.reason) : null));
  }
  items.sort((a, b) => a.at.localeCompare(b.at));

  const capLeft = Math.max(0, day.cap_min - day.used_min);

  fill(main,
    h("a", { class: "back-link", href: backHref }, "‹ Back to week"),
    h("div", { class: "page-head" },
      h("p", { class: "eyebrow" }, isToday ? "Today" : day.past ? "Earlier this week" : index >= 7 ? "Next week" : "This week"),
      h("h1", {}, fmtDay(date, true))),

    day.past ? null : h("div", { class: "day-stats" },
      h("div", { class: "stat" }, h("span", { class: "stat-num" }, fmtMinutes(day.used_min)), h("span", { class: "stat-label" }, "homework planned")),
      h("div", { class: "stat" }, h("span", { class: "stat-num" }, fmtMinutes(capLeft)), h("span", { class: "stat-label" }, "room left today")),
      h("div", { class: "stat" }, h("span", { class: "stat-num" }, fmtTime(day.cutoff)), h("span", { class: "stat-label" }, "stop by"))),

    h("section", { class: "card" }, h("h2", {}, "The day"),
      h("ol", { class: "timeline" }, items.map((i) => i.el)),
      h("div", { style: { marginTop: "14px" } },
        day.past ? reportedSleepBar(night, settings.sleep_goal_min) : sleepBar(night, settings.sleep_goal_min))),

    h("section", { class: "card" }, h("h2", {}, "Due this day"),
      dueToday.length
        ? h("div", {}, dueToday.map((t) => h("div", { class: "list-row" }, icon("book", 18),
            h("div", { class: "grow" }, h("strong", {}, t.title),
              h("div", { class: "small muted" }, `${t.subject} · due ${fmtTime(t.due)} · ${fmtMinutes(Math.max(0, t.planned_min - t.done_min))} left`)))))
        : h("p", { class: "muted small", style: { margin: 0 } }, "Nothing due this day.")),

    day.past ? null : h("section", { class: "card" }, h("h2", {}, "Add to this day"),
      h("div", { class: "action-grid" },
        h("a", { class: "btn btn-ghost", href: `#/add?due=${date}` }, icon("book", 18), "Assignment due this day"),
        h("a", { class: "btn btn-ghost", href: `#/add?tab=shift&date=${date}` }, icon("briefcase", 18), "Shift or activity"),
        h("a", { class: "btn btn-ghost", href: `#/decision?date=${date}` }, icon("scale", 18), "What would an extra shift cost?"))),
  );
}
