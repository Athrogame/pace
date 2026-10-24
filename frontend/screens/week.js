import { api } from "../api.js";
import { busy, fmtDay, fmtDue, fmtMinutes, fmtRange, fmtTime, h, icon, lastNightNote, mergeBlocks, reportedSleepBar, sleepBar, toast, fill } from "../ui.js";

function dayItems(day, blocks) {
  const items = [];
  if (day.school) items.push({ at: day.school[0], el: h("div", { class: "item item-school" },
    h("span", { class: "t" }, icon("school", 14), " School"), h("span", { class: "w" }, fmtRange(day.school[0], day.school[1]))) });
  for (const e of day.events) items.push({ at: e.start, el: h("div", { class: `item item-${e.kind}` },
    h("span", { class: "t" }, icon(e.source === "google" ? "week" : e.kind === "shift" ? "briefcase" : "heart", 14), " ", e.title),
    h("span", { class: "w" }, fmtRange(e.start, e.end), e.source === "google" ? " · Google Calendar" : "")) });
  for (const b of day.blocked) {
    const s = b.start.slice(0, 10) === day.date ? b.start : `${day.date}T00:00:00`;
    items.push({ at: s, el: h("div", { class: "item item-blocked" },
      h("span", { class: "t" }, "Time off (something came up)"),
      h("span", { class: "w" }, b.start.slice(0, 10) === day.date ? `from ${fmtTime(b.start)}` : "all day")) });
  }
  for (const b of mergeBlocks(blocks)) items.push({ at: b.start, el: h("div", { class: "item item-study" },
    h("span", { class: "t" }, icon("book", 14), " ", b.title),
    h("span", { class: "w" }, `${fmtRange(b.start, b.end)} · ${fmtMinutes(b.minutes)}${b.parts > 1 ? " with a break" : ""}`)) });
  items.sort((a, b) => a.at.localeCompare(b.at));
  return items.map((i) => i.el);
}

/** The one-line version of a day for phones: tap it for the full day. */
function daySummary(day, blocks, night) {
  const study = blocks.reduce((sum, b) => sum + b.minutes, 0);
  const shifts = day.events.filter((e) => e.kind === "shift");
  const others = day.events.filter((e) => e.kind !== "shift");
  const bits = [];
  if (day.school) bits.push(h("span", { class: "sum-chip sum-school" }, icon("school", 13), " School"));
  if (study) bits.push(h("span", { class: "sum-chip sum-study" }, icon("book", 13), ` ${fmtMinutes(study)}`));
  for (const s of shifts) bits.push(h("span", { class: "sum-chip sum-shift" }, icon("briefcase", 13), ` ${fmtRange(s.start, s.end)}`));
  if (others.length) bits.push(h("span", { class: "sum-chip sum-activity" }, icon("heart", 13), ` ${others.length} more`));
  if (day.blocked.length) bits.push(h("span", { class: "sum-chip sum-blocked" }, "Time off"));
  if (!bits.length) bits.push(h("span", { class: "sum-chip" }, "Free day"));
  return h("div", { class: "day-summary" },
    h("div", { class: "sum-chips" }, bits),
    h("div", { class: `sum-sleep sum-sleep-${night.status}` }, icon("moon", 13),
      night.reported
        ? (night.sleep_min == null ? " No check-in" : ` Slept ${fmtMinutes(night.sleep_min)} (your check-in)`)
        : ` Bed by ${fmtTime(night.sleep_start)} · ${fmtMinutes(night.sleep_min)}`));
}

const HORIZON_DAYS = 14;   // two weeks, matching how far ahead the calendar import reads

export async function render(main, { app, settings }) {
  let which = new URLSearchParams(location.hash.split("?")[1] || "").get("w") === "next" ? 1 : 0;
  const draw = (plan) => {
    const goal = settings.sleep_goal_min;
    const todayKey = plan.generated_at.slice(0, 10);
    const badNights = plan.nights.filter((n) => !n.reported && n.status !== "green");   // planned nights only
    const hours = plan.work_hours_this_week;
    const meterPct = Math.min(100, (hours / 25) * 100);
    const meterColor = { green: "var(--green-bar)", yellow: "var(--yellow-bar)", red: "var(--red-bar)" }[plan.work_hours_status];

    const rebalanceBtn = h("button", { class: "btn btn-primary" }, icon("sparkle", 18), "Rebalance my week");
    rebalanceBtn.addEventListener("click", busy(rebalanceBtn, async () => {
      const after = await api.rebalance();
      draw(await api.planWeeks());
      if (after.still_at_risk) toast("Some work still won't fit. Consider asking for an extension.", "error");
      else if (after.fixed_nights.length) toast(`Fixed ${after.fixed_nights.length} night${after.fixed_nights.length > 1 ? "s" : ""}. Every night is protected.`);
      else toast("Spread the work out a bit more.");
    }));
    const normalBtn = h("button", { class: "btn btn-ghost btn-sm" }, "Back to normal limits");
    normalBtn.addEventListener("click", busy(normalBtn, async () => {
      await api.undoRebalance();
      draw(await api.planWeeks());
      toast("Back to your normal study limits");
    }));

    const banners = [];
    if (plan.mode === "recovery") banners.push(h("div", { class: "banner banner-yellow" }, icon("moon"),
      h("div", {}, h("strong", {}, "Recovery mode"), h("p", { class: "small" },
        "Tonight only has what's due in the next two days. Everything else moved later so you can rest."))));
    if (plan.at_risk.length) banners.push(h("div", { class: "banner banner-red", role: "status" }, icon("alert"),
      h("div", { class: "grow" }, h("strong", {}, plan.at_risk.length === 1 ? "1 task won't fit" : `${plan.at_risk.length} tasks won't fit`),
        ...plan.at_risk.map((r) => h("p", { class: "small" },
          `${r.title} (due ${fmtDue(r.due)}): ${fmtMinutes(r.short_by_min)} short. `,
          r.overdue ? "This is past due." : `This won't fit before ${fmtDay(r.due).split(",")[0]}. Consider asking your teacher for an extension.`)))));
    else if (badNights.length) banners.push(h("div", { class: "banner banner-yellow" }, icon("moon"),
      h("div", {}, h("strong", {}, `${badNights.length} night${badNights.length > 1 ? "s" : ""} short on sleep`),
        h("p", { class: "small" }, "Usually a late shift. Pace can't move shifts, but it keeps study out of your sleep."))));
    else banners.push(h("div", { class: "banner banner-green" }, icon("check"),
      h("div", {}, h("strong", {}, "Every night is protected"), h("p", { class: "small" }, "All your work fits without cutting into sleep."))));

    const shown = plan.days.slice(which * 7, which * 7 + 7);
    const cards = shown.map((day) => {
      const night = plan.nights.find((n) => n.date === day.date);
      const blocks = plan.blocks.filter((b) => b.start.slice(0, 10) === day.date);
      const items = dayItems(day, blocks);
      // The whole card opens that day's full view.
      return h("a", { class: `day-card day-link${day.date === todayKey ? " today" : ""}${day.past ? " past" : ""}${night.status === "red" && !day.past ? " bad" : ""}`,
        href: `#/day?d=${day.date}`, "aria-label": `${fmtDay(day.date, true)}. Open the full day.` },
        h("div", { class: "day-head" },
          h("h3", {}, h("span", { class: "day-name" }, fmtDay(day.date).split(",")[0]), " ",
            h("span", { class: "day-date" }, fmtDay(day.date).split(", ")[1])),
          day.date === todayKey ? h("span", { class: "badge badge-ai" }, "Today") : h("span", { class: "day-open", "aria-hidden": "true" }, "›")),
        daySummary(day, blocks, night),
        h("div", { class: "day-detail" },
          ...(items.length ? items : [h("p", { class: "day-empty" }, "Free day")]),
          blocks.length ? h("p", { class: "study-line" }, `${fmtMinutes(day.used_min)} of homework (up to ${fmtMinutes(day.cap_min)})`) : null),
        h("div", { class: "day-sleep" }, day.past ? reportedSleepBar(night, goal) : sleepBar(night, goal)));
    });

    const tabs = h("div", { class: "seg week-tabs", role: "group", "aria-label": "Which week" },
      [["This week", 0], ["Next week", 1]].map(([label, i]) => h("button", { type: "button", "aria-pressed": String(which === i),
        onClick: () => { which = i; history.replaceState(null, "", i ? "#/week?w=next" : "#/week"); draw(plan); } }, label)));

    // Order: what you came for first (the days), the details after.
    fill(main,
      h("div", { class: "week-head" },
        h("div", {}, h("h1", {}, "Your week"),
          h("p", { class: "small muted", style: { margin: 0 } }, `Planned at ${fmtTime(plan.generated_at)} · tap a day to see all of it`)),
        h("div", { class: "row" }, tabs, plan.relaxed ? normalBtn : null,
          (plan.at_risk.length || badNights.some((n) => n.overflow_min)) && !plan.relaxed ? rebalanceBtn : null)),
      ...banners,
      h("div", { class: "week-grid" }, ...cards),
      plan.relaxed ? h("p", { class: "small muted", style: { marginTop: "14px" } },
        "Rebalanced: study limits are 50% higher this week so earlier days absorb the work. Sleep is never touched.") : null,
      h("div", { class: "legend", "aria-hidden": "true" },
        h("span", { style: { "--c": "var(--school)" } }, "School"), h("span", { style: { "--c": "var(--shift)" } }, "Work"),
        h("span", { style: { "--c": "var(--activity)" } }, "Activity"), h("span", { style: { "--c": "var(--accent)" } }, "Study"),
        h("span", { style: { "--c": "var(--green-bar)" } }, "Sleep Pace has planned for each night")),
      h("div", { class: "week-extras" },
        checks ? lastNightNote(todaysCheckin, goal) : null,
        h("section", { class: "card" },
          h("div", { class: "row between" }, h("h2", { style: { margin: 0 } }, "Work this week"),
            h("strong", {}, `${hours} hr`)),
          h("div", { class: "meter", role: "img", "aria-label": `${hours} work hours this week` },
            h("div", { style: { width: `${meterPct}%`, background: meterColor } })),
          h("p", { class: "small muted", style: { margin: 0 } },
            plan.work_hours_status === "red" ? "Over 20 hours. That's a lot on top of school."
              : plan.work_hours_status === "yellow" ? "Over 15 hours. Watch how your nights look."
                : "Under 15 hours on school weeks is a healthy range."))),
    );
  };
  const [firstPlan, checks] = await Promise.all([api.planWeeks(), api.checkins().catch(() => null)]);
  const todaysCheckin = checks && checks.checkins.find((c) => c.date === checks.today);
  draw(firstPlan);
}
