// First-time setup: a short, friendly walk-through instead of one long form.
import { api } from "../api.js";
import { busy, chips, field, fmtMinutes, fmtTime, h, icon, minutesSelect, timePicker, toast, WEEKDAY_LABEL, WEEKDAYS, fill } from "../ui.js";
import { accountFields, googleButton, orDivider, recurringEditor } from "./parts.js";
import { session } from "../api.js";

const STEPS = ["you", "school", "sleep", "work", "limits", "save"];

function minusMinutes(hm, minutes) {
  const [H, M] = hm.split(":").map(Number);
  let t = (H * 60 + M - minutes) % 1440;
  if (t < 0) t += 1440;
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

function heroArt() {
  // A day arc: sun rising on the left, moon on the right, a protected sleep band underneath.
  const svg = `<svg viewBox="0 0 320 150" role="img" aria-label="A day from sunrise to a protected night of sleep" class="hero-art">
    <defs><linearGradient id="arc" x1="0" x2="1"><stop offset="0" stop-color="#F2B84B"/><stop offset=".55" stop-color="var(--accent)"/><stop offset="1" stop-color="#5B5BD6"/></linearGradient></defs>
    <!-- The arc starts past the sun's edge and stops before the moon, so it never crosses either. -->
    <path d="M78 80 Q164 4 252 88" fill="none" stroke="url(#arc)" stroke-width="5" stroke-linecap="round" stroke-dasharray="2 12"/>
    <circle cx="44" cy="96" r="16" fill="#F2B84B"/>
    <g fill="#F2B84B" opacity=".8"><rect x="42" y="66" width="4" height="9" rx="2"/><rect x="14" y="94" width="9" height="4" rx="2"/><rect x="20" y="74" width="4" height="9" rx="2" transform="rotate(-45 22 78)"/></g>
    <path d="M286 82a18 18 0 1 0 14 26 15 15 0 1 1-14-26z" fill="#5B5BD6"/>
    <g fill="var(--fg)" opacity=".5"><circle cx="256" cy="58" r="2"/><circle cx="270" cy="44" r="1.5"/><circle cx="244" cy="40" r="1.5"/></g>
    <rect x="30" y="132" width="260" height="10" rx="5" fill="var(--muted)"/>
    <rect x="30" y="132" width="70" height="10" rx="5" fill="#E8E6F5"/>
    <rect x="104" y="132" width="44" height="10" rx="5" fill="var(--study)" stroke="var(--accent)" stroke-width="1.5"/>
    <rect x="152" y="132" width="56" height="10" rx="5" fill="#FDEBD8"/>
    <rect x="214" y="132" width="76" height="10" rx="5" fill="#22A55A"/>
  </svg>`;
  return h("div", { class: "hero-wrap", html: svg });
}

export async function render(main, { app }) {
  const state = {
    step: -1,               // -1 = welcome
    nickname: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "America/New_York",
    schoolDays: ["mon", "tue", "wed", "thu", "fri"],
    schoolStart: "07:45", schoolEnd: "14:45", commute: 20,
    sleepGoal: 510, schoolWake: "06:45", offWake: "09:00",
    schoolNightCap: 120, offDayCap: 240,
    saveChoice: "device",
    saved: false,
  };
  const recurring = recurringEditor({});

  // ---------- step bodies ----------
  const steps = {
    you() {
      const input = h("input", { type: "text", maxlength: 40, value: state.nickname, autocomplete: "off",
        placeholder: "A nickname is perfect", onInput: (e) => { state.nickname = e.target.value; } });
      return {
        title: "First, what should we call you?",
        sub: "Just a nickname. Pace never asks for your real name, email, or school.",
        body: [field("Nickname (optional)", input, "Only used to say hi. It's never sent to the AI coach.")],
        focus: input,
      };
    },
    school() {
      const days = chips(WEEKDAYS.map((d) => [d, WEEKDAY_LABEL[d]]), state.schoolDays,
        (v) => { state.schoolDays = v; summary(); }, { label: "School days" });
      const commute = minutesSelect(state.commute, { min: 0, max: 90, step: 5, label: "Commute each way" });
      commute.querySelector('option[value="0"]').textContent = "No commute";
      commute.addEventListener("change", () => { state.commute = Number(commute.value); summary(); });
      const note = h("p", { class: "step-summary", "aria-live": "polite" });
      const summary = () => {
        if (!state.schoolDays.length) { fill(note, icon("sparkle", 16), " No school days. Pace will treat every day as a day off."); return; }
        fill(note, icon("school", 16), ` You're busy ${fmtTime(minusMinutes(state.schoolStart, state.commute))} to ${fmtTime(minusMinutes(state.schoolEnd, -state.commute))} on school days, counting the commute.`);
      };
      summary();
      return {
        title: "When do you have school?",
        sub: "Pace never plans homework during school or your commute.",
        body: [
          field("School days", days),
          h("div", { class: "two-col" },
            field("School starts", timePicker({ value: state.schoolStart, label: "School starts", onChange: (v) => { state.schoolStart = v; summary(); } })),
            field("School ends", timePicker({ value: state.schoolEnd, label: "School ends", onChange: (v) => { state.schoolEnd = v; summary(); } }))),
          field("Commute each way", commute),
          note,
        ],
        check: () => (state.schoolDays.length && state.schoolEnd <= state.schoolStart ? "School has to end after it starts." : null),
      };
    },
    sleep() {
      const note = h("p", { class: "step-summary", "aria-live": "polite" });
      const summary = () => {
        const bed = minusMinutes(state.schoolWake, state.sleepGoal);
        fill(note, icon("moon", 16), " Pace will keep homework done by ",
          h("strong", {}, fmtTime(minusMinutes(bed, 30))), " and you in bed by ", h("strong", {}, fmtTime(bed)),
          state.schoolDays.length ? " on school nights." : ".");
      };
      const goalOptions = [[480, "8 hr"], [510, "8 hr 30 min"], [540, "9 hr"], [570, "9 hr 30 min"]];
      const goal = chips(goalOptions.map(([v, t]) => [String(v), t]), [String(state.sleepGoal)],
        (v) => { state.sleepGoal = Number(v); summary(); }, { multi: false, label: "Sleep goal" });
      summary();
      return {
        title: "How much sleep do you want?",
        sub: "Teens need about 8 to 10 hours. Pace plans backward from your wake-up time, so sleep comes first.",
        body: [
          field("Sleep goal", goal, "8 hr 30 min is a good place to start."),
          h("div", { class: "two-col" },
            state.schoolDays.length ? field("Wake up on school days", timePicker({ value: state.schoolWake, label: "School-day wake time", onChange: (v) => { state.schoolWake = v; summary(); } })) : null,
            field(state.schoolDays.length ? "Wake up on days off" : "Wake up", timePicker({ value: state.offWake, label: "Day-off wake time", onChange: (v) => { state.offWake = v; } }))),
          note,
        ],
      };
    },
    work() {
      return {
        title: "What else fills your week?",
        sub: "Work, practice, prayer, family time: add anything at a set time each week. Pace plans around it and gives you 30 minutes to rest after a work shift.",
        body: [recurring.el, h("p", { class: "hint" }, "No job or activities? Just continue. You can add one-time shifts later.")],
      };
    },
    limits() {
      const night = minutesSelect(state.schoolNightCap, { min: 30, max: 300, step: 15, label: "School nights" });
      const off = minutesSelect(state.offDayCap, { min: 30, max: 480, step: 15, label: "Days off" });
      night.addEventListener("change", () => { state.schoolNightCap = Number(night.value); });
      off.addEventListener("change", () => { state.offDayCap = Number(off.value); });
      return {
        title: "How much homework is too much?",
        sub: "Pace won't plan more than this in one day. When a week gets tight, Rebalance can stretch it a little, but never into your sleep.",
        body: [h("div", { class: "two-col" }, field("Most on a school night", night), field("Most on a day off", off))],
      };
    },
    save() {
      if (session.isChild()) {
        state.saveChoice = "device";
        return { title: "Last step: save this plan", sub: "Your parent approved this browser for a Pace plan.",
          body: [h("p", {}, "This plan stays on the approved browser. Google and AI features are unavailable."),
            h("a", { href: "/privacy-policy" }, "Read the Privacy Policy")], next: "Finish setup" };
      }
      if (session.signedIn()) {
        state.saveChoice = "signed-in";
        return {
          title: "Last step: you're all set to save",
          sub: "You're signed in, so your plan is saved to your account and works on any device.",
          body: [h("div", { class: "banner banner-green", style: { margin: 0 } }, icon("check"),
            h("p", {}, "Signed in with Google. Pace only keeps Google's account number, never your email or name."))],
          next: "Finish setup",
        };
      }
      const account = accountFields("signup");
      const accountBlock = h("div", {},
        googleButton({ text: "signup_with", onSignedIn: async (r) => {
          if (r.has_settings) {
            await app.refreshSettings();
            toast("Welcome back. Your saved plan is loaded.");
            app.go("today");
            return;
          }
          state.saveChoice = "signed-in";
          await finish();
        } }),
        orDivider(),
        account.el);
      const formWrap = h("div", { class: "account-reveal" });
      const choice = (key, ic, title, text) => h("button", {
        type: "button", class: "choice", role: "radio", "aria-checked": String(state.saveChoice === key),
        onClick: () => { state.saveChoice = key; render(); },
      }, h("span", { class: "choice-icon" }, icon(ic, 22)),
        h("span", { class: "grow" }, h("strong", {}, title), h("span", { class: "sub" }, text)),
        h("span", { class: "choice-dot", "aria-hidden": "true" }));
      const choices = h("div", { class: "choice-list", role: "radiogroup", "aria-label": "How to save your plan" });
      const render = () => {
        fill(choices,
          choice("account", "check", "Create an account", "Use Pace on your phone and laptop. Continue with Google, or pick a username."),
          choice("device", "today", "Just use this device", "Your plan stays in this browser. You can make an account later in Settings."));
        fill(formWrap, state.saveChoice === "account" ? accountBlock : null);
      };
      render();
      state.account = account;
      return {
        title: "Last step: keep your plan safe",
        sub: "Accounts are optional. Pace never keeps your email or real name.",
        body: [choices, formWrap, h("p", { class: "hint" }, h("a", { href: "#/privacy", target: "_blank" }, "See everything Pace stores"))],
        next: "Finish setup",
      };
    },
  };

  // ---------- finishing ----------
  async function finish() {
    if (!state.saved) {
      const school = new Set(state.schoolDays);
      await api.putSettings({
        nickname: state.nickname.trim() || null,
        timezone: state.timezone,
        sleep_goal_min: state.sleepGoal,
        wake_times: Object.fromEntries(WEEKDAYS.map((d) => [d, school.has(d) ? state.schoolWake : state.offWake])),
        school_blocks: Object.fromEntries(WEEKDAYS.map((d) => [d, school.has(d) ? [state.schoolStart, state.schoolEnd] : null])),
        commute_min: state.commute,
        max_study_school_night_min: state.schoolNightCap,
        max_study_weekend_day_min: state.offDayCap,
      });
      for (const ev of recurring.pending) await api.addEvent(ev);
      recurring.pending.length = 0;
      state.saved = true;
    }
    let username = state.saveChoice === "signed-in" ? "google" : null;
    if (state.saveChoice === "account") {
      const { username: u, password } = state.account.values();
      if (!u || !password) throw new Error("Pick a username and a password, or choose \"Just use this device\".");
      const r = await api.signup(u, password);
      session.start(r);
      username = r.username;
    }
    await app.refreshSettings();
    done(username);
  }

  // ---------- screens ----------
  function welcome() {
    const start = h("button", { type: "button", class: "btn btn-primary btn-block btn-lg", onClick: () => go(0) }, "Get started");
    fill(main, h("div", { class: "onboard welcome step-enter" },
      heroArt(),
      h("p", { class: "eyebrow" }, "Welcome to Pace"),
      h("h1", { class: "display", tabindex: "-1" }, "Homework, work, and sleep. All in one plan."),
      h("p", { class: "lead" }, "Pace is a planner for students with jobs. It fits your homework into the time you actually have."),
      h("ul", { class: "feature-list" },
        h("li", {}, h("span", { class: "feature-icon" }, icon("moon", 20)),
          h("span", {}, h("strong", {}, "Sleep comes first."), " Homework never gets planned into your sleep.")),
        h("li", {}, h("span", { class: "feature-icon" }, icon("scale", 20)),
          h("span", {}, h("strong", {}, "See the cost first."), " Check what an extra shift does to your week before you say yes.")),
        h("li", {}, h("span", { class: "feature-icon" }, icon("alert", 20)),
          h("span", {}, h("strong", {}, "Life happens."), " Hit \"Something came up\" and Pace rearranges everything, no questions asked."))),
      start,
      googleButton({ onSignedIn: async (r) => {
        if (r.has_settings) { await app.refreshSettings(); app.go("today"); return; }
        toast("Signed in with Google. Let's set up your week.");
        go(0);
      } }),
      session.isChild() ? null : h("a", { class: "btn btn-ghost btn-block", href: "#/signin" }, "I already have an account"),
      h("p", { class: "fine-print" }, session.isChild() ? "Takes about 2 minutes. Under-13 plans use local planning messages. " : "Takes about 2 minutes. The coach inside Pace is an AI. ", "Pace helps you plan; it isn't therapy or medical advice. If you're struggling with sleep or mood, talk to a parent, counselor or doctor. ",
        h("a", { href: "#/privacy" }, "What Pace stores"))));
    main.querySelector("h1").focus({ preventScroll: true });
  }

  function go(i) {
    state.step = i;
    if (i < 0) { welcome(); return; }
    const key = STEPS[i];
    const s = steps[key]();
    const back = h("button", { type: "button", class: "btn btn-ghost", onClick: () => go(i - 1) }, "Back");
    const next = h("button", { type: "button", class: "btn btn-primary grow" }, s.next || "Continue");
    next.addEventListener("click", busy(next, async () => {
      const problem = s.check && s.check();
      if (problem) { toast(problem, "error"); return; }
      if (i === STEPS.length - 1) await finish();
      else go(i + 1);
    }));
    const pct = Math.round(((i + 1) / STEPS.length) * 100);
    fill(main, h("div", { class: "onboard step-enter" },
      h("div", { class: "progress-head" },
        h("span", { class: "small muted" }, `Step ${i + 1} of ${STEPS.length}`),
        h("div", { class: "progress", role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": pct,
          "aria-label": "Setup progress" }, h("div", { style: { width: `${pct}%` } }))),
      h("h1", { tabindex: "-1" }, s.title),
      h("p", { class: "lead" }, s.sub),
      h("form", { class: "card step-card", novalidate: true,
        onSubmit: (e) => { e.preventDefault(); next.click(); } }, ...s.body, h("button", { type: "submit", hidden: true })),
      h("div", { class: "step-actions" }, back, next)));
    (s.focus || main.querySelector("h1")).focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }

  function done(username) {
    document.body.classList.add("no-chrome");
    fill(main, h("div", { class: "onboard done step-enter" },
      h("div", { class: "done-badge", "aria-hidden": "true" }, icon("check", 40)),
      h("h1", { class: "display", tabindex: "-1" }, state.nickname.trim() ? `You're all set, ${state.nickname.trim()}.` : "You're all set."),
      h("p", { class: "lead" }, "Your week is ready. Add your homework and Pace will fit it in around school, work, and sleep."),
      username === "google" ? h("div", { class: "banner banner-green" }, icon("check"),
        h("p", {}, "Signed in with Google. Use the same Google account to open your plan on another device.")) : null,
      username && username !== "google" ? h("div", { class: "banner banner-green" }, icon("check"),
        h("p", {}, "Signed in as ", h("strong", { style: { display: "inline" } }, `@${username}`), ". Use the same username to sign in on another device.")) : null,
      h("a", { class: "btn btn-primary btn-block btn-lg", href: "#/add" }, icon("plus", 18), "Add your first assignment"),
      h("a", { class: "btn btn-ghost btn-block", href: "#/week" }, "See my week")));
    main.querySelector("h1").focus({ preventScroll: true });
  }

  welcome();
}
