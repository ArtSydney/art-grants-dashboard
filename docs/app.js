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

// ── Tab switching ────────────────────────────────────────────────────────────
document.getElementById("tab-list").addEventListener("click", () => switchTab("list"));
document.getElementById("tab-calendar").addEventListener("click", () => switchTab("calendar"));

function switchTab(tab) {
  const isCal = tab === "calendar";
  document.getElementById("panel-list").hidden = isCal;
  document.getElementById("panel-calendar").hidden = !isCal;
  document.getElementById("tab-list").classList.toggle("active", !isCal);
  document.getElementById("tab-calendar").classList.toggle("active", isCal);
  document.getElementById("tab-list").setAttribute("aria-selected", !isCal);
  document.getElementById("tab-calendar").setAttribute("aria-selected", isCal);
  if (isCal) renderCalendar();
}

// ── Calendar state ───────────────────────────────────────────────────────────
const calState = {
  year: new Date().getFullYear(),
  month: new Date().getMonth(), // 0-indexed
};

document.getElementById("cal-prev").addEventListener("click", () => {
  calState.month--;
  if (calState.month < 0) { calState.month = 11; calState.year--; }
  renderCalendar();
});
document.getElementById("cal-next").addEventListener("click", () => {
  calState.month++;
  if (calState.month > 11) { calState.month = 0; calState.year++; }
  renderCalendar();
});
document.getElementById("cal-download").addEventListener("click", downloadAllIcs);
document.getElementById("cal-popup-close").addEventListener("click", closePopup);
document.getElementById("cal-overlay").addEventListener("click", (e) => {
  if (e.target === document.getElementById("cal-overlay")) closePopup();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closePopup();
});

// ── Build deadline index: "YYYY-MM-DD" -> [item, ...] ────────────────────────
function deadlineIndex() {
  const idx = {};
  for (const item of state.items) {
    if (!item.deadline) continue;
    if (!idx[item.deadline]) idx[item.deadline] = [];
    idx[item.deadline].push(item);
  }
  return idx;
}

// ── Render calendar month grid ───────────────────────────────────────────────
const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function renderCalendar() {
  const { year, month } = calState;
  const idx = deadlineIndex();

  // label
  const label = new Date(year, month, 1).toLocaleString("en-AU", {
    month: "long", year: "numeric", timeZone: "Australia/Sydney"
  });
  document.getElementById("cal-month-label").textContent = label;

  const grid = document.getElementById("cal-grid");
  grid.innerHTML = "";

  // day-of-week headers (Mon first)
  DOW_LABELS.forEach((d) => {
    const h = document.createElement("div");
    h.className = "cal-dow";
    h.textContent = d;
    grid.appendChild(h);
  });

  // first day of month (0=Sun … 6=Sat), shift to Mon-first
  const firstDow = new Date(year, month, 1).getDay(); // 0=Sun
  const startOffset = (firstDow + 6) % 7; // Mon=0 … Sun=6
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrev = new Date(year, month, 0).getDate();
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,"0")}-${String(today.getDate()).padStart(2,"0")}`;

  // total cells: fill to complete weeks
  const totalCells = Math.ceil((startOffset + daysInMonth) / 7) * 7;

  for (let i = 0; i < totalCells; i++) {
    const cell = document.createElement("div");
    cell.className = "cal-cell";

    let dayNum, cellYear, cellMonth, isOther = false;
    if (i < startOffset) {
      dayNum = daysInPrev - startOffset + i + 1;
      cellYear = month === 0 ? year - 1 : year;
      cellMonth = month === 0 ? 11 : month - 1;
      isOther = true;
    } else if (i >= startOffset + daysInMonth) {
      dayNum = i - startOffset - daysInMonth + 1;
      cellYear = month === 11 ? year + 1 : year;
      cellMonth = month === 11 ? 0 : month + 1;
      isOther = true;
    } else {
      dayNum = i - startOffset + 1;
      cellYear = year;
      cellMonth = month;
    }

    const dateStr = `${cellYear}-${String(cellMonth+1).padStart(2,"0")}-${String(dayNum).padStart(2,"0")}`;
    if (isOther) cell.classList.add("other-month");
    if (dateStr === todayStr) cell.classList.add("today");

    const numEl = document.createElement("div");
    numEl.className = "cal-day-num";
    numEl.textContent = dayNum;
    cell.appendChild(numEl);

    const events = idx[dateStr] || [];
    if (events.length) {
      cell.classList.add("has-events");
      const MAX_DOTS = 3;
      events.slice(0, MAX_DOTS).forEach((item) => {
        const dot = document.createElement("span");
        dot.className = "cal-dot";
        const cat = item.category && CATS.includes(item.category) ? item.category : "Other";
        dot.style.background = CAT_COLOUR[cat];
        dot.textContent = item.title;
        dot.title = item.title;
        cell.appendChild(dot);
      });
      if (events.length > MAX_DOTS) {
        const more = document.createElement("span");
        more.className = "cal-more";
        more.textContent = `+${events.length - MAX_DOTS} more`;
        cell.appendChild(more);
      }
      cell.addEventListener("click", () => openPopup(dateStr, events));
    }

    grid.appendChild(cell);
  }
}

// ── Popup ────────────────────────────────────────────────────────────────────
function openPopup(dateStr, events) {
  const d = new Date(dateStr + "T00:00:00");
  const formatted = d.toLocaleDateString("en-AU", {
    weekday: "long", day: "numeric", month: "long", year: "numeric"
  });
  document.getElementById("cal-popup-title").textContent = `Closing ${formatted}`;

  const body = document.getElementById("cal-popup-body");
  body.innerHTML = "";
  events.forEach((item) => {
    const div = document.createElement("div");
    div.className = "cal-popup-item";
    const cat = item.category && CATS.includes(item.category) ? item.category : "Other";
    div.innerHTML = `
      <h4>${escapeHtml(item.title)}</h4>
      <p class="popup-meta">${escapeHtml(item.source)} &middot; <span style="background:${CAT_COLOUR[cat]};color:#fff;border-radius:4px;padding:1px 6px;font-size:.7rem">${escapeHtml(cat)}</span></p>
      ${item.amount ? `<div class="popup-amount">${escapeHtml(item.amount)}</div>` : ""}
      ${item.summary ? `<p style="font-size:.82rem;color:var(--c-muted);margin:6px 0 0">${escapeHtml(item.summary)}</p>` : ""}
      <div class="popup-links">
        ${item.link ? `<a href="${encodeURI(item.link)}" target="_blank" rel="noopener">View opening →</a>` : ""}
        <button class="cal-ics-btn">Add to calendar</button>
      </div>
    `;
    // Attach listener directly — avoids serialising item into an inline onclick
    // attribute, which breaks when the JSON contains double-quotes.
    div.querySelector(".cal-ics-btn").addEventListener("click", () => downloadSingleIcs(item));
    body.appendChild(div);
  });

  document.getElementById("cal-overlay").hidden = false;
  document.body.style.overflow = "hidden";
}

function closePopup() {
  document.getElementById("cal-overlay").hidden = true;
  document.body.style.overflow = "";
}

// ── .ics generation ──────────────────────────────────────────────────────────
function icsTimestamp() {
  return new Date().toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
}

function icsDate(dateStr) {
  // YYYYMMDD for all-day events
  return dateStr.replace(/-/g, "");
}

function icsEscape(s) {
  return String(s || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");
}

function buildIcs(item) {
  const uid = `opencalls-${item.id || Math.random().toString(36).slice(2)}@artsgrants.au`;
  const now = icsTimestamp();
  const date = icsDate(item.deadline);
  // DTEND is the day after for all-day events in iCal
  const dateEnd = icsDate(
    new Date(new Date(item.deadline + "T00:00:00").getTime() + 86400000)
      .toISOString().slice(0, 10)
  );
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Open Calls//Arts Grants AU//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    `UID:${uid}`,
    `DTSTAMP:${now}`,
    `DTSTART;VALUE=DATE:${date}`,
    `DTEND;VALUE=DATE:${dateEnd}`,
    `SUMMARY:DEADLINE: ${icsEscape(item.title)}`,
    `DESCRIPTION:${icsEscape([
      item.source,
      item.category,
      item.amount,
      item.summary,
      item.link,
    ].filter(Boolean).join(" | "))}`,
    item.link ? `URL:${icsEscape(item.link)}` : null,
    "BEGIN:VALARM",
    "TRIGGER:-P7D",
    "ACTION:DISPLAY",
    `DESCRIPTION:Deadline in 7 days: ${icsEscape(item.title)}`,
    "END:VALARM",
    "END:VEVENT",
    "END:VCALENDAR",
  ].filter((l) => l !== null);
  return lines.join("\r\n");
}

function slugify(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 50);
}

function downloadSingleIcs(item) {
  const content = buildIcs(item);
  const blob = new Blob([content], { type: "text/calendar;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${item.deadline}-${slugify(item.title)}.ics`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function downloadAllIcs() {
  const withDeadline = state.items.filter((i) => i.deadline);
  if (!withDeadline.length) { alert("No items with deadlines to export."); return; }

  const btn = document.getElementById("cal-download");
  btn.textContent = "Building…";
  btn.disabled = true;

  try {
    const zip = new JSZip();
    withDeadline.forEach((item) => {
      const content = buildIcs(item);
      const filename = `${item.deadline}-${slugify(item.title)}.ics`;
      zip.file(filename, content);
    });
    const blob = await zip.generateAsync({ type: "blob" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "open-calls-deadlines.zip";
    a.click();
    URL.revokeObjectURL(a.href);
  } finally {
    btn.textContent = "Download .ics (zip)";
    btn.disabled = false;
  }
}
