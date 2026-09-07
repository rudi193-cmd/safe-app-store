// KB 2026B306 — install-time capability composition.
//
// If an organ is installed, it is connected, and being connected is disclosed
// as two lists: what becomes possible, and what becomes reachable. Enabling
// without disclosure is refused. Enabling when the server does not actually
// offer the organ is refused. Absence is a state, not a failure of the seat.
//
// Authorization is the intersection of a disclosed install and tools the
// ratified willow-mcp --serve instance actually lists. Same shape as Kart
// bind_try: declare, fail closed, disclose at install.

export const PRODUCT_NAME = 'Willow';

/** Ratified local OAuth/MCP URL. Signing (Nestor UI) holds 8765; --serve is 8768. Never 8766. */
export const WILLOW_MCP_SERVE_LOCAL = 'http://127.0.0.1:8768';

export const NEVER_REACH_PORTS = Object.freeze(['8766']);

export const STORAGE_KEY = 'willow.composition';

export const ORGANS = Object.freeze([
  {
    id: 'grove',
    name: 'Grove',
    possible: [
      'whoami, dispatch_list/read/send, verify_handoff, agent_clear',
      'grove_* readers when the serve instance lists them',
    ],
    reachable: [
      'willow-mcp --serve only (local http://127.0.0.1:8768)',
      'remote: Pangolin in front of that same --serve process',
      'Grove HTML on :8766 stays loopback on the box — this app never opens it',
    ],
    detectTools: ['whoami', 'dispatch_list', 'grove_inbox', 'grove_agents'],
  },
  {
    id: 'nestor',
    name: 'Nestor',
    possible: ['nestor_ask / nestor_tool_route — sealed answers first', 'knowledge_verify'],
    reachable: [
      'the same willow-mcp --serve the seat already signed into',
      'never a second bind of the Grove desk page',
    ],
    detectTools: ['nestor_ask', 'nestor_tool_route', 'knowledge_verify'],
  },
  {
    id: 'jeles',
    name: 'Jeles',
    possible: ['corpus_search / corpus_verify_claim via federation_call'],
    reachable: [
      'federated MCP only — five keys at once (manifest, per-tool grant, ratified registry, consent.federation, net lease)',
    ],
    detectTools: ['federation_call', 'corpus_search', 'corpus_web_search'],
  },
  {
    id: 'hornbook',
    name: 'Hornbook',
    possible: ['the Hornbook organ this install actually ships'],
    reachable: ['only hosts that organ already reaches — no extra ports from this seat'],
    detectTools: ['specialist_list', 'specialist_get'],
  },
]);

export function emptyState() {
  return { disclosed: {}, enabled: {} };
}

export function loadState(storage = globalThis.localStorage) {
  try {
    const raw = storage?.getItem?.(STORAGE_KEY);
    if (!raw) return emptyState();
    const parsed = JSON.parse(raw);
    return {
      disclosed: parsed.disclosed && typeof parsed.disclosed === 'object' ? parsed.disclosed : {},
      enabled: parsed.enabled && typeof parsed.enabled === 'object' ? parsed.enabled : {},
    };
  } catch {
    return emptyState();
  }
}

export function saveState(state, storage = globalThis.localStorage) {
  storage?.setItem?.(STORAGE_KEY, JSON.stringify(state));
  return state;
}

export function disclose(state, organId) {
  if (!ORGANS.some((o) => o.id === organId)) throw new Error(`unknown organ: ${organId}`);
  return {
    disclosed: { ...state.disclosed, [organId]: true },
    enabled: { ...state.enabled },
  };
}

export function setEnabled(state, organId, on) {
  if (!ORGANS.some((o) => o.id === organId)) throw new Error(`unknown organ: ${organId}`);
  if (on && !state.disclosed[organId]) {
    throw new Error(`fail closed: ${organId} was not disclosed`);
  }
  return {
    disclosed: { ...state.disclosed },
    enabled: { ...state.enabled, [organId]: Boolean(on) },
  };
}

export function organPresent(organId, presentTools) {
  const organ = ORGANS.find((o) => o.id === organId);
  if (!organ) return false;
  const tools = presentTools || [];
  return organ.detectTools.some((name) => tools.includes(name));
}

/** Enabled in settings AND the serve instance actually listed a detecting tool. */
export function isLive(state, organId, presentTools) {
  return Boolean(state.enabled[organId]) && organPresent(organId, presentTools);
}

export function toolDefsFor(allDefs, state, presentTools) {
  return (allDefs || []).filter((def) => {
    if (!def.organ) return true;
    return isLive(state, def.organ, presentTools);
  });
}

export function serveUrlLooksForbidden(url) {
  try {
    const parsed = new URL(url);
    return NEVER_REACH_PORTS.includes(parsed.port) || parsed.port === '8766';
  } catch {
    return /:8766(?:\/|$)/.test(String(url));
  }
}
