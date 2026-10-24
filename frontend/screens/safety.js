// Help & resources. Fixed text only: no AI anywhere on this screen.
// Numbers checked October 2026 against each organization's own site (see SECURITY.md / README).
import { h, icon, fill } from "../ui.js";

const tel = (n) => `tel:${n.replace(/[^0-9]/g, "")}`;

function resource({ name, who, hours, call, text, textWord, chat, site }) {
  const actions = [];
  if (call) actions.push(h("a", { class: "btn btn-ghost btn-sm", href: tel(call) }, icon("phone", 16), `Call ${call}`));
  const shown = text && text.length === 11 ? `${text[0]}-${text.slice(1, 4)}-${text.slice(4, 7)}-${text.slice(7)}` : text;
  if (text) actions.push(h("a", { class: "btn btn-ghost btn-sm", href: `sms:${text}` }, icon("message", 16),
    textWord ? `Text ${textWord} to ${shown}` : `Text ${shown}`));
  if (chat) actions.push(h("a", { class: "btn btn-ghost btn-sm", href: chat, target: "_blank", rel: "noopener noreferrer" }, "Chat online"));
  return h("div", { class: "res-row" },
    h("div", { class: "res-head" }, h("strong", {}, name), hours ? h("span", { class: "res-hours" }, hours) : null),
    h("p", { class: "res-who" }, who),
    actions.length ? h("div", { class: "res-actions" }, actions) : null,
    site ? h("a", { class: "res-site", href: site, target: "_blank", rel: "noopener noreferrer" }, site.replace(/^https:\/\/(www\.)?/, "").replace(/\/$/, "")) : null);
}

function group(title, ic, intro, items) {
  return h("section", { class: "card res-group" },
    h("h2", {}, icon(ic, 20), " ", title),
    intro ? h("p", { class: "muted small" }, intro) : null,
    items.map(resource));
}

export async function render(main, { settings }) {
  fill(main, h("div", { class: "resources" },
    // ---------- right now ----------
    h("section", { class: "card safety-card" },
      h("h1", {}, "You don't have to handle this alone."),
      h("p", {}, "If you're thinking about hurting yourself, please reach out now."),
      h("p", {}, h("strong", {}, "Call or text 988"), " (Suicide & Crisis Lifeline, 24/7, free)."),
      h("p", {}, "If you're in immediate danger, call 911."),
      h("p", {}, "Talking to a parent, school counselor or another trusted adult can help too."),
      h("div", { class: "safety-actions" },
        h("a", { class: "btn btn-primary btn-block", href: "tel:988" }, icon("phone", 18), "Call 988"),
        h("a", { class: "btn btn-primary btn-block", href: "sms:988" }, icon("message", 18), "Text 988"),
        h("a", { class: "btn btn-ghost btn-block", href: "https://988lifeline.org/chat/", target: "_blank", rel: "noopener noreferrer" }, "Chat with 988 online"),
        h("a", { class: "btn btn-ghost btn-block", href: settings ? "#/today" : "#/welcome" }, "Back to my plan")),
      h("p", { class: "small muted", style: { margin: "14px 0 0" } },
        "En español: llama al 988 y oprime 2, o envía AYUDA al 988. Deaf or hard of hearing: dial 711, then 988.")),

    // ---------- talk to someone ----------
    group("Talk to someone, any time", "message", "Free and confidential. You don't need a reason to reach out.", [
      { name: "Crisis Text Line", hours: "24/7", text: "741741", textWord: "HOME",
        who: "Text with a trained crisis counselor about anything. In Spanish, text HOLA to 741741.", site: "https://www.crisistextline.org" },
      { name: "The Trevor Project", hours: "24/7", call: "1-866-488-7386", text: "678678", textWord: "START",
        chat: "https://www.thetrevorproject.org/get-help/", who: "For LGBTQ+ young people under 25." },
      { name: "Teen Line", hours: "Evenings, 6–10 PM Pacific (9 PM–1 AM Eastern)", call: "1-800-852-8336", text: "839863", textWord: "TEEN",
        who: "Talk or text with another teen who's been trained to listen. Outside those hours, calls go to 988.", site: "https://www.teenline.org" },
    ]),

    // ---------- if someone is hurting you ----------
    group("If someone is hurting you", "shield", "At home, in a relationship, or anywhere else. It's not your fault, and you can get help.", [
      { name: "Childhelp National Child Abuse Hotline", hours: "24/7", call: "1-800-422-4453", text: "18004224453", textWord: "GO",
        who: "For kids and teens being hurt or scared at home, and for adults worried about a child. Over 170 languages.", site: "https://www.childhelphotline.org" },
      { name: "love is respect", hours: "24/7", call: "1-866-331-9474", text: "22522", textWord: "LOVEIS",
        who: "For dating and relationship abuse, or if something just doesn't feel right.", site: "https://www.loveisrespect.org" },
    ]),

    // ---------- more support ----------
    group("More support (not for emergencies)", "heart", null, [
      { name: "NAMI HelpLine", hours: "Weekdays, 10 AM–10 PM Eastern", call: "1-800-950-6264", text: "62640", textWord: "helpline",
        who: "Answers about mental health, how to get help, and how to support a friend.", site: "https://www.nami.org/support-education/nami-helpline/" },
      { name: "SAMHSA National Helpline", hours: "24/7", call: "1-800-662-4357",
        who: "Free help finding treatment and support for mental health or substance use, in English and Spanish.", site: "https://www.samhsa.gov/find-help/helplines/national-helpline" },
    ]),

    // ---------- work ----------
    group("Problems at work", "briefcase", "Teens have legal limits on how late and how many hours they can work during the school year, and you have the right to be paid for every hour.", [
      { name: "U.S. Department of Labor, Wage and Hour Division", hours: "Weekdays, 8 AM–4:30 PM local time", call: "1-866-487-9243",
        who: "Questions about your hours, pay, breaks, or work that feels unsafe. Your state labor office can help too.", site: "https://www.youthrules.gov" },
    ]),

    // ---------- a quick reset ----------
    h("section", { class: "card" },
      h("h2", {}, icon("moon", 20), " If you're overwhelmed right now"),
      h("p", { class: "muted small" }, "Small things that can help in the moment. They aren't a replacement for talking to someone."),
      h("ol", { class: "reset-steps" },
        h("li", {}, h("strong", {}, "Breathe slowly. "), "In for 4, hold for 4, out for 4, hold for 4. Do it 4 times."),
        h("li", {}, h("strong", {}, "Ground yourself. "), "Name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste."),
        h("li", {}, h("strong", {}, "Change the scene. "), "Get water, step outside, or move to a different room."),
        h("li", {}, h("strong", {}, "Reach out. "), "Text a friend or tell a family member \"I'm having a hard night.\""),
        h("li", {}, h("strong", {}, "Let tonight be lighter. "), "Homework can wait. In Pace, tap \"Something came up\" and your plan moves without any questions."))),

    h("section", { class: "card" },
      h("h2", {}, "Outside the U.S.?"),
      h("p", { class: "small", style: { margin: 0 } }, "Find a free helpline in your country at ",
        h("a", { href: "https://findahelpline.com", target: "_blank", rel: "noopener noreferrer" }, "findahelpline.com"), ".")),

    h("p", { class: "fine-print center" }, "Pace helps you plan. It isn't therapy or medical advice, and nothing on this page is written by AI. Numbers checked October 2026."),
  ));
}
