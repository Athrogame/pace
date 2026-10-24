import { api } from "../api.js";
import { busy, fmtMinutes, h, toast, fill } from "../ui.js";
import { skipCheckin } from "../app.js";

function scale(name, low, high, onPick) {
  let value = null;
  const wrap = h("div", { class: "scale", role: "radiogroup", "aria-label": name });
  const draw = () => wrap.replaceChildren(...[1, 2, 3, 4, 5].map((n) => h("button", {
    type: "button", role: "radio", "aria-checked": String(value === n), "aria-pressed": String(value === n),
    "aria-label": `${name} ${n} of 5`, onClick: () => { value = n; draw(); onPick(n); },
  }, n)));
  draw();
  return h("div", { class: "field" }, h("span", { class: "label" }, name), wrap,
    h("div", { class: "scale-ends", "aria-hidden": "true" }, h("span", {}, low), h("span", {}, high)));
}

export async function render(main, { app, settings }) {
  const goal = settings.sleep_goal_min;
  let sleep = goal, energy = null, stress = null;
  const day = settings.now.slice(0, 10);

  const sleepSel = h("select", { id: "sleepSel" });
  for (let m = 180; m <= 720; m += 15) sleepSel.append(h("option", { value: m }, fmtMinutes(m)));
  sleepSel.value = goal;
  sleepSel.addEventListener("change", () => { sleep = Number(sleepSel.value); });

  const save = h("button", { type: "button", class: "btn btn-primary btn-block" }, "Done");
  save.addEventListener("click", busy(save, async () => {
    if (energy === null || stress === null) { toast("Tap a number for energy and stress", "error"); return; }
    const r = await api.checkin({ sleep_min: sleep, energy, stress });
    app.markCheckedIn(day);
    if (r.mode === "safety") { app.go("safety"); return; }
    if (r.mode === "recovery") toast("Thanks. Tonight's plan is lighter.");
    else toast("Thanks. Plan updated.");
    app.go("today");
  }));

  fill(main, 
    h("div", { class: "page-head" }, h("p", { class: "eyebrow" }, "Morning check-in"), h("h1", {}, "How are you doing?"),
      h("p", {}, "Three taps. Pace uses this to decide whether tonight should be lighter.")),
    h("section", { class: "card" },
      h("div", { class: "field" }, h("label", { class: "label", for: "sleepSel" }, "How long did you sleep?"), sleepSel),
      scale("Energy", "Running on empty", "Full of energy", (n) => { energy = n; }),
      scale("Stress", "Calm", "Very stressed", (n) => { stress = n; }),
      save,
      h("button", { type: "button", class: "btn btn-ghost btn-block", style: { marginTop: "10px" },
        onClick: () => { skipCheckin(day); app.go("today"); } }, "Skip today")),
  );
}
