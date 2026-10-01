"""
Synthetic Web Bot Auth fixtures from Marketfauna's Python signer (site/tools/wba.py),
for developers testing a receiver. Uses only the public RFC 9421 Appendix B.1.4 test key
(test-key-ed25519), never our own key.

    python make_fixtures.py [--now UNIX] > fixtures.json

Profile (October 2026 revision): request nonces are 64 random bytes (base64), as
web-bot-auth 0.2.0 requires; directory responses carry a SHA-256 Content-Digest of
the exact body, signed together with "@authority";req. Positive cases expect VERIFIED,
negatives DENY, matching AgentGate 0.2.1's result contract.

Each request case is signed separately, so a receiver with a per-batch replay cache
rejects each negative for its intended reason rather than as a replay. The one
deliberate replay case repeats the valid case's headers.

Each fixture records its own verification clock `now`; set your receiver's clock
to that value per fixture (the expired case is checked 61 s after signing; the
future-created case is signed 600 s after its check time). Pass --now to regenerate
the whole set at a different base time.

Licence: see the accompanying LICENSE for Marketfauna's contribution and scope.
RFC test material: https://www.rfc-editor.org/rfc/rfc9421.html#appendix-B.1.4
Copyright (c) 2024 IETF Trust and the persons identified as authors of the code. All rights reserved.
Redistribution and use in source and binary forms, with or without modification, is permitted pursuant to, and subject to the license terms contained in, the Revised BSD License set forth in Section 4.c of the IETF Trust’s Legal Provisions Relating to IETF Documents (https://trustee.ietf.org/license-info).

Keep the IETF notice with redistributed test material, including regenerated JSON.
"""

import argparse
import copy
import json
import os
import sys
import time

# Needs wba.py (Marketfauna site/tools/wba.py) next to this file or in ../tools.
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")]
import wba  # noqa: E402

# RFC 9421 Appendix B.1.4, published test key. Public; not trusted anywhere.
RFC9421_TEST_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIJ+DYvh6SEqVTm50DFtMDoQikTmiCqirVv9mWG9qfSnF
-----END PRIVATE KEY-----
"""
RFC9421_TEST_PUBLIC_X = "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs"

AGENT = "https://agent.example"
TARGET = "https://receiver.example/protected/resource"

IETF_NOTICE = {
    "scope": "RFC 9421 Appendix B.1.4 test-key-ed25519 PEM/JWK test material",
    "source": "https://www.rfc-editor.org/rfc/rfc9421.html#appendix-B.1.4",
    "notice": "Copyright (c) 2024 IETF Trust and the persons identified as authors of the code. "
              "All rights reserved.\nRedistribution and use in source and binary forms, with or "
              "without modification, is permitted pursuant to, and subject to the license terms "
              "contained in, the Revised BSD License set forth in Section 4.c of the IETF Trust’s "
              "Legal Provisions Relating to IETF Documents (https://trustee.ietf.org/license-info).",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", type=int, default=int(time.time()))
    a = ap.parse_args()
    now = a.now

    priv = wba.load_private_key(RFC9421_TEST_KEY_PEM)
    jwk = wba.public_jwk(priv.public_key())
    assert jwk["x"] == RFC9421_TEST_PUBLIC_X, "not the RFC 9421 test key"
    kid = wba.thumbprint(jwk)
    keys = {kid: priv.public_key()}

    other = wba.generate_private_key()  # throwaway, never saved
    other_kid = wba.thumbprint(wba.public_jwk(other.public_key()))

    def sign(**kw):
        args = dict(priv=priv, kid=kid, method="GET", url=TARGET, agent_url=AGENT,
                    expires_in=60, now=now)
        args.update(kw)
        return wba.sign_request(**args)

    def fx(name, expect, headers, method="GET", url=TARGET, verify_url=None, at=now, note="",
           ours_checks_replay=True):
        ok, reason, _ = wba.verify_request(method, verify_url or url, headers, keys, now=at)
        got = "VERIFIED" if ok else "DENY"
        if ours_checks_replay:
            assert got == expect, (name, got, reason)
        return {"name": name, "note": note, "method": method, "url": url,
                "received_at_url": verify_url or url, "headers": headers, "now": at,
                "expected": expect, "our_verifier": got, "our_verifier_reason": reason}

    base = sign()
    fixtures = [fx("valid", "VERIFIED", base,
                   note="legacy sf-string Signature-Agent; covers @authority and signature-agent")]

    fixtures.append(fx("tampered-authority", "DENY", sign(),
                       verify_url="https://other.example/protected/resource",
                       note="own signature, presented to a different host"))

    fixtures.append(fx("expired", "DENY", sign(), at=now + 61,
                       note="clock past expires (created+60)"))

    fixtures.append(fx("created-in-future", "DENY", sign(now=now + 600),
                       note="created 600 s ahead of the verifier clock"))

    fixtures.append(fx("unknown-keyid", "DENY", sign(priv=other, kid=other_kid),
                       note="valid signature by a key the receiver doesn't trust (not the RFC test key)"))

    swapped = sign()
    swapped["Signature-Agent"] = '"https://impostor.example"'
    fixtures.append(fx("signature-agent-swapped", "DENY", swapped,
                       note="Signature-Agent changed after signing; the covered component no longer matches"))

    fixtures.append(fx("wrong-tag", "DENY", sign(tag="other"),
                       note="validly signed with tag=\"other\"; isolates the tag check"))

    fixtures.append(fx("replay", "DENY", copy.deepcopy(base),
                       note="repeats the valid case's headers and nonce; a receiver with a "
                            "per-batch replay cache must reject it. Our verifier has no replay "
                            "cache, so its own verdict here is VERIFIED.",
                       ours_checks_replay=False))

    # Directory responses: a receiver should count a key only if the directory
    # response is signed with it (draft-meunier-http-message-signatures-directory s.5.2),
    # and the strict profile also requires a signed Content-Digest of the exact body.
    body = wba.directory_body([jwk]).decode()
    good = wba.sign_directory_response(priv, kid, "agent.example", now=now, body=body)
    tampered_body = body.replace('"keys"', '"keys" ')
    legacy = wba.sign_directory_response(priv, kid, "agent.example", now=now)
    directories = []
    for name, hdrs, auth, dbody, expect, note in [
            ("directory-signed", good, "agent.example", body, "VERIFIED",
             "signed with Content-Digest and \"@authority\";req"),
            ("directory-unsigned", {"Content-Type": wba.DIRECTORY_MEDIA_TYPE,
                                    "Content-Digest": wba.content_digest(body)},
             "agent.example", body, "DENY", "correct digest, no signature"),
            ("directory-signed-for-other-authority", good, "mirror.example", body, "DENY",
             "signature bound to agent.example, served for mirror.example"),
            ("directory-body-tampered", good, "agent.example", tampered_body, "DENY",
             "body changed after signing; Content-Digest no longer matches"),
            ("directory-legacy-no-digest", legacy, "agent.example", body, "DENY",
             "older form: signs only \"@authority\";req, no Content-Digest (rejected by the strict profile)"),
    ]:
        valid, reasons = wba.verify_directory_response(auth, hdrs, dbody, now=now, require_digest=True)
        got = "VERIFIED" if valid else "DENY"
        assert got == expect, (name, got, reasons)
        directories.append({"name": name, "note": note, "request_authority": auth,
                            "directory_url": "https://{}{}".format(auth, wba.DIRECTORY_PATH),
                            "headers": hdrs, "body": dbody, "now": now, "expected": expect,
                            "keys_accepted_by_our_verifier": sorted(valid),
                            "our_verifier_reasons": reasons})

    json.dump({"generator": "Marketfauna site/tools/wba.py (Python, cryptography)",
               "profile": {"request_nonce_bytes": wba.NONCE_BYTES,
                           "directory": "SHA-256 Content-Digest signed with \"@authority\";req",
                           "verdicts": "VERIFIED / DENY (AgentGate 0.2.1 vocabulary)"},
               "key": {"source": "RFC 9421 Appendix B.1.4 test-key-ed25519", "jwk": jwk, "keyid": kid},
               "requests": fixtures, "directories": directories,
               "third_party_notice": IETF_NOTICE}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
