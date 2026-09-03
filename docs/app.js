// Open Calls dashboard. Loads data.json, renders cards in batches, filters live.
// No framework, no build step: this file runs straight in the browser.
//
// Two things differ from the pre-mobile version and are load-bearing:
//   · the calendar builds its date index from the FILTERED set, so filters set
//     on the list carry across to the calendar tab
//   · JSZip is fetched on demand rather than on every page load

/* ══ OPTION A logic. Self-contained: nothing here touches app.js. ═════════ */

const CATS = ["Grant","Scholarship","Prize","Award","Residency","Fellowship","Commission","Other"];
const CAT_COLOUR = {
  Grant:"var(--c-grant)", Scholarship:"var(--c-scholarship)", Prize:"var(--c-prize)",
  Award:"var(--c-award)", Residency:"var(--c-residency)", Fellowship:"var(--c-fellowship)",
  Commission:"var(--c-commission)", Other:"var(--c-other)",
};
const IS_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
               (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const SOON_DAYS = 7;
const BATCH = 24;
const FALLBACK_DISCIPLINES = ["Painting","Drawing","Sculpture","Photography","Printmaking",
  "Ceramics","Textiles","Illustration","Digital/New Media","Installation","Mixed Media"];
let WILDCARDS = ["Visual Arts","Multidisciplinary"];

const state = {
  items:[], filtered:[], rendered:0,
  search:"", eligibility:"all", location:"all", sort:"deadline",
  soonOnly:false, freeOnly:false, showClosed:false,
  cats:new Set(), forms:new Set(),
};

const $ = (s) => document.querySelector(s);
const grid = $("#grid");

/* ── boot ─────────────────────────────────────────────────────────────── */
init();

async function init(){
  wire();
  let disciplines = FALLBACK_DISCIPLINES;
  try{
    // Default cache, not no-store: GitHub Pages sends an ETag, so repeat
    // visits cost a 304 rather than re-downloading ~490KB every time.
    const res = await fetch("data.json");
    if(!res.ok) throw new Error(res.status);
    const data = await res.json();
    state.items = data.items || [];
    if(Array.isArray(data.disciplines) && data.disciplines.length) disciplines = data.disciplines;
    if(Array.isArray(data.wildcards)) WILDCARDS = data.wildcards;
    $("#meta").textContent = metaLine(data);
  }catch(e){
    $("#meta").textContent = "Couldn't load the latest run. Reload, or try again shortly.";
  }
  buildChips("#category-chips", CATS, state.cats);
  buildChips("#discipline-chips", disciplines, state.forms);
  render();
}

function metaLine(data){
  const when = data.generated ? new Date(data.generated) : null;
  const stamp = when ? when.toLocaleString("en-AU",{timeZone:"Australia/Sydney",dateStyle:"medium",timeStyle:"short"}) : "unknown";
  return "Last updated " + stamp + " AEST";
}

/* ── filtering ────────────────────────────────────────────────────────── */
function daysLeft(deadline){
  if(!deadline) return null;
  const d = new Date(deadline + "T00:00:00");
  if(isNaN(d)) return null;
  const today = new Date(); today.setHours(0,0,0,0);
  return Math.round((d - today) / 86400000);
}
function countdownLabel(n){
  if(n === null) return {text:"No deadline", cls:"none"};
  if(n < 0)      return {text:"Closed", cls:"none"};
  if(n === 0)    return {text:"Closes today", cls:"soon"};
  if(n === 1)    return {text:"1 day left", cls:"soon"};
  return {text:n + " days left", cls: n <= SOON_DAYS ? "soon" : ""};
}
function isClosed(item){
  const n = daysLeft(item.deadline);
  return !!item.deadline && n !== null && n < 0;
}
function matchesForms(item){
  if(!state.forms.size) return true;
  const forms = item.art_forms || [];
  if(forms.some((f) => WILDCARDS.includes(f))) return true;
  return forms.some((f) => state.forms.has(f));
}
function passes(item){
  if(state.showClosed){ if(!isClosed(item)) return false; }
  else { if(isClosed(item)) return false; }
  if(state.cats.size && !state.cats.has(item.category)) return false;
  if(!matchesForms(item)) return false;
  if(state.location !== "all" && item.location_scope !== state.location) return false;
  if(state.eligibility !== "all" && item.au_eligibility !== state.eligibility) return false;
  if(state.soonOnly){
    const n = daysLeft(item.deadline);
    if(n === null || n > SOON_DAYS || n < 0) return false;
  }
  if(state.freeOnly && String(item.entry_fee || "").toLowerCase() !== "free") return false;
  if(state.search){
    const hay = (item.title + " " + item.source + " " + (item.description || item.summary || "")).toLowerCase();
    if(!hay.includes(state.search)) return false;
  }
  return true;
}
function amountValue(item){
  const m = String(item.amount || "").replace(/,/g,"").match(/\d+/g);
  return m ? Math.max.apply(null, m.map(Number)) : -1;
}
function sortItems(list){
  const s = state.sort;
  return list.slice().sort((a,b) => {
    if(s === "newest") return String(b.first_seen || "").localeCompare(String(a.first_seen || ""));
    if(s === "amount") return amountValue(b) - amountValue(a);
    if(s === "title")  return String(a.title || "").localeCompare(String(b.title || ""));
    const da = a.deadline || "9999-12-31", db = b.deadline || "9999-12-31";
    return da.localeCompare(db);
  });
}

/* ── rendering, in batches ────────────────────────────────────────────── */
function render(){
  state.filtered = sortItems(state.items.filter(passes));
  state.rendered = 0;
  grid.innerHTML = "";
  $("#empty").hidden = state.filtered.length > 0;
  const n = state.filtered.length;
  $("#result-count").textContent = n + (n === 1 ? " open call" : " open calls");
  renderMore();
  updateFilterCount();
}
function renderMore(){
  const slice = state.filtered.slice(state.rendered, state.rendered + BATCH);
  const frag = document.createDocumentFragment();
  slice.forEach((item) => frag.appendChild(card(item)));
  grid.appendChild(frag);
  state.rendered += slice.length;
}
new IntersectionObserver((entries) => {
  if(entries[0].isIntersecting && state.rendered < state.filtered.length) renderMore();
}, {rootMargin:"600px"}).observe($("#sentinel"));

function blurb(item){
  if(item.description) return item.description;
  const s = String(item.summary || "").trim();
  if(!s) return "";
  return s.length <= 180 ? s : s.slice(0,180).replace(/\s+\S*$/,"") + "…";
}

function card(item){
  const n = daysLeft(item.deadline);
  const cd = countdownLabel(n);
  const el = document.createElement(item.link ? "a" : "article");
  el.className = "card" + (cd.cls === "soon" ? " urgent" : "");
  if(item.link){ el.href = safeLink(item.link); el.target = "_blank"; el.rel = "noopener"; }

  const cat = CATS.includes(item.category) ? item.category : "Other";
  const elig = item.au_eligibility === "eligible" ? "eligible"
             : item.au_eligibility === "unclear" ? "unclear" : null;
  const forms = item.art_forms || [];
  const shown = forms.slice(0,3);
  const extra = forms.length - shown.length;

  el.innerHTML =
    '<div class="card-top">' +
      '<span class="cat" style="background:' + CAT_COLOUR[cat] + '">' + cat + '</span>' +
      '<span class="count ' + cd.cls + '">' + cd.text + '</span>' +
    '</div>' +
    '<h2>' + esc(item.title) + '</h2>' +
    '<p class="source">' + esc(item.source) + '</p>' +
    (blurb(item) ? '<p class="desc">' + esc(blurb(item)) + '</p>' : "") +
    (shown.length ? '<div class="forms">' +
        shown.map((f) => '<span class="form-tag">' + esc(f) + '</span>').join("") +
        (extra > 0 ? '<span class="form-tag">+' + extra + '</span>' : "") +
      '</div>' : "") +
    '<div class="card-foot">' +
      '<span class="foot-left">' +
        (item.amount ? '<span class="amount">' + esc(item.amount) + '</span>' : "") +
        (String(item.entry_fee || "").toLowerCase() === "free" ? '<span class="fee free">Free entry</span>' : "") +
        (elig ? '<span class="elig ' + elig + '">' + (elig === "eligible" ? "AU eligible" : "eligibility unclear") + '</span>' : "") +
      '</span>' +
      (item.link ? '<span class="go">Open listing</span>' : "") +
    '</div>';
  return el;
}

function esc(s){
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function safeLink(url){
  try{ const u = new URL(url); return (u.protocol === "https:" || u.protocol === "http:") ? url : "#"; }
  catch(e){ return "#"; }
}

/* ── chips + controls ─────────────────────────────────────────────────── */
function buildChips(sel, labels, set){
  const box = $(sel);
  box.innerHTML = "";
  labels.forEach((label) => {
    const b = document.createElement("button");
    b.className = "chip"; b.type = "button"; b.textContent = label;
    b.dataset.value = label;
    b.setAttribute("aria-pressed", set.has(label));
    b.addEventListener("click", () => {
      set.has(label) ? set.delete(label) : set.add(label);
      b.setAttribute("aria-pressed", set.has(label));
      render();
    });
    box.appendChild(b);
  });
}

function activeFilterCount(){
  let n = state.cats.size + state.forms.size;
  if(state.location !== "all") n++;
  if(state.eligibility !== "all") n++;
  if(state.soonOnly) n++;
  if(state.freeOnly) n++;
  if(state.showClosed) n++;
  return n;
}
function updateFilterCount(){
  const n = activeFilterCount();
  const badge = $("#filter-count");
  badge.hidden = n === 0;
  badge.textContent = n;
  $("#sheet-apply").textContent = "Show " + state.filtered.length + " result" + (state.filtered.length === 1 ? "" : "s");
}

let searchTimer;
function wire(){
  $("#search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const v = e.target.value.toLowerCase().trim();
    searchTimer = setTimeout(() => { state.search = v; render(); }, 140);
  });
  $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
  $("#location").addEventListener("change", (e) => { state.location = e.target.value; render(); });
  $("#eligibility").addEventListener("change", (e) => { state.eligibility = e.target.value; render(); });
  $("#closing-soon").addEventListener("change", (e) => { state.soonOnly = e.target.checked; render(); });
  $("#free-only").addEventListener("change", (e) => { state.freeOnly = e.target.checked; render(); });
  $("#show-closed").addEventListener("change", (e) => { state.showClosed = e.target.checked; render(); });

  $("#open-filters").addEventListener("click", openSheet);
  $("#sheet-close").addEventListener("click", closeSheet);
  $("#sheet-apply").addEventListener("click", closeSheet);
  $("#sheet-backdrop").addEventListener("click", closeSheet);
  $("#sheet-clear").addEventListener("click", clearAll);
  $("#empty-clear").addEventListener("click", clearAll);

  document.addEventListener("keydown", (e) => {
    if(e.key !== "Escape") return;
    if(!$("#sheet").hidden) closeSheet();
    if(!$("#cal-overlay").hidden) closePopup();
  });

  document.querySelectorAll(".tab[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  $("#cal-prev").addEventListener("click", () => { stepMonth(-1); });
  $("#cal-next").addEventListener("click", () => { stepMonth(1); });
  $("#cal-download").addEventListener("click", downloadAllIcs);
  $("#cal-popup-close").addEventListener("click", closePopup);
  $("#cal-overlay").addEventListener("click", (e) => { if(e.target === $("#cal-overlay")) closePopup(); });

  const toTop = $("#to-top");
  toTop.addEventListener("click", () => window.scrollTo({top:0, behavior:"smooth"}));
  window.addEventListener("scroll", () => { toTop.hidden = window.scrollY < 700; }, {passive:true});

  matchMedia("(min-width:760px)").addEventListener("change", () => {
    if(!$("#panel-calendar").hidden) renderCalendar();
  });
}

function clearAll(){
  state.cats.clear(); state.forms.clear();
  state.location = "all"; state.eligibility = "all";
  state.soonOnly = false; state.freeOnly = false; state.showClosed = false;
  state.search = ""; 
  $("#search").value = "";
  $("#location").value = "all"; $("#eligibility").value = "all";
  $("#closing-soon").checked = false; $("#free-only").checked = false; $("#show-closed").checked = false;
  document.querySelectorAll(".chip[data-value]").forEach((c) => c.setAttribute("aria-pressed","false"));
  render();
}

let scrollLock = 0;
function lockScroll(){ scrollLock = window.scrollY; document.body.style.position = "fixed";
  document.body.style.top = -scrollLock + "px"; document.body.style.width = "100%"; }
function unlockScroll(){ document.body.style.position = ""; document.body.style.top = "";
  document.body.style.width = ""; window.scrollTo(0, scrollLock); }

function openSheet(){
  updateFilterCount();
  $("#sheet-backdrop").hidden = false;
  $("#sheet").hidden = false;
  lockScroll();
}
function closeSheet(){
  $("#sheet").hidden = true;
  $("#sheet-backdrop").hidden = true;
  unlockScroll();
}

/* ── tabs ─────────────────────────────────────────────────────────────── */
function switchTab(tab){
  const isCal = tab === "calendar";
  $("#panel-list").hidden = isCal;
  $("#panel-calendar").hidden = !isCal;
  document.querySelectorAll(".tab[data-tab]").forEach((b) => {
    b.setAttribute("aria-selected", b.dataset.tab === tab);
  });
  window.scrollTo(0,0);
  if(isCal) renderCalendar();
}

/* ── calendar ─────────────────────────────────────────────────────────── */
const calState = {year:new Date().getFullYear(), month:new Date().getMonth()};
const DOW = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

function stepMonth(delta){
  calState.month += delta;
  if(calState.month < 0){ calState.month = 11; calState.year--; }
  if(calState.month > 11){ calState.month = 0; calState.year++; }
  renderCalendar();
}

// Deadline index built from the FILTERED set, so filters chosen on the list
// carry through to the calendar. Production builds this from all items, which
// makes the two tabs disagree.
function deadlineIndex(){
  const idx = {};
  for(const item of state.filtered){
    if(!item.deadline) continue;
    (idx[item.deadline] = idx[item.deadline] || []).push(item);
  }
  return idx;
}

function renderCalendar(){
  const wide = matchMedia("(min-width:760px)").matches;
  $("#cal-toolbar").querySelectorAll(".cal-nav, .cal-month-label").forEach((el) => { el.hidden = !wide; });
  wide ? renderMonthGrid() : renderAgenda();
}

function renderMonthGrid(){
  const body = $("#cal-body");
  const idx = deadlineIndex();
  const first = new Date(calState.year, calState.month, 1);
  const label = first.toLocaleDateString("en-AU",{month:"long", year:"numeric"});
  $("#cal-month-label").textContent = label;

  const startDow = (first.getDay() + 6) % 7;         // Monday-first
  const daysInMonth = new Date(calState.year, calState.month+1, 0).getDate();
  const todayStr = ymd(new Date());

  let html = '<div class="cal-grid">';
  DOW.forEach((d) => { html += '<div class="cal-dow">' + d + '</div>'; });
  const cells = Math.ceil((startDow + daysInMonth) / 7) * 7;
  for(let i = 0; i < cells; i++){
    const dayNum = i - startDow + 1;
    const inMonth = dayNum >= 1 && dayNum <= daysInMonth;
    const d = new Date(calState.year, calState.month, dayNum);
    const key = ymd(d);
    const events = idx[key] || [];
    html += '<div class="cal-cell' + (inMonth ? "" : " other-month") +
            (key === todayStr ? " today" : "") +
            (events.length ? " has-events" : "") + '" data-date="' + key + '">' +
            '<div class="cal-day-num">' + d.getDate() + '</div>';
    events.slice(0,2).forEach((it) => {
      const cat = CATS.includes(it.category) ? it.category : "Other";
      html += '<span class="cal-dot" style="background:' + CAT_COLOUR[cat] + '">' + esc(it.title) + '</span>';
    });
    if(events.length > 2) html += '<span class="cal-more">+' + (events.length - 2) + ' more</span>';
    html += '</div>';
  }
  html += '</div>';
  body.innerHTML = html;

  body.querySelectorAll(".cal-cell.has-events").forEach((cell) => {
    cell.addEventListener("click", () => openPopup(cell.dataset.date, idx[cell.dataset.date]));
  });
}

function ymd(d){
  return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
}

function renderAgenda(){
  const idx = deadlineIndex();
  const body = $("#cal-body");
  const today = new Date(); today.setHours(0,0,0,0);
  const dates = Object.keys(idx).filter((d) => new Date(d + "T00:00:00") >= today).sort();

  if(!dates.length){
    body.innerHTML = '<div class="empty"><p>No upcoming deadlines match your filters.</p>' +
                     '<p class="empty-sub">Clear a filter to see the full run.</p></div>';
    return;
  }

  let html = '<div class="agenda">';
  dates.forEach((dateStr) => {
    const d = new Date(dateStr + "T00:00:00");
    const cd = countdownLabel(daysLeft(dateStr));
    html += '<div class="agenda-head">' +
      '<span class="agenda-date">' + d.toLocaleDateString("en-AU",{weekday:"short",day:"numeric",month:"short"}) + '</span>' +
      '<span class="count ' + cd.cls + '">' + cd.text + '</span></div>';
    idx[dateStr].forEach((item, i) => {
      const cat = CATS.includes(item.category) ? item.category : "Other";
      html += '<div class="agenda-row" data-date="' + dateStr + '" data-i="' + i + '">' +
        '<span class="cat" style="background:' + CAT_COLOUR[cat] + '">' + cat + '</span>' +
        '<div class="agenda-title">' + esc(item.title) + '</div>' +
        '<div class="source">' + esc(item.source) +
          (item.amount ? ' · <span class="amount">' + esc(item.amount) + '</span>' : "") + '</div>' +
        '<div class="agenda-acts">' +
          (item.link ? '<a class="act primary" href="' + safeLink(item.link) + '" target="_blank" rel="noopener">Open listing</a>' : "") +
          '<a class="act" href="' + buildGoogleCalUrl(item) + '"' + (IS_IOS ? "" : ' target="_blank" rel="noopener"') + '>Google Calendar</a>' +
          '<button class="act" data-ics>Save .ics</button>' +
        '</div></div>';
    });
  });
  html += '</div>';
  body.innerHTML = html;

  body.querySelectorAll("[data-ics]").forEach((btn) => {
    const row = btn.closest(".agenda-row");
    const item = idx[row.dataset.date][Number(row.dataset.i)];
    btn.addEventListener("click", () => downloadSingleIcs(item));
  });
}

function openPopup(dateStr, events){
  const d = new Date(dateStr + "T00:00:00");
  $("#cal-popup-title").textContent = "Closing " +
    d.toLocaleDateString("en-AU",{weekday:"long",day:"numeric",month:"long",year:"numeric"});
  const body = $("#cal-popup-body");
  body.innerHTML = "";
  events.forEach((item) => {
    const cat = CATS.includes(item.category) ? item.category : "Other";
    const div = document.createElement("div");
    div.className = "pop-item";
    div.innerHTML =
      '<h4>' + esc(item.title) + '</h4>' +
      '<p class="source">' + esc(item.source) + ' · <span class="cat" style="background:' + CAT_COLOUR[cat] + '">' + cat + '</span></p>' +
      (item.amount ? '<div class="amount">' + esc(item.amount) + '</div>' : "") +
      (blurb(item) ? '<p class="desc">' + esc(blurb(item)) + '</p>' : "") +
      '<div class="agenda-acts">' +
        (item.link ? '<a class="act primary" href="' + safeLink(item.link) + '" target="_blank" rel="noopener">Open listing</a>' : "") +
        '<a class="act" href="' + buildGoogleCalUrl(item) + '"' + (IS_IOS ? "" : ' target="_blank" rel="noopener"') + '>Google Calendar</a>' +
        '<button class="act" data-ics>Save .ics</button>' +
      '</div>';
    div.querySelector("[data-ics]").addEventListener("click", () => downloadSingleIcs(item));
    body.appendChild(div);
  });
  $("#cal-overlay").hidden = false;
  lockScroll();
}
function closePopup(){ $("#cal-overlay").hidden = true; unlockScroll(); }

/* ── calendar export ──────────────────────────────────────────────────── */
function icsTimestamp(){ return new Date().toISOString().replace(/[-:]/g,"").split(".")[0] + "Z"; }
function icsEscape(s){
  return String(s || "").replace(/\\/g,"\\\\").replace(/;/g,"\\;").replace(/,/g,"\\,").replace(/\n/g,"\\n");
}
function slugify(s){ return String(s).toLowerCase().replace(/[^a-z0-9]+/g,"-").slice(0,50); }

// Manual string build: percent-encoding the slash in dates= makes Google
// Calendar's frontend hang on a loading spinner.
function buildGoogleCalUrl(item){
  const date = String(item.deadline || "").replace(/-/g,"");
  const p = String(item.deadline || "").split("-").map(Number);
  const next = new Date(Date.UTC(p[0], p[1]-1, p[2]+1));
  const nextDay = next.getUTCFullYear() + String(next.getUTCMonth()+1).padStart(2,"0") + String(next.getUTCDate()).padStart(2,"0");
  const details = [item.source, item.category, item.amount, item.link].filter(Boolean).join(" | ");
  const base = IS_IOS ? "comgooglecalendar://calendar/render?action=TEMPLATE"
                      : "https://calendar.google.com/calendar/render?action=TEMPLATE";
  const parts = [
    "text=" + encodeURIComponent("DEADLINE: " + item.title),
    "dates=" + date + "/" + nextDay,
    "details=" + encodeURIComponent(details),
  ];
  if(item.link) parts.push("location=" + encodeURIComponent(item.link));
  return base + "&" + parts.join("&");
}

function buildIcs(item){
  const uid = "opencalls-" + (item.id || Math.random().toString(36).slice(2)) + "@artsgrants.au";
  const date = String(item.deadline).replace(/-/g,"");
  const end = new Date(new Date(item.deadline + "T00:00:00").getTime() + 86400000).toISOString().slice(0,10).replace(/-/g,"");
  const lines = [
    "BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Open Calls//Arts Grants AU//EN",
    "CALSCALE:GREGORIAN","METHOD:PUBLISH","BEGIN:VEVENT",
    "UID:" + uid, "DTSTAMP:" + icsTimestamp(),
    "DTSTART;VALUE=DATE:" + date, "DTEND;VALUE=DATE:" + end,
    "SUMMARY:DEADLINE: " + icsEscape(item.title),
    "DESCRIPTION:" + icsEscape([item.source,item.category,item.amount,item.summary,item.link].filter(Boolean).join(" | ")),
    item.link ? "URL:" + icsEscape(item.link) : null,
    "BEGIN:VALARM","TRIGGER:-P7D","ACTION:DISPLAY",
    "DESCRIPTION:Deadline in 7 days: " + icsEscape(item.title),
    "END:VALARM","END:VEVENT","END:VCALENDAR",
  ].filter((l) => l !== null);
  return lines.join("\r\n");
}

// iOS ignores the download attribute, so navigate to the blob and let the
// system calendar sheet take over.
function downloadSingleIcs(item){
  const blob = new Blob([buildIcs(item)], {type:"text/calendar;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  if(IS_IOS){ window.location.href = url; }
  else{
    const a = document.createElement("a");
    a.href = url; a.download = item.deadline + "-" + slugify(item.title) + ".ics"; a.click();
  }
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// JSZip is ~95KB and only needed if someone taps export, so load it then.
function loadJSZip(){
  if(window.JSZip) return Promise.resolve();
  return new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
    s.onload = res; s.onerror = rej;
    document.head.appendChild(s);
  });
}

async function downloadAllIcs(){
  const withDeadline = state.filtered.filter((i) => i.deadline);
  const btn = $("#cal-download");
  if(!withDeadline.length){ btn.textContent = "Nothing to export yet"; setTimeout(resetBtn, 2200); return; }
  btn.disabled = true; btn.textContent = "Building " + withDeadline.length + " events…";
  try{
    await loadJSZip();
    const zip = new JSZip();
    withDeadline.forEach((item) => {
      zip.file(item.deadline + "-" + slugify(item.title) + ".ics", buildIcs(item));
    });
    const blob = await zip.generateAsync({type:"blob"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "open-calls-deadlines.zip"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }catch(e){
    btn.textContent = "Export failed. Check your connection and try again.";
    setTimeout(resetBtn, 3000); btn.disabled = false; return;
  }
  btn.disabled = false; resetBtn();
}
function resetBtn(){ $("#cal-download").textContent = "Add every deadline to your calendar"; }

/* ── theme ────────────────────────────────────────────────────────────── */
(function theme(){
  const KEY = "oc-theme";
  const root = document.documentElement;
  const btns = document.querySelectorAll(".theme-btn");
  function apply(name){
    if(name && name !== "default") root.setAttribute("data-theme", name);
    else root.removeAttribute("data-theme");
    btns.forEach((b) => b.setAttribute("aria-pressed", (b.dataset.theme || "default") === (name || "default")));
  }
  btns.forEach((b) => b.addEventListener("click", () => {
    const name = b.dataset.theme || "default";
    apply(name);
    try{ localStorage.setItem(KEY, name); }catch(e){}
  }));
  $("#theme-toggle").addEventListener("click", () => {
    const next = root.getAttribute("data-theme") === "bloom" ? "default" : "bloom";
    apply(next);
    try{ localStorage.setItem(KEY, next); }catch(e){}
  });
  let saved = "bloom";
  try{ saved = localStorage.getItem(KEY) || "bloom"; }catch(e){}
  apply(saved);
})();
