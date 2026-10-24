// "What Pace stores": a plain-language privacy page (Take9 pledge, see SECURITY.md).
import { h, icon, fill } from "../ui.js";

const STORED = [
  ["Plan and account", "A random plan ID and optional nickname. If you make an account, Pace keeps your username and a salted password hash, never the password itself.", "Pace also stores a hash of each sign-in session token."],
  ["Routine and schedule", "Your time zone, sleep goal, wake and school times, commute, study limits, shifts, and activities.", "These let Pace build your plan."],
  ["Assignments and work history", "Task titles, subjects, deadlines, estimates, progress, and time you log.", "If you accept a time-estimate suggestion, Pace keeps that subject preference."],
  ["Check-ins", "The sleep duration, energy score, and stress score you enter each day.", "Pace uses them to choose a planning mode; the AI does not receive your individual scores."],
  ["Coach and safety records", "Pace saves the daily coach messages it shows you, their source and time, and your daily Decide request count.", "It also keeps blocked times from Something came up and timestamps for safety alerts. A safety marker stores a time, not a copy of the triggering text. Decide chat text is not saved in Pace's database."],
  ["Google sign-in and imports", "If these features are available and you choose them, Pace keeps Google's account ID, selected Calendar event times and optional titles, and the Google Tasks you import as assignments.", "It also keeps import IDs and the last Calendar import time. Google access tokens are not stored on Pace's server."],
  ["Parent consent", "For an under-13 plan, Pace keeps the parent or guardian email and consent status.", "An unapproved request is removed after seven days when cleanup next runs; an approved record stays until the plan is deleted."],
  ["Abuse prevention", "Pace briefly keeps a cryptographic digest of your IP address and the action requested to limit repeated sign-ins and other sensitive requests.", "The counter does not contain the raw IP and is cleared after a day when cleanup next runs."],
  ["This browser", "Your anonymous plan ID, an optional Google photo URL, a running timer, and small preferences are kept locally.", "Sign-in and age-status cookies are HttpOnly; the age cookie lasts up to one year. Your birth month and year are not saved."],
];

const NOT_REQUIRED = ["Your real name", "Your own email address", "Your school's name", "Your precise location or contacts"];

export async function render(main, { settings }) {
  fill(main, h("div", { class: "privacy" },
    h("div", { class: "page-head" },
      h("p", { class: "eyebrow" }, "Privacy"),
      h("h1", {}, "What Pace stores"),
      h("p", {}, "Here is what Pace keeps in its database and in this browser.")),

    h("section", { class: "card" },
      h("h2", {}, "What Pace keeps"),
      h("div", { class: "store-list" }, STORED.map(([what, why, note]) => h("div", { class: "store-row" },
        h("span", { class: "store-icon" }, icon("check", 16)),
        h("div", { class: "grow" }, h("strong", {}, what), h("p", { class: "small muted" }, why, note ? ` ${note}` : "")))))),

    h("section", { class: "card" },
      h("h2", {}, "What you don't need to provide"),
      h("ul", { class: "never-list" }, NOT_REQUIRED.map((n) => h("li", {}, icon("x", 16), n))),
      h("p", { class: "small muted" }, "A parent or guardian email is needed for under-13 consent. Please avoid putting personal details in titles or coach questions unless they are needed for planning.")),

    h("section", { class: "card" },
      h("h2", {}, "What the AI coach sees"),
      h("p", {}, "For daily messages, the AI gets the mode Pace selected and plan facts, like \"Chem lab report, 45 minutes, stop by 9:45 PM\". When you choose AI suggestions for Google Tasks, it gets task titles and list names. If you use Decide coach chat, it may get your question, options, plan sleep outlook, and broad sleep and energy bands. It does not receive your nickname, individual check-in answers, or text caught by the safety filter. Under-13 plans use local replies instead.")),

    h("section", { class: "card" },
      h("h2", {}, "How it's protected"),
      h("ul", { class: "plain-list" },
        h("li", {}, "Pace runs over HTTPS, so your plan is encrypted on the way to the server."),
        h("li", {}, "Passwords are scrambled (hashed) before they're saved. After 5 wrong tries, that username is locked for 15 minutes."),
        h("li", {}, "Once your plan has an account, it can only be opened by signing in."),
        h("li", {}, "Other websites can't load Pace inside their pages or run their code in it."),
        h("li", {}, "API keys and secrets stay on the server, never in the app or on GitHub."))),

    h("section", { class: "card" },
      h("h2", {}, "You're in control"),
      h("p", {}, "You can delete your plan and account from Pace's active database at any time in Settings → Privacy → Delete my data. This includes check-ins, coach messages, safety markers, and any parent consent record. Hosting logs and backups may follow their providers' retention schedules."),
      settings ? h("a", { class: "btn btn-ghost btn-sm", href: "#/settings" }, "Go to Settings") : null),

    h("div", { class: "banner banner-info" }, icon("shield"),
      h("div", {}, h("strong", {}, "Pause before you share"),
        h("p", { class: "small" }, "Pace will never email, text or message you asking for your password. If something asks, don't answer it. Pace supports Take9, a campaign that encourages everyone to pause and think before clicking, downloading or sharing online. ",
          h("a", { href: "https://pausetake9.org/", target: "_blank", rel: "noopener noreferrer" }, "pausetake9.org")))),

    h("a", { class: "back-link", href: "/privacy-policy" }, "Read the full Privacy Policy"),
    h("a", { class: "btn btn-ghost btn-block", href: settings ? "#/today" : "#/welcome" }, settings ? "Back to my plan" : "Back")));
}
