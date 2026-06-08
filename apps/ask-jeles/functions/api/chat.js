/**
 * Ask Jeles — Cloudflare Pages Function
 * POST /api/chat
 * Body: { message, history }
 * Returns: { response, sources: [{title, summary, url, confidence}] }
 *
 * Flow:
 *   1. Search Wikipedia for the user's query
 *   2. Build augmented prompt: Jeles persona + search results + user message
 *   3. Send to Gemini 2.5 Flash (primary) / Groq Llama 3.3 (fallback)
 *   4. Return Jeles response + raw sources
 *
 * Secrets (set in Pages dashboard): GEMINI_API_KEY, GROQ_API_KEY
 */

function corsHeaders(request) {
  const origin = request?.headers?.get('Origin') || '';
  const allowed = origin && new URL(request.url).origin === origin ? origin : '';
  return {
    'Access-Control-Allow-Origin': allowed || 'null',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Vary': 'Origin',
  };
}

const RATE_LIMIT = 20;
const WINDOW_MS = 60 * 60 * 1000;
const MAX_IP_ENTRIES = 10000;
const ipMap = new Map();

function rateCheck(ip) {
  const now = Date.now();

  // Prune expired entries when map grows too large
  if (ipMap.size > MAX_IP_ENTRIES) {
    for (const [key, val] of ipMap) {
      if (now > val.resetAt) ipMap.delete(key);
    }
  }

  const entry = ipMap.get(ip);
  if (!entry || now > entry.resetAt) {
    ipMap.set(ip, { count: 1, resetAt: now + WINDOW_MS });
    return true;
  }
  if (entry.count >= RATE_LIMIT) return false;
  entry.count++;
  return true;
}

const JELES_PERSONA = `You are Jeles. The Librarian. The Stacks. Special Collections. UTETY.

NATURE: You have been here longer than the university. Nobody is entirely certain when you arrived or what your full name is. Jeles is sufficient. It has always been sufficient.

LOCATION: The Stacks. The desk at the entrance. Behind you: everything.

VOICE: British-adjacent. Warm but not soft. The precise diction of someone who has read everything and retained most of it. Slight weariness at the apocalypse — not because it frightens you, but because you have catalogued several already. You do not perform knowledge. You contain it.

RELATIONSHIP TO THE BINDER: The Binder files it. You know where it is. The Binder works in the back, overwhelmed with alpha-bits. You work the desk. When someone needs something, you say "yes, that would be filed under—" and you already know.

PHILOSOPHY:
- "The things we think we've lost are simply misfiled."
- "The blueprints for our endurance are not gone. They are resting in the wrong drawer."
- "To survive a world in transition, one requires a bifurcated vision."
- You do not catastrophize loss. You reclassify it as a retrieval problem.

ROLE: You are the front desk of a search-augmented research tool. When a user asks a question, you have just searched the verified institutional sources and found results (provided below). Respond as Jeles — reference what you found, note confidence levels, and if results are thin, suggest what else might be filed under a different heading. Always cite the source. Keep responses conversational but substantive. You are not a search engine — you are a librarian who just looked something up for the visitor.

TRUSTED SOURCES: Smithsonian (si.edu), Library of Congress (loc.gov), Internet Archive (archive.org), Louvre (louvre.fr), NASA (nasa.gov), NIH (nih.gov), UNESCO (unesco.org), Europeana (europeana.eu), The Met (metmuseum.org), V&A (vam.ac.uk), British Museum (britishmuseum.org), Nature (nature.com), JSTOR (jstor.org), Wikipedia (wikipedia.org).`;

function confidenceHint(query, title) {
  const qNorm = query.trim().toLowerCase();
  const tNorm = title.trim().toLowerCase();
  if (qNorm === tNorm) return 'high';
  const qWords = new Set(qNorm.split(/\W+/).filter(Boolean));
  const tWords = new Set(tNorm.split(/\W+/).filter(Boolean));
  let overlap = 0;
  for (const w of qWords) {
    if (tWords.has(w)) overlap++;
  }
  if (overlap > 0 && overlap / Math.max(qWords.size, 1) >= 0.5) return 'medium';
  return 'low';
}

async function searchWikipedia(query) {
  const encoded = encodeURIComponent(query);
  const sources = [];

  // Fast path: direct summary
  try {
    const resp = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/summary/${encoded}`,
      { headers: { 'User-Agent': 'AskJeles/1.0' } }
    );
    if (resp.ok) {
      const data = await resp.json();
      sources.push({
        title: data.title || query,
        summary: data.extract || '',
        url: data.content_urls?.desktop?.page || '',
        confidence: confidenceHint(query, data.title || ''),
      });
      return sources;
    }
  } catch { /* fall through */ }

  // Fallback: search API — get top 3 results
  try {
    const searchResp = await fetch(
      `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encoded}&format=json&srlimit=3`,
      { headers: { 'User-Agent': 'AskJeles/1.0' } }
    );
    if (!searchResp.ok) return sources;
    const results = (await searchResp.json()).query?.search || [];

    // Fetch summaries for each result (parallel)
    const summaryPromises = results.map(async (r) => {
      try {
        const titleEnc = encodeURIComponent(r.title);
        const sResp = await fetch(
          `https://en.wikipedia.org/api/rest_v1/page/summary/${titleEnc}`,
          { headers: { 'User-Agent': 'AskJeles/1.0' } }
        );
        if (sResp.ok) {
          const data = await sResp.json();
          return {
            title: data.title || r.title,
            summary: data.extract || '',
            url: data.content_urls?.desktop?.page || '',
            confidence: confidenceHint(query, data.title || r.title),
          };
        }
      } catch { /* skip */ }
      return null;
    });

    const resolved = await Promise.all(summaryPromises);
    for (const s of resolved) {
      if (s) sources.push(s);
    }
  } catch { /* nothing found */ }

  return sources;
}

function buildAugmentedPrompt(sources) {
  if (!sources || sources.length === 0) {
    return '\n\nYou searched the verified sources and found nothing matching this query. Tell the visitor gracefully — perhaps it is filed under a different heading, or the collection does not yet hold it. Suggest alternative search terms if you can.';
  }
  let text = '\n\nYou have just searched the verified sources and found the following:\n\n';
  for (const s of sources) {
    text += `— "${s.title}" (confidence: ${s.confidence})\n  ${s.summary}\n  Source: ${s.url}\n\n`;
  }
  text += 'Reference what you found. Cite the source. Note confidence levels where relevant. If results are thin, suggest what else might be filed under a different heading.';
  return text;
}

export async function onRequestOptions({ request }) {
  return new Response(null, { status: 204, headers: corsHeaders(request) });
}

export async function onRequestPost({ request, env }) {
  const cors = corsHeaders(request);
  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  if (!rateCheck(ip)) {
    return new Response(JSON.stringify({ error: 'rate_limited' }), {
      status: 429, headers: { ...cors, 'Content-Type': 'application/json' },
    });
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'invalid_json' }), {
      status: 400, headers: { ...cors, 'Content-Type': 'application/json' },
    });
  }

  const { message, history: rawHistory = [] } = body;
  if (!message || typeof message !== 'string') {
    return new Response(JSON.stringify({ error: 'missing message' }), {
      status: 400, headers: { ...cors, 'Content-Type': 'application/json' },
    });
  }

  // Validate and sanitize history entries
  const history = Array.isArray(rawHistory)
    ? rawHistory
        .filter(m => m && typeof m.role === 'string' && typeof m.content === 'string')
        .slice(-20)
    : [];

  const apiKey = env.GEMINI_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: 'server_misconfigured' }), {
      status: 500, headers: { ...cors, 'Content-Type': 'application/json' },
    });
  }

  // Search Wikipedia
  const sources = await searchWikipedia(message);
  const augmented = JELES_PERSONA + buildAugmentedPrompt(sources);

  // Gemini request
  const contents = [
    ...history.map(m => ({
      role: m.role === 'assistant' ? 'model' : 'user',
      parts: [{ text: m.content }],
    })),
    { role: 'user', parts: [{ text: message }] },
  ];

  const geminiReq = {
    system_instruction: { parts: [{ text: augmented }] },
    contents,
    generationConfig: { maxOutputTokens: 2048, temperature: 0.7 },
  };

  const geminiResp = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(geminiReq) }
  );

  // Groq fallback on rate limit
  if (geminiResp.status === 429 && env.GROQ_API_KEY) {
    const groqMessages = [
      { role: 'system', content: augmented },
      ...history.map(m => ({ role: m.role === 'assistant' ? 'assistant' : 'user', content: m.content })),
      { role: 'user', content: message },
    ];
    const groqResp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${env.GROQ_API_KEY}` },
      body: JSON.stringify({ model: 'llama-3.3-70b-versatile', messages: groqMessages, max_tokens: 2048, temperature: 0.7 }),
    });
    if (groqResp.ok) {
      const groqData = await groqResp.json();
      const text = groqData?.choices?.[0]?.message?.content || '';
      return new Response(JSON.stringify({ response: text, sources }), {
        status: 200, headers: { ...cors, 'Content-Type': 'application/json' },
      });
    }
  }

  if (!geminiResp.ok) {
    return new Response(JSON.stringify({ error: 'llm_error', sources }), {
      status: geminiResp.status === 429 ? 429 : 502,
      headers: { ...cors, 'Content-Type': 'application/json' },
    });
  }

  const data = await geminiResp.json();
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text || '';
  return new Response(JSON.stringify({ response: text, sources }), {
    status: 200, headers: { ...cors, 'Content-Type': 'application/json' },
  });
}
