/* ============================================================================
 *  LAYOUT ENGINE
 * ----------------------------------------------------------------------------
 *  Turns the flat COURSES list into positioned nodes:
 *    1. Validate edges & detect cycles.
 *    2. Assign each node a `depth` = longest dependency chain (topological rank).
 *       -> depth becomes a horizontal level (a row) in the graph.
 *    3. Order nodes within each level to (a) keep same-field subjects together
 *       and (b) minimise edge crossings, via iterated barycenter sweeps.
 * ==========================================================================*/

const Layout = (() => {

  // Tunable geometry (graph-space pixels).
  const NODE_W = 190;
  const NODE_H = 62;
  const COL_GAP = 46;   // horizontal gap between node centers within a level
  const ROW_GAP = 150;  // vertical gap between levels
  const FIELD_GAP = 120; // extra breathing room inserted between field clusters

  function build(courses, fields) {
    const byId = new Map();
    courses.forEach(c => byId.set(c.id, {
      ...c,
      requires: (c.requires || []).slice(),
      children: [],
      depth: 0,
      x: 0, y: 0,
      w: NODE_W, h: NODE_H,
    }));

    // Drop dangling prerequisite references but warn loudly in the console.
    for (const n of byId.values()) {
      n.requires = n.requires.filter(r => {
        if (!byId.has(r)) {
          console.warn(`[knowledge-map] "${n.id}" requires unknown course "${r}" — ignored.`);
          return false;
        }
        return true;
      });
    }
    // Wire children (reverse edges).
    for (const n of byId.values())
      for (const r of n.requires) byId.get(r).children.push(n.id);

    // ---- Longest-path depth via topological order (Kahn) ------------------
    const indeg = new Map();
    for (const n of byId.values()) indeg.set(n.id, n.requires.length);
    const queue = [];
    for (const n of byId.values()) if (indeg.get(n.id) === 0) queue.push(n.id);

    let processed = 0;
    while (queue.length) {
      const id = queue.shift();
      processed++;
      const n = byId.get(id);
      for (const cid of n.children) {
        const c = byId.get(cid);
        c.depth = Math.max(c.depth, n.depth + 1);
        indeg.set(cid, indeg.get(cid) - 1);
        if (indeg.get(cid) === 0) queue.push(cid);
      }
    }
    if (processed !== byId.size) {
      console.error("[knowledge-map] Dependency cycle detected — some nodes could not be ranked. Check `requires` for a loop.");
    }

    // ---- Group nodes by level, then by field ------------------------------
    // Each field occupies its own fixed horizontal "lane", so a discipline's
    // courses always sit in a vertical band directly beneath its root node,
    // and same-field subjects stay clustered rather than scattered.
    const levels = [];                 // levels[d] = flat array (built at the end)
    const byLevelField = [];           // byLevelField[d] = Map(field -> [nodes])
    for (const n of byId.values()) {
      const d = n.depth;
      if (!byLevelField[d]) byLevelField[d] = new Map();
      const m = byLevelField[d];
      if (!m.has(n.field)) m.set(n.field, []);
      m.get(n.field).push(n);
    }

    const colStride = NODE_W + COL_GAP;
    const fieldOrder = Object.keys(fields);

    // Widest occupancy of each field across all levels → its lane width.
    const maxCount = {};
    for (const m of byLevelField) {
      if (!m) continue;
      for (const [f, arr] of m) maxCount[f] = Math.max(maxCount[f] || 0, arr.length);
    }
    const presentFields = fieldOrder.filter(f => f in maxCount);

    // Lay the lanes left-to-right in a fixed field order, with a gap between.
    const laneWidth = {}, laneStart = {};
    let cursor = 0;
    for (const f of presentFields) {
      laneWidth[f] = Math.max(maxCount[f], 1) * colStride;
      laneStart[f] = cursor;
      cursor += laneWidth[f] + FIELD_GAP;
    }
    const totalWidth = cursor - FIELD_GAP;
    const originShift = -totalWidth / 2;   // center the whole atlas around x = 0

    // Place a field's nodes for one level, centered within that field's lane.
    const placeGroup = (arr, f, d) => {
      const c = arr.length;
      const used = c * colStride - COL_GAP;
      const pad = (laneWidth[f] - used) / 2;
      const baseX = laneStart[f] + originShift + pad;
      for (let i = 0; i < c; i++) {
        arr[i].x = baseX + i * colStride;
        arr[i].y = d * (NODE_H + ROW_GAP);
      }
    };

    // Initial within-lane order: alphabetical, then place.
    for (let d = 0; d < byLevelField.length; d++) {
      const m = byLevelField[d];
      if (!m) continue;
      for (const f of presentFields) {
        const arr = m.get(f);
        if (!arr) continue;
        arr.sort((a, b) => a.title.localeCompare(b.title));
        placeGroup(arr, f, d);
      }
    }

    // ---- Barycenter crossing reduction (within each lane) -----------------
    // Reorder nodes inside a lane by the mean x of their neighbours (prereqs +
    // dependents). Nodes never leave their field lane, so fields stay grouped
    // while edge crossings within a discipline are minimised.
    const centerX = n => n.x + NODE_W / 2;
    const SWEEPS = 10;
    for (let s = 0; s < SWEEPS; s++) {
      for (let d = 0; d < byLevelField.length; d++) {
        const m = byLevelField[d];
        if (!m) continue;
        for (const f of presentFields) {
          const arr = m.get(f);
          if (!arr || arr.length < 2) continue;
          const bc = new Map();
          for (const n of arr) {
            const nbrs = n.requires.concat(n.children);
            if (!nbrs.length) { bc.set(n.id, centerX(n)); continue; }
            let sum = 0;
            for (const id of nbrs) sum += centerX(byId.get(id));
            bc.set(n.id, sum / nbrs.length);
          }
          arr.sort((a, b) =>
            (bc.get(a.id) - bc.get(b.id)) || a.title.localeCompare(b.title));
          placeGroup(arr, f, d);
        }
      }
    }

    // Flatten to per-level arrays (field order preserved) for compatibility.
    for (let d = 0; d < byLevelField.length; d++) {
      const m = byLevelField[d];
      if (!m) { levels[d] = []; continue; }
      const flat = [];
      for (const f of presentFields) if (m.has(f)) flat.push(...m.get(f));
      levels[d] = flat;
    }

    // ---- Build a flat edge list for the renderer --------------------------
    const nodes = [...byId.values()];
    const edges = [];
    for (const n of nodes)
      for (const r of n.requires)
        edges.push({ from: r, to: n.id }); // prereq -> course

    // Bounds (graph space) for fit-to-screen and the minimap.
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x + n.w);
      maxY = Math.max(maxY, n.y + n.h);
    }
    const bounds = { minX, minY, maxX, maxY, w: maxX - minX, h: maxY - minY };

    return { nodes, edges, byId, levels, bounds, dims: { NODE_W, NODE_H } };
  }

  return { build };
})();

window.Layout = Layout;
