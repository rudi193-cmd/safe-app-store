"""
The Squirrel — HTTP server on port 8425.
b17: SQ002

Routes:
  GET  /              Journal (Squirrel.md render + live poll)
  GET  /people        Person grid with silhouette cameos
  GET  /person/<id>   Person detail view
  GET  /tree          Pedigree with daguerreotype ovals (?name=X)
  GET  /stash         Fragment stash
  GET  /sources       Source registry browser (?q=query)
  GET  /stories       Jeles oral history interview room
  GET  /mtime         {"mtime": float} for live polling
  GET  /skins/*       Serve CSS files
  POST /write         Append text to Squirrel.md
  POST /api/stories/chat   AJAX: {session_id?, message} -> {session_id, reply}
  POST /api/stories/save   AJAX: {session_id, subject} -> {saved: int}
"""
import html as _html
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

import markdown as _md

PORT = 8425
SQUIRREL_MD = Path("Squirrel.md")
SKINS_DIR = Path(__file__).parent / "skins"

WELCOME_BLOCK = """# The Squirrel
*genealogy research terminal — the file is the interface*

**Commands:**
- `@squirrel: demo load` — meet the fictional Acorn family
- `@squirrel: add person Hazel Acorn b.1902 p.Cedar_Grove`
- `@squirrel: tree Hazel Acorn`
- `@squirrel: show people`
- `@squirrel: find sources Iowa 1880s`
- `@squirrel: mode listening` — invite the LLM in
- `@squirrel: status`
- `@squirrel: receipts` — the tool-call trail (who touched what)
- `@squirrel: skin 80s`

---
"""

_file_lock = threading.RLock()
_app_state = None  # set in run()

# Stories sessions: session_id -> {"turns": [{"role": str, "content": str}]}
_stories_sessions: dict = {}
_stories_lock = threading.Lock()

_RENDER_LIMIT = 50_000

# ── Cameo silhouette SVG ───────────────────────────────────────────────────────

_CAMEO_SVG = (
    '<svg class="cameo-silhouette" viewBox="0 0 60 80" '
    'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<circle cx="30" cy="22" r="13" fill="currentColor"/>'
    '<path d="M8,56 C8,42 18,34 30,34 C42,34 52,42 52,56 L52,80 L8,80 Z" fill="currentColor"/>'
    "</svg>"
)

# ── Skin + config helpers ──────────────────────────────────────────────────────

def _get_skin() -> str:
    p = Path.home() / ".squirrel" / "config.json"
    if p.exists():
        try:
            return json.loads(p.read_text()).get("skin", "mcm")
        except Exception:
            pass
    return "mcm"


def _get_model() -> str:
    p = Path.home() / ".squirrel" / "config.json"
    if p.exists():
        try:
            return json.loads(p.read_text()).get("ollama_model", "qwen2.5:3b")
        except Exception:
            pass
    return "qwen2.5:3b"


# ── Shared layout ──────────────────────────────────────────────────────────────

def _nav_html(current_route: str, skin: str) -> str:
    links = [("/", "Journal"), ("/people", "People"), ("/tree", "Tree"),
             ("/stash", "Stash"), ("/sources", "Sources"), ("/stories", "Stories"),
             ("/privacy", "Privacy")]
    items = "".join(
        f'<a href="{href}" class="nav-link{"  nav-link--active" if current_route == href else ""}">'
        f"{label}</a>"
        for href, label in links
    )
    skin_opts = "".join(
        f'<option value="{s}"{"  selected" if s == skin else ""}>{s.upper()}</option>'
        for s in ("mcm", "80s", "00s", "20s")
    )
    return (
        f'<nav id="nav"><div id="nav-links">{items}</div>'
        f'<div id="nav-controls"><select id="skin-select" onchange="setSkin(this.value)">'
        f"{skin_opts}</select></div></nav>"
    )


_SHARED_JS = """
const MODES=["journal","listening","chat"];
function setMode(v){fetch("/write",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:"@squirrel: mode "+MODES[v]})});}
function submitCmd(){
  const t=document.getElementById("cmd").value.trim();
  if(!t)return;
  fetch("/write",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t})})
  .then(()=>{document.getElementById("cmd").value="";window.location.href="/";});
}
document.addEventListener("DOMContentLoaded",()=>{
  const el=document.getElementById("cmd");
  if(el)el.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();submitCmd();}});
});
function setSkin(s){fetch("/write",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:"@squirrel: skin "+s})}).then(()=>location.reload());}
"""


def _html_page(title: str, current_route: str, body_html: str,
               extra_js: str = "") -> str:
    skin = _get_skin()
    nav = _nav_html(current_route, skin)
    return f"""<!DOCTYPE html>
<html lang="en" data-skin="{skin}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — The Squirrel</title>
<link rel="stylesheet" href="/skins/base.css">
<link rel="stylesheet" href="/skins/{skin}.css">
</head>
<body>
<div id="header">
  <div id="title">THE SQUIRREL</div>
  <div id="mode-toggle">
    <label>Journal</label>
    <input type="range" min="0" max="2" value="0" id="mode-slider" oninput="setMode(this.value)">
    <label>Chat</label>
  </div>
</div>
{nav}
<div id="content">{body_html}</div>
<div id="input-area">
  <textarea id="cmd" placeholder="@squirrel: ..." rows="2"></textarea>
  <button onclick="submitCmd()">&#8629;</button>
</div>
<script>{_SHARED_JS}</script>
{extra_js}
</body>
</html>"""


# ── DB helper ──────────────────────────────────────────────────────────────────

def _with_db(fn, *args, current_route="/", **kwargs) -> str:
    from db import get_connection, release_connection
    import sap.core.gate as _gate
    conn = get_connection()
    try:
        # Web views are the user browsing their own tree — the journal actor.
        with _gate.actor("journal"):
            return fn(conn, *args, **kwargs)
    except Exception as e:
        return _html_page("Error", current_route,
                          f'<p class="error">Database error: {e}</p>')
    finally:
        release_connection(conn)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _fmt_dates(p: dict) -> str:
    parts = []
    if p.get("birth_date"):  parts.append(f"b.{p['birth_date']}")
    if p.get("death_date"):  parts.append(f"d.{p['death_date']}")
    return " · ".join(parts)


def ensure_squirrel_md(path: Path = SQUIRREL_MD):
    if not path.exists():
        path.write_text(WELCOME_BLOCK, encoding="utf-8")


# ── Page renderers ─────────────────────────────────────────────────────────────

def _render_journal() -> str:
    ensure_squirrel_md()
    raw = SQUIRREL_MD.read_text(encoding="utf-8")
    if len(raw) > _RENDER_LIMIT:
        raw = "*[…earlier entries trimmed]*\n\n" + raw[-_RENDER_LIMIT:]
    body = _md.markdown(raw, extensions=["fenced_code", "tables"])
    poll_js = ("<script>let _mt=0;setInterval(async()=>{"
               "const r=await fetch('/mtime');const d=await r.json();"
               "if(d.mtime!==_mt){_mt=d.mtime;location.reload();}},1500);</script>")
    return _html_page("Journal", "/", body, extra_js=poll_js)


def _render_people(conn) -> str:
    import db.persons as persons_db
    people = persons_db.search_persons(conn, "")
    if not people:
        body = ('<h2 class="page-title">People</h2>'
                '<div class="empty-state"><p>No persons in the tree yet.</p>'
                '<p>Add one: <code>@squirrel: add person Hazel Acorn b.1902 p.Cedar_Grove</code></p>'
                '<p>Or meet a sample family: <code>@squirrel: demo load</code></p></div>')
    else:
        cards = "".join(
            f'<a class="person-card" href="/person/{p["id"]}">'
            f'<div class="cameo">{_CAMEO_SVG}</div>'
            f'<div class="person-card-name">{_html.escape(p["full_name"])}</div>'
            f'<div class="person-card-dates">{_html.escape(_fmt_dates(p))}</div></a>'
            for p in people
        )
        n = len(people)
        body = (f'<h2 class="page-title">People</h2>'
                f'<p class="page-subtitle">{n} {"person" if n == 1 else "persons"} in the tree</p>'
                f'<div class="person-grid">{cards}</div>')
    return _html_page("People", "/people", body)


def _render_person(conn, person_id: int) -> str:
    import db.persons as persons_db
    tree = persons_db.get_family_tree(conn, person_id)
    if tree["person"] is None:
        return _html_page("Person", "/people",
                          '<div class="empty-state"><p>No person found with that ID.</p></div>')
    p = tree["person"]
    portrait = (f'<div class="cameo" style="width:120px;height:150px;'
                f'border-radius:60px/75px;">{_CAMEO_SVG}</div>')
    fields = ""
    for label, key in [("Born", "birth_date"), ("Birthplace", "birth_place"),
                       ("Died", "death_date"), ("Deathplace", "death_place"),
                       ("Buried", "burial_place")]:
        if p.get(key):
            fields += f"<dt>{label}</dt><dd>{_html.escape(str(p[key]))}</dd>"
    if p.get("bio"):
        fields += f"<dt>Bio</dt><dd>{_html.escape(p['bio'])}</dd>"
    kin_items = ""
    _INVERT = {"parent": "child", "child": "parent"}
    for r in tree["relationships"]:
        rid = r.get("related_person_id") or r.get("person_id")
        rtype = r.get("relationship_type", "")
        if rid == person_id:
            # Reverse row: the OTHER person points at the subject, so the
            # label inverts — (Hans → parent → Albert) shows on Albert's
            # page as "child: Hans", not "parent: Hans".
            rid = r.get("person_id")
            rtype = _INVERT.get(rtype, rtype)
        rname = r.get("related_name", "Unknown")
        kin_items += (f'<div class="person-kin-item">'
                      f'<div class="person-kin-rel">{_html.escape(rtype)}</div>'
                      f'<div class="person-kin-name"><a href="/person/{rid}">{_html.escape(rname)}</a></div>'
                      f'</div>')
    kin = (f"<h3>Relationships</h3>"
           f'<div class="person-kin-list">{kin_items}</div>') if kin_items else ""
    tree_link = (f'<p style="margin:0.75rem 0">'
                 f'<a href="/tree?name={quote(p["full_name"])}">View in tree →</a></p>')
    body = (f'<h2 class="page-title">{_html.escape(p["full_name"])}</h2>'
            f'<div class="person-detail">'
            f'<div class="person-detail-portrait">{portrait}</div>'
            f'<div><dl class="person-detail-fields">{fields}</dl>{tree_link}{kin}</div>'
            f'</div>')
    return _html_page(_html.escape(p["full_name"]), "/people", body)


def _render_tree(conn, name: str = "") -> str:
    import db.persons as persons_db
    from responder.commands.tree import build_ancestors_dict

    search_form = (
        f'<div class="tree-search">'
        f'<input type="text" id="tree-name" placeholder="Enter a name" '
        f'value="{_html.escape(name)}" onkeydown="if(event.key===\'Enter\')goTree()">'
        f'<button onclick="goTree()">View Tree</button></div>'
        f'<script>function goTree(){{const n=document.getElementById("tree-name").value.trim();'
        f'if(n)window.location.href="/tree?name="+encodeURIComponent(n);}}</script>'
    )

    if not name.strip():
        body = ('<h2 class="page-title">Pedigree Tree</h2>' + search_form +
                '<div class="empty-state"><p>Enter a name to view their ancestors.</p></div>')
        return _html_page("Tree", "/tree", body)

    matches = persons_db.search_persons(conn, name)
    if not matches:
        body = (f'<h2 class="page-title">Pedigree Tree</h2>' + search_form +
                f'<div class="empty-state"><p>No person found matching "{_html.escape(name)}".</p></div>')
        return _html_page("Tree", "/tree", body)

    subject = matches[0]
    ancestors = build_ancestors_dict(conn, subject["id"], depth=3)

    def _dag(n: int) -> str:
        p = ancestors.get(n)
        if p:
            link = f'<a href="/person/{p["id"]}" class="dag-name">{_html.escape(p["full_name"])}</a>'
            dates = f'<div class="dag-dates">{_fmt_dates(p)}</div>' if _fmt_dates(p) else ""
            return (f'<div class="dag-node">'
                    f'<div class="dag-frame">{_CAMEO_SVG}</div>{link}{dates}</div>')
        return (f'<div class="dag-node">'
                f'<div class="dag-frame" style="opacity:0.3">{_CAMEO_SVG}</div>'
                f'<div class="dag-name" style="color:var(--color-muted)">Unknown</div></div>')

    gp_col = (f'<div class="tree-generation">{_dag(4)}{_dag(5)}{_dag(6)}{_dag(7)}</div>'
              if any(n in ancestors for n in [4, 5, 6, 7]) else "")
    p_col = (f'<div class="tree-generation">{_dag(2)}{_dag(3)}</div>'
             if any(n in ancestors for n in [2, 3]) else "")
    s_col = f'<div class="tree-generation">{_dag(1)}</div>'

    tree_html = f'<div class="tree-container">{gp_col}{p_col}{s_col}</div>'
    body = (f'<h2 class="page-title">Pedigree — {_html.escape(subject["full_name"])}</h2>'
            f'{search_form}{tree_html}')
    return _html_page("Tree", "/tree", body)


def _render_stash(conn) -> str:
    import db.fragments as fragments_db
    all_frags = fragments_db.search_fragments(conn, "")
    if not all_frags:
        body = ('<h2 class="page-title">Stash</h2>'
                '<div class="empty-state"><p>No fragments yet.</p>'
                '<p>Add one: <code>@squirrel: stash "Oscar Mann, b. 1882" --confidence likely</code></p></div>')
    else:
        rows = ""
        for f in all_frags[:100]:
            synced = bool(f.get("binder_synced_at"))
            cls = " stash-synced" if synced else ""
            badge = " ✓ bound" if synced else ""
            text = f.get("story_text") or f.get("person_name") or ""
            meta = f"{f.get('fragment_type','')} · {f.get('confidence','')}{badge}"
            rows += (f'<div class="stash-item{cls}">'
                     f'<div class="stash-text">{_html.escape(text)}</div>'
                     f'<div class="stash-meta">{_html.escape(meta)}</div></div>')
        n = len(all_frags)
        body = (f'<h2 class="page-title">Stash</h2>'
                f'<p class="page-subtitle">{n} fragments · '
                f'<code>@squirrel: bind all → auto</code> to promote</p>'
                f'<div class="stash-list">{rows}</div>')
    return _html_page("Stash", "/stash", body)


def _render_sources(conn, q: str = "") -> str:
    import db.sources as sources_db
    sources_db.init_schema(conn)
    search_form = (
        f'<form class="sources-search" action="/sources" method="get">'
        f'<input type="text" name="q" value="{_html.escape(q)}" '
        f'placeholder="Search by state, city, archive name...">'
        f'<button type="submit">Search</button></form>'
    )
    results = sources_db.lookup_sources(conn, query=q, limit=25)
    from sap.core import consent as _consent
    link_ok = _consent.online()
    if not results:
        cards = '<div class="empty-state"><p>No sources found.</p></div>'
    else:
        cards = "".join(
            (f'<div class="source-card">'
             + (f'<a href="{r["url"]}" target="_blank" rel="noopener">{_html.escape(r["name"])}</a>'
                if link_ok else f'<span>{_html.escape(r["name"])}</span>')
             + f'<div class="source-card-meta">'
               f'{r.get("state","") or ""} · {r.get("provider","")}</div></div>')
            for r in results
        )
    note = f"{len(results)} results" if q.strip() else "779 archives · search above"
    if not link_ok:
        note += ' · links hidden — <a href="/privacy">ONLINE is off</a>'
    body = (f'<h2 class="page-title">Sources</h2>'
            f'<p class="page-subtitle">{note}</p>{search_form}{cards}')
    return _html_page("Sources", "/sources", body)


_STORIES_JS = """<script>
let _sid=null,_turns=0;
async function storySend(){
  const inp=document.getElementById("story-input");
  const msg=inp.value.trim();if(!msg)return;
  inp.value="";_appendMsg(msg,"user");
  const payload={message:msg};if(_sid)payload.session_id=_sid;
  const r=await fetch("/api/stories/chat",{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const d=await r.json();_sid=d.session_id;_turns++;
  document.getElementById("turn-count").textContent=_turns+" exchange"+(_turns===1?"":"s");
  _appendMsg(d.reply,"jeles");
}
function _appendMsg(text,role){
  const log=document.getElementById("chat-log");
  const div=document.createElement("div");
  div.className="story-msg story-msg--"+role;div.textContent=text;
  log.appendChild(div);log.scrollTop=log.scrollHeight;
}
async function storySave(){
  if(!_sid){alert("Nothing to save yet.");return;}
  const subject=prompt("Who is this story about?");if(!subject)return;
  const r=await fetch("/api/stories/save",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session_id:_sid,subject:subject})});
  const d=await r.json();
  alert("Saved "+d.saved+" fragments for "+subject+".");
  _sid=null;_turns=0;
  document.getElementById("chat-log").innerHTML=
    "<div class=\\"story-msg story-msg--jeles\\">Story saved. Who else shall we remember?</div>";
  document.getElementById("turn-count").textContent="";
}
function storyDiscard(){
  if(!_sid)return;
  if(!confirm("Discard this session? Nothing will be saved."))return;
  _sid=null;_turns=0;
  document.getElementById("chat-log").innerHTML=
    "<div class=\\"story-msg story-msg--jeles\\">Session cleared. Ready when you are.</div>";
  document.getElementById("turn-count").textContent="";
}
document.addEventListener("DOMContentLoaded",()=>{
  const el=document.getElementById("story-input");
  if(el)el.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();storySend();}});
});
</script>"""


def _render_stories() -> str:
    body = (
        '<h2 class="page-title">Tell Your Stories</h2>'
        '<div class="stories-header">'
        '<p>Jeles will ask you questions about your family. Share what you remember.<br>'
        'Nothing is saved until you choose to save it.</p></div>'
        '<div class="stories-container">'
        '<div class="stories-chat" id="chat-log">'
        '<div class="story-msg story-msg--jeles">'
        "Hello. I'm Jeles. Who would you like to talk about today?"
        '</div></div>'
        '<div class="stories-input">'
        '<textarea id="story-input" rows="2" placeholder="Share a memory..."></textarea>'
        '<button onclick="storySend()">Send</button></div>'
        '<div class="stories-save-bar">'
        '<span id="turn-count" style="color:var(--color-muted);align-self:center;"></span>'
        '<button class="save-btn" onclick="storySave()">Save Story</button>'
        '<button onclick="storyDiscard()">Discard</button>'
        '</div></div>'
    )
    return _html_page("Stories", "/stories", body, extra_js=_STORIES_JS)


# ── Privacy page — the passenger view ─────────────────────────────────────────
# Four controls, per the divider: ONLINE, the AI slider, THE TRAIL, GO QUIET.
# A view over enforcement that already exists (consent, gate, receipts) —
# it adds no new authority, and it shows no switch that doesn't truly switch.

_TRAIL_WHO = {"squirrel-journal": "You", "squirrel-jeles": "Jeles",
              "operator-bypass": "A trusted script", "unattributed": "Something unidentified"}
_TRAIL_WHAT = {"pii:read": "looked at the tree", "pii:write": "changed the tree",
               "pii:export": "carried the tree out (export)",
               "llm:chat": "spoke in chat", "llm:hint": "listened and offered a note",
               "llm:stories": "asked a story question"}


def _trail_sentence(r: dict) -> str:
    who = _TRAIL_WHO.get(r["app_id"], r["app_id"])
    tool = r["tool"]
    if tool.startswith("cmd:"):
        what = f"ran <code>{_html.escape(tool[4:])}</code>"
    else:
        what = _TRAIL_WHAT.get(tool, _html.escape(tool))
    tail = {"denied": " — <strong>blocked</strong>",
            "bypass": " (with a written reason)",
            "error": " — failed"}.get(r["outcome"], "")
    when = _html.escape(r["ts"][:16].replace("T", " ")) + " UTC"
    return f"<li><span class=\"trail-when\">{when}</span> — {who} {what}{tail}</li>"


def _render_privacy() -> str:
    from sap.core import consent, receipts
    online = consent.online()
    wound = consent.damaged()
    mode = _app_state.mode.value if _app_state else "journal"

    online_label = "ON — links to outside archives show" if online else \
                   "OFF — nothing points off this machine"
    online_note = ("The Squirrel never sends your tree anywhere. Search results are "
                   "links; nothing leaves unless <em>you</em> click one. This switch "
                   "controls whether those links appear at all.")
    if wound:
        online_note = ("<strong>Settings file is damaged</strong> — everything is off "
                       "until it's repaired. Flipping the switch writes a fresh one. ") \
                      + online_note

    mode_notes = {
        "journal": "Jeles is out of the room. Commands only.",
        "listening": "Jeles reads new entries and may offer a note. Read-only — the gate keeps it that way.",
        "chat": "Jeles converses. Still read-only, still cannot export. Runs on this machine (Ollama).",
    }
    trail_items = "".join(_trail_sentence(r) for r in receipts.tail(limit=15)) or \
                  "<li>Nothing yet.</li>"

    body = f"""<h2 class="page-title">Privacy</h2>
<p class="page-subtitle">Everything lives at <code>~/.squirrel</code>. Yours to keep, yours to delete.</p>

<div class="privacy-row">
  <h3>ONLINE</h3>
  <button id="online-btn" class="privacy-toggle{' privacy-toggle--on' if online else ''}"
          onclick="flipOnline({str(online).lower()})">{online_label}</button>
  <p>{online_note}</p>
</div>

<div class="privacy-row">
  <h3>THE AI</h3>
  <p>Mode: <strong>{mode}</strong> — use the slider in the header to change it.</p>
  <p>{mode_notes.get(mode, "")}</p>
</div>

<div class="privacy-row">
  <h3>THE TRAIL</h3>
  <p>What has been touched, newest first. The full ledger: <code>@squirrel: receipts</code></p>
  <ul class="trail">{trail_items}</ul>
</div>

<div class="privacy-row">
  <h3>GO QUIET</h3>
  <button class="privacy-quiet" onclick="goQuiet()">Go quiet</button>
  <p>One motion: Jeles leaves the room and ONLINE turns off. Nothing is deleted.</p>
</div>

<script>
async function flipOnline(cur){{
  await fetch("/api/privacy",{{method:"POST",headers:{{"Content-Type":"application/json"}},
    body:JSON.stringify({{online:!cur}})}});
  location.reload();
}}
async function goQuiet(){{
  await fetch("/api/quiet",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:"{{}}"}});
  location.reload();
}}
</script>
<style>
.privacy-row{{margin:1.2rem 0;}}
.privacy-toggle,.privacy-quiet{{padding:0.6rem 1rem;cursor:pointer;
  border:2px solid var(--color-accent,#b5432a);background:transparent;
  color:var(--color-text,inherit);font:inherit;}}
.privacy-toggle--on{{background:var(--color-accent,#b5432a);color:var(--color-bg,#fff);}}
.trail{{list-style:none;padding:0;}}
.trail li{{margin:0.25rem 0;}}
.trail-when{{opacity:0.6;font-size:0.85em;}}
</style>"""
    return _html_page("Privacy", "/privacy", body)


def _handle_privacy(handler, body: dict):
    from sap.core import consent, receipts
    value = bool(body.get("online"))
    consent.set_online(value)
    receipts.record("squirrel-journal", "cmd:privacy.online",
                    "ok", "on" if value else "off")
    handler._send_json({"online": value})


def _handle_quiet(handler, body: dict):
    from sap.core import consent, receipts
    from responder.state import Mode
    consent.set_online(False)
    if _app_state is not None:
        _app_state.mode = Mode.JOURNAL
    receipts.record("squirrel-journal", "cmd:quiet", "ok",
                    "mode->journal, online->off")
    handler._send_json({"quiet": True})


# ── Stories API ────────────────────────────────────────────────────────────────

_JELES_STORIES_SYSTEM = """You are Jeles, conducting an oral history interview.
Ask warm, open-ended questions to draw out family memories. Focus on one person per session.
Style: short responses (1-2 sentences max), exactly one follow-up question per turn.
Never invent facts. Only reflect what the user has shared.
If the subject is not established, ask who they want to talk about."""


def _handle_stories_chat(handler, body: dict):
    message = body.get("message", "").strip()
    if not message:
        handler._send_json({"error": "message required"}, 400)
        return
    sid = body.get("session_id")
    import time as _time
    _TTL = 7200  # 2 hours
    with _stories_lock:
        # Evict stale sessions
        now = _time.time()
        stale = [k for k, v in _stories_sessions.items()
                 if now - v.get("created_at", now) > _TTL]
        for k in stale:
            del _stories_sessions[k]
        # Get or create session
        if sid and sid in _stories_sessions:
            session = _stories_sessions[sid]
        else:
            sid = str(uuid.uuid4())
            session = {"turns": [], "created_at": _time.time()}
            _stories_sessions[sid] = session
        session["turns"].append({"role": "user", "content": message})

    try:
        import urllib.request
        messages = [{"role": "system", "content": _JELES_STORIES_SYSTEM}]
        messages += [{"role": t["role"], "content": t["content"]}
                     for t in session["turns"]]
        payload = json.dumps({"model": _get_model(), "stream": False,
                               "messages": messages}).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/chat", data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            reply = json.loads(resp.read())["message"]["content"].strip()
        from sap.core import receipts as _receipts
        _receipts.record("squirrel-jeles", "llm:stories", "ok")
    except Exception:
        reply = "I'm having trouble connecting right now. Please try again."
        from sap.core import receipts as _receipts
        _receipts.record("squirrel-jeles", "llm:stories", "error")

    with _stories_lock:
        session["turns"].append({"role": "assistant", "content": reply})
    handler._send_json({"session_id": sid, "reply": reply})


def _handle_stories_save(handler, body: dict):
    sid = body.get("session_id", "")
    subject = body.get("subject", "").strip()
    saved = 0
    with _stories_lock:
        session = _stories_sessions.pop(sid, None)
    if session and subject:
        try:
            from db import get_connection, release_connection
            import db.fragments as fragments_db
            import sap.core.gate as _gate
            conn = get_connection()
            try:
                # Saving is the user's explicit click — journal, not jeles.
                with _gate.actor("journal"):
                    for turn in session["turns"]:
                        if turn["role"] == "user" and turn["content"].strip():
                            fragments_db.add_fragment(
                                conn, person_name=subject,
                                fragment_type="oral_history",
                                story_text=turn["content"],
                                source="stories_room",
                                confidence="uncertain")
                            saved += 1
            finally:
                release_connection(conn)
            from sap.core import receipts as _receipts
            _receipts.record("squirrel-journal", "cmd:stories.save", "ok",
                             f"{saved} fragments")
        except Exception as _e:
            from sap.core import receipts as _receipts
            _receipts.record("squirrel-journal", "cmd:stories.save", "error",
                             str(_e)[:200])
            handler._send_json({"saved": saved, "error": str(_e)})
            return
    handler._send_json({"saved": saved})


# ── HTTP handler ───────────────────────────────────────────────────────────────

class SquirrelHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_html(self, html: str, status: int = 200):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj: dict, status: int = 200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            self._do_GET()
        except BrokenPipeError:
            pass

    def _do_GET(self):
        p = urlparse(self.path)
        path = p.path
        qs = parse_qs(p.query)

        if path == "/":
            self._send_html(_render_journal())
        elif path == "/people":
            self._send_html(_with_db(_render_people, current_route="/people"))
        elif path.startswith("/person/"):
            try:
                pid = int(path[len("/person/"):])
            except ValueError:
                self.send_response(404); self.end_headers(); return
            self._send_html(_with_db(_render_person, pid, current_route="/people"))
        elif path == "/tree":
            name = qs.get("name", [""])[0]
            self._send_html(_with_db(_render_tree, name, current_route="/tree"))
        elif path == "/stash":
            self._send_html(_with_db(_render_stash, current_route="/stash"))
        elif path == "/sources":
            q = qs.get("q", [""])[0]
            self._send_html(_with_db(_render_sources, q, current_route="/sources"))
        elif path == "/stories":
            self._send_html(_render_stories())
        elif path == "/privacy":
            self._send_html(_render_privacy())
        elif path == "/mtime":
            mtime = SQUIRREL_MD.stat().st_mtime if SQUIRREL_MD.exists() else 0
            self._send_json({"mtime": mtime})
        elif path.startswith("/skins/"):
            fname = path[len("/skins/"):]
            css_path = (SKINS_DIR / fname).resolve()
            skins_root = SKINS_DIR.resolve()
            if (css_path.is_file() and css_path.suffix == ".css"
                    and skins_root in css_path.parents):
                data = css_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/css")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        try:
            self._do_POST()
        except BrokenPipeError:
            pass

    def _do_POST(self):
        MAX_BODY = 64 * 1024
        length = min(int(self.headers.get("Content-Length", 0)), MAX_BODY)
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self.send_response(400); self.end_headers(); return

        if self.path == "/write":
            text = body.get("text", "").strip()
            if text:
                with _file_lock:
                    with open(SQUIRREL_MD, "a", encoding="utf-8") as f:
                        f.write("\n" + text + "\n")
            self.send_response(200); self.end_headers()
        elif self.path == "/api/stories/chat":
            _handle_stories_chat(self, body)
        elif self.path == "/api/stories/save":
            _handle_stories_save(self, body)
        elif self.path == "/api/privacy":
            _handle_privacy(self, body)
        elif self.path == "/api/quiet":
            _handle_quiet(self, body)
        else:
            self.send_response(404); self.end_headers()


# ── Entry point ────────────────────────────────────────────────────────────────

def run(port: int = PORT):
    global _app_state
    from squirrel_watcher import start_watcher
    from squirrel_responder import make_responder
    from responder.state import AppState
    from sap.core.vault import provision
    provision()  # stand up the box: 0700, gate dir, vault.db + vault.key
    ensure_squirrel_md()
    _app_state = AppState(squirrel_md=SQUIRREL_MD)
    _app_state.load_config()
    responder_cb = make_responder(_app_state)
    watcher = start_watcher(SQUIRREL_MD, responder_cb, lambda: _app_state.mode.value)
    try:
        server = HTTPServer(("127.0.0.1", port), SquirrelHandler)
        print(f"The Squirrel is open at http://localhost:{port}")
        server.serve_forever()
    finally:
        watcher.stop()
        watcher.join()
        import sap.core.gate as _gate
        _gate.close()


if __name__ == "__main__":
    run()
