// Local test of the Worker's /verify and /gated routes under Node's WebCrypto with a throwaway key.
// Signs requests the way tools/wba.py sign_request does, then runs worker.fetch on each control.
// Usage: node test-verify.mjs   (exit 0 when every control gives the expected status and reason)
import worker from "./worker.js";

const enc = new TextEncoder();
const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const b64url = (buf) => b64(buf).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

const kp = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const pkcs8 = await crypto.subtle.exportKey("pkcs8", kp.privateKey);
const pubJwk = await crypto.subtle.exportKey("jwk", kp.publicKey);
const jwk = { kty: "OKP", crv: "Ed25519", x: pubJwk.x };
const kid = b64url(await crypto.subtle.digest("SHA-256", enc.encode(JSON.stringify({ crv: jwk.crv, kty: jwk.kty, x: jwk.x }))));
const authority = "verifier.test";
const env = { WBA_PRIVATE_KEY_PKCS8_B64: b64(pkcs8), PURPOSE_URL: "https://marketfauna.com/bot.html" };

async function signed(path, { agent = `https://${authority}`, keyid = kid, now = Math.floor(Date.now() / 1000), expiresIn = 60, tamper = false, tag = "web-bot-auth", key = kp.privateKey } = {}) {
  const agentHeader = `"${agent}"`;
  const nonce = b64(crypto.getRandomValues(new Uint8Array(48)));
  const ser = `("@authority" "signature-agent");alg="ed25519";keyid="${keyid}";nonce="${nonce}";tag="${tag}";created=${now};expires=${now + expiresIn}`;
  const base = `"@authority": ${authority}\n"signature-agent": ${agentHeader}\n"@signature-params": ${ser}`;
  const sigBuf = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, key, enc.encode(base)));
  if (tamper) sigBuf[0] ^= 1;
  return new Request(`https://${authority}${path}`, { headers: { host: authority, "Signature-Agent": agentHeader, "Signature-Input": `sig1=${ser}`, Signature: `sig1=:${b64(sigBuf)}:` } });
}

const other = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const cases = [
  ["unsigned", new Request(`https://${authority}/verify`, { headers: { host: authority } }), 400, /missing/],
  ["valid", await signed("/verify"), 200, /^ok$/],
  ["tampered", await signed("/verify", { tamper: true }), 401, /signature invalid/],
  ["expired", await signed("/verify", { now: Math.floor(Date.now() / 1000) - 3600 }), 401, /expired/],
  ["future", await signed("/verify", { now: Math.floor(Date.now() / 1000) + 3600 }), 401, /future/],
  ["unknown keyid", await signed("/verify", { keyid: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" }), 401, /unknown keyid/],
  ["wrong key, right keyid", await signed("/verify", { key: other.privateKey }), 401, /signature invalid/],
  ["wrong tag", await signed("/verify", { tag: "http-message-signatures-directory" }), 401, /wrong tag/],
  ["external agent, not allowlisted (no fetch)", await signed("/verify", { agent: "https://example.com" }), 401, /not verified by this test bed/],
  ["gated valid", await signed("/gated/sample.json"), 200, null],
  ["gated unsigned", new Request(`https://${authority}/gated/sample.json`, { headers: { host: authority } }), 400, null],
];

let failures = 0;
for (const [name, req, wantStatus, wantReason] of cases) {
  const res = await worker.fetch(req, env);
  const body = await res.json();
  const reason = body.reason ?? body.verdict?.reason ?? (body.ok ? "ok" : "");
  const pass = res.status === wantStatus && (wantReason === null || wantReason.test(reason));
  if (!pass) failures++;
  console.log(`${pass ? "PASS" : "FAIL"} ${name}: status ${res.status} (want ${wantStatus}) reason "${reason}"`);
}
console.log(failures === 0 ? "all controls behave as specified" : `${failures} control(s) failed`);
process.exit(failures === 0 ? 0 : 1);
