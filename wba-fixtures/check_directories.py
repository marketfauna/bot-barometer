"""Check live Web Bot Auth key directories against draft-ietf-webbotauth-httpsig-protocol-00.

Read-only: one GET per directory, through curl (local Python TLS is unreliable on this machine).
Robots/terms are checked by the operator of this script before adding a URL (research/terms/REGISTER.md).

Checks (section of protocol -00 in brackets):
  status 200 with no redirect followed            [5.5: MUST be 200, verifiers MUST NOT follow redirects]
  media type                                       [8.x registration]
  kid absent or equal to the RFC 7638/8037 thumbprint   [5.5 note: if a JWK carries kid it MUST be the thumbprint]
  if signed: "@authority";req covered              [B.1 MUST]
             content-digest covered and matching   [B.1 MUST]
             created and expires present           [B.1 MUST]
             created not in the future             [B.1 MUST reject]
             keyid is a thumbprint                 [B.1 MUST]
             tag = http-message-signatures-directory [B.1 MUST]
             Ed25519 signature valid for the authority fetched
  keys signed / keys published                     [B.1 SHOULD one signature per key]

Usage: python check_directories.py <url> [<url> ...] > result.json
"""
import email.utils
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parent.parent / "tools")]
import wba  # noqa: E402

SPEC = "draft-ietf-webbotauth-httpsig-protocol-00"


def fetch(url):
    out = subprocess.run(
        ["curl", "-s", "-m", "20", "-A", "Claude-User", "-D", "-", "-o", "-", "-w", "\n__STATUS__%{http_code}", url],
        capture_output=True, check=True).stdout
    raw, status = out.rsplit(b"\n__STATUS__", 1)
    head, _, body = raw.partition(b"\r\n\r\n")
    headers = {}
    for line in head.decode("latin-1").split("\r\n")[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().lower()
            headers[k] = (headers[k] + ", " + v.strip()) if k in headers else v.strip()
    return int(status), headers, body


def members(value):
    return [m.strip() for m in re.split(r',\s*(?=[A-Za-z0-9_-]+=\()', value) if m.strip()]


def check(url, now=None):
    now = int(now or time.time())
    authority = urllib.parse.urlsplit(url).netloc.lower()
    status, headers, body = fetch(url)
    if "date" in headers:  # judge "future" against the server's clock; ours ran ~2 s slow on 3 Oct
        now = max(now, int(email.utils.parsedate_to_datetime(headers["date"]).timestamp()))
    r = {"url": url, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
         "status": status, "body_sha256": hashlib.sha256(body).hexdigest(), "checks": {}}
    c = r["checks"]
    c["status_200_no_redirect"] = status == 200
    if status != 200:
        r["location"] = headers.get("location")
        return r
    c["media_type"] = headers.get("content-type", "").split(";")[0].strip() == wba.DIRECTORY_MEDIA_TYPE
    keys = json.loads(body).get("keys", [])
    tps = {wba.thumbprint(k): k for k in keys}
    r["keys"] = len(keys)
    c["kid_absent_or_thumbprint"] = all(k.get("kid") in (None, wba.thumbprint(k)) for k in keys)
    sigs = []
    si, sg = headers.get("signature-input"), headers.get("signature")
    digest_ok = None
    if "content-digest" in headers:
        digest_ok = wba.content_digest(body) == headers["content-digest"].strip()
    for m in members(si or ""):
        label, params_ser, idents, params = wba.parse_signature_input(m)
        s = {"label": label, "components": idents,
             "authority_req": '"@authority";req' in idents,
             "content_digest_covered": '"content-digest"' in idents,
             "content_digest_matches_body": digest_ok,
             "created_and_expires": "created" in params and "expires" in params,
             "created_not_future": isinstance(params.get("created"), int) and params["created"] <= now,
             "keyid_is_thumbprint": params.get("keyid") in tps,
             "tag": params.get("tag") == wba.DIRECTORY_TAG}
        key = tps.get(params.get("keyid")) or next((k for k in keys if k.get("kid") == params.get("keyid")), None)
        s["key_found"] = key is not None
        comps = []
        for ident in idents:
            name = ident.split('"')[1]
            comps.append((ident, authority if name == "@authority" else headers.get(name, "")))
        try:
            wba.public_key_from_jwk(key).verify(wba.parse_signature(sg, label), wba.signature_base(comps, params_ser))
            s["signature_valid_for_authority"] = True
        except Exception:
            s["signature_valid_for_authority"] = False
        sigs.append(s)
    r["signatures"] = sigs
    r["keys_signed"] = len(sigs)
    c["signed"] = bool(sigs)
    if sigs:
        c["b1_all_musts"] = all(s["authority_req"] and s["content_digest_covered"] and s["content_digest_matches_body"]
                                and s["created_and_expires"] and s["created_not_future"]
                                and s["keyid_is_thumbprint"] and s["tag"] for s in sigs)
        c["all_signatures_valid"] = all(s["signature_valid_for_authority"] for s in sigs)
    return r


if __name__ == "__main__":
    print(json.dumps({"spec": SPEC, "results": [check(u) for u in sys.argv[1:]]}, indent=2))
