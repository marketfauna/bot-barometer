"""Run Marketfauna's Web Bot Auth request fixtures against regent-httpsig.

Usage (in a venv with regent-httpsig installed):
    python crossval_regent_httpsig.py fixtures.json out.json

Each case runs at its own fixture clock (`now`), by freezing the clock that
http-message-signatures reads. The agent's key directory is served in memory
through an httpx.MockTransport from the fixture file's "directory-signed" body,
only for agent.example; every other host gets 404. Nothing touches the network.
The fixture key is the public RFC 9421 B.1.4 test key.
"""

import asyncio
import datetime as _dt
import hashlib
import json
import sys
from importlib.metadata import version

import httpx
import http_message_signatures.signatures as hms_sig

import regent_httpsig.verify as rv
from regent_httpsig import HttpsigConfig, HttpsigVerifier

FIXTURES, OUT = sys.argv[1], sys.argv[2]
raw = open(FIXTURES, "rb").read()
fx = json.loads(raw)
directory_body = next(d for d in fx["directories"] if d["name"] == "directory-signed")["body"]


class _FrozenDatetime(_dt.datetime):
    frozen = 0

    @classmethod
    def now(cls, tz=None):
        return _dt.datetime.fromtimestamp(cls.frozen, tz)


class _FrozenModule:
    datetime = _FrozenDatetime
    timedelta = _dt.timedelta


hms_sig.datetime = _FrozenModule  # the library reads datetime.datetime.now()


async def _allow(url, allow_hosts=frozenset()):  # no DNS: the hosts are fictional
    return None


rv.assert_public_url = _allow


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "agent.example" and request.url.path == rv.WBA_DIRECTORY_PATH:
        return httpx.Response(200, content=directory_body.encode(),
                              headers={"content-type": "application/http-message-signatures-directory+json"})
    return httpx.Response(404)


async def main():
    results = []
    for case in fx["requests"]:
        _FrozenDatetime.frozen = case["now"]
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        verifier = HttpsigVerifier(HttpsigConfig(), http_client=client)
        sig = await verifier.verify(case["method"], case["received_at_url"], case["headers"])
        await client.aclose()
        got = "VERIFIED" if sig else "DENY"
        results.append({"name": case["name"], "now": case["now"], "expected": case["expected"],
                        "regent_httpsig": got, "match": got == case["expected"],
                        "keyid": sig.keyid if sig else None})
    # replay: the library keeps no nonce store, so a batch presenting the same
    # request twice is reported for completeness, using one verifier instance
    valid = next(c for c in fx["requests"] if c["name"] == "valid")
    _FrozenDatetime.frozen = valid["now"]
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    v = HttpsigVerifier(HttpsigConfig(), http_client=client)
    first = await v.verify(valid["method"], valid["received_at_url"], valid["headers"])
    second = await v.verify(valid["method"], valid["received_at_url"], valid["headers"])
    await client.aclose()
    # expiry boundary probe: the same 'expired' request at expires+1..+6 seconds
    exp_case = next(c for c in fx["requests"] if c["name"] == "expired")
    boundary = []
    for dt in range(0, 7):
        t = exp_case["now"] - 1 + dt  # fixture now is expires+1
        _FrozenDatetime.frozen = t
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        s = await HttpsigVerifier(HttpsigConfig(), http_client=client).verify(
            exp_case["method"], exp_case["received_at_url"], exp_case["headers"])
        await client.aclose()
        boundary.append({"seconds_after_expires": dt, "verdict": "VERIFIED" if s else "DENY"})
    report = {
        "verifier": {"package": "regent-httpsig", "version": version("regent-httpsig"),
                     "http-message-signatures": version("http-message-signatures"),
                     "source_commit": sys.argv[3] if len(sys.argv) > 3 else None},
        "fixtures_sha256": hashlib.sha256(raw).hexdigest(),
        "clock": "per-case fixture now, frozen in http_message_signatures.signatures",
        "directory": "fixture 'directory-signed' body served in memory for agent.example only",
        "requests": results,
        "matched": sum(r["match"] for r in results),
        "total": len(results),
        "same_request_twice_same_instance": ["VERIFIED" if first else "DENY",
                                             "VERIFIED" if second else "DENY"],
        "expired_case_boundary": boundary,
    }
    json.dump(report, open(OUT, "w"), indent=1)
    print(json.dumps(report, indent=1))


asyncio.run(main())
