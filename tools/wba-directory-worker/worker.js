// Signed Web Bot Auth key directory for MarketfaunaBot, as a Cloudflare Worker,
// plus an owned verifier (v2, 2026-09-16) used as a controlled test bed.
//
// Routes
//   GET /.well-known/http-message-signatures-directory
//       The signed directory Cloudflare requires (developers.cloudflare.com/bots/reference/
//       bot-verification/web-bot-auth/, read 2026-09-13): Content-Type
//       application/http-message-signatures-directory+json, one Ed25519 signature per key over
//       ("@authority";req), tag http-message-signatures-directory, keyid = RFC 7638 thumbprint.
//   GET /verify
//       Verifies the incoming request's RFC 9421 signature (tag web-bot-auth) and returns a JSON
//       verdict with every check's result. 400 when the three headers are absent, 401 when present
//       but not verified, 200 when verified. Keys are looked up first in this Worker's own
//       directory, else fetched from the Signature-Agent's directory (the directory response's own
//       signature is NOT verified in this version; the verdict says so).
//   GET /gated/sample.json
//       A resource served only to a verified request: the "demonstrated useful task" control.
//   anything else -> 302 to the purpose page.
//
// The private key arrives only as the secret WBA_PRIVATE_KEY_PKCS8_B64 (base64 of the DER
// PKCS#8 key). Only kty, crv and x are ever written to a response.
// Mirrors tools/wba.py (sign_request / verify_request), whose tests cover the same signature base.

const DIRECTORY_PATH = "/.well-known/http-message-signatures-directory";
const MEDIA_TYPE = "application/http-message-signatures-directory+json";
const REQUEST_TAG = "web-bot-auth";
const CLOCK_SKEW_S = 60;

const enc = new TextEncoder();
const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const b64url = (buf) => b64(buf).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const b64decode = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

async function thumbprint(jwk) {
  const canonical = JSON.stringify({ crv: jwk.crv, kty: jwk.kty, x: jwk.x });
  return b64url(await crypto.subtle.digest("SHA-256", enc.encode(canonical)));
}

async function loadKey(env) {
  if (!env.WBA_PRIVATE_KEY_PKCS8_B64) throw new Error("secret WBA_PRIVATE_KEY_PKCS8_B64 not set");
  const der = b64decode(env.WBA_PRIVATE_KEY_PKCS8_B64);
  const priv = await crypto.subtle.importKey("pkcs8", der, { name: "Ed25519" }, true, ["sign"]);
  const exported = await crypto.subtle.exportKey("jwk", priv); // contains d; used only to read x
  const jwk = { kty: "OKP", crv: "Ed25519", x: exported.x };
  return { priv, jwk, kid: await thumbprint(jwk) };
}

// ------------------------------------------------------------------ RFC 9421 parsing (mirrors wba.py)

function parseSignatureInput(value) {
  const m = /^\s*([A-Za-z0-9_-]+)=(.*)$/s.exec(value);
  if (!m) throw new Error("bad Signature-Input");
  const label = m[1];
  const rest = m[2].trim();
  const m2 = /^\((.*?)\)(.*)$/s.exec(rest);
  if (!m2) throw new Error("bad Signature-Input inner list");
  const idents = [];
  const identRe = /"([^"]+)"((?:;[a-z]+(?:=(?:"[^"]*"|[^;\s)]+))?)*)/g;
  let im;
  while ((im = identRe.exec(m2[1])) !== null) idents.push(`"${im[1]}"${im[2]}`);
  const params = {};
  const paramRe = /;([a-z]+)(?:=("(?:[^"\\]|\\.)*"|[^;]+))?/g;
  let pm;
  while ((pm = paramRe.exec(m2[2])) !== null) {
    const k = pm[1];
    const v = pm[2];
    if (v === undefined) params[k] = true;
    else if (v.startsWith('"')) params[k] = v.slice(1, -1);
    else params[k] = /^\d+$/.test(v) ? parseInt(v, 10) : v;
  }
  return { label, ser: rest, idents, params };
}

function parseSignature(value, label) {
  const m = new RegExp(`(?:^|,)\\s*${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=:([A-Za-z0-9+/=]+):`).exec(value);
  if (!m) throw new Error("no signature for label " + label);
  return b64decode(m[1]);
}

function componentValue(ident, request, url) {
  const name = ident.split('"')[1];
  if (name === "@authority") return (request.headers.get("host") || url.host).toLowerCase();
  if (name === "@method") return request.method.toUpperCase();
  if (name === "@path") return url.pathname || "/";
  if (name === "@scheme") return url.protocol.replace(":", "").toLowerCase();
  if (name === "@target-uri") return url.toString();
  if (name === "@query") return "?" + url.search.replace(/^\?/, "");
  if (name.startsWith("@")) throw new Error("unsupported derived component " + name);
  const v = request.headers.get(name);
  if (v === null) throw new Error("missing header " + name);
  return v.split(/\s+/).filter(Boolean).join(" ");
}

function signatureBase(components, ser) {
  return components.map(([i, v]) => `${i}: ${v}`).concat([`"@signature-params": ${ser}`]).join("\n");
}

// ------------------------------------------------------------------ key lookup

async function keysFromDirectory(agentUrl, own) {
  // Own directory first (no network); otherwise fetch the Signature-Agent's directory.
  const result = { source: null, directory_signature_verified: false, error: null, keys: {} };
  let host;
  try { host = new URL(agentUrl).host.toLowerCase(); } catch (e) { result.error = "Signature-Agent is not a URL"; return result; }
  if (host === own.host) {
    result.source = "own directory (in-process)";
    result.keys[own.kid] = own.jwk;
    return result;
  }
  try {
    const r = await fetch(`https://${host}${DIRECTORY_PATH}`, {
      headers: { accept: MEDIA_TYPE, "user-agent": "MarketfaunaVerifier/1.0 (+https://marketfauna.com/bot.html)" },
      signal: AbortSignal.timeout(5000),
    });
    result.source = `fetched https://${host}${DIRECTORY_PATH} (status ${r.status})`;
    if (!r.ok) { result.error = "directory fetch failed"; return result; }
    const body = await r.json();
    for (const k of body.keys || []) {
      if (k.kty === "OKP" && k.crv === "Ed25519" && typeof k.x === "string") result.keys[await thumbprint(k)] = { kty: k.kty, crv: k.crv, x: k.x };
    }
  } catch (e) {
    result.error = "directory fetch error: " + (e && e.name ? e.name : String(e));
  }
  return result;
}

// ------------------------------------------------------------------ verification

async function verifyRequest(request, url, own) {
  const now = Math.floor(Date.now() / 1000);
  const h = request.headers;
  const verdict = {
    verified: false, reason: null, http_status: 401, now, authority: (h.get("host") || url.host).toLowerCase(),
    headers_present: { "signature-input": h.has("signature-input"), signature: h.has("signature"), "signature-agent": h.has("signature-agent") },
    checks: {}, keyid: null, signature_agent: h.get("signature-agent"), key_lookup: null,
    note: "Owned verifier on the bot operator's own Worker; a control for method testing, not a destination site's decision. The Signature-Agent directory's response signature is not verified in this version.",
  };
  if (!verdict.headers_present["signature-input"] || !verdict.headers_present.signature || !verdict.headers_present["signature-agent"]) {
    verdict.reason = "missing signature / signature-input / signature-agent headers";
    verdict.http_status = 400;
    return verdict;
  }
  let parsed, sig;
  try {
    parsed = parseSignatureInput(h.get("signature-input"));
    sig = parseSignature(h.get("signature"), parsed.label);
    verdict.checks.parsed = true;
  } catch (e) {
    verdict.checks.parsed = false;
    verdict.reason = "malformed: " + e.message;
    return verdict;
  }
  const p = parsed.params;
  verdict.keyid = p.keyid || null;
  verdict.params = { alg: p.alg, tag: p.tag, created: p.created, expires: p.expires, nonce_present: typeof p.nonce === "string" };
  verdict.covered = parsed.idents;
  const fail = (key, reason) => { verdict.checks[key] = false; verdict.reason = reason; return verdict; };
  verdict.checks.tag = p.tag === REQUEST_TAG; if (!verdict.checks.tag) return fail("tag", "wrong tag");
  verdict.checks.alg = (p.alg || "ed25519") === "ed25519"; if (!verdict.checks.alg) return fail("alg", "unsupported alg");
  verdict.checks.authority_covered = parsed.idents.includes('"@authority"'); if (!verdict.checks.authority_covered) return fail("authority_covered", "@authority not covered");
  verdict.checks.signature_agent_covered = parsed.idents.includes('"signature-agent"'); if (!verdict.checks.signature_agent_covered) return fail("signature_agent_covered", "signature-agent not covered");
  verdict.checks.created_expires_present = Number.isInteger(p.created) && Number.isInteger(p.expires); if (!verdict.checks.created_expires_present) return fail("created_expires_present", "created/expires missing");
  verdict.checks.not_future = now >= p.created - CLOCK_SKEW_S; if (!verdict.checks.not_future) return fail("not_future", "created in the future");
  verdict.checks.not_expired = now <= p.expires; if (!verdict.checks.not_expired) return fail("not_expired", "expired");
  const agentUrl = (h.get("signature-agent") || "").trim().replace(/^"|"$/g, "");
  const lookup = await keysFromDirectory(agentUrl, own);
  verdict.key_lookup = { source: lookup.source, directory_signature_verified: lookup.directory_signature_verified, error: lookup.error, keys_found: Object.keys(lookup.keys).length };
  const jwk = lookup.keys[p.keyid];
  verdict.checks.keyid_known = !!jwk; if (!jwk) return fail("keyid_known", "unknown keyid");
  let components;
  try {
    components = parsed.idents.map((i) => [i, componentValue(i, request, url)]);
  } catch (e) {
    return fail("components", "component error: " + e.message);
  }
  const base = signatureBase(components, parsed.ser);
  let ok = false;
  try {
    const pub = await crypto.subtle.importKey("jwk", { kty: "OKP", crv: "Ed25519", x: jwk.x }, { name: "Ed25519" }, true, ["verify"]);
    ok = await crypto.subtle.verify({ name: "Ed25519" }, pub, sig, enc.encode(base));
  } catch (e) {
    return fail("signature", "verify error: " + (e && e.name ? e.name : String(e)));
  }
  verdict.checks.signature = ok;
  if (!ok) { verdict.reason = "signature invalid"; return verdict; }
  verdict.verified = true; verdict.reason = "ok"; verdict.http_status = 200;
  return verdict;
}

// ------------------------------------------------------------------ routes

async function directoryResponse(request, env, url) {
  if (request.method !== "GET" && request.method !== "HEAD") return new Response("method not allowed", { status: 405 });
  const { priv, jwk, kid } = await loadKey(env);
  const authority = (request.headers.get("host") || url.host).toLowerCase();
  const now = Math.floor(Date.now() / 1000);
  const nonce = b64(crypto.getRandomValues(new Uint8Array(48)));
  const params =
    `("@authority";req);alg="ed25519";keyid="${kid}";nonce="${nonce}";` +
    `tag="http-message-signatures-directory";created=${now};expires=${now + 300}`;
  const base = `"@authority";req: ${authority}\n"@signature-params": ${params}`;
  const sig = await crypto.subtle.sign({ name: "Ed25519" }, priv, enc.encode(base));
  const body = JSON.stringify({ keys: [jwk] });
  return new Response(request.method === "HEAD" ? null : body, {
    status: 200,
    headers: { "Content-Type": MEDIA_TYPE, "Signature-Input": `sig1=${params}`, "Signature": `sig1=:${b64(sig)}:`, "Cache-Control": "no-store" },
  });
}

const json = (obj, status) => new Response(JSON.stringify(obj, null, 1), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === DIRECTORY_PATH) return directoryResponse(request, env, url);
    if (url.pathname === "/verify" || url.pathname === "/gated/sample.json") {
      const { jwk, kid } = await loadKey(env);
      const own = { host: url.host.toLowerCase(), jwk, kid };
      const verdict = await verifyRequest(request, url, own);
      if (url.pathname === "/verify") return json(verdict, verdict.http_status);
      if (verdict.verified) {
        return json({ ok: true, resource: "sample.json", served_to_keyid: verdict.keyid, served_at: verdict.now,
          message: "Served only to a request whose Web Bot Auth signature verified against the Signature-Agent's directory." }, 200);
      }
      return json({ ok: false, resource: "sample.json", verdict }, verdict.http_status);
    }
    return Response.redirect(env.PURPOSE_URL || "https://marketfauna.com/bot.html", 302);
  },
};
