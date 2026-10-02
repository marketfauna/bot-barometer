import { readFileSync } from "node:fs";
import { verify } from "web-bot-auth";
import { verifierFromJWK } from "web-bot-auth/crypto";
const fx = JSON.parse(readFileSync(process.argv[2], "utf8"));
const verifier = await verifierFromJWK({ ...fx.key.jwk, alg: "EdDSA" });
const seen = new Set();
const out = [];
for (const c of fx.requests) {
  const req = new Request(c.received_at_url || c.url, { method: c.method, headers: c.headers });
  let verdict, reason;
  try {
    await verify(req, {
      now: new Date(c.now * 1000),
      resolver: (cand) => { if (cand.keyid !== verifier.keyid) throw new Error("unknown key " + cand.keyid); return verifier; },
      validate: ({ nonce }) => { if (seen.has(nonce)) throw new Error("replayed nonce"); seen.add(nonce); },
    });
    verdict = "VERIFIED"; reason = "ok";
  } catch (e) { verdict = "DENY"; reason = String(e && e.message || e) + (e && e.cause ? " / cause: " + (e.cause.message || e.cause) : ""); }
  out.push({ name: c.name, now: c.now, expected: c.expected, cloudflare_web_bot_auth_0_2_0: verdict, reason, match: verdict === c.expected });
}
console.log(JSON.stringify(out, null, 1));
