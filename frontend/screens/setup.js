// Settings: edit your routine, manage your optional account, delete your data.
// (First-time setup lives in onboarding.js.)
import { api, session } from "../api.js";
import { busy, chips, field, fmtMinutes, h, icon, minutesSelect, timePicker, toast, WEEKDAY_LABEL, WEEKDAYS, fill } from "../ui.js";
import { googleButton, orDivider, signupForm } from "./parts.js";
import { calendarSection } from "./calendar.js";
import { googleTasksSection } from "./google-tasks.js";

async function accountSection(app) {
  const wrap = h("div");
  if (session.isChild()) return h("section", { class: "card" }, h("h2", {}, "Account"),
    h("p", { class: "small muted" }, "This under-13 plan stays on the approved browser. Account sign-in is unavailable."));
  if (session.signedIn()) {
    let me = { username: null };
    try { me = await api.me(); } catch (_) { /* handled by sign-in redirect */ }
    const out = h("button", { type: "button", class: "btn btn-ghost" }, "Sign out");
    out.addEventListener("click", busy(out, async () => {
      try { await api.logout(); } catch (_) { /* signing out anyway */ }
      session.end();
      await app.refreshSettings();
      toast("Signed out");
      app.go("welcome");
    }));
    const outAll = h("button", { type: "button", class: "btn btn-ghost" }, "Sign out of all devices");
    outAll.addEventListener("click", busy(outAll, async () => {
      await api.logoutAll();
      session.end();
      await app.refreshSettings();
      toast("Signed out on all devices");
      app.go("welcome");
    }));
    const isGoogle = me.provider === "google";
    const photo = isGoogle ? session.photo() : null;
    const avatar = h("span", { class: "avatar", "aria-hidden": "true" }, isGoogle ? "G" : (me.username || "?").slice(0, 1).toUpperCase());
    if (photo) {
      const img = h("img", { src: photo, alt: "", referrerpolicy: "no-referrer", width: 48, height: 48 });
      img.addEventListener("error", () => { img.remove(); avatar.textContent = "G"; });   // fall back to the letter
      fill(avatar, img);
      avatar.classList.add("avatar-photo");
    }
    // Signed in with Google before photos were added: one quick sign-in brings it in.
    const photoOffer = isGoogle && !photo ? h("div", { class: "photo-offer" },
      h("p", { class: "small muted" }, "Want your Google photo here? Sign in with Google once more. The photo stays in this browser; Pace's server never gets it."),
      h("div", { style: { maxWidth: "320px" } }, googleButton({ text: "continue_with", onSignedIn: () => app.go("settings") }))) : null;
    fill(wrap,
      h("div", { class: "account-row" },
        avatar,
        h("div", { class: "grow" }, h("strong", {}, isGoogle ? "Signed in with Google" : `@${me.username}`),
          h("div", { class: "small muted" }, isGoogle
            ? "Your plan is saved to your account. Use the same Google account on any device. Pace never keeps your email or name."
            : "Your plan is saved to your account. Sign in with this username on any device."))),
      photoOffer,
      h("div", { class: "row", style: { marginTop: "12px" } }, out, outAll));
  } else {
    const open = h("button", { type: "button", class: "btn btn-primary" }, "Create an account");
    const formSlot = h("div");
    open.addEventListener("click", () => {
      fill(formSlot, h("div", { class: "card soft", style: { marginTop: "12px", marginBottom: 0 } },
        signupForm({ onDone: (u) => { toast(`Account created. You're @${u}.`); app.go("settings"); } })));
      open.remove();
    });
    const google = googleButton({ onSignedIn: async (r) => {
      await app.refreshSettings();
      toast(r.created ? "Your plan is now saved to your Google account." : "Signed in. Your saved plan is loaded.");
      app.go(r.has_settings ? "settings" : "welcome");
    } });
    fill(wrap,
      h("p", { class: "small muted" }, "Right now your plan only lives in this browser. An account lets you use it on your phone and laptop."),
      h("div", { style: { maxWidth: "400px" } }, google),
      orDivider(),
      h("div", { class: "row" }, open, h("a", { class: "btn btn-ghost", href: "#/signin" }, "Sign in instead")),
      formSlot);
  }
  return h("section", { class: "card" }, h("h2", {}, "Account"), wrap);
}

export async function render(main, { app, settings }) {
  const s = structuredClone(settings);

  // ----- wake times -----
  const firstSchool = WEEKDAYS.find((d) => s.school_blocks[d]) || "mon";
  const firstWeekend = WEEKDAYS.find((d) => !s.school_blocks[d]) || "sat";
  const perDay = {};
  const perDayWrap = h("div", { class: "two-col" });
  for (const d of WEEKDAYS) {
    perDay[d] = timePicker({ value: s.wake_times[d], label: `${WEEKDAY_LABEL[d]} wake time`,
      onChange: (v) => { s.wake_times[d] = v; } });
    perDayWrap.append(field(WEEKDAY_LABEL[d], perDay[d]));
  }
  const setGroup = (days, v) => days.forEach((d) => { s.wake_times[d] = v; perDay[d].setValue(v); });
  const schoolWake = timePicker({ value: s.wake_times[firstSchool], label: "School-day wake time",
    onChange: (v) => setGroup(WEEKDAYS.filter((d) => s.school_blocks[d]), v) });
  const weekendWake = timePicker({ value: s.wake_times[firstWeekend], label: "Day-off wake time",
    onChange: (v) => setGroup(WEEKDAYS.filter((d) => !s.school_blocks[d]), v) });

  // ----- school -----
  const block = s.school_blocks[firstSchool] || ["07:45", "14:45"];
  let schoolStart = block[0], schoolEnd = block[1];
  const dayChips = chips(WEEKDAYS.map((d) => [d, WEEKDAY_LABEL[d]]), WEEKDAYS.filter((d) => s.school_blocks[d]),
    null, { label: "School days" });
  const startPick = timePicker({ value: schoolStart, label: "School starts", onChange: (v) => { schoolStart = v; } });
  const endPick = timePicker({ value: schoolEnd, label: "School ends", onChange: (v) => { schoolEnd = v; } });

  // ----- other numbers -----
  const commute = minutesSelect(s.commute_min, { min: 0, max: 90, step: 5, label: "Commute" });
  commute.querySelector('option[value="0"]').textContent = "No commute";
  const sleepGoal = h("select", { "aria-label": "Sleep goal" });
  for (let m = 420; m <= 600; m += 15) sleepGoal.append(h("option", { value: m }, fmtMinutes(m) + (m === 510 ? " (recommended)" : "")));
  sleepGoal.value = s.sleep_goal_min;
  const schoolNight = minutesSelect(s.max_study_school_night_min, { min: 30, max: 300, step: 15, label: "Most study on a school night" });
  const weekend = minutesSelect(s.max_study_weekend_day_min, { min: 30, max: 480, step: 15, label: "Most study on a day off" });
  const nickname = h("input", { type: "text", maxlength: 40, value: s.nickname || "", autocomplete: "off",
    placeholder: "What should Pace call you?" });

  // ----- save -----
  const save = h("button", { type: "button", class: "btn btn-primary btn-block" }, "Save changes");
  save.addEventListener("click", busy(save, async () => {
    if (schoolEnd <= schoolStart) { toast("School has to end after it starts", "error"); return; }
    const days = new Set(dayChips.getValue());
    await api.putSettings({
      nickname: nickname.value.trim() || null,
      timezone: s.timezone || "America/New_York",
      sleep_goal_min: Number(sleepGoal.value),
      wake_times: s.wake_times,
      school_blocks: Object.fromEntries(WEEKDAYS.map((d) => [d, days.has(d) ? [schoolStart, schoolEnd] : null])),
      commute_min: Number(commute.value),
      max_study_school_night_min: Number(schoolNight.value),
      max_study_weekend_day_min: Number(weekend.value),
    });
    await app.refreshSettings();
    toast("Saved");
    app.go("week");
  }));

  // ----- delete -----
  const confirmWrap = h("div");
  const del = h("button", { type: "button", class: "btn btn-ghost btn-block" }, icon("trash", 18), "Delete my data");
  del.addEventListener("click", () => {
    const yes = h("button", { type: "button", class: "btn btn-danger" }, "Yes, delete everything");
    yes.addEventListener("click", busy(yes, async () => {
      await api.deleteMe();
      if (session.isChild()) { location.href = "/"; return; }
      session.end();
      await app.refreshSettings();
      app.go("welcome");
    }));
    fill(confirmWrap, h("div", { class: "banner banner-red", role: "alert" }, icon("alert"),
      h("div", { class: "grow" }, h("strong", {}, "This deletes your whole plan, tasks, check-ins and account."),
        h("p", { class: "small" }, "It can't be undone."),
        h("div", { class: "row", style: { marginTop: "10px" } }, yes,
          h("button", { type: "button", class: "btn btn-ghost", onClick: () => fill(confirmWrap, del) }, "Keep my data")))));
  });
  confirmWrap.append(del);

  fill(main,
    h("div", { class: "page-head" }, h("h1", {}, "Settings"), h("p", {}, "Change your routine anytime. Your plan updates right away.")),
    await accountSection(app),
    await calendarSection(settings, () => app.go("settings")),
    googleTasksSection(() => app.go("week")),

    h("section", { class: "card" }, h("h2", {}, "About you"),
      field("Nickname (optional)", nickname, "Only used to say hi. Never sent to the AI coach.")),

    h("section", { class: "card" }, h("h2", {}, "Sleep"),
      field("Sleep goal", sleepGoal, "Teens need about 8 to 10 hours. Pace plans backward from this."),
      h("div", { class: "two-col" }, field("Wake up on school days", schoolWake), field("Wake up on days off", weekendWake)),
      h("details", {}, h("summary", { class: "small summary-toggle" }, "Set a different wake time for each day"), perDayWrap)),

    h("section", { class: "card" }, h("h2", {}, "School"),
      field("School days", dayChips),
      h("div", { class: "two-col" }, field("School starts", startPick), field("School ends", endPick)),
      field("Commute each way", commute)),

    h("section", { class: "card" }, h("h2", {}, "Study limits"),
      h("p", { class: "muted small" }, "Pace won't plan more than this in one day. Rebalancing can stretch it a little when a week gets tight."),
      h("div", { class: "two-col" }, field("School nights", schoolNight), field("Days off", weekend))),

    save,

    h("section", { class: "card" },
      h("h2", {}, "Privacy"),
      h("p", { class: "small muted" }, session.isChild()
        ? "Pace keeps your plan, check-ins, coach messages, and your parent's consent email. Google and AI are unavailable for this plan. Your parent can request review or deletion using the contact in the Privacy Policy."
        : "Pace keeps your plan, check-ins, and daily coach messages, plus an optional nickname and account. It does not require your real name, email, or school name. The AI coach receives selected plan facts, not your nickname or individual check-in answers."),
      h("a", { class: "btn btn-ghost btn-block", href: "#/privacy", style: { marginBottom: "10px" } }, icon("shield", 18), "What Pace stores"),
      confirmWrap,
      h("p", { class: "small muted", style: { marginTop: "12px", marginBottom: 0 } },
        "Pace helps you plan. It isn't therapy or medical advice. If you're struggling with sleep or mood, talk to a parent, counselor or doctor. ",
        h("a", { href: "#/safety" }, "Crisis help: call or text 988."))),
    h("nav", { class: "settings-legal", "aria-label": "Legal information" },
      h("a", { href: "/privacy-policy" }, "Privacy Policy"),
      h("a", { href: "/terms" }, "Terms of Service")),
  );
}
