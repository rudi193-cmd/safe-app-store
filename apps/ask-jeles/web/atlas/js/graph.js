/* ============================================================================
 *  GRAPH RENDERER
 * ----------------------------------------------------------------------------
 *  Renders the laid-out graph with:
 *    - a single CSS-transformed world layer for pan/zoom,
 *    - DOM nodes that are VIRTUALIZED (only those near the viewport exist),
 *    - constellation edges drawn on a canvas with off-screen culling,
 *    - a minimap for whole-atlas overview.
 * ==========================================================================*/

const Graph = (() => {
  const MIN_SCALE = 0.04;
  const MAX_SCALE = 2.2;

  function create(opts) {
    const {
      root,        // container element
      model,       // Layout.build(...) result
      fields,      // FIELDS map
      state,       // completion state (Set of completed ids) manager
      onSelect,    // callback(node|null) when a node opens/closes
    } = opts;

    // ---- DOM scaffold -----------------------------------------------------
    root.classList.add("km-viewport");
    const canvas = document.createElement("canvas");
    canvas.className = "km-edges";
    const world = document.createElement("div");
    world.className = "km-world";
    root.append(canvas, world);

    const ctx = canvas.getContext("2d");

    // ---- View transform ---------------------------------------------------
    // screen = graph * scale + offset
    let scale = 1, offsetX = 0, offsetY = 0;
    let dpr = window.devicePixelRatio || 1;

    // ---- Node element pool (virtualization) -------------------------------
    const elements = new Map(); // id -> element (only visible / expanded ones)
    let expandedId = null;
    let highlightSet = null;    // Set of ids to highlight (prereq chain), or null
    let visibleSet = null;      // Set of ids to show (field filter), or null = all
    let currentFilter = null;   // active field key, or null

    const { nodes, edges, byId, bounds } = model;

    // Quick lookups.
    const nodeArr = nodes;

    // ---------------------------------------------------------------------
    //  Transform helpers
    // ---------------------------------------------------------------------
    function applyWorldTransform() {
      world.style.transform =
        `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;
    }

    function clampScale(s) { return Math.max(MIN_SCALE, Math.min(MAX_SCALE, s)); }

    function screenToGraph(sx, sy) {
      return { x: (sx - offsetX) / scale, y: (sy - offsetY) / scale };
    }

    // ---------------------------------------------------------------------
    //  Rendering pipeline (throttled via rAF)
    // ---------------------------------------------------------------------
    let rafPending = false;
    function scheduleRender() {
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(() => { rafPending = false; render(); });
    }

    function visibleGraphRect(margin = 240) {
      const w = root.clientWidth, h = root.clientHeight;
      const tl = screenToGraph(-margin, -margin);
      const br = screenToGraph(w + margin, h + margin);
      return { x0: tl.x, y0: tl.y, x1: br.x, y1: br.y };
    }

    function render() {
      applyWorldTransform();
      renderNodes();
      renderEdges();
      renderMinimapViewport();
    }

    // ---- Nodes ------------------------------------------------------------
    function renderNodes() {
      const vr = visibleGraphRect();
      const needed = new Set();

      // When zoomed far out, individual cards are illegible; we still render
      // them (as tiny colored stars via CSS) but skip building expanded cards.
      for (const n of nodeArr) {
        if (visibleSet && !visibleSet.has(n.id)) continue;   // field filter
        if (n.x + n.w < vr.x0 || n.x > vr.x1 || n.y + n.h < vr.y0 || n.y > vr.y1)
          continue;
        needed.add(n.id);
        if (!elements.has(n.id)) mountNode(n);
      }
      // Always keep the expanded node mounted even if scrolled slightly away.
      if (expandedId && (!visibleSet || visibleSet.has(expandedId))) needed.add(expandedId);

      // Unmount nodes no longer needed.
      for (const [id, el] of elements) {
        if (!needed.has(id)) { el.remove(); elements.delete(id); }
      }
      // Refresh dynamic classes (completion / highlight) on mounted nodes.
      for (const [id, el] of elements) styleNode(byId.get(id), el);
    }

    function nodeStatus(n) {
      if (state.isComplete(n.id)) return "complete";
      // available = all prereqs complete (or none); else locked.
      const ready = n.requires.every(r => state.isComplete(r));
      return ready ? "available" : "locked";
    }

    function styleNode(n, el) {
      const status = nodeStatus(n);
      el.dataset.status = status;
      const isExp = n.id === expandedId;
      if (isExp && el._ensureBody) el._ensureBody(); // build body lazily on open
      el.classList.toggle("km-expanded", isExp);
      if (highlightSet) {
        el.classList.toggle("km-dim", !highlightSet.has(n.id));
        el.classList.toggle("km-hl", highlightSet.has(n.id));
      } else {
        el.classList.remove("km-dim", "km-hl");
      }
    }

    function mountNode(n) {
      const el = document.createElement("div");
      el.className = "km-node";
      el.style.left = n.x + "px";
      el.style.top = n.y + "px";
      el.style.width = n.w + "px";
      el.style.setProperty("--field-hue", (fields[n.field]?.hue ?? 44));

      // Collapsed header (always present): completion star, title, field badge.
      const f = fields[n.field] || {};
      const head = document.createElement("div");
      head.className = "km-node-head";
      head.innerHTML = `
        <button class="km-check" title="Mark complete" aria-label="Toggle completion"></button>
        <span class="km-title">${escapeHtml(n.title)}</span>
        <span class="km-ribbon" title="${escapeAttr(f.label ?? n.field)}">${escapeHtml(f.abbr ?? n.field)}</span>`;
      el.appendChild(head);

      // Expanded body is built lazily on first open.
      let body = null;
      const ensureBody = () => {
        if (body) return body;
        body = buildBody(n);
        el.appendChild(body);
        return body;
      };
      el._ensureBody = ensureBody; // reachable when opened via search / prereq link

      // Interactions.
      head.querySelector(".km-check").addEventListener("click", (e) => {
        e.stopPropagation();
        const res = state.toggle(n.id);
        if (res && res.ok === false) {
          // Prerequisites not met — refuse and shake the card for feedback.
          el.classList.remove("km-deny");
          void el.offsetWidth;            // restart the animation
          el.classList.add("km-deny");
        }
        scheduleRender();
      });
      el.addEventListener("click", (e) => {
        if (e.target.closest("a")) return; // let links work
        toggleExpand(n, el, ensureBody);
      });

      if (n.id === expandedId) { ensureBody(); }
      styleNode(n, el);
      world.appendChild(el);
      elements.set(n.id, el);
    }

    function toggleExpand(n, el, ensureBody) {
      if (expandedId === n.id) {
        expandedId = null;
        onSelect && onSelect(null);
      } else {
        expandedId = n.id;
        ensureBody();
        onSelect && onSelect(n);
      }
      // Restyle all mounted (previous expanded needs to collapse).
      for (const [id, e] of elements) styleNode(byId.get(id), e);
      scheduleRender();
    }

    function buildBody(n) {
      const body = document.createElement("div");
      body.className = "km-node-body";

      // Full field label chip at the top of the details.
      const f = fields[n.field] || {};
      const fieldLine = document.createElement("div");
      fieldLine.className = "km-field-full";
      fieldLine.innerHTML = `<span class="km-field-swatch"></span>${escapeHtml(f.label ?? n.field)}`;
      body.appendChild(fieldLine);

      const desc = document.createElement("p");
      desc.className = "km-desc";
      desc.textContent = n.desc || "";
      body.appendChild(desc);

      // Requirements (clickable — pan to prereq).
      const reqWrap = document.createElement("div");
      reqWrap.className = "km-section";
      const reqTitle = n.requires.length
        ? `<h4>Requires</h4>` : `<h4>Requires</h4><p class="km-none">No prerequisites — a starting point.</p>`;
      reqWrap.innerHTML = reqTitle;
      if (n.requires.length) {
        const ul = document.createElement("ul");
        ul.className = "km-reqs";
        for (const r of n.requires) {
          const rn = byId.get(r);
          const li = document.createElement("li");
          const a = document.createElement("a");
          a.href = "#";
          a.className = "km-req";
          a.dataset.goto = r;
          a.textContent = rn ? rn.title : r;
          a.addEventListener("click", (e) => {
            e.preventDefault(); e.stopPropagation();
            api.focusNode(r, true);
          });
          li.appendChild(a);
          ul.appendChild(li);
        }
        reqWrap.appendChild(ul);
      }
      body.appendChild(reqWrap);

      // Collapsible topics.
      const topicsWrap = document.createElement("div");
      topicsWrap.className = "km-section";
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.innerHTML = `Topics covered <span class="km-count">${(n.topics || []).length}</span>`;
      details.appendChild(summary);
      const tl = document.createElement("ul");
      tl.className = "km-topics";
      for (const t of (n.topics || [])) {
        const li = document.createElement("li");
        li.textContent = t;
        tl.appendChild(li);
      }
      details.appendChild(tl);
      details.addEventListener("click", e => e.stopPropagation());
      topicsWrap.appendChild(details);
      body.appendChild(topicsWrap);

      // Resources.
      body.appendChild(resourceBlock("Free resources", n.free, "free"));
      body.appendChild(resourceBlock("Paid resources", n.paid, "paid"));

      return body;
    }

    function resourceBlock(title, list, cls) {
      const wrap = document.createElement("div");
      wrap.className = "km-section";
      const items = list || [];
      wrap.innerHTML = `<h4 class="km-res-h ${cls}">${title}</h4>`;
      if (!items.length) {
        const p = document.createElement("p");
        p.className = "km-none";
        p.textContent = "—";
        wrap.appendChild(p);
        return wrap;
      }
      const ul = document.createElement("ul");
      ul.className = "km-resources";
      for (const r of items) {
        const li = document.createElement("li");
        const label = `${escapeHtml(r.t)}${r.by ? ` <span class="km-by">— ${escapeHtml(r.by)}</span>` : ""}`;
        if (r.url) {
          li.innerHTML = `<a href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${label}</a>`;
        } else {
          li.innerHTML = label;
        }
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
      return wrap;
    }

    // ---- Edges (canvas) ---------------------------------------------------
    function resizeCanvas() {
      dpr = window.devicePixelRatio || 1;
      const w = root.clientWidth, h = root.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = w + "px";
      canvas.style.height = h + "px";
    }

    function renderEdges() {
      const w = root.clientWidth, h = root.clientHeight;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      // Cull: skip edges whose bounding box is off-screen.
      const pad = 60;
      const showLabelsThreshold = 0.18;
      const thin = scale < 0.4;

      ctx.lineWidth = thin ? 0.6 : 1;
      for (const e of edges) {
        const a = byId.get(e.from), b = byId.get(e.to);
        if (!a || !b) continue;
        if (visibleSet && (!visibleSet.has(a.id) || !visibleSet.has(b.id))) continue;
        // endpoints in screen space (bottom-center of prereq -> top-center of course)
        const ax = (a.x + a.w / 2) * scale + offsetX;
        const ay = (a.y + a.h) * scale + offsetY;
        const bx = (b.x + b.w / 2) * scale + offsetX;
        const by = (b.y) * scale + offsetY;

        const minx = Math.min(ax, bx), maxx = Math.max(ax, bx);
        const miny = Math.min(ay, by), maxy = Math.max(ay, by);
        if (maxx < -pad || minx > w + pad || maxy < -pad || miny > h + pad) continue;

        const active = highlightSet && (highlightSet.has(a.id) && highlightSet.has(b.id));
        const dim = highlightSet && !active;

        ctx.strokeStyle = active
          ? "rgba(214,178,94,0.9)"
          : dim ? "rgba(120,104,74,0.10)" : "rgba(150,132,92,0.34)";
        ctx.lineWidth = active ? (thin ? 1.2 : 1.8) : (thin ? 0.6 : 1);

        // Curved constellation line (vertical S-curve).
        const midy = (ay + by) / 2;
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.bezierCurveTo(ax, midy, bx, midy, bx, by);
        ctx.stroke();

        // Star node at the child end when reasonably zoomed in.
        if (scale > showLabelsThreshold) {
          ctx.fillStyle = active ? "rgba(230,200,120,0.95)" : "rgba(150,132,92,0.45)";
          ctx.beginPath();
          ctx.arc(bx, by, active ? 2.4 : 1.6, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // ---- Minimap ----------------------------------------------------------
    let mini = null, miniCtx = null, miniRect = null;
    function attachMinimap(canvasEl) {
      mini = canvasEl;
      miniCtx = mini.getContext("2d");
      mini.addEventListener("click", (e) => {
        const r = mini.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width;
        const py = (e.clientY - r.top) / r.height;
        const gx = bounds.minX + px * bounds.w;
        const gy = bounds.minY + py * bounds.h;
        api.centerOn(gx, gy);
      });
      drawMinimapBase();
    }

    function drawMinimapBase() {
      if (!mini) return;
      const w = mini.width, h = mini.height;
      miniCtx.clearRect(0, 0, w, h);
      const sx = w / bounds.w, sy = h / bounds.h;
      const s = Math.min(sx, sy) * 0.94;
      const ox = (w - bounds.w * s) / 2 - bounds.minX * s;
      const oy = (h - bounds.h * s) / 2 - bounds.minY * s;
      miniRect = { s, ox, oy };
      // edges faint
      miniCtx.strokeStyle = "rgba(150,132,92,0.25)";
      miniCtx.lineWidth = 0.4;
      for (const e of edges) {
        const a = byId.get(e.from), b = byId.get(e.to);
        if (visibleSet && (!visibleSet.has(a.id) || !visibleSet.has(b.id))) continue;
        miniCtx.beginPath();
        miniCtx.moveTo((a.x + a.w / 2) * s + ox, (a.y + a.h) * s + oy);
        miniCtx.lineTo((b.x + b.w / 2) * s + ox, b.y * s + oy);
        miniCtx.stroke();
      }
      // nodes as dots colored by status
      for (const n of nodeArr) {
        if (visibleSet && !visibleSet.has(n.id)) continue;
        const st = nodeStatus(n);
        miniCtx.fillStyle = st === "complete" ? "rgba(214,178,94,0.95)"
          : st === "available" ? "rgba(196,182,150,0.8)" : "rgba(120,110,88,0.5)";
        miniCtx.beginPath();
        miniCtx.arc((n.x + n.w / 2) * s + ox, (n.y + n.h / 2) * s + oy, 1.5, 0, Math.PI * 2);
        miniCtx.fill();
      }
    }

    function renderMinimapViewport() {
      if (!mini || !miniRect) return;
      // Redraw base occasionally is heavy; we overlay viewport on a cached base.
      // Simpler: redraw base + rect each frame (cheap for a few hundred dots).
      drawMinimapBase();
      const { s, ox, oy } = miniRect;
      const vr = visibleGraphRect(0);
      miniCtx.strokeStyle = "rgba(232,206,140,0.9)";
      miniCtx.lineWidth = 1;
      miniCtx.strokeRect(vr.x0 * s + ox, vr.y0 * s + oy,
        (vr.x1 - vr.x0) * s, (vr.y1 - vr.y0) * s);
    }

    // ---------------------------------------------------------------------
    //  Interaction: pan & zoom
    // ---------------------------------------------------------------------
    let dragging = false, dragMoved = false, lastX = 0, lastY = 0;
    const pointers = new Map();  // active pointerId -> {x, y} in client px
    let pinchPrev = null;        // { dist, cx, cy } (cx/cy root-relative), or null

    // Midpoint & finger distance of the first two active pointers.
    function pinchState() {
      const [a, b] = [...pointers.values()];
      const r = root.getBoundingClientRect();
      return {
        dist: Math.hypot(a.x - b.x, a.y - b.y),
        cx: (a.x + b.x) / 2 - r.left,
        cy: (a.y + b.y) / 2 - r.top,
      };
    }

    root.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".km-node")) return; // let node handle clicks
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      try { root.setPointerCapture(e.pointerId); } catch {}
      dragMoved = false;
      if (pointers.size === 1) {
        dragging = true;
        lastX = e.clientX; lastY = e.clientY;
        root.classList.add("km-grabbing");
      } else if (pointers.size === 2) {
        dragging = false;            // second finger down → start pinch
        pinchPrev = pinchState();
      }
    });

    root.addEventListener("pointermove", (e) => {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (pointers.size >= 2) {
        // Two-finger pinch-zoom, anchored on the moving midpoint (pans too).
        const cur = pinchState();
        if (pinchPrev && pinchPrev.dist > 0) {
          const factor = cur.dist / pinchPrev.dist;
          const gx = (pinchPrev.cx - offsetX) / scale;   // graph pt under old midpoint
          const gy = (pinchPrev.cy - offsetY) / scale;
          const next = clampScale(scale * factor);
          offsetX = cur.cx - gx * next;
          offsetY = cur.cy - gy * next;
          scale = next;
          dragMoved = true;
          scheduleRender();
        }
        pinchPrev = cur;
      } else if (dragging) {
        // Single-finger / mouse pan.
        const dx = e.clientX - lastX, dy = e.clientY - lastY;
        if (Math.abs(dx) + Math.abs(dy) > 2) dragMoved = true;
        offsetX += dx; offsetY += dy;
        lastX = e.clientX; lastY = e.clientY;
        scheduleRender();
      }
    });

    const endPointer = (e) => {
      if (!pointers.has(e.pointerId)) return;
      pointers.delete(e.pointerId);
      try { root.releasePointerCapture(e.pointerId); } catch {}
      if (pointers.size >= 2) {
        pinchPrev = pinchState();
      } else if (pointers.size === 1) {
        // One finger remains → resume panning from it (no jump).
        const p = [...pointers.values()][0];
        lastX = p.x; lastY = p.y;
        dragging = true;
        pinchPrev = null;
      } else {
        dragging = false;
        pinchPrev = null;
        root.classList.remove("km-grabbing");
      }
    };
    root.addEventListener("pointerup", endPointer);
    root.addEventListener("pointercancel", endPointer);

    // Clicking empty space clears highlight & closes expansion.
    root.addEventListener("click", (e) => {
      if (dragMoved) return;
      if (e.target === root || e.target === canvas) {
        if (expandedId) { expandedId = null; onSelect && onSelect(null); }
        highlightSet = null;
        for (const [id, el] of elements) styleNode(byId.get(id), el);
        scheduleRender();
      }
    });

    root.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = root.getBoundingClientRect();
      const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
      const g = screenToGraph(sx, sy);
      const factor = Math.exp(-e.deltaY * 0.0016);
      const next = clampScale(scale * factor);
      // keep cursor anchored
      offsetX = sx - g.x * next;
      offsetY = sy - g.y * next;
      scale = next;
      scheduleRender();
    }, { passive: false });

    // ---------------------------------------------------------------------
    //  Public API
    // ---------------------------------------------------------------------
    const api = {
      render, scheduleRender,

      zoomBy(factor, cx, cy) {
        const rect = root.getBoundingClientRect();
        const sx = cx ?? rect.width / 2, sy = cy ?? rect.height / 2;
        const g = screenToGraph(sx, sy);
        const next = clampScale(scale * factor);
        offsetX = sx - g.x * next;
        offsetY = sy - g.y * next;
        scale = next;
        scheduleRender();
      },

      fit(pad = 80) {
        const w = root.clientWidth, h = root.clientHeight;
        const b = activeBounds();                 // whole graph, or the filtered subset
        const s = clampScale(Math.min(
          (w - pad * 2) / b.w,
          (h - pad * 2) / b.h));
        scale = s;
        offsetX = (w - b.w * s) / 2 - b.minX * s;
        offsetY = (h - b.h * s) / 2 - b.minY * s;
        scheduleRender();
      },

      // Field filter: null = show everything; a field key = show that field's
      // courses PLUS their full prerequisite chains (across fields), hide the rest.
      setFilter(fieldKey) {
        currentFilter = fieldKey || null;
        if (!currentFilter) {
          visibleSet = null;
        } else {
          const set = new Set();
          for (const n of nodeArr) {
            if (n.field !== currentFilter) continue;
            for (const id of ancestorsOf(n.id)) set.add(id); // node + its prereqs
          }
          visibleSet = set;
          if (expandedId && !visibleSet.has(expandedId)) {
            expandedId = null; onSelect && onSelect(null);
          }
        }
        highlightSet = null;
        // Drop any mounted nodes that are now hidden.
        for (const [id, el] of elements)
          if (visibleSet && !visibleSet.has(id)) { el.remove(); elements.delete(id); }
        api.fit();
      },
      getFilter() { return currentFilter; },

      centerOn(gx, gy, targetScale) {
        const w = root.clientWidth, h = root.clientHeight;
        if (targetScale) scale = clampScale(targetScale);
        offsetX = w / 2 - gx * scale;
        offsetY = h / 2 - gy * scale;
        scheduleRender();
      },

      // Pan (and optionally open) a node, highlighting its prerequisite chain.
      focusNode(id, open) {
        const n = byId.get(id);
        if (!n) return;
        const target = Math.max(scale, 0.7);
        api.centerOn(n.x + n.w / 2, n.y + n.h / 2, target);
        highlightSet = ancestorsOf(id);
        if (open) {
          expandedId = id;
          onSelect && onSelect(n);
        }
        scheduleRender();
        // Ensure the node mounts, then style.
        requestAnimationFrame(() => {
          const el = elements.get(id);
          if (el) { if (open) { /* body built on demand via click path */ }
            styleNode(n, el); }
        });
      },

      setHighlight(set) {
        highlightSet = set;
        for (const [id, el] of elements) styleNode(byId.get(id), el);
        scheduleRender();
      },

      clearHighlight() { api.setHighlight(null); },

      getScale() { return scale; },
      attachMinimap,
      resize() { resizeCanvas(); scheduleRender(); },

      // Search: return nodes whose title matches (case-insensitive).
      search(q) {
        q = q.trim().toLowerCase();
        if (!q) return [];
        return nodeArr
          .filter(n => n.title.toLowerCase().includes(q))
          .slice(0, 12);
      },
    };

    // Compute the ancestor set (all transitive prerequisites) + the node.
    function ancestorsOf(id) {
      const seen = new Set([id]);
      const stack = [id];
      while (stack.length) {
        const cur = byId.get(stack.pop());
        for (const r of cur.requires) if (!seen.has(r)) { seen.add(r); stack.push(r); }
      }
      return seen;
    }

    // Bounding box to fit: the whole graph, or just the filtered subset.
    function activeBounds() {
      if (!visibleSet) return bounds;
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const n of nodeArr) {
        if (!visibleSet.has(n.id)) continue;
        minX = Math.min(minX, n.x);       minY = Math.min(minY, n.y);
        maxX = Math.max(maxX, n.x + n.w); maxY = Math.max(maxY, n.y + n.h);
      }
      if (minX === Infinity) return bounds;
      return { minX, minY, maxX, maxY, w: maxX - minX, h: maxY - minY };
    }

    // ---- init -------------------------------------------------------------
    resizeCanvas();
    window.addEventListener("resize", () => api.resize());
    api.fit();

    return api;
  }

  // ---- tiny helpers -------------------------------------------------------
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function escapeAttr(s) { return escapeHtml(s); }

  return { create };
})();

window.Graph = Graph;
