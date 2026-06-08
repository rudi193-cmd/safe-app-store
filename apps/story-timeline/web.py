"""
web.py — stdlib HTTP server + Canvas force-graph UI for story-timeline v2.

Endpoints:
  GET /              → HTML page with inline Canvas force-directed graph
  GET /api/nodes     → JSON list of all nodes
  GET /api/edges     → JSON list of all edges (from Willow)
  GET /api/node/{id} → JSON single node
  Everything else    → 404
"""
import json
import socketserver
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import timeline_db
import willow_edges

_USER_UUID: Optional[str] = None

# ---------------------------------------------------------------------------
# HTML template — Canvas force-directed graph, inline JS, no external deps
# ---------------------------------------------------------------------------
_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Story Timeline</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { display: flex; height: 100vh; font-family: sans-serif; background: #1a1a2e; color: #e0e0e0; }
#sidebar {
  width: 220px; min-width: 180px; background: #16213e; padding: 12px;
  overflow-y: auto; display: flex; flex-direction: column; gap: 8px;
}
#sidebar h2 { font-size: 14px; color: #a8d8ea; text-transform: uppercase; letter-spacing: 1px; }
#filter { width: 100%; padding: 4px 6px; background: #0f3460; border: 1px solid #444; color: #e0e0e0; border-radius: 4px; font-size: 12px; }
#node-list { list-style: none; overflow-y: auto; flex: 1; }
#node-list li {
  padding: 5px 8px; cursor: pointer; border-radius: 4px; font-size: 12px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
#node-list li:hover { background: #0f3460; }
#node-list li.selected { background: #e94560; color: #fff; }
#graph-area { flex: 1; position: relative; }
canvas { display: block; width: 100%; height: 100%; }
#detail {
  width: 260px; min-width: 200px; background: #16213e; padding: 12px;
  overflow-y: auto; display: none; flex-direction: column; gap: 8px;
}
#detail.visible { display: flex; }
#detail h2 { font-size: 14px; color: #a8d8ea; text-transform: uppercase; letter-spacing: 1px; }
#detail-type { font-size: 11px; color: #888; }
#detail-fields, #detail-edges { font-size: 12px; }
#detail-fields dt { color: #a8d8ea; margin-top: 6px; }
#detail-fields dd { color: #e0e0e0; margin-left: 8px; }
#detail-edges ul { list-style: none; }
#detail-edges li { padding: 3px 0; border-bottom: 1px solid #2a2a4a; }
</style>
</head>
<body>
<div id="sidebar">
  <h2>Nodes</h2>
  <select id="filter"><option value="">All types</option></select>
  <ul id="node-list"></ul>
</div>
<div id="graph-area">
  <canvas id="graph"></canvas>
</div>
<div id="detail">
  <h2 id="detail-name">—</h2>
  <div id="detail-type"></div>
  <dl id="detail-fields"></dl>
  <div id="detail-edges"><strong>Edges</strong><ul id="edge-list"></ul></div>
</div>

<script>
const canvas = document.getElementById('graph');
const ctx = canvas.getContext('2d');
let nodes = [], edges = [], nodeMap = {};
let sim = { running: true };
let selected = null;
const TYPE_COLORS = {};
const PALETTE = ['#e94560','#a8d8ea','#f7d08a','#b8f0b8','#d4a5f5','#f0b8d4','#a5d4f5'];

function typeColor(t) {
  if (!TYPE_COLORS[t]) {
    const keys = Object.keys(TYPE_COLORS);
    TYPE_COLORS[t] = PALETTE[keys.length % PALETTE.length];
  }
  return TYPE_COLORS[t];
}

function resize() {
  canvas.width = canvas.parentElement.clientWidth;
  canvas.height = canvas.parentElement.clientHeight;
}

async function loadAll() {
  const [nr, er] = await Promise.all([
    fetch('/api/nodes').then(r => r.json()),
    fetch('/api/edges').then(r => r.json())
  ]);
  nodes = nr.map(n => ({
    ...n,
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    vx: 0, vy: 0
  }));
  edges = er;
  nodeMap = {};
  nodes.forEach(n => nodeMap[n.id] = n);
  buildSidebar();
  requestAnimationFrame(tick);
}

function buildSidebar() {
  const filter = document.getElementById('filter');
  const types = [...new Set(nodes.map(n => n.type))].sort();
  types.forEach(t => {
    const o = document.createElement('option');
    o.value = t; o.textContent = t;
    filter.appendChild(o);
  });
  filter.addEventListener('change', renderList);
  renderList();
}

function label(n) {
  const f = n.fields || {};
  return f.name || f.title || f.label || n.type + ':' + n.id.slice(0,6);
}

function renderList() {
  const type = document.getElementById('filter').value;
  const ul = document.getElementById('node-list');
  ul.innerHTML = '';
  nodes.filter(n => !type || n.type === type).forEach(n => {
    const li = document.createElement('li');
    li.textContent = label(n);
    li.dataset.id = n.id;
    if (selected && selected.id === n.id) li.classList.add('selected');
    li.addEventListener('click', () => selectNode(n.id));
    ul.appendChild(li);
  });
}

function selectNode(id) {
  selected = nodeMap[id] || null;
  renderList();
  showDetail(selected);
  // Fetch fresh edges for this node
  if (selected) {
    fetch('/api/edges').then(r => r.json()).then(er => {
      edges = er;
      showDetail(selected);
    });
  }
}

function showDetail(n) {
  const panel = document.getElementById('detail');
  if (!n) { panel.classList.remove('visible'); return; }
  panel.classList.add('visible');
  document.getElementById('detail-name').textContent = label(n);
  document.getElementById('detail-type').textContent = 'type: ' + n.type;
  const dl = document.getElementById('detail-fields');
  dl.innerHTML = '';
  Object.entries(n.fields || {}).forEach(([k, v]) => {
    const dt = document.createElement('dt'); dt.textContent = k;
    const dd = document.createElement('dd'); dd.textContent = String(v);
    dl.appendChild(dt); dl.appendChild(dd);
  });
  const ul = document.getElementById('edge-list');
  ul.innerHTML = '';
  edges.filter(e => e.from_id === n.id || e.to_id === n.id).forEach(e => {
    const li = document.createElement('li');
    const other = e.from_id === n.id ? e.to_id : e.from_id;
    const dir = e.from_id === n.id ? '→' : '←';
    const peer = nodeMap[other];
    li.textContent = dir + ' ' + e.relation + ' ' + (peer ? label(peer) : other.slice(0,8));
    ul.appendChild(li);
  });
}

// Force simulation — repulsion + spring + centering + damping
const K_REPEL = 4000;
const K_SPRING = 0.04;
const REST_LEN = 120;
const DAMP = 0.85;
const DT = 0.5;

function tick() {
  if (!sim.running) return;
  const W = canvas.width, H = canvas.height;
  const cx = W / 2, cy = H / 2;

  // Reset forces
  nodes.forEach(n => { n.fx = 0; n.fy = 0; });

  // Repulsion (O(n^2) — fine for typical story sizes)
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      const d2 = dx*dx + dy*dy + 1;
      const d = Math.sqrt(d2);
      const f = K_REPEL / d2;
      const nx = dx / d, ny = dy / d;
      a.fx -= f * nx; a.fy -= f * ny;
      b.fx += f * nx; b.fy += f * ny;
    }
  }

  // Spring forces for edges
  edges.forEach(e => {
    const a = nodeMap[e.from_id], b = nodeMap[e.to_id];
    if (!a || !b) return;
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx*dx + dy*dy) || 1;
    const f = K_SPRING * (d - REST_LEN);
    const nx = dx / d, ny = dy / d;
    a.fx += f * nx; a.fy += f * ny;
    b.fx -= f * nx; b.fy -= f * ny;
  });

  // Centering gravity
  nodes.forEach(n => {
    n.fx += (cx - n.x) * 0.005;
    n.fy += (cy - n.y) * 0.005;
  });

  // Integrate
  nodes.forEach(n => {
    n.vx = (n.vx + n.fx * DT) * DAMP;
    n.vy = (n.vy + n.fy * DT) * DAMP;
    n.x += n.vx;
    n.y += n.vy;
    n.x = Math.max(20, Math.min(W - 20, n.x));
    n.y = Math.max(20, Math.min(H - 20, n.y));
  });

  draw();
  requestAnimationFrame(tick);
}

function draw() {
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  // Edges
  ctx.lineWidth = 1.5;
  edges.forEach(e => {
    const a = nodeMap[e.from_id], b = nodeMap[e.to_id];
    if (!a || !b) return;
    ctx.strokeStyle = 'rgba(168,216,234,0.3)';
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
    // Arrow tip
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx*dx + dy*dy) || 1;
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const nx = dx / d, ny = dy / d;
    ctx.fillStyle = 'rgba(168,216,234,0.5)';
    ctx.beginPath();
    ctx.moveTo(mx + nx*6, my + ny*6);
    ctx.lineTo(mx - ny*3 - nx*4, my + nx*3 - ny*4);
    ctx.lineTo(mx + ny*3 - nx*4, my - nx*3 - ny*4);
    ctx.closePath();
    ctx.fill();
  });

  // Nodes
  const R = 14;
  nodes.forEach(n => {
    const color = typeColor(n.type);
    const isSel = selected && selected.id === n.id;
    ctx.beginPath();
    ctx.arc(n.x, n.y, isSel ? R + 4 : R, 0, Math.PI * 2);
    ctx.fillStyle = isSel ? '#e94560' : color;
    ctx.fill();
    ctx.strokeStyle = isSel ? '#fff' : 'rgba(255,255,255,0.3)';
    ctx.lineWidth = isSel ? 2.5 : 1;
    ctx.stroke();
    // Label
    ctx.fillStyle = '#fff';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(label(n).slice(0, 14), n.x, n.y + R + 12);
  });
}

// Click to select
canvas.addEventListener('click', e => {
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const R = 18;
  const hit = nodes.find(n => {
    const dx = n.x - mx, dy = n.y - my;
    return dx*dx + dy*dy < R*R;
  });
  selectNode(hit ? hit.id : null);
});

window.addEventListener('resize', () => { resize(); });
resize();
loadAll();
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    """Request handler — serves HTML root and JSON API endpoints."""

    def log_message(self, format, *args):
        # Suppress access logs
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/":
            self._send_html(_HTML)

        elif path == "/api/nodes":
            self._send_json(timeline_db.get_nodes())

        elif path == "/api/edges":
            # Gather edges for all nodes, deduplicate by edge id
            seen = {}
            for node_id in timeline_db.get_all_node_ids():
                for edge in willow_edges.edges_for(node_id, uuid=_USER_UUID):
                    seen[edge["id"]] = edge
            self._send_json(list(seen.values()))

        elif path.startswith("/api/node/"):
            node_id = path[len("/api/node/"):]
            node = timeline_db.get_node(node_id)
            if node is None:
                self._send_json({"error": "not found"}, status=404)
            else:
                self._send_json(node)

        else:
            self._send_json({"error": "not found"}, status=404)


class _ReusingHTTPServer(HTTPServer):
    allow_reuse_address = True


class TimelineHTTPServer:
    """Thin wrapper around HTTPServer."""

    def __init__(self, port: int = 8765):
        self.port = port
        self._server = _ReusingHTTPServer(("127.0.0.1", port), _Handler)

    def start(self):
        """Blocking — call from a daemon thread."""
        self._server.serve_forever()

    def stop(self):
        self._server.shutdown()


def _set_user_uuid(uuid: Optional[str]) -> None:
    """Set module-level UUID used for Willow edge lookups."""
    global _USER_UUID
    _USER_UUID = uuid


def run_web(port: int = 8765, open_browser: bool = True) -> "TimelineHTTPServer":
    """Start the HTTP server in a background thread and optionally open browser."""
    srv = TimelineHTTPServer(port=port)
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    if open_browser:
        webbrowser.open(f"http://localhost:{port}/")
    return srv
