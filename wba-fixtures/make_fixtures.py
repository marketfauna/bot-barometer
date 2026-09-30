"""
Synthetic Web Bot Auth fixtures from Marketfauna's Python signer (site/tools/wba.py),
for developers testing a receiver. Uses only the public RFC 9421 Appendix B.1.4 test key
(test-key-ed25519), never our own key.

    python make_fixtures.py [--now UNIX] > fixtures.json

Each fixture has the request (method, url, headers), the verification clock `now`,
the key directory it assumes, and the verdict our own verifier (wba.verify_request /
wba.verify_directory_response) returns for it. Fixtures are signed at `now`, so pass a
fresh --now for live-clock receivers, or fix your receiver's clock to the recorded `now`.
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

    def fx(name, expect, method="GET", url=TARGET, headers=None, verify_url=None, at=now, note=""):
        ok, reason, _ = wba.verify_request(method, verify_url or url, headers, keys, now=at)
        got = "ALLOW" if ok else "DENY"
        assert got == expect, (name, got, reason)
        return {"name": name, "note": note, "method": method, "url": url,
                "received_at_url": verify_url or url, "headers": headers, "now": at,
                "expected": expect, "our_verifier_reason": reason}

    base = wba.sign_request(priv, kid, "GET", TARGET, AGENT, expires_in=60, now=now)
    fixtures = [fx("valid", "ALLOW", headers=base,
                   note="legacy sf-string Signature-Agent; covers @authority and signature-agent")]

    fixtures.append(fx("tampered-authority", "DENY", headers=base,
                       verify_url="https://other.example/protected/resource",
                       note="same headers presented to a different host"))

    fixtures.append(fx("expired", "DENY", headers=base, at=now + 61,
                       note="clock past expires (created+60)"))

    future = wba.sign_request(priv, kid, "GET", TARGET, AGENT, expires_in=60, now=now + 600)
    fixtures.append(fx("created-in-future", "DENY", headers=future,
                       note="created 600 s ahead of the verifier clock"))

    fixtures.append(fx("unknown-keyid", "DENY",
                       headers=wba.sign_request(other, other_kid, "GET", TARGET, AGENT, now=now),
                       note="valid signature by a key not in the directory"))

    swapped = copy.deepcopy(base)
    swapped["Signature-Agent"] = '"https://impostor.example"'
    fixtures.append(fx("signature-agent-swapped", "DENY", headers=swapped,
                       note="Signature-Agent changed after signing; the covered component no longer matches"))

    wrong_tag = copy.deepcopy(base)
    wrong_tag["Signature-Input"] = wrong_tag["Signature-Input"].replace('tag="web-bot-auth"', 'tag="other"')
    fixtures.append(fx("wrong-tag", "DENY", headers=wrong_tag,
                       note="tag parameter altered; also breaks the signature base"))

    # Directory responses: a receiver should count a key only if the directory
    # response is signed with it (draft-meunier-http-message-signatures-directory s.5.2).
    body = wba.directory_body([jwk]).decode()
    good_dir = wba.sign_directory_response(priv, kid, "agent.example", now=now)
    unsigned_dir = {"Content-Type": wba.DIRECTORY_MEDIA_TYPE}
    directories = []
    for name, hdrs, auth in [("directory-signed", good_dir, "agent.example"),
                             ("directory-unsigned", unsigned_dir, "agent.example"),
                             ("directory-signed-for-other-authority", good_dir, "mirror.example")]:
        valid, reasons = wba.verify_directory_response(auth, hdrs, body, now=now)
        directories.append({"name": name, "request_authority": auth, "headers": hdrs, "body": body,
                            "now": now, "keys_accepted_by_our_verifier": sorted(valid),
                            "our_verifier_reasons": reasons})

    json.dump({"generator": "Marketfauna site/tools/wba.py (Python, cryptography)",
               "key": {"source": "RFC 9421 Appendix B.1.4 test-key-ed25519", "jwk": jwk, "keyid": kid},
               "requests": fixtures, "directories": directories}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
