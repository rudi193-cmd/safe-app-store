// A thin client for willow-mcp's serve mode — the fleet's orchestrator seat,
// reached over HTTP instead of the stdio transport every other willow-mcp
// client uses.
//
// Why this is safe to add to a browser tab with no backend: willow-mcp's
// `--serve` mode is itself an OAuth 2.1 resource server (PKCE + dynamic
// client registration), and the identity a call runs as comes from the
// *signed-in session's operator-confirmed binding*, never from anything the
// caller asserts (see willow-mcp docs/design/human-orchestrator.md and
// tests/test_serve_mode_gate.py). A browser tab that signs in with the
// operator's own Google/Apple account and has been bound to an app_id by
// `willow-mcp confirm-binding` on the host is, to the server, exactly the
// same trust class as a human at an orchestrator IDE session — not a
// specialist agent self-declaring authority. The security boundary is
// entirely server-side; this file is a dumb client of it.
//
// What this file structurally cannot prove, stated the way this app's other
// external-service surfaces are: no test here talks to a real willow-mcp
// instance or a real Google/Apple sign-in. The pure helpers (PKCE, the
// authorize URL, SSE framing) are unit-tested, and discoverMetadata /
// registerClient are tested against a mocked fetch — but the popup round
// trip, a real discovery document, and token refresh are exercised only by
// hand. Treat every network path below as `assumed` against the MCP
// Authorization spec and willow-mcp's own route names, not `measured`, until
// it has actually completed a sign-in against a running instance.

const CLIENT_NAME = 'jarvis';
const MCP_PROTOCOL_VERSION = '2025-06-18';
const OAUTH_REDIRECT_MESSAGE = 'willow-oauth-redirect';

const CONFIG_KEY = 'jarvis.willowConfig'; // { baseUrl, clientId, authorizationEndpoint, tokenEndpoint } — not secret
const ACCESS_TOKEN_KEY = 'jarvis.willowAccessToken';
const REFRESH_TOKEN_KEY = 'jarvis.willowRefreshToken';

// --- PKCE + framing, pure enough to unit test without a network -------------

function toBase64Url(bytes) {
  let str = '';
  for (const b of bytes) str += String.fromCharCode(b);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** RFC 7636 PKCE pair. `verifier` is kept client-side; `challenge` is sent. */
export async function generatePkce() {
  const verifier = toBase64Url(crypto.getRandomValues(new Uint8Array(32)));
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return { verifier, challenge: toBase64Url(new Uint8Array(digest)), method: 'S256' };
}

export function randomState() {
  return toBase64Url(crypto.getRandomValues(new Uint8Array(16)));
}

/**
 * Build the `/authorize` redirect URL. A pure function of its inputs so the
 * query-param shape is testable without opening a real popup.
 */
export function buildAuthorizeUrl({ authorizationEndpoint, clientId, redirectUri, challenge, state }) {
  const url = new URL(authorizationEndpoint);
  url.searchParams.set('response_type', 'code');
  url.searchParams.set('client_id', clientId);
  url.searchParams.set('redirect_uri', redirectUri);
  url.searchParams.set('code_challenge', challenge);
  url.searchParams.set('code_challenge_method', 'S256');
  url.searchParams.set('state', state);
  url.searchParams.set('scope', 'willow');
  return url.toString();
}

/**
 * MCP's streamable-http transport may answer JSON directly or as an SSE
 * stream carrying JSON-RPC messages in `data:` lines. This app makes one
 * request per call and wants the one response, so it takes the last
 * complete JSON-RPC message in the stream rather than staying subscribed.
 */
export function parseSseJsonRpc(text) {
  let last = null;
  for (const block of text.split('\n\n')) {
    const line = block.split('\n').find((l) => l.startsWith('data:'));
    if (!line) continue;
    try {
      last = JSON.parse(line.slice(5).trim());
    } catch {
      // A partial block at the end of the buffer — not the message we want.
    }
  }
  if (!last) throw new Error('willow-mcp: no JSON-RPC message found in event stream');
  return last;
}

// --- discovery + dynamic client registration ---------------------------------

export async function discoverMetadata(baseUrl) {
  const res = await fetch(`${baseUrl}/.well-known/oauth-authorization-server`);
  if (res.ok) return res.json();
  // Fallback to the MCP SDK's conventional route names. Not verified against
  // a running server — see the file-level note on what is assumed here.
  return {
    authorization_endpoint: `${baseUrl}/authorize`,
    token_endpoint: `${baseUrl}/token`,
    registration_endpoint: `${baseUrl}/register`,
  };
}

export async function registerClient(meta, redirectUri) {
  const res = await fetch(meta.registration_endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_name: CLIENT_NAME,
      redirect_uris: [redirectUri],
      grant_types: ['authorization_code', 'refresh_token'],
      response_types: ['code'],
      // A static page with no build step cannot keep a client_secret, so this
      // registers as a public client — PKCE is what protects the code
      // exchange instead, per RFC 8252 §8.4.
      token_endpoint_auth_method: 'none',
    }),
  });
  if (!res.ok) throw new Error(`willow-mcp: client registration failed (${res.status}): ${await res.text()}`);
  return res.json();
}

// --- the popup round trip -----------------------------------------------------

/**
 * Runs at module load, on every page (including inside the sign-in popup).
 * A normal load has no `code`/`error` in the query string and this is a
 * no-op. The popup's redirect back to this same page's URL is the only case
 * with `window.opener` set, so a bare reload with a stale query string from
 * a copied URL can never be mistaken for a completed sign-in.
 *
 * Returns true when it handled a popup callback — the caller (app.js) should
 * skip the rest of boot() in that case, since this window's only job was to
 * hand the result back and close.
 */
export function handleOAuthRedirect() {
  const params = new URLSearchParams(location.search);
  if (!params.has('code') && !params.has('error')) return false;
  if (!window.opener) return false;
  window.opener.postMessage(
    {
      type: OAUTH_REDIRECT_MESSAGE,
      code: params.get('code'),
      state: params.get('state'),
      error: params.get('error'),
    },
    location.origin,
  );
  document.title = 'Jarvis — sign-in complete, you can close this window';
  window.close();
  return true;
}

function popupAuthorize(url) {
  return new Promise((resolve, reject) => {
    const popup = window.open(url, 'willow-oauth', 'width=480,height=640');
    if (!popup) {
      reject(new Error('willow-mcp: sign-in popup was blocked — allow popups for this site and try again'));
      return;
    }
    let settled = false;
    const onMessage = (event) => {
      if (event.origin !== location.origin || event.data?.type !== OAUTH_REDIRECT_MESSAGE) return;
      settled = true;
      window.removeEventListener('message', onMessage);
      clearInterval(poll);
      resolve(event.data);
    };
    window.addEventListener('message', onMessage);
    const poll = setInterval(() => {
      if (!popup.closed) return;
      clearInterval(poll);
      window.removeEventListener('message', onMessage);
      if (!settled) reject(new Error('willow-mcp: sign-in window was closed before completing'));
    }, 500);
  });
}

// --- the JSON-RPC/MCP call surface --------------------------------------------

class WillowClient {
  #baseUrl;
  #accessToken;
  #id = 0;
  #initialized = null;

  constructor({ baseUrl, accessToken }) {
    this.#baseUrl = baseUrl.replace(/\/$/, '');
    this.#accessToken = accessToken;
  }

  async #rpc(method, params) {
    const res = await fetch(`${this.#baseUrl}/mcp`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json, text/event-stream',
        Authorization: `Bearer ${this.#accessToken}`,
      },
      body: JSON.stringify({ jsonrpc: '2.0', id: ++this.#id, method, params }),
    });
    const contentType = res.headers.get('content-type') || '';
    const payload = contentType.includes('text/event-stream')
      ? parseSseJsonRpc(await res.text())
      : await res.json();
    if (res.status === 401) throw Object.assign(new Error('willow-mcp: access token expired or invalid'), { code: 401 });
    if (!res.ok) throw new Error(`willow-mcp ${method} failed (${res.status}): ${JSON.stringify(payload)}`);
    if (payload.error) throw new Error(`willow-mcp ${method}: ${payload.error.message}`);
    return payload.result;
  }

  #ensureInitialized() {
    if (!this.#initialized) {
      this.#initialized = this.#rpc('initialize', {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: { name: CLIENT_NAME, version: '0.1.0' },
      });
    }
    return this.#initialized;
  }

  async callTool(name, args = {}) {
    await this.#ensureInitialized();
    const result = await this.#rpc('tools/call', { name, arguments: args });
    const text = (result.content || []).map((b) => b.text).filter(Boolean).join('\n');
    let data = null;
    try {
      data = JSON.parse(text);
    } catch {
      // Not every tool result is JSON; leave data null and let text carry it.
    }
    return { text, data, isError: Boolean(result.isError) };
  }
}

// --- session: config persistence + token refresh ------------------------------

/**
 * Holds the willow-mcp connection across the app's lifetime. Non-secret
 * config (base URL, the registered client_id, the discovered endpoints)
 * lives in localStorage next to this app's other settings; the access and
 * refresh tokens go through the same `platform.keys` store the Anthropic API
 * key uses, so they land on whatever the best available rung is (app-private
 * preferences natively, localStorage on the web) without a second storage
 * decision being made here.
 */
export class WillowSession {
  #keys;
  client = null;
  baseUrl = null;

  constructor({ keys }) {
    this.#keys = keys;
  }

  async load() {
    const raw = localStorage.getItem(CONFIG_KEY);
    if (!raw) return this;
    this.#config = JSON.parse(raw);
    this.baseUrl = this.#config.baseUrl;
    const accessToken = await this.#keys.get(ACCESS_TOKEN_KEY);
    if (accessToken) this.client = new WillowClient({ baseUrl: this.baseUrl, accessToken });
    return this;
  }

  #config = null;

  get connected() {
    return Boolean(this.client);
  }

  async signIn(baseUrl) {
    const trimmed = baseUrl.replace(/\/$/, '');
    const meta = await discoverMetadata(trimmed);
    const redirectUri = `${location.origin}${location.pathname}`;
    const registration = await registerClient(meta, redirectUri);
    const { verifier, challenge } = await generatePkce();
    const state = randomState();
    const authorizeUrl = buildAuthorizeUrl({
      authorizationEndpoint: meta.authorization_endpoint,
      clientId: registration.client_id,
      redirectUri,
      challenge,
      state,
    });

    const redirect = await popupAuthorize(authorizeUrl);
    if (redirect.error) throw new Error(`willow-mcp: sign-in denied (${redirect.error})`);
    if (redirect.state !== state) throw new Error('willow-mcp: state mismatch on sign-in redirect — aborting');

    const tokens = await this.#exchangeToken(meta.token_endpoint, {
      grant_type: 'authorization_code',
      code: redirect.code,
      redirect_uri: redirectUri,
      client_id: registration.client_id,
      code_verifier: verifier,
    });

    this.#config = {
      baseUrl: trimmed,
      clientId: registration.client_id,
      authorizationEndpoint: meta.authorization_endpoint,
      tokenEndpoint: meta.token_endpoint,
    };
    localStorage.setItem(CONFIG_KEY, JSON.stringify(this.#config));
    await this.#storeTokens(tokens);
    this.baseUrl = trimmed;
    this.client = new WillowClient({ baseUrl: trimmed, accessToken: tokens.access_token });
    return this;
  }

  async signOut() {
    await this.#keys.remove(ACCESS_TOKEN_KEY);
    await this.#keys.remove(REFRESH_TOKEN_KEY);
    localStorage.removeItem(CONFIG_KEY);
    this.#config = null;
    this.baseUrl = null;
    this.client = null;
  }

  /** Runs a tool call, refreshing the access token once on a 401 before giving up. */
  async callTool(name, args) {
    if (!this.client) throw new Error('willow-mcp: not signed in — open settings and connect');
    try {
      return await this.client.callTool(name, args);
    } catch (err) {
      if (err.code !== 401) throw err;
      await this.#refresh();
      return this.client.callTool(name, args);
    }
  }

  async #refresh() {
    const refreshToken = await this.#keys.get(REFRESH_TOKEN_KEY);
    if (!refreshToken || !this.#config) {
      throw new Error('willow-mcp: access token expired and no refresh token is stored — sign in again');
    }
    const tokens = await this.#exchangeToken(this.#config.tokenEndpoint, {
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
      client_id: this.#config.clientId,
    });
    await this.#storeTokens(tokens);
    this.client = new WillowClient({ baseUrl: this.baseUrl, accessToken: tokens.access_token });
  }

  async #exchangeToken(tokenEndpoint, body) {
    const res = await fetch(tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams(body),
    });
    if (!res.ok) throw new Error(`willow-mcp: token exchange failed (${res.status}): ${await res.text()}`);
    return res.json();
  }

  async #storeTokens(tokens) {
    await this.#keys.set(ACCESS_TOKEN_KEY, tokens.access_token);
    if (tokens.refresh_token) await this.#keys.set(REFRESH_TOKEN_KEY, tokens.refresh_token);
  }
}
