// Open Calls dashboard. Loads data.json, renders cards, and filters live.
// No framework, no build step: this file runs straight in the browser.

const CATS = ["Grant", "Scholarship", "Prize", "Award", "Residency", "Fellowship", "Commission", "Other"];
const IS_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
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
  items: [], search: "", eligibility: "all", location: "all",
  soonOnly: false, freeOnly: false, showClosed: false,
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
  $("#free-only").addEventListener("change", (e) => { state.freeOnly = e.target.checked; render(); });
  $("#show-closed").addEventListener("change", (e) => { state.showClosed = e.target.checked; render(); });
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

function isClosed(item) {
  const n = daysLeft(item.deadline);
  // has a deadline and it has passed
  return item.deadline && n !== null && n < 0;
}

function passes(item) {
  // show-closed: when ticked show only closed, when unticked hide all closed
  if (state.showClosed) {
    if (!isClosed(item)) return false;
  } else {
    if (isClosed(item)) return false;
  }
  if (state.cats.size && !state.cats.has(item.category)) return false;
  if (!matchesForms(item)) return false;
  if (state.location !== "all" && item.location_scope !== state.location) return false;
  if (state.eligibility !== "all" && item.au_eligibility !== state.eligibility) return false;
  if (state.soonOnly) {
    const n = daysLeft(item.deadline);
    if (n === null || n > SOON_DAYS || n < 0) return false;
  }
  if (state.freeOnly && String(item.entry_fee || "").toLowerCase() !== "free") return false;
  if (state.search) {
    const hay = `${item.title} ${item.source} ${item.description || item.summary || ""}`.toLowerCase();
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

// Card/popup blurb: prefer the clean classifier description; if only the raw
// scraped summary exists (older records), truncate it so it never spills as a
// wall of text on the card.
function blurb(item) {
  if (item.description) return item.description;
  const s = String(item.summary || "").trim();
  if (!s) return "";
  if (s.length <= 180) return s;
  return s.slice(0, 180).replace(/\s+\S*$/, "") + "…";
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
    ${blurb(item) ? `<p class="desc">${escapeHtml(blurb(item))}</p>` : ""}
    ${forms.length ? `<div class="forms">${forms.map((f) => `<span class="form-tag">${escapeHtml(f)}</span>`).join("")}</div>` : ""}
    <div class="card-foot">
      <span class="foot-left">
        <span class="amount">${item.amount ? escapeHtml(item.amount) : ""}</span>
        ${String(item.entry_fee || "").toLowerCase() === "free" ? `<span class="fee free">Free entry</span>` : ""}
      </span>
      ${elig ? `<span class="elig ${elig}">${elig === "eligible" ? "AU eligible" : "eligibility unclear"}</span>` : ""}
    </div>
    ${item.link ? `<a class="view" href="${safeLink(item.link)}" target="_blank" rel="noopener">View opening →</a>` : ""}
  `;
  return el;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

// Reject any link whose scheme is not http or https, guarding against
// javascript: or data: URLs that could appear in scraped content.
function safeLink(url) {
  try {
    const u = new URL(url);
    return (u.protocol === "https:" || u.protocol === "http:") ? url : "#";
  } catch { return "#"; }
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

// ── Render calendar: grid on desktop, list on mobile ────────────────────────
const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function renderCalendar() {
  if (window.innerWidth <= 600) { renderCalendarList(); return; }
  // ensure grid class and toolbar are restored after a mobile→desktop resize
  document.getElementById("cal-grid").className = "cal-grid";
  document.querySelector(".cal-toolbar").hidden = false;
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

// ── Mobile calendar list ─────────────────────────────────────────────────────
// On narrow screens the month grid cells are too small to show any text.
// Instead we render a scrollable list of deadline dates, grouped by date,
// with the same "Add to calendar" action available inline.
function renderCalendarList() {
  const idx = deadlineIndex();
  const grid = document.getElementById("cal-grid");
  grid.innerHTML = "";
  grid.className = "cal-list"; // swap CSS class so list styles apply

  // hide the month-nav toolbar — not needed for the list view
  document.querySelector(".cal-toolbar").hidden = true;

  // collect all future (or today) deadline dates, sorted ascending
  const today = new Date(); today.setHours(0,0,0,0);
  const dates = Object.keys(idx)
    .filter((d) => new Date(d + "T00:00:00") >= today)
    .sort();

  if (!dates.length) {
    grid.innerHTML = "<p class='cal-list-empty'>No upcoming deadlines.</p>";
    return;
  }

  dates.forEach((dateStr) => {
    const items = idx[dateStr];
    const d = new Date(dateStr + "T00:00:00");
    const n = daysLeft(dateStr);
    const cd = countdownLabel(n);

    // date heading
    const heading = document.createElement("div");
    heading.className = "cal-list-heading";
    heading.innerHTML = `
      <span class="cal-list-date">${d.toLocaleDateString("en-AU", { weekday:"short", day:"numeric", month:"short", year:"numeric" })}</span>
      <span class="count ${cd.cls}" style="font-size:.75rem">${cd.text}</span>
    `;
    grid.appendChild(heading);

    // one row per item
    items.forEach((item) => {
      const cat = item.category && CATS.includes(item.category) ? item.category : "Other";
      const row = document.createElement("div");
      row.className = "cal-list-row";
      row.innerHTML = `
        <span class="cat" style="background:${CAT_COLOUR[cat]};font-size:.65rem;padding:3px 8px">${escapeHtml(cat)}</span>
        <span class="cal-list-title">${escapeHtml(item.title)}</span>
        ${item.amount ? `<span class="cal-list-amount">${escapeHtml(item.amount)}</span>` : ""}
        ${String(item.entry_fee || "").toLowerCase() === "free" ? `<span class="cal-list-fee free">Free entry</span>` : ""}
        <div class="cal-list-actions">
          ${item.link ? `<a class="view" style="padding:8px 12px;font-size:.7rem" href="${safeLink(item.link)}" target="_blank" rel="noopener">View →</a>` : ""}
          <a class="cal-gcal-btn" href="${buildGoogleCalUrl(item)}" ${IS_IOS ? '' : 'target="_blank" rel="noopener"'}>+ Google Cal</a>
          <button class="cal-ics-btn">.ics</button>
        </div>
      `;
      row.querySelector(".cal-ics-btn").addEventListener("click", () => downloadSingleIcs(item));
      grid.appendChild(row);
    });
  });
}

// Re-render when crossing the 600px breakpoint (e.g. rotating device)
let _lastMobile = window.innerWidth <= 600;
window.addEventListener("resize", () => {
  const nowMobile = window.innerWidth <= 600;
  if (nowMobile !== _lastMobile) {
    _lastMobile = nowMobile;
    // restore toolbar visibility before re-render so grid mode can show it
    document.querySelector(".cal-toolbar").hidden = false;
    const calPanel = document.getElementById("panel-calendar");
    if (!calPanel.hidden) {
      document.getElementById("cal-grid").className = "cal-grid";
      renderCalendar();
    }
  }
});

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
      ${String(item.entry_fee || "").toLowerCase() === "free" ? `<div class="popup-fee free">Free entry</div>` : ""}
      ${blurb(item) ? `<p style="font-size:.82rem;color:var(--c-muted);margin:6px 0 0">${escapeHtml(blurb(item))}</p>` : ""}
      <div class="popup-links">
        ${item.link ? `<a href="${safeLink(item.link)}" target="_blank" rel="noopener">View opening →</a>` : ""}
        <button class="cal-ics-btn">Download .ics</button>
        <a class="cal-gcal-btn" href="${buildGoogleCalUrl(item)}" ${IS_IOS ? '' : 'target="_blank" rel="noopener"'}>+ Google Calendar</a>
      </div>
    `;
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

// ── Google Calendar URL ───────────────────────────────────────────────────────
// Opens Google Calendar in the browser and pre-fills the event. Works on iOS
// where .ics files can't be opened directly by Google Calendar.
function buildGoogleCalUrl(item) {
  const date = (item.deadline || "").replace(/-/g, "");
  // Parse parts directly to avoid local-timezone drift when converting back
  // via toISOString() (which is always UTC). E.g. midnight Sydney is 2pm UTC
  // the day before, so adding 86400000ms and calling toISOString() can return
  // the same date rather than the next one.
  const [y, m, d] = (item.deadline || "").split("-").map(Number);
  const next = new Date(Date.UTC(y, m - 1, d + 1));
  const nextDay = `${next.getUTCFullYear()}${String(next.getUTCMonth()+1).padStart(2,"0")}${String(next.getUTCDate()).padStart(2,"0")}`;
  const details = [item.source, item.category, item.amount, item.link]
    .filter(Boolean).join(" | ");
  // Build manually so the slash in dates= is not percent-encoded — Google
  // Calendar's frontend rejects %2F and gets stuck loading.
  const base = IS_IOS
    ? "comgooglecalendar://calendar/render?action=TEMPLATE"
    : "https://calendar.google.com/calendar/render?action=TEMPLATE";
  const parts = [
    `text=${encodeURIComponent("DEADLINE: " + item.title)}`,
    `dates=${date}/${nextDay}`,
    `details=${encodeURIComponent(details)}`,
    item.link ? `location=${encodeURIComponent(item.link)}` : null,
  ].filter(Boolean);
  return `${base}&${parts.join("&")}`;
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


// ── Theme switcher ───────────────────────────────────────────────────────────
// Footer buttons flip data-theme on <html> and remember the choice. A tiny
// inline script in <head> applies the saved theme before paint to avoid a flash.
// Bloom is the default when nothing is saved.
(function themeSwitcher() {
  const KEY = "oc-theme";
  const root = document.documentElement;
  const btns = document.querySelectorAll(".theme-btn");

  function apply(name) {
    if (name && name !== "default") root.setAttribute("data-theme", name);
    else root.removeAttribute("data-theme");
    btns.forEach((b) => {
      const active = (b.dataset.theme || "default") === (name || "default");
      b.setAttribute("aria-pressed", active);
    });
  }

  btns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.theme || "default";
      apply(name);
      try { localStorage.setItem(KEY, name); } catch (e) {}
    });
  });

  let saved = "bloom";
  try { saved = localStorage.getItem(KEY) || "bloom"; } catch (e) {}
  apply(saved);
})();
