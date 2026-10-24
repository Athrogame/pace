import { api } from "../api.js";
import { busy, fmtDay, fmtDue, fmtMinutes, fmtRange, h, icon, toast, fill } from "../ui.js";

const OPTIONS = [
  ["15", "15 minutes", "A quick break, no questions", { minutes: 15 }],
  ["today", "The rest of today", "Clear tonight's plan", { rest_of_today: true }],
  ["day", "1 day", "The next 24 hours", { minutes: 1440 }],
  ["few", "A few days", "Pick how many", null],
  ["custom", "Custom", "Pick the hours", null],
];

export async function render(main, { app }) {
  let choice = null, fewDays = 2, customHours = 3;
  const active = await api.cameUpList();
  const result = h("div", { "aria-live": "polite" });
  const extra = h("div");
  const list = h("div", { class: "option-list", role: "radiogroup", "aria-label": "How much time do you need?" });

  const drawOptions = () => {
    list.replaceChildren(...OPTIONS.map(([key, label, sub]) => h("button", {
      type: "button", class: "option", role: "radio", "aria-checked": String(choice === key), "aria-pressed": String(choice === key),
      onClick: () => { choice = key; drawOptions(); drawExtra(); },
    }, icon(key === "15" ? "clock" : "week", 22), h("span", {}, label, h("span", { class: "sub" }, sub)))));
  };
  const drawExtra = () => {
    if (choice === "few") {
      const sel = h("select", { id: "fewDays" }, ...[2, 3, 4, 5, 6, 7].map((n) => h("option", { value: n }, `${n} days`)));
      sel.value = fewDays; sel.addEventListener("change", () => { fewDays = Number(sel.value); });
      extra.replaceChildren(h("div", { class: "field", style: { marginTop: "12px" } }, h("label", { class: "label", for: "fewDays" }, "How many days?"), sel));
    } else if (choice === "custom") {
      const sel = h("select", { id: "customHours" }, ...[1, 2, 3, 4, 5, 6, 8, 10, 12].map((n) => h("option", { value: n }, `${n} hour${n > 1 ? "s" : ""}`)));
      sel.value = customHours; sel.addEventListener("change", () => { customHours = Number(sel.value); });
      extra.replaceChildren(h("div", { class: "field", style: { marginTop: "12px" } }, h("label", { class: "label", for: "customHours" }, "Starting now, for"), sel));
    } else extra.replaceChildren();
  };

  const go = h("button", { type: "button", class: "btn btn-danger btn-block", style: { marginTop: "14px" } }, "Clear this time");
  go.addEventListener("click", busy(go, async () => {
    if (!choice) { toast("Pick how much time you need", "error"); return; }
    const opt = OPTIONS.find((o) => o[0] === choice);
    const body = opt[3] || (choice === "few" ? { minutes: fewDays * 1440 } : { minutes: customHours * 60 });
    const r = await api.cameUp(body);
    drawResult(r);
  }));

  function drawResult(r) {
    const undo = h("button", { type: "button", class: "btn btn-ghost" }, icon("undo", 18), "Undo");
    undo.addEventListener("click", busy(undo, async () => {
      await api.undoCameUp(r.id);
      toast("Undone. Your plan is back.");
      render(main, { app });
    }));
    result.replaceChildren(h("section", { class: "card" },
      h("p", { class: "eyebrow" }, `${fmtDue(r.start)} to ${fmtDue(r.end)}`),
      h("h2", {}, "Done. Take care of what you need to."),
      h("p", {}, r.moved_blocks.length
        ? `${r.moved_blocks.length} study block${r.moved_blocks.length > 1 ? "s" : ""} moved out of the way.`
        : "Nothing needed to move."),
      r.newly_at_risk.length ? h("div", { class: "banner banner-red" }, icon("alert"), h("div", {},
        h("strong", {}, "Some work won't fit now"),
        ...r.newly_at_risk.map((t) => h("p", { class: "small" },
          `${t.title}: this won't fit before ${fmtDay(t.due).split(",")[0]}. Consider asking your teacher for an extension.`)))) : null,
      r.shifts_affected.length ? h("div", { class: "banner banner-yellow" }, icon("briefcase"), h("div", {},
        h("strong", {}, "Shifts during this time"),
        ...r.shifts_affected.map((s) => h("p", { class: "small" }, `${s.title}, ${fmtDay(s.start).split(",")[0]} ${fmtRange(s.start, s.end)}`)),
        h("p", { class: "small" }, "Pace can't move shifts. If you can't make one, let your manager know as early as you can."))) : null,
      r.uses_7d >= 3 ? h("p", { class: "small muted" }, "You've needed time a few times this week. Pace is keeping your plan lighter for now.") : null,
      h("div", { class: "row" }, h("a", { class: "btn btn-primary", href: "#/week" }, "See my week"), undo)));
    main.querySelector(".chooser")?.remove();
  }

  const activeCard = active.blocks.length ? h("section", { class: "card" }, h("h2", {}, "Time you've cleared"),
    ...active.blocks.map((b) => {
      const btn = h("button", { type: "button", class: "btn btn-ghost btn-sm" }, icon("undo", 16), "Undo");
      btn.addEventListener("click", busy(btn, async () => { await api.undoCameUp(b.id); toast("Undone"); render(main, { app }); }));
      return h("div", { class: "list-row" }, h("div", { class: "grow" },
        h("strong", {}, `${fmtDue(b.start)} to ${fmtDue(b.end)}`), h("div", { class: "small muted" }, fmtMinutes((new Date(b.end) - new Date(b.start)) / 60000))), btn);
    })) : null;

  drawOptions();
  fill(main, 
    h("div", { class: "page-head" }, h("h1", {}, "Something came up"),
      h("p", {}, "No need to explain. Pick how much time you need and Pace rearranges everything else.")),
    h("section", { class: "card chooser" }, list, extra, go),
    result,
    activeCard,
  );
}
