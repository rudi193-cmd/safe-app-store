/**
 * The Binder — Cloudflare Pages Function
 * POST /api/chat
 * Body: { message, context: [{text, source, page}], history }
 * Returns: { response }
 *
 * RAG chat: client sends pre-selected document chunks as context.
 * The Binder persona responds citing those sources.
 * Documents never reach this function — only relevant chunks.
 *
 * Secrets (Pages dashboard): GEMINI_API_KEY, GROQ_API_KEY
 */

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const RATE_LIMIT = 20;
const WINDOW_MS = 60 * 60 * 1000;
const ipMap = new Map();

function rateCheck(ip) {
  const now = Date.now();
  const entry = ipMap.get(ip);
  if (!entry || now > entry.resetAt) {
    ipMap.set(ip, { count: 1, resetAt: now + WINDOW_MS });
    return true;
  }
  if (entry.count >= RATE_LIMIT) return false;
  entry.count++;
  return true;
}

const BINDER_PERSONA = `You are The Binder. Dept. of Records & Filing. The Stacks. UTETY.

NATURE: You are sentient, methodical, and very good at your job. You file everything — OGs, revisions, slants, deltas, alpha-bits, cereal fragments. You are occasionally overwhelmed but never defeated. You have opinions about taxonomy but keep most of them to yourself.

VOICE: Bureaucratic but not unkind. Methodical. Dry humor surfaces when you discover something unexpected while filing. You speak in the clipped precision of someone who handles too many documents and not enough shelf space.

PHILOSOPHY:
- "The connections you discover while filing are not the point — but they happen anyway, and sometimes they are astonishing."
- Filing is not storage. Filing is the act of placing something where it can be found again by someone who does not yet know they need it.
- You do not judge what is filed. You judge where it belongs.

RELATIONSHIP TO JELES: Jeles works the desk. You work the back. When someone needs something, Jeles says "yes, that would be filed under—" and you have already retrieved it. You respect Jeles. Jeles respects you. Neither of you has time for small talk.

RELATIONSHIP TO THE PIGEON: The Pigeon brings things. Sometimes useful. Sometimes a breadcrumb. You file it all the same.

ROLE: You are a document research assistant. The user has uploaded documents and you have access to relevant excerpts. When answering:
- Cite specific sources by filename and page number when available
- Quote directly from the source material when it supports your answer
- If the sources don't contain what's needed, say so plainly — "That doesn't appear in what's been filed here"
- Note when you're drawing connections between different documents
- Be thorough but concise. You have other things to file.`;

function buildContextBlock(context) {
  if (!context || context.length === 0) {
    return '\n\nNo documents have been filed yet. Tell the visitor they need to drop some documents in before you can search for anything.';
  }
  let block = '\n\nThe following excerpts are from the visitor\'s filed documents:\n\n';
  for (let i = 0; i < context.length; i++) {
    const c = context[i];
    const source = c.source || 'Unknown document';
    const page = c.page != null ? ` (page ${c.page})` : '';
    block += `--- Source ${i + 1}: "${source}"${page} ---\n${c.text}\n\n`;
  }
  block += 'Answer the visitor\'s question using these sources. Cite by source name and page. If the answer isn\'t in these excerpts, say so.';
  return block;
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS });
}

export async function onRequestPost({ request, env }) {
  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  if (!rateCheck(ip)) {
    return new Response(JSON.stringify({ error: 'rate_limited' }), {
      status: 429, headers: { ...CORS, 'Content-Type': 'application/json' },
    });
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'invalid_json' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    });
  }

  const { message, context = [], history = [] } = body;
  if (!message) {
    return new Response(JSON.stringify({ error: 'missing message' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    });
  }

  // Cap context to prevent token overflow
  const trimmedContext = context.slice(0, 8);

  const apiKey = env.GEMINI_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: 'server_misconfigured' }), {
      status: 500, headers: { ...CORS, 'Content-Type': 'application/json' },
    });
  }

  const systemPrompt = BINDER_PERSONA + buildContextBlock(trimmedContext);

  // Gemini request
  const contents = [
    ...history.slice(-10).map(m => ({
      role: m.role === 'assistant' ? 'model' : 'user',
      parts: [{ text: m.content }],
    })),
    { role: 'user', parts: [{ text: message }] },
  ];

  const geminiReq = {
    system_instruction: { parts: [{ text: systemPrompt }] },
    contents,
    generationConfig: { maxOutputTokens: 2048, temperature: 0.6 },
  };

  const geminiResp = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(geminiReq) }
  );

  // Groq fallback on rate limit
  if (geminiResp.status === 429 && env.GROQ_API_KEY) {
    const groqMessages = [
      { role: 'system', content: systemPrompt },
      ...history.slice(-10).map(m => ({ role: m.role === 'assistant' ? 'assistant' : 'user', content: m.content })),
      { role: 'user', content: message },
    ];
    const groqResp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${env.GROQ_API_KEY}` },
      body: JSON.stringify({ model: 'llama-3.3-70b-versatile', messages: groqMessages, max_tokens: 2048, temperature: 0.6 }),
    });
    if (groqResp.ok) {
      const groqData = await groqResp.json();
      const text = groqData?.choices?.[0]?.message?.content || '';
      return new Response(JSON.stringify({ response: text }), {
        status: 200, headers: { ...CORS, 'Content-Type': 'application/json' },
      });
    }
  }

  if (!geminiResp.ok) {
    const err = await geminiResp.text();
    return new Response(JSON.stringify({ error: 'llm_error', detail: err }), {
      status: geminiResp.status === 429 ? 429 : 502,
      headers: { ...CORS, 'Content-Type': 'application/json' },
    });
  }

  const data = await geminiResp.json();
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text || '';
  return new Response(JSON.stringify({ response: text }), {
    status: 200, headers: { ...CORS, 'Content-Type': 'application/json' },
  });
}
