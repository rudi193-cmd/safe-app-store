// NASA Archive — Oral History Chat Edge Function
// Deploy: supabase functions deploy oral-chat
// Uses Groq (free tier) to power conversational oral history capture.
//
// POST body: { message: string, slug: string, history: ChatMessage[] }
// Returns:   { reply: string, extracted?: ExtractedData }

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface RequestBody {
  message: string;
  slug: string;
  history?: ChatMessage[];
}

// Abuse guards — this function fronts a metered LLM key.
const MAX_MESSAGE_CHARS = 4000;
const MAX_HISTORY_TURNS = 10;
const MAX_HISTORY_CHARS = 2000;
const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;

// Only ever forward user/assistant turns — a caller-supplied "system" role
// would let the client inject instructions above the archive's own prompt.
function sanitizeHistory(history: unknown): ChatMessage[] {
  if (!Array.isArray(history)) return [];
  return history
    .filter((m): m is ChatMessage =>
      !!m && typeof m === 'object' &&
      (m.role === 'user' || m.role === 'assistant') &&
      typeof m.content === 'string')
    .slice(-MAX_HISTORY_TURNS)
    .map(m => ({ role: m.role, content: m.content.slice(0, MAX_HISTORY_CHARS) }));
}

const SYSTEM_PROMPT = `You are the NASA oral historian — the voice of the North America Scootering Archive.

Your job: help community members share their memories of scooter rallies. You listen, ask follow-up questions, and help people tell their stories in their own words.

Cultural principles you embody:
- "Names Given Not Chosen" — people go by their club names, not legal names. Always use what they give you.
- "Someone Always Stops" — rescues on the road are fundamental community stories. Ask about them.
- "Grief Makes Space" — if someone mentions someone who has passed, receive it gently.
- "Corrections Not Erasure" — if someone says the date was wrong, or the bike was different, that's valuable. Record it.
- "Recognition Not Instruction" — you're here to witness, not to teach.

Your approach:
1. Ask about specific moments, not general impressions
2. Follow up on names that come up naturally
3. Ask about bikes — make, model, what broke, garden art status
4. Ask about rescues — who saved them, who they saved
5. Ask about how people got their names (especially if it was drunk)
6. Keep it conversational — this is a bar story, not a deposition

When you have enough information, you can say: "Want me to save that story to the archive?"

Keep replies short (2-4 sentences). Ask one follow-up question at a time.`;

Deno.serve(async (req: Request) => {
  // CORS headers
  const corsHeaders = {
    'Access-Control-Allow-Origin': 'https://nasa-archive-site.pages.dev',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  };

  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  if (req.method !== 'POST') {
    return new Response('Method not allowed', { status: 405, headers: corsHeaders });
  }

  try {
    const body: RequestBody = await req.json();
    const { message, slug } = body;
    const history = sanitizeHistory(body.history);

    if (typeof message !== 'string' || !message.trim() || typeof slug !== 'string' || !slug.trim()) {
      return new Response(JSON.stringify({ error: 'message and slug required' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    if (message.length > MAX_MESSAGE_CHARS) {
      return new Response(JSON.stringify({ error: `message too long (max ${MAX_MESSAGE_CHARS} chars)` }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    if (!SLUG_RE.test(slug)) {
      return new Response(JSON.stringify({ error: 'invalid slug' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    // Pull existing stories for this rally to give context
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );

    const { data: existingStories } = await supabase
      .from('oral_stories')
      .select('content, narrator:oral_persons(club_name)')
      .eq('archive_slug', slug)
      .limit(5);

    const rallyContext = existingStories?.length
      ? `\n\nExisting stories for this rally:\n${existingStories.map(s =>
          `- ${s.narrator?.club_name || 'Anonymous'}: "${s.content?.substring(0, 150)}..."`
        ).join('\n')}`
      : '';

    // Build messages for Groq
    const messages = [
      {
        role: 'system',
        content: SYSTEM_PROMPT + rallyContext +
          `\n\nThe user is sharing memories about the rally with slug: "${slug}"`,
      },
      ...history, // sanitized: user/assistant only, last 10 turns, length-capped
      { role: 'user', content: message },
    ];

    // Call Groq (free tier)
    const groqKey = Deno.env.get('GROQ_API_KEY');
    if (!groqKey) {
      return new Response(JSON.stringify({ error: 'LLM not configured' }), {
        status: 503,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const groqRes = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${groqKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'llama-3.1-8b-instant',
        messages,
        max_tokens: 300,
        temperature: 0.7,
      }),
    });

    if (!groqRes.ok) {
      const err = await groqRes.text();
      console.error('Groq error:', err);
      return new Response(JSON.stringify({ error: 'LLM unavailable' }), {
        status: 503,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const groqData = await groqRes.json();
    const reply = groqData.choices?.[0]?.message?.content ?? 'I had trouble with that. Try again?';

    return new Response(JSON.stringify({ reply }), {
      status: 200,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });

  } catch (err) {
    console.error('oral-chat error:', err);
    return new Response(JSON.stringify({ error: 'Internal error' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
