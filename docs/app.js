// Open Calls dashboard. Loads data.json, renders cards, and filters live.
// No framework, no build step: this file runs straight in the browser.

const CATS = ["Grant", "Scholarship", "Prize", "Award", "Residency", "Fellowship", "Commission", "Other"];
const CAT_COLOUR = {
  Grant: "var(--c-grant)", Scholarship: "var(--c-scholarship)", Prize: "var(--c-prize)",
  Award: "var(--c-award)", Residency: "var(--c-residency)", Fellowship: "var(--c-fellowship)",
  Commission: "var(--c-commission)", Other: "var(--c-other)",
};
const SOON_DAYS = 7;

// Fallback discipline list if the data file doesn't carry one (older data.json).
const FALLBACK_DISCIPLINES = ["Painting", "Drawing", "Sculpture", "Photography",
  "Printmaking", "Ceramics", "Textiles", "Illustration", "Digital/New Media",
  "Installation", "Mixed Media"];
// Tags that match every discipline filter (a painter can apply to these too).
let WILDCARDS = ["Visual Arts", "Multidisciplinary"];

const state = {
  items: [], search: "", eligibility: "all", location: "all", soonOnly: false,
  cats: new Set(),        // opportunity-type chips
  forms: new Set(),       // discipline chips
};

const $ = (sel) => document.querySelector(sel);
const grid = $("#grid");
const emptyEl = $("#empty");

init();

async function init() {
  wireControls();
  let disciplines = FALLBACK_DISCIPLINES;
  try {
    const res = await fetch("data.json", { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    state.items = data.items || [];
    if (Array.isArray(data.disciplines) && data.disciplines.length) disciplines = data.disciplines;
    if (Array.isArray(data.wildcards)) WILDCARDS = data.wildcards;
    $("#meta").textContent = metaLine(data);
  } catch (e) {
    $("#meta").textContent = "Couldn't load data.json. Run the pipeline, or serve this folder over http rather than opening the file directly.";
  }
  buildCategoryChips();
  buildDisciplineChips(disciplines);
  render();
}

function metaLine(data) {
  const when = data.generated ? new Date(data.generated) : null;
  const stamp = when ? when.toLocaleString("en-AU", {
    timeZone: "Australia/Sydney",
    dateStyle: "medium",
    timeStyle: "short"
  }) : "unknown";
  return `${data.count ?? state.items.length} open opportunities · last updated ${stamp} AEST`;
}

function makeChip(label, selectedSet, container) {
  const b = document.createElement("button");
  b.className = "chip";
  b.textContent = label;
  b.setAttribute("aria-pressed", "false");
  b.addEventListener("click", () => {
    selectedSet.has(label) ? selectedSet.delete(label) : selectedSet.add(label);
    b.setAttribute("aria-pressed", selectedSet.has(label));
    render();
  });
  container.appendChild(b);
}

function buildCategoryChips() {
  const box = $("#category-chips");
  CATS.forEach((cat) => makeChip(cat, state.cats, box));
}

function buildDisciplineChips(disciplines) {
  const box = $("#discipline-chips");
  disciplines.forEach((form) => makeChip(form, state.forms, box));
}

function wireControls() {
  $("#search").addEventListener("input", (e) => { state.search = e.target.value.toLowerCase().trim(); render(); });
  $("#location").addEventListener("change", (e) => { state.location = e.target.value; render(); });
  $("#eligibility").addEventListener("change", (e) => { state.eligibility = e.target.value; render(); });
  $("#closing-soon").addEventListener("change", (e) => { state.soonOnly = e.target.checked; render(); });
}

function daysLeft(deadline) {
  if (!deadline) return null;
  const d = new Date(deadline + "T00:00:00");
  if (isNaN(d)) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((d - today) / 86400000);
}

function countdownLabel(n) {
  if (n === null) return { text: "No deadline", cls: "none" };
  if (n < 0) return { text: "Closed", cls: "none" };
  if (n === 0) return { text: "Closes today", cls: "soon" };
  return { text: `${n}d left`, cls: n <= SOON_DAYS ? "soon" : "" };
}

// A discipline filter matches an item if the item shares a selected discipline,
// OR the item carries a wildcard tag (open to all / general visual), since a
// specialist can apply to those too.
function matchesForms(item) {
  if (!state.forms.size) return true;
  const forms = item.art_forms || [];
  if (forms.some((f) => WILDCARDS.includes(f))) return true;
  return forms.some((f) => state.forms.has(f));
}

function passes(item) {
  if (state.cats.size && !state.cats.has(item.category)) return false;
  if (!matchesForms(item)) return false;
  if (state.location !== "all" && item.location_scope !== state.location) return false;
  if (state.eligibility !== "all" && item.au_eligibility !== state.eligibility) return false;
  if (state.soonOnly) {
    const n = daysLeft(item.deadline);
    if (n === null || n > SOON_DAYS || n < 0) return false;
  }
  if (state.search) {
    const hay = `${item.title} ${item.source} ${item.summary || ""}`.toLowerCase();
    if (!hay.includes(state.search)) return false;
  }
  return true;
}

function render() {
  const shown = state.items.filter(passes);
  grid.innerHTML = "";
  emptyEl.hidden = shown.length > 0;
  shown.forEach((item) => grid.appendChild(card(item)));
}

function card(item) {
  const n = daysLeft(item.deadline);
  const cd = countdownLabel(n);
  const el = document.createElement("article");
  el.className = "card" + (cd.cls === "soon" ? " urgent" : "");

  const cat = item.category && CATS.includes(item.category) ? item.category : "Other";
  const elig = item.au_eligibility === "eligible" ? "eligible"
             : item.au_eligibility === "unclear" ? "unclear" : null;
  const forms = (item.art_forms || []);

  el.innerHTML = `
    <div class="card-top">
      <span class="cat" style="background:${CAT_COLOUR[cat]}">${cat}</span>
      <span class="count ${cd.cls}">${cd.text}</span>
    </div>
    <h2>${escapeHtml(item.title)}</h2>
    <p class="source">${escapeHtml(item.source)}</p>
    ${item.summary ? `<p class="desc">${escapeHtml(item.summary)}</p>` : ""}
    ${forms.length ? `<div class="forms">${forms.map((f) => `<span class="form-tag">${escapeHtml(f)}</span>`).join("")}</div>` : ""}
    <div class="card-foot">
      <span class="amount">${item.amount ? escapeHtml(item.amount) : ""}</span>
      ${elig ? `<span class="elig ${elig}">${elig === "eligible" ? "AU eligible" : "eligibility unclear"}</span>` : ""}
    </div>
    ${item.link ? `<a class="view" href="${encodeURI(item.link)}" target="_blank" rel="noopener">View opening →</a>` : ""}
  `;
  return el;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
