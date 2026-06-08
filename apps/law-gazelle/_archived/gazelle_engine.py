"""
gazelle_engine.py -- Core engine for Law Gazelle (SAFE-framework legal assistant)
b17: 3L2N9

Full-cycle legal assistant: classify issue, extract facts, look up statutes,
fill document templates, return ready-to-print HTML.
"""
from __future__ import annotations
import hashlib, json, sys, time, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure repo root is on path so core.db is importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.db import get_connection

import safe_integration as _safe

def _ask_fleet(prompt: str, fallback: str = "") -> str:
    """Route LLM requests through Willow's Pigeon bus."""
    try:
        result = _safe.ask(prompt, tier="free")
        if result and not result.startswith("[Error:"):
            return result.strip()
    except Exception:
        pass
    return fallback

ISSUE_TYPES = {
    "small_claims":     "Small claims court / money owed",
    "landlord_tenant":  "Landlord-tenant dispute (rent, deposit, eviction)",
    "employment":       "Employment dispute (unpaid wages, wrongful termination)",
    "foia":             "Freedom of Information Act request",
    "cease_desist":     "Cease and desist (harassment, IP, debt)",
    "contract_dispute": "Contract breach / demand",
    "consumer":         "Consumer protection / defective product / fraud",
    "bankruptcy":       "Bankruptcy filing (Chapter 7, 11, or 13)",
    "other":            "Other legal matter",
}

# Sub-types for bankruptcy. Keyed by the classifier label returned by the fleet.
BANKRUPTCY_SUBTYPES = {
    "chapter_7":  "Chapter 7 liquidation bankruptcy",
    "chapter_13": "Chapter 13 wage-earner repayment plan",
    "chapter_11": "Chapter 11 business reorganization",
}

ISSUE_TEMPLATES = {
    "small_claims":     ["small_claims_demand"],
    "landlord_tenant":  ["security_deposit_demand"],
    "employment":       ["wage_claim_letter"],
    "foia":             ["foia_request"],
    "cease_desist":     ["cease_desist"],
    "contract_dispute": ["small_claims_demand"],
    "consumer":         ["cease_desist"],
    # Bankruptcy templates are placeholder keys — full templates in progress.
    "bankruptcy":       ["chapter_13_plan_summary"],
    "other":            [],
}

REQUIRED_FACTS = {
    "small_claims":     ["sender_name","sender_address","recipient_name",
                         "recipient_address","amount_owed","reason","jurisdiction"],
    "landlord_tenant":  ["tenant_name","tenant_address","tenant_current_address",
                         "landlord_name","landlord_address","move_out_date","deposit_amount","state"],
    "employment":       ["employee_name","employee_address","employer_name",
                         "employer_address","wages_owed","employment_period","pay_periods","jurisdiction"],
    "foia":             ["sender_name","sender_address","agency_name",
                         "agency_address","description_of_records"],
    "cease_desist":     ["sender_name","sender_address","recipient_name",
                         "recipient_address","conduct_description","demand_description"],
    "contract_dispute": ["sender_name","sender_address","recipient_name",
                         "recipient_address","amount_owed","reason","jurisdiction"],
    "consumer":         ["sender_name","sender_address","recipient_name",
                         "recipient_address","conduct_description","demand_description"],
    "bankruptcy":       ["debtor_name","debtor_address","jurisdiction",
                         "total_debt","monthly_income","bankruptcy_chapter"],
    "other":            [],
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gazelle_sessions (
    id TEXT PRIMARY KEY, user_name TEXT, issue_raw TEXT, issue_type TEXT,
    jurisdiction TEXT, facts_json TEXT DEFAULT \'{}\', status TEXT DEFAULT \'intake\',
    consent_given INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS gazelle_messages (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY, session_id TEXT, role TEXT,
    content TEXT, metadata_json TEXT DEFAULT \'{}\', timestamp TEXT
);
CREATE TABLE IF NOT EXISTS gazelle_documents (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY, session_id TEXT, doc_type TEXT,
    doc_title TEXT, content TEXT, status TEXT DEFAULT \'draft\', created_at TEXT
);
"""

def _get_conn():
    import sqlite3 as _sqlite3
    c = get_connection()
    c.row_factory = _sqlite3.Row
    return c

def _ensure_schema():
    with _get_conn() as c:
        for stmt in _SCHEMA.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    c.execute(stmt)
                except Exception:
                    pass

try:
    _ensure_schema()
except Exception:
    pass
def _now(): return datetime.now().isoformat() + "Z"
def _make_id(s): return hashlib.sha1(f"{s}:{time.time()}".encode()).hexdigest()[:12]
def _rd(r): return dict(r)

def create_session(user_name: str, context: dict = None) -> dict:
    """Create a new Gazelle session.

    Args:
        user_name: Display name for the session owner.
        context: Optional dict with Willow-supplied background info.
                 Expected keys:
                   - facts (list[str]): pre-known fact strings
                   - source_files (list[str]): filenames that contributed the facts
                 Stored internally under the reserved key ``_willow_context``
                 inside facts_json so it survives DB round-trips without a
                 schema migration.
    """
    sid = _make_id(user_name); now = _now()
    initial_facts: dict = {}
    if context and isinstance(context, dict):
        initial_facts["_willow_context"] = {
            "facts":        context.get("facts") or [],
            "source_files": context.get("source_files") or [],
        }
    with _get_conn() as c:
        c.execute("INSERT INTO gazelle_sessions "
                  "(id,user_name,issue_raw,issue_type,jurisdiction,facts_json,status,consent_given,created_at,updated_at)"
                  " VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (sid, user_name, None, None, None,
                   json.dumps(initial_facts), "intake", 0, now, now))
    return get_session(sid)

def get_session(session_id: str) -> Optional[dict]:
    with _get_conn() as c:
        row = c.execute("SELECT * FROM gazelle_sessions WHERE id=?",(session_id,)).fetchone()
    if not row: return None
    d = _rd(row)
    try:
        raw = json.loads(d.get("facts_json") or "{}")
    except:
        raw = {}
    # Surface willow_context as a top-level key on the session dict.
    d["willow_context"] = raw.pop("_willow_context", None)
    d["facts"] = raw
    return d

def _upd(session_id: str, **kw):
    if not kw: return
    kw["updated_at"] = _now()
    if "facts" in kw:
        # Re-merge with any stored willow_context so it is not lost on update.
        existing_raw = {}
        try:
            with _get_conn() as c:
                row = c.execute("SELECT facts_json FROM gazelle_sessions WHERE id=?",
                                (session_id,)).fetchone()
            if row:
                existing_raw = json.loads(row["facts_json"] or "{}")
        except:
            pass
        merged = {**existing_raw, **kw.pop("facts")}
        kw["facts_json"] = json.dumps(merged)
    sql = "UPDATE gazelle_sessions SET " + ", ".join(f"{k}=?" for k in kw) + " WHERE id=?"
    with _get_conn() as c: c.execute(sql, list(kw.values()) + [session_id])

def delete_session(session_id: str) -> bool:
    if not get_session(session_id): return False
    with _get_conn() as c:
        c.execute("DELETE FROM gazelle_documents WHERE session_id=?",(session_id,))
        c.execute("DELETE FROM gazelle_messages WHERE session_id=?",(session_id,))
        c.execute("DELETE FROM gazelle_sessions WHERE id=?",(session_id,))
    return True

def add_message(session_id: str, role: str, content: str, metadata=None) -> int:
    with _get_conn() as c:
        cur = c.execute("INSERT INTO gazelle_messages (session_id,role,content,metadata_json,timestamp) VALUES (?,?,?,?,?)",
                        (session_id,role,content,json.dumps(metadata or {}),_now()))
        return cur.lastrowid

def get_messages(session_id: str, limit: int = 50) -> list:
    with _get_conn() as c:
        rows = c.execute("SELECT * FROM gazelle_messages WHERE session_id=? ORDER BY id DESC LIMIT ?",(session_id,limit)).fetchall()
    msgs = [_rd(r) for r in reversed(rows)]
    for m in msgs:
        try: m["metadata"] = json.loads(m.get("metadata_json") or "{}")
        except: m["metadata"] = {}
    return msgs

def classify_issue(session_id: str, user_description: str) -> dict:
    """Classify the user's legal issue.

    Adds "bankruptcy" to recognized types.  When the fleet (or fallback)
    returns issue_type == "bankruptcy", the classifier also attempts to
    identify which chapter (chapter_7 / chapter_13 / chapter_11) and
    returns it as ``bankruptcy_subtype``.
    """
    il = "\n".join(f"  {k}: {v}" for k,v in ISSUE_TYPES.items())
    # Include bankruptcy sub-types in the prompt so the fleet can signal them.
    bk_hint = ("When issue_type is 'bankruptcy', also include a "
                "'bankruptcy_subtype' key with one of: "
                + ", ".join(BANKRUPTCY_SUBTYPES.keys()) + ".")
    prompt = ("You are a legal intake classifier.\n\nSituation:\n---\n" + user_description +
              "\n---\n\nIssue types:\n" + il +
              '\n\n' + bk_hint +
              '\n\nRespond ONLY with JSON: {"issue_type":"<key>","bankruptcy_subtype":"<sub or null>",'
              '"jurisdiction":"<state or federal>",'
              '"confidence":0.0,"clarifying_questions":["q1","q2","q3"]}')
    raw = _ask_fleet(prompt, "")
    result = {"issue_type":"other","bankruptcy_subtype":None,
              "jurisdiction":"federal","confidence":0.5,
              "clarifying_questions":["What state?","Names of all parties?","Desired outcome?"]}
    if raw:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1].strip()
            if clean.startswith("json"): clean = clean[4:].strip()
        try:
            p = json.loads(clean)
            if p.get("issue_type") in ISSUE_TYPES: result["issue_type"] = p["issue_type"]
            result["jurisdiction"] = p.get("jurisdiction","federal") or "federal"
            result["confidence"] = float(p.get("confidence",0.5))
            if isinstance(p.get("clarifying_questions"),list):
                result["clarifying_questions"] = p["clarifying_questions"][:5]
            # Bankruptcy sub-type — only trust it when issue is bankruptcy.
            if result["issue_type"] == "bankruptcy":
                sub = p.get("bankruptcy_subtype") or ""
                if sub in BANKRUPTCY_SUBTYPES:
                    result["bankruptcy_subtype"] = sub
        except: pass
    _upd(session_id, issue_raw=user_description, issue_type=result["issue_type"],
         jurisdiction=result["jurisdiction"], status="clarifying")
    return result

def extract_facts(session_id: str, conversation_text: str) -> dict:
    s = get_session(session_id)
    if not s: return {"facts":{},"missing_fields":[],"complete":False}
    it = s.get("issue_type") or "other"; req = REQUIRED_FACTS.get(it,[])
    prompt = ("Extract legal facts.\nIssue: " + it + "\nRequired: " + json.dumps(req) +
              "\nConversation:\n---\n" + conversation_text + "\n---\nJSON only. Null for missing.")
    raw = _ask_fleet(prompt,"")
    existing = s.get("facts") or {}; new = {}
    if raw:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1].strip()
            if clean.startswith("json"): clean = clean[4:].strip()
        try:
            p = json.loads(clean)
            if isinstance(p,dict): new = {k:v for k,v in p.items() if v is not None}
        except: pass
    merged = {**existing,**new}; missing = [f for f in req if not merged.get(f)]
    _upd(session_id, facts=merged)
    return {"facts":merged,"missing_fields":missing,"complete":len(missing)==0}

def get_required_templates(issue_type: str, bankruptcy_subtype: str = None) -> list:
    """Return the list of template keys required for the given issue type.

    For bankruptcy, Chapter 13 specifically returns the Chapter 13 plan
    summary plus a schedule recap placeholder.  All other bankruptcy
    sub-types (and the generic bankruptcy case) return the base placeholder.

    Note: Full Chapter 13 templates are in progress. The keys
    ``chapter_13_plan_summary`` and ``schedule_recap`` are placeholders
    and will resolve to actual templates once they are authored.
    """
    if issue_type == "bankruptcy":
        if bankruptcy_subtype == "chapter_13":
            # Chapter 13-specific placeholders — full templates in progress.
            return ["chapter_13_plan_summary", "schedule_recap"]
        # chapter_7 / chapter_11 / unspecified — base placeholder only.
        return ISSUE_TEMPLATES.get("bankruptcy", ["chapter_13_plan_summary"])
    return ISSUE_TEMPLATES.get(issue_type, [])

_DISC = ("This document was prepared with AI assistance. "
         "Review with a qualified attorney before submission.")
_CSS = ('<style>body{font-family:"Times New Roman",serif;font-size:12pt;margin:1in;'
        'color:#000;background:#fff;line-height:1.5}'
        '.hd{text-align:right;margin-bottom:24pt}.pa{margin-bottom:18pt}'
        '.su{font-weight:bold;margin-bottom:18pt}p{margin:0 0 12pt}.sg{margin-top:36pt}'
        '.di{margin-top:48pt;padding-top:12pt;border-top:1px solid #999;'
        'font-size:9pt;color:#666;font-style:italic}'
        '@media print{body{margin:1in}}</style>')

def _w(t, b):
    return ('<!DOCTYPE html><html><head><meta charset="UTF-8"><title>' + t + '</title>'
            + _CSS + '</head><body>' + b
            + '<div class="di">' + _DISC + '</div></body></html>')
def _e(v,df="[Not provided]"):
    if v is None: return df
    return str(v).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
def _a(v): return _e(v).replace(", ","<br>")
def _f(d,k,df="[Not provided]"): return _e(d.get(k) or None,df)

def _small_claims(f):
    t = "Small Claims Demand Letter"; td = datetime.now().strftime("%B %d, %Y")
    dl = _e(f.get("deadline_days","14"))
    b = ("".join([
        '<div class="hd">'+_f(f,"date",td)+'</div>',
        '<div class="pa"><strong>FROM:</strong><br>'+_f(f,"sender_name")+'<br>'+_a(f.get("sender_address",""))+'<br><br>',
        '<strong>TO:</strong><br>'+_f(f,"recipient_name")+'<br>'+_a(f.get("recipient_address",""))+'</div>',
        '<div class="su">RE: Formal Demand for Payment of $'+_f(f,"amount_owed","[Amount]")+'</div>',
        '<p>Dear '+_f(f,"recipient_name")+',</p>',
        '<p>This letter constitutes formal notice that you owe me <strong>$'+_f(f,"amount_owed","[Amount]")+'</strong> for: '+_f(f,"reason","[reason]")+'.</p>',
        '<p>Demand is hereby made for payment in full within <strong>'+dl+' days</strong>. Failure may result in a small claims court filing.</p>',
        '<div class="sg">Sincerely,<br><br><br>____________________________<br>'+_f(f,"sender_name")+'<br>'+_f(f,"date",td)+'</div>',
    ]))
    return t, _w(t,b)

def _foia(f):
    t = "Freedom of Information Act Request"; td = datetime.now().strftime("%B %d, %Y")
    ep = ('<p>Expedited processing requested: '+_e(f.get("expedite_reason",""))+'</p>') if f.get("expedite_reason") else ""
    b = ("".join([
        '<div class="hd">'+_f(f,"date",td)+'</div>',
        '<div class="pa"><strong>FROM:</strong><br>'+_f(f,"sender_name")+'<br>'+_a(f.get("sender_address",""))+'<br><br>',
        '<strong>TO:</strong><br>FOIA Officer<br>'+_f(f,"agency_name")+'<br>'+_a(f.get("agency_address",""))+'</div>',
        '<div class="su">RE: FOIA Request &#8212; 5 U.S.C. &#167; 552</div>',
        '<p>Dear FOIA Officer,</p>',
        '<p>Pursuant to 5 U.S.C. &#167; 552, I request the following records from '+_f(f,"agency_name")+':</p>',
        '<p><em>'+_f(f,"description_of_records","[describe records]")+'</em></p>',ep,
        '<p>Willing to pay reasonable fees up to $25. Notify me if higher. Please respond within 20 business days.</p>',
        '<div class="sg">Sincerely,<br><br><br>____________________________<br>'+_f(f,"sender_name")+'<br>'+_f(f,"date",td)+'</div>',
    ]))
    return t, _w(t,b)

def _deposit(f):
    t = "Security Deposit Return Demand"; td = datetime.now().strftime("%B %d, %Y")
    st = _e(f.get("state","your state")); dl = _e(f.get("deadline_days","14"))
    b = ("".join([
        '<div class="hd">'+_f(f,"date",td)+'</div>',
        '<div class="pa"><strong>FROM:</strong><br>'+_f(f,"tenant_name")+'<br>'+_a(f.get("tenant_current_address",""))+'<br><br>',
        '<strong>TO:</strong><br>'+_f(f,"landlord_name")+'<br>'+_a(f.get("landlord_address",""))+'</div>',
        '<div class="su">RE: Security Deposit Return &#8212; $'+_f(f,"deposit_amount","[Amount]")+'</div>',
        '<p>Dear '+_f(f,"landlord_name")+',</p>',
        '<p>I demand return of my security deposit of <strong>$'+_f(f,"deposit_amount","[Amount]")+'</strong> for '+_f(f,"tenant_address")+'.',
        ' I vacated on '+_f(f,"move_out_date","[date]")+' and left the property in good condition.</p>',
        '<p>Under '+st+' law, landlords must return the deposit within the statutory period. You have not done so.</p>',
        '<p>Please return the full deposit within <strong>'+dl+' days</strong> or I will pursue legal action.</p>',
        '<div class="sg">Sincerely,<br><br><br>____________________________<br>'+_f(f,"tenant_name")+'<br>'+_f(f,"date",td)+'</div>',
    ]))
    return t, _w(t,b)

def _cease(f):
    t = "Cease and Desist Letter"; td = datetime.now().strftime("%B %d, %Y")
    dl = _e(f.get("deadline_days","10"))
    b = ("".join([
        '<div class="hd">'+_f(f,"date",td)+'</div>',
        '<div class="pa"><strong>FROM:</strong><br>'+_f(f,"sender_name")+'<br>'+_a(f.get("sender_address",""))+'<br><br>',
        '<strong>TO:</strong><br>'+_f(f,"recipient_name")+'<br>'+_a(f.get("recipient_address",""))+'</div>',
        '<div class="su">RE: CEASE AND DESIST</div>',
        '<p>Dear '+_f(f,"recipient_name")+',</p>',
        '<p>The following conduct must cease immediately:</p>',
        '<p><strong>'+_f(f,"conduct_description","[conduct]")+'</strong></p>',
        '<p>You are demanded to: '+_f(f,"demand_description","[demand]")+'</p>',
        '<p>Comply within <strong>'+dl+' days</strong> or face civil legal action.</p>',
        '<div class="sg">Sincerely,<br><br><br>____________________________<br>'+_f(f,"sender_name")+'<br>'+_f(f,"date",td)+'</div>',
    ]))
    return t, _w(t,b)

def _wages(f):
    t = "Unpaid Wages Demand Letter"; td = datetime.now().strftime("%B %d, %Y")
    b = ("".join([
        '<div class="hd">'+_f(f,"date",td)+'</div>',
        '<div class="pa"><strong>FROM:</strong><br>'+_f(f,"employee_name")+'<br>'+_a(f.get("employee_address",""))+'<br><br>',
        '<strong>TO:</strong><br>'+_f(f,"employer_name")+'<br>'+_a(f.get("employer_address",""))+'</div>',
        '<div class="su">RE: Demand for Unpaid Wages &#8212; $'+_f(f,"wages_owed","[Amount]")+'</div>',
        '<p>Dear '+_f(f,"employer_name")+',</p>',
        '<p>I demand payment of <strong>$'+_f(f,"wages_owed","[Amount]")+'</strong> for '+_f(f,"employment_period","[period]")+' ('+_f(f,"pay_periods","[pay periods]")+').</p>',
        '<p>Under the FLSA (29 U.S.C. &#167; 201 et seq.) all earned wages must be paid on scheduled dates.</p>',
        '<p>Payment required within <strong>14 days</strong>. Failure may result in DOL complaint and civil action.</p>',
        '<div class="sg">Sincerely,<br><br><br>____________________________<br>'+_f(f,"employee_name")+'<br>'+_f(f,"date",td)+'</div>',
    ]))
    return t, _w(t,b)

_TB = {
    "small_claims_demand":     _small_claims,
    "foia_request":            _foia,
    "security_deposit_demand": _deposit,
    "cease_desist":            _cease,
    "wage_claim_letter":       _wages,
}

def fill_document(session_id: str, template_key: str, facts: dict) -> dict:
    b = _TB.get(template_key)
    if not b:
        # Placeholder template keys (e.g. bankruptcy) have no renderer yet.
        # Return a stub so callers know the document is pending.
        return {
            "doc_id": None,
            "title": template_key.replace("_", " ").title() + " (Template In Progress)",
            "content": "",
            "status": "placeholder",
            "note": f"Template '{template_key}' is not yet authored. Full templates are in progress.",
        }
    title, html = b(facts)
    with _get_conn() as c:
        cur = c.execute("INSERT INTO gazelle_documents (session_id,doc_type,doc_title,content,status,created_at) VALUES (?,?,?,?,'draft',?)",
                        (session_id,template_key,title,html,_now()))
        return {"doc_id":cur.lastrowid,"title":title,"content":html,"status":"draft"}

def get_documents(session_id: str) -> list:
    with _get_conn() as c:
        rows = c.execute("SELECT * FROM gazelle_documents WHERE session_id=? ORDER BY id ASC",(session_id,)).fetchall()
    return [_rd(r) for r in rows]

def lookup_statute(query: str, jurisdiction: str = "federal") -> dict:
    results = []
    if jurisdiction in ("federal","us","usa"):
        try:
            enc = urllib.parse.quote(query[:100])
            url = f"https://www.ecfr.gov/api/search/v1/results?query={enc}&per_page=3"
            req = urllib.request.Request(url, headers={"Accept":"application/json"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                for item in (data.get("results") or [])[:3]:
                    results.append({"title":item.get("label_description",""),"citation":item.get("citation",""),
                                    "url":"https://www.ecfr.gov"+item.get("full_text_excerpt_url",""),
                                    "summary":item.get("full_text_excerpt","")})
        except: pass
    if not results:
        txt = _ask_fleet("Briefly describe the most relevant US federal or "+jurisdiction+" statute(s) for: "+query+". Name, citation, 1-2 sentence summary. Plain text.","")
        if txt: results.append({"title":"Applicable Law (AI Summary)","citation":"","url":"","summary":txt})
    return {"results":results,"query":query,"jurisdiction":jurisdiction}

def explain_law(statute_text: str, issue_context: str) -> str:
    return _ask_fleet("Plain-language explanation.\n\nLegal text:\n"+statute_text[:2000]+
                      "\n\nSituation: "+issue_context+"\n\nExplain in 2-3 simple sentences.",
                      "Explanation unavailable. Please consult an attorney.")

_ML = {
    "sender_name":"your full name","recipient_name":"the other party's full name",
    "sender_address":"your mailing address","recipient_address":"their address",
    "amount_owed":"the exact dollar amount","reason":"why they owe you",
    "jurisdiction":"what state this is in","state":"what state this is in",
    "tenant_name":"your full name (as tenant)","landlord_name":"the landlord's full name",
    "deposit_amount":"the security deposit amount","move_out_date":"your move-out date",
    "tenant_current_address":"your current mailing address","tenant_address":"the rental property address",
    "employee_name":"your full name","employer_name":"the employer's full name",
    "wages_owed":"the amount of unpaid wages","employment_period":"your employment dates",
    "pay_periods":"which pay periods are missing","employer_address":"the employer's address",
    "employee_address":"your mailing address","agency_name":"the agency's name",
    "description_of_records":"what records you want","conduct_description":"what conduct to stop",
    "demand_description":"what you want them to do",
    "debtor_name":"your full legal name","debtor_address":"your mailing address",
    "total_debt":"the total amount of debt","monthly_income":"your monthly income",
    "bankruptcy_chapter":"which bankruptcy chapter (7, 11, or 13)",
}

def _build_willow_context_intro(willow_context: dict) -> str:
    """Build an acknowledgment string from Willow-supplied context facts.

    Returns an empty string if there are no facts to surface.
    """
    if not willow_context or not isinstance(willow_context, dict):
        return ""
    facts = willow_context.get("facts") or []
    if not facts:
        return ""

    # Summarize facts: show up to 3, then indicate if there are more.
    shown = facts[:3]
    remainder = len(facts) - len(shown)
    facts_text = "; ".join(shown)
    if remainder > 0:
        facts_text += f" (and {remainder} more)"

    # Infer a topic from the facts using a simple heuristic: take the first fact.
    first_fact = shown[0] if shown else ""
    # Try to identify a rough topic keyword from the first fact.
    topic = first_fact[:80].rstrip(".").rstrip(",") if first_fact else "your situation"

    intro = (
        "I can see some background information from your files: "
        + facts_text
        + ". Let me confirm \u2014 is this related to "
        + topic
        + "?"
    )
    return intro

def process_message(session_id: str, user_message: str) -> dict:
    s = get_session(session_id)
    if not s: return {"response":"Session not found.","status":"error","documents_ready":False,"documents":[]}
    add_message(session_id,"user",user_message)
    status = s.get("status","intake")

    if status == "intake":
        clf = classify_issue(session_id, user_message)
        it = clf["issue_type"]
        qs = clf.get("clarifying_questions") or ["What state?","Names of parties?","Desired outcome?"]
        qt = "\n".join("\u2022 "+q for q in qs[:4])
        law = lookup_statute(user_message, clf.get("jurisdiction","federal"))
        ln = ""
        if law["results"]:
            top = law["results"][0]; sm=(top.get("summary") or "")[:200]
            ln = "\n\nRelevant law: **"+top["title"]+"**"+((" \u2014 "+sm) if sm else "")

        # Check for Willow-supplied context facts and prepend an acknowledgment
        # instead of a cold generic intro when background is available.
        willow_context = s.get("willow_context")
        context_intro = _build_willow_context_intro(willow_context)

        if context_intro:
            resp = (context_intro +
                    "\n\nBased on what you've described, it sounds like a **"
                    + ISSUE_TYPES.get(it, it) + "** situation." + ln +
                    "\n\nTo prepare your documents I need a few details:\n\n" + qt +
                    "\n\nAnswer as many as you can.")
        else:
            resp = ("I understand \u2014 it sounds like you have a **" + ISSUE_TYPES.get(it,it) +
                    "** situation." + ln +
                    "\n\nTo prepare your documents I need a few details:\n\n" + qt +
                    "\n\nAnswer as many as you can.")

        add_message(session_id,"gazelle",resp)
        return {"response":resp,"status":"clarifying","documents_ready":False,"documents":[]}

    if status == "clarifying":
        msgs = get_messages(session_id,20)
        conv = "\n".join(("User" if m["role"]=="user" else "Gazelle")+": "+m["content"] for m in msgs)
        ext = extract_facts(session_id,conv); missing = ext.get("missing_fields",[])
        if missing and len(missing) > 2:
            ask = [_ML.get(f,f) for f in missing[:3]]
            q = (", ".join(ask[:-1])+" and "+ask[-1]) if len(ask)>1 else ask[0]
            resp = "Thank you \u2014 just a few more details: **"+q+"**."
            add_message(session_id,"gazelle",resp)
            return {"response":resp,"status":"clarifying","documents_ready":False,"documents":[]}
        _upd(session_id,status="drafting")
        s = get_session(session_id); facts = s.get("facts") or {}
        facts["date"] = datetime.now().strftime("%B %d, %Y")
        it = s.get("issue_type") or "other"
        # Pass bankruptcy_subtype through to get_required_templates when relevant.
        bk_sub = facts.get("bankruptcy_chapter") if it == "bankruptcy" else None
        docs = [fill_document(session_id,t,facts) for t in get_required_templates(it, bk_sub)]
        _upd(session_id,status="complete")
        if docs:
            names = ", ".join(d["title"] for d in docs)
            resp = ("Your documents are ready: **"+names+"**.\n\nReview carefully before signing. "
                    "Fields marked [Not provided] need your attention.\n\n"
                    "\u26a0\ufe0f _AI-assisted \u2014 review with an attorney before submitting._")
        else:
            resp = "This situation has no standard template. Contact a local legal aid organization."
        add_message(session_id,"gazelle",resp)
        return {"response":resp,"status":"complete","documents_ready":bool(docs),"documents":docs}

    if status == "complete":
        s = get_session(session_id); msgs = get_messages(session_id,30)
        conv = "\n".join(("User" if m["role"]=="user" else "Gazelle")+": "+m["content"] for m in msgs)
        ext = extract_facts(session_id,conv)
        facts = ext.get("facts") or s.get("facts") or {}
        facts["date"] = datetime.now().strftime("%B %d, %Y")
        it = s.get("issue_type") or "other"
        bk_sub = facts.get("bankruptcy_chapter") if it == "bankruptcy" else None
        tmps = get_required_templates(it, bk_sub)
        if tmps:
            with _get_conn() as c: c.execute("DELETE FROM gazelle_documents WHERE session_id=?",(session_id,))
            docs = [fill_document(session_id,t,facts) for t in tmps]
        else:
            docs = get_documents(session_id)
        resp = _ask_fleet("You are Gazelle. User said: '"+user_message+"'. Documents updated. Reply in 1-2 warm professional sentences.",
                          "Your documents have been updated. Please review before submitting.")
        add_message(session_id,"gazelle",resp)
        return {"response":resp,"status":"complete","documents_ready":bool(docs),"documents":docs}

    resp = "Tell me about your legal situation and I'll help you prepare documents."
    add_message(session_id,"gazelle",resp)
    return {"response":resp,"status":status,"documents_ready":False,"documents":[]}


# ── Case Management ──────────────────────────────────────────────────────────

def get_cases(username: str) -> list:
    """All open cases for a user, with next deadline."""
    with _get_conn() as c:
        rows = c.execute(
            "SELECT gc.*, "
            "(SELECT MIN(gd.deadline_date) FROM sweet_pea_rudi19.gazelle_deadlines gd "
            " WHERE gd.case_id = gc.id AND gd.status = 'pending') as next_deadline, "
            "(SELECT COUNT(*) FROM sweet_pea_rudi19.gazelle_case_documents gcd "
            " WHERE gcd.case_id = gc.id AND gcd.action_required = 1 "
            " AND gcd.status = 'unreviewed') as action_count "
            "FROM sweet_pea_rudi19.gazelle_cases gc "
            "WHERE gc.username = ? ORDER BY gc.status ASC, gc.created_at DESC",
            (username,)
        ).fetchall()
    result = []
    for r in rows:
        d = _rd(r)
        try: d["parties"] = json.loads(d.get("parties_json") or "{}")
        except: d["parties"] = {}
        result.append(d)
    return result


def get_case(case_id: int, username: str) -> dict | None:
    """Single case with full detail."""
    with _get_conn() as c:
        row = c.execute(
            "SELECT * FROM sweet_pea_rudi19.gazelle_cases "
            "WHERE id = ? AND username = ?", (case_id, username)
        ).fetchone()
    if not row: return None
    d = _rd(row)
    try: d["parties"] = json.loads(d.get("parties_json") or "{}")
    except: d["parties"] = {}
    d["documents"] = get_case_documents(case_id, username)
    d["deadlines"] = get_case_deadlines(case_id, username)
    return d


def get_case_documents(case_id: int, username: str, doc_type: str = None) -> list:
    """Documents for a case, optionally filtered by type."""
    with _get_conn() as c:
        if doc_type:
            rows = c.execute(
                "SELECT * FROM sweet_pea_rudi19.gazelle_case_documents "
                "WHERE case_id = ? AND username = ? AND doc_type = ? "
                "ORDER BY created_at DESC", (case_id, username, doc_type)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM sweet_pea_rudi19.gazelle_case_documents "
                "WHERE case_id = ? AND username = ? ORDER BY created_at DESC",
                (case_id, username)
            ).fetchall()
    return [_rd(r) for r in rows]


def get_case_deadlines(case_id: int, username: str, status: str = None) -> list:
    """Deadlines for a case, optionally filtered by status."""
    with _get_conn() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM sweet_pea_rudi19.gazelle_deadlines "
                "WHERE case_id = ? AND username = ? AND status = ? "
                "ORDER BY deadline_date ASC", (case_id, username, status)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM sweet_pea_rudi19.gazelle_deadlines "
                "WHERE case_id = ? AND username = ? ORDER BY deadline_date ASC",
                (case_id, username)
            ).fetchall()
    return [_rd(r) for r in rows]


def add_case_document(case_id: int, username: str, doc_type: str, title: str,
                       content_text: str, source: str = "manual", **kwargs) -> dict:
    """Insert a document and auto-extract deadlines if ECF."""
    now = _now()
    parsed_summary = kwargs.get("parsed_summary", "")
    action_required = kwargs.get("action_required", 0)
    action_type = kwargs.get("action_type", "informational")
    deadline = kwargs.get("deadline")
    source_file = kwargs.get("source_file", "")

    with _get_conn() as c:
        cur = c.execute(
            "INSERT INTO sweet_pea_rudi19.gazelle_case_documents "
            "(case_id, username, doc_type, title, source, source_file, content_text, "
            "parsed_summary, action_required, action_type, deadline, status, "
            "created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (case_id, username, doc_type, title, source, source_file,
             content_text[:10000], parsed_summary, action_required,
             action_type, deadline, "unreviewed", now, now)
        )
        row = cur.fetchone()
        doc_id = row[0] if row else None

    return {"doc_id": doc_id, "title": title, "doc_type": doc_type}


def update_deadline(deadline_id: int, username: str, status: str,
                     notes: str = None) -> dict:
    """Mark a deadline as met, missed, extended, etc."""
    now = _now()
    with _get_conn() as c:
        if notes is not None:
            c.execute(
                "UPDATE sweet_pea_rudi19.gazelle_deadlines "
                "SET status = ?, notes = ?, updated_at = ? "
                "WHERE id = ? AND username = ?",
                (status, notes, now, deadline_id, username)
            )
        else:
            c.execute(
                "UPDATE sweet_pea_rudi19.gazelle_deadlines "
                "SET status = ?, updated_at = ? WHERE id = ? AND username = ?",
                (status, now, deadline_id, username)
            )
    return {"deadline_id": deadline_id, "status": status}


def get_legal_nest_items(username: str) -> list:
    """Query nest_review_queue for legal-tagged pending items."""
    with _get_conn() as c:
        rows = c.execute(
            "SELECT * FROM sweet_pea_rudi19.nest_review_queue "
            "WHERE username = ? AND status = 'pending' "
            "AND (proposed_category ILIKE '%%legal%%' "
            "     OR proposed_category ILIKE '%%court%%' "
            "     OR proposed_category ILIKE '%%bankruptcy%%' "
            "     OR proposed_category ILIKE '%%ecf%%') "
            "ORDER BY created_at DESC LIMIT 50",
            (username,)
        ).fetchall()
    return [_rd(r) for r in rows]
