/* ============================================================================
 *  APP BOOTSTRAP
 *  Wires the data -> layout -> renderer, plus completion tracking (localStorage),
 *  the toolbar, search, progress meter and legend.
 * ==========================================================================*/

(function () {
  const { FIELDS, COURSES } = window.KNOWLEDGE_MAP;

  // ---- Completion state (persisted) -------------------------------------
  const STORAGE_KEY = "knowledge-map.completed.v1";
  const completed = new Set(load());

  function load() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); }
    catch { return []; }
  }
  function save() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...completed])); }
    catch {}
  }

  // ---- Build layout (needed by the state's prerequisite checks) ----------
  const model = window.Layout.build(COURSES, FIELDS);

  // A course is "ready" when every prerequisite is already completed.
  function isReady(id) {
    const n = model.byId.get(id);
    return n ? n.requires.every(r => completed.has(r)) : false;
  }

  // Un-completing a course also un-completes anything that (transitively)
  // depends on it, so a completed course always has all its prereqs completed.
  function cascadeIncomplete(id) {
    const stack = [id], removed = [];
    while (stack.length) {
      const cur = stack.pop();
      if (completed.has(cur)) { completed.delete(cur); removed.push(cur); }
      const n = model.byId.get(cur);
      if (n) for (const childId of n.children)
        if (completed.has(childId)) stack.push(childId);
    }
    return removed;
  }

  const state = {
    isComplete: id => completed.has(id),
    isReady,
    // Returns { ok, reason?, cascaded? } so the UI can give feedback.
    toggle(id) {
      if (completed.has(id)) {
        const removed = cascadeIncomplete(id);
        save(); updateProgress();
        return { ok: true, cascaded: removed.length - 1 };
      }
      if (!isReady(id)) return { ok: false, reason: "locked" };
      completed.add(id);
      save(); updateProgress();
      return { ok: true };
    },
    reset() { completed.clear(); save(); updateProgress(); },
  };

  // ---- Renderer ----------------------------------------------------------
  const viewport = document.getElementById("viewport");
  const graph = window.Graph.create({
    root: viewport,
    model,
    fields: FIELDS,
    state,
    onSelect: (node) => {
      if (node) graph.setHighlight(ancestors(node.id));
      // when closing (node null) leave highlight as-is; empty-space click clears it
    },
  });

  function ancestors(id) {
    const seen = new Set([id]);
    const stack = [id];
    const byId = model.byId;
    while (stack.length) {
      const cur = byId.get(stack.pop());
      for (const r of cur.requires) if (!seen.has(r)) { seen.add(r); stack.push(r); }
    }
    return seen;
  }

  // ---- Toolbar buttons ---------------------------------------------------
  const $ = sel => document.querySelector(sel);
  $("#zoom-in").addEventListener("click", () => graph.zoomBy(1.3));
  $("#zoom-out").addEventListener("click", () => graph.zoomBy(1 / 1.3));
  $("#zoom-fit").addEventListener("click", () => { graph.clearHighlight(); graph.fit(); });
  $("#reset-progress").addEventListener("click", () => {
    if (confirm("Clear all completion progress? This cannot be undone.")) {
      state.reset(); graph.scheduleRender();
    }
  });

  // ---- Field filter ------------------------------------------------------
  // "All fields" shows the big picture; picking a field shows only that field's
  // courses plus their full prerequisite chains. Options are grouped by family.
  const filterSelect = $("#field-filter");
  {
    const fams = window.KNOWLEDGE_MAP.FAMILIES || [];
    let html = `<option value="">✦ All fields</option>`;
    for (const fam of fams) {
      const fields = Object.entries(FIELDS).filter(([, f]) => f.family === fam.key);
      if (!fields.length) continue;
      html += `<optgroup label="${fam.label}">`
        + fields.map(([k, f]) => `<option value="${k}">${f.label}</option>`).join("")
        + `</optgroup>`;
    }
    filterSelect.innerHTML = html;
  }
  function applyFilter(fieldKey) {
    filterSelect.value = fieldKey || "";
    filterSelect.classList.toggle("km-active", !!fieldKey);
    graph.setFilter(fieldKey || null);
  }
  filterSelect.addEventListener("change", () => applyFilter(filterSelect.value || null));

  // Discover: jump to a random course whose prerequisites are all satisfied.
  $("#random-course").addEventListener("click", () => {
    const ready = COURSES.filter(c => !completed.has(c.id) && isReady(c.id));
    if (!ready.length) {
      const anyLeft = COURSES.some(c => !completed.has(c.id));
      toast(anyLeft
        ? "No courses are unlocked yet — complete a starting subject first."
        : "You've completed the entire atlas. Bravo! ✦");
      return;
    }
    const pick = ready[Math.floor(Math.random() * ready.length)];
    if (graph.getFilter()) applyFilter(null);  // jump out of a field filter
    graph.focusNode(pick.id, true);
    toast(`Suggested: ${pick.title}`);
  });

  // ---- Transient toast ---------------------------------------------------
  const toastEl = $("#toast");
  let toastTimer = null;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2600);
  }

  // ---- Search ------------------------------------------------------------
  const searchInput = $("#search");
  const results = $("#search-results");
  let activeIdx = -1, current = [];

  function renderResults(list) {
    current = list; activeIdx = -1;
    if (!list.length) { results.hidden = true; results.innerHTML = ""; return; }
    results.hidden = false;
    results.innerHTML = list.map((n, i) =>
      `<li data-id="${n.id}" data-i="${i}">
         <span class="dot" style="--field-hue:${FIELDS[n.field]?.hue ?? 44}"></span>
         <span class="r-title">${n.title}</span>
         <span class="r-field">${FIELDS[n.field]?.label ?? n.field}</span>
       </li>`).join("");
  }

  function goTo(id) {
    if (graph.getFilter()) applyFilter(null);  // search jumps across the whole atlas
    graph.focusNode(id, true);
    searchInput.value = "";
    results.hidden = true;
  }

  searchInput.addEventListener("input", () => {
    renderResults(graph.search(searchInput.value));
  });
  searchInput.addEventListener("keydown", (e) => {
    if (results.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); activeIdx = Math.min(activeIdx + 1, current.length - 1); markActive(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); activeIdx = Math.max(activeIdx - 1, 0); markActive(); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const pick = current[activeIdx >= 0 ? activeIdx : 0];
      if (pick) goTo(pick.id);
    } else if (e.key === "Escape") { results.hidden = true; }
  });
  function markActive() {
    [...results.children].forEach((li, i) =>
      li.classList.toggle("active", i === activeIdx));
  }
  results.addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (li) goTo(li.dataset.id);
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".km-search")) results.hidden = true;
  });

  // ---- Progress meter ----------------------------------------------------
  const progressText = $("#progress-text");
  const progressBar = $("#progress-bar");
  function updateProgress() {
    const total = COURSES.length;
    const done = completed.size;
    const pct = total ? Math.round((done / total) * 100) : 0;
    progressText.textContent = `${done} / ${total} completed`;
    progressBar.style.width = pct + "%";
  }
  updateProgress();

  // ---- Legend / field key (grouped into family sections) -----------------
  const legend = $("#field-legend");
  const FAMILIES = window.KNOWLEDGE_MAP.FAMILIES ||
    [{ key: null, label: "" }];
  legend.innerHTML = FAMILIES.map(fam => {
    const items = Object.entries(FIELDS)
      .filter(([, f]) => f.family === fam.key)
      .map(([, f]) =>
        `<span class="km-legend-item"><span class="swatch" style="--field-hue:${f.hue}"></span>${f.label}</span>`)
      .join("");
    if (!items) return "";
    return `<div class="km-legend-group">
        <div class="km-legend-group-title">${fam.label}</div>
        <div class="km-legend-items">${items}</div>
      </div>`;
  }).join("");

  // Collapsible legend (remembers its state).
  const legendEl = $("#legend");
  const legendToggle = $("#legend-toggle");
  const LEGEND_KEY = "knowledge-map.legend.collapsed";
  function setLegendCollapsed(c) {
    legendEl.classList.toggle("collapsed", c);
    legendToggle.setAttribute("aria-expanded", String(!c));
    legendToggle.title = c ? "Expand legend" : "Collapse legend";
    try { localStorage.setItem(LEGEND_KEY, c ? "1" : "0"); } catch {}
  }
  setLegendCollapsed(localStorage.getItem(LEGEND_KEY) === "1");
  legendToggle.addEventListener("click", () =>
    setLegendCollapsed(!legendEl.classList.contains("collapsed")));

  // ---- Minimap -----------------------------------------------------------
  graph.attachMinimap($("#minimap"));

  // ---- Keyboard shortcuts ------------------------------------------------
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT") return;
    if (e.key === "+" || e.key === "=") graph.zoomBy(1.3);
    else if (e.key === "-" || e.key === "_") graph.zoomBy(1 / 1.3);
    else if (e.key === "0" || e.key === "f") { graph.clearHighlight(); graph.fit(); }
    else if (e.key === "/") { e.preventDefault(); searchInput.focus(); }
  });

  // Initial paint.
  graph.scheduleRender();

  // ── Jeles bridge (additive; safe if unused) ────────────────────────────
  // Lets the optional companion js/jeles-progress.js seed completion from the
  // user's local Ask Jeles learning history. Ships no data on its own; the
  // upstream engine is otherwise untouched.
  window.KnowledgeMap = {
    getCompleted: () => [...completed],
    hasCourse: (id) => model.byId.has(id),
    // Union known ids into the completed set (prerequisite closure is done by
    // the generator). Unknown ids are ignored. Returns the count newly added.
    applyCompleted(ids) {
      let added = 0;
      for (const id of ids || []) {
        if (model.byId.has(id) && !completed.has(id)) { completed.add(id); added++; }
      }
      if (added) { save(); updateProgress(); graph.scheduleRender(); }
      return added;
    },
    toast: (msg) => toast(msg),
  };

  console.log(`[knowledge-map] ${COURSES.length} courses across ${model.levels.length} levels loaded.`);
})();
