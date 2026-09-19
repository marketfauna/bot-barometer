"""Agent Access Reading: delivery instrument (version 3, 2026-09-18). Python 3.7 or later, standard library only;
the signed condition additionally needs the cryptography package and a private key, and drops itself without them.

One command from an agreed scope file to the two delivered artefacts (reading.json, reading.md/html):

    python reading.py run   <scope.json> [--out DIR]     # network; honours robots.txt
    python reading.py render <DIR/reading.json>           # no network; rebuilds the readable report
    python reading.py check <scope.json>                  # no network; validates the scope file

Scope file (JSON):
  reading_id        short id used for the output directory
  customer          name printed on the report (may be "public case")
  agent_token       the robots.txt product token the customer's bot answers to (e.g. "Iframely")
  user_agent        the customer's User-Agent string as they supplied it (optional)
  ua_mode           "appended" (default): we send "<their UA> MarketfaunaReading/1.0 (+bot.html; reading for <customer>)"
                    "own": we send only our own MarketfaunaBot User-Agent
                    "verbatim": their exact string; refused unless verbatim_authorized_by is set, because it
                    presents their identity from our addresses and a site may treat that as spoofing
  sites             list of {"url", "label"?, "expect_marker"?, "source"?}, at most 25, one URL per site
  attempts          per condition, default 3;  spacing_s default 2.0
  conditions        default ["control", "unsigned", "signed"]

Rules kept from the specimen: robots.txt governs and is evaluated under RFC 9309 for the exact URL, for
the customer's token AND for our own token (we are the ones fetching, so the stricter verdict decides);
unreachable robots.txt means policy unknown and nothing is fetched; bodies are hashed, not stored,
except a bounded text head used for the title and content-marker check; a 200 is an HTTP observation.
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
import urllib.parse
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "site", "tools"))
sys.path.insert(0, os.path.join(HERE, ".."))  # when the instrument lives at tools/reading/ in the public repository
import rfc9309  # noqa: E402

OWN_TOKEN = "MarketfaunaBot"
READING_TOKEN = "MarketfaunaReading"  # the token appended in ua_mode appended; a site may name it
CONTROL_TOKEN = "python-urllib"
OWN_UA = "MarketfaunaBot/1.0 (+https://marketfauna.com/bot.html; hello@marketfauna.com)"
AGENT_URL = "https://marketfauna-wba-directory.marketfauna.workers.dev"
KEY_PATH = os.path.join(os.path.expanduser("~"), ".marketfauna", "wba-ed25519-private.pem")
TIMEOUT = 25
MAX_SITES = 25
HEAD_BYTES = 200000
VERSION = "reading.py 3 (2026-09-18)"
ROBOTS_BYTES = 512 * 1024  # RFC 9309 2.5 asks parsers to accept at least 500 KiB
MAX_CRAWL_DELAY = 30.0
CONTROL_UA = "python-urllib (generic HTTP client; control request for an access reading; +https://marketfauna.com/bot.html)"
DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.9,*/*;q=0.8"
DEFAULT_VANTAGE = "one residential broadband connection in the north-eastern United States; not a datacenter range; not the customer's network"
SELFTEST_URL = "https://crawltest.com/cdn-cgi/web-bot-auth"

DROP_HEADER_VALUES = {"set-cookie"}  # names kept, values reduced to cookie names only


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- scope

def check_scope(scope):
    errs = []
    for k in ("reading_id", "customer", "agent_token", "sites"):
        if not scope.get(k):
            errs.append("missing " + k)
    sites = scope.get("sites") or []
    if len(sites) > MAX_SITES:
        errs.append("more than %d sites" % MAX_SITES)
    hosts = {}
    for i, s in enumerate(sites):
        u = urlsplit(s.get("url", ""))
        if u.scheme not in ("http", "https") or not u.netloc:
            errs.append("site %d: url must be absolute http(s)" % i)
        if u.username or u.password:
            errs.append("site %d: credentials in URL are not accepted" % i)
        hosts.setdefault(u.netloc.lower(), []).append(i)
    for h, idx in hosts.items():
        if len(idx) > 1:
            errs.append("host %s appears %d times; the offer is one URL per site" % (h, len(idx)))
    mode = scope.get("ua_mode", "appended")
    if mode not in ("appended", "own", "verbatim"):
        errs.append("ua_mode must be appended, own or verbatim")
    if mode == "verbatim" and not scope.get("verbatim_authorized_by"):
        errs.append("ua_mode verbatim needs verbatim_authorized_by (who at the customer authorised it, and where)")
    if mode != "own" and not scope.get("user_agent"):
        errs.append("user_agent is required unless ua_mode is own")
    return errs


def effective_ua(scope):
    mode = scope.get("ua_mode", "appended")
    if mode == "own":
        return OWN_UA
    if mode == "verbatim":
        return scope["user_agent"]
    return "%s MarketfaunaReading/1.0 (+https://marketfauna.com/bot.html; reading for %s)" % (
        scope["user_agent"].strip(), re.sub(r"[^A-Za-z0-9 ._-]", "", scope["customer"])[:40])


# ---------------------------------------------------------------- fetch

def _headers_record(msg):
    out = {}
    for k, v in msg.items():
        k = k.lower()
        if k in DROP_HEADER_VALUES:
            name = v.split("=", 1)[0].strip()
            out.setdefault(k + "-names", [])
            out[k + "-names"].append(name)
        else:
            out[k] = v if k not in out else out[k] + ", " + v
    return out


CA_BUNDLE_CANDIDATES = [os.environ.get("MF_CA_BUNDLE"), r"C:\Program Files\Git\mingw64\ssl\certs\ca-bundle.crt",
                        "/etc/ssl/certs/ca-certificates.crt"]


def tls_context():
    """Verify against a Mozilla-derived bundle only, when one is present. Found 2026-09-18: the Windows
    system store on this host holds an expired certificate that OpenSSL prefers when building the chain
    for Let's Encrypt's new hierarchy, so the default context rejects sites whose served chain is valid
    (curl and openssl, which use the bundle, accept them). The trust store used is recorded in the reading."""
    import ssl
    for c in CA_BUNDLE_CANDIDATES:
        if c and os.path.exists(c):
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.load_verify_locations(cafile=c)
            return ctx, "bundle: " + c
    return ssl.create_default_context(), "python default (system store)"


_TLS = None
HOST_CEILING = 10
_HOST_COUNTS = {}  # authority -> requests actually started in this run; checked before every request


def reset_host_budget():
    _HOST_COUNTS.clear()


def authority_key(url):
    """Scheme-aware authority with the default port removed, so https://h and https://h:443 share one budget."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((parts.scheme == "https" and port == 443) or (parts.scheme == "http" and port == 80)):
        host = "%s:%d" % (host, port)
    return host


def _take_budget(url):
    """True if one more request to this authority may start; counts it if so."""
    host = authority_key(url)
    if _HOST_COUNTS.get(host, 0) >= HOST_CEILING:
        return False
    _HOST_COUNTS[host] = _HOST_COUNTS.get(host, 0) + 1
    return True


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def fetch(url, ua, extra=None, follow=True, max_hops=5, hop_allowed=None, accept=None, keep_bytes=HEAD_BYTES):
    """GET with recorded redirect chain. Returns (record, body_head_bytes).
    hop_allowed(next_url) -> (bool, note) is consulted before following a redirect to another authority,
    because robots.txt applies per authority (RFC 9309 2.3)."""
    hops, cur = [], url
    global _TLS
    if _TLS is None:
        _TLS = tls_context()
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_TLS[0]))
    rec = {"url": url, "requested_at_utc": now_utc(), "signed": bool(extra and "Signature" in extra)}
    t0 = time.time()
    body = b""
    for _ in range(max_hops + 1):
        h = {"User-Agent": ua, "Accept": accept or DEFAULT_ACCEPT, "Accept-Language": "en-US,en;q=0.9"}
        if extra and cur == url:
            h.update(extra)  # a signature covers the first request only (@authority is bound)
        req = urllib.request.Request(cur, headers=h, method="GET")
        if not _take_budget(cur):
            rec.update(status=None, final_url=cur, redirects=hops,
                       budget_stopped="request not started: %d requests already made to %s in this run" % (HOST_CEILING, urlsplit(cur).netloc))
            break
        rec["requests_started"] = rec.get("requests_started", 0) + 1
        try:
            with opener.open(req, timeout=TIMEOUT) as r:
                status, msg, body = r.status, r.headers, r.read(HEAD_BYTES * 5)
        except urllib.error.HTTPError as e:
            status, msg = e.code, e.headers
            body = e.read(HEAD_BYTES * 5) if e.fp else b""
        except Exception as e:  # DNS, TLS, timeout, reset
            rec.update(status=None, error=type(e).__name__ + ": " + str(e)[:200], final_url=cur, redirects=hops)
            break
        if follow and status in (301, 302, 303, 307, 308) and msg.get("Location"):
            nxt = urllib.parse.urljoin(cur, msg.get("Location"))
            hops.append({"status": status, "from": cur, "to": nxt})
            if hop_allowed:  # every hop is evaluated, same host or not: a verdict belongs to a path
                ok, note = hop_allowed(nxt)
                if not ok:
                    rec.update(status=status, final_url=cur, redirects=hops, headers=_headers_record(msg),
                               redirect_stopped="redirect to %s not followed: %s" % (urlsplit(nxt).netloc, note))
                    break
            cur = nxt
            continue
        rec.update(status=status, final_url=cur, redirects=hops, headers=_headers_record(msg))
        break
    else:
        rec.update(status=None, error="too many redirects", final_url=cur, redirects=hops)
    rec["elapsed_ms"] = int((time.time() - t0) * 1000)
    rec["body_sha256"] = hashlib.sha256(body).hexdigest()
    rec["body_bytes_read"] = len(body)
    rec["requests_made"] = rec.get("requests_started", 0)
    return rec, body[:keep_bytes]


# ---------------------------------------------------------------- interpretation (pure functions; tested offline)

CHALLENGE_BODY_MARKERS = ["just a moment", "cf-chl", "challenge-platform", "captcha", "access denied",
                          "are you a human", "px-captcha", "request blocked", "pardon our interruption",
                          "verify you are human", "attention required", "datadome", "unusual traffic"]


def body_facts(body, expect_marker=None):
    text = body.decode("utf-8", "replace")
    low = text.lower()
    m = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    title = html.unescape(re.sub(r"\s+", " ", m.group(1)).strip())[:160] if m else None
    head = low[:3000]
    is_feed = bool(re.search(r"<(rss|feed|rdf:rdf)[\s>]", head))
    is_json = low.lstrip()[:1] in ("{", "[")
    facts = {"title": title, "looks_like_feed": is_feed, "looks_like_json": is_json,
             "challenge_markers": [k for k in CHALLENGE_BODY_MARKERS if k in low]}
    if expect_marker:
        facts["expect_marker"] = expect_marker
        facts["expect_marker_found"] = expect_marker.lower() in low
    return facts


def classify_attempt(rec, facts):
    """One word for what came back, without asserting cause."""
    st = rec.get("status")
    if rec.get("budget_stopped"):
        return "budget-stop"  # our own ceiling, not a refusal and not a transport failure
    if rec.get("redirect_stopped"):
        return "redirect-not-followed"
    if st is None:
        return "transport-failure"
    h = rec.get("headers", {})
    if h.get("cf-mitigated", "").lower() == "challenge" or "x-amzn-waf-action" in h:
        return "challenge"
    if st in (401, 407):
        return "auth-required"
    if st == 403 and (facts.get("title") or "").lower().startswith("attention required"):
        return "refused"  # Cloudflare's block page mentions a captcha in its script names but offers no challenge to pass
    if st == 403:
        return "challenge" if facts.get("challenge_markers") and any(
            k in facts["challenge_markers"] for k in ("just a moment", "captcha", "px-captcha", "verify you are human")) else "refused"
    if st == 429:
        return "rate-limited"
    if st in (404, 410):
        return "not-found"
    if 500 <= st < 600:
        return "server-error"
    if 200 <= st < 300:
        if facts.get("expect_marker") is not None:
            return "delivered" if facts.get("expect_marker_found") else "200-marker-missing"
        if facts.get("challenge_markers") and any(k in facts["challenge_markers"] for k in
                                                  ("just a moment", "px-captcha", "verify you are human", "pardon our interruption")):
            return "200-challenge-page"
        if facts.get("looks_like_feed"):
            return "delivered-feed"
        return "200-unconfirmed"
    return "other-%s" % st


def vendor_clues(rec, clue_table, body_low="", title=""):
    """Match the response against the sourced clue table. Each hit keeps its tier (decisive, transit,
    possible) and source. A clue says which product answered, never why."""
    h = rec.get("headers", {}) or {}
    found = []
    cookie_names = [c.lower() for c in h.get("set-cookie-names", [])]
    for c in clue_table["clues"]:
        kind, key = c["where"], c["key"].lower()
        hit = False
        if kind == "header-present":
            hit = key in h
        elif kind == "header-prefix":
            hit = any(k.startswith(key) for k in h)
        elif kind == "header-value":
            hit = c["value"].lower() in h.get(key, "").lower()
        elif kind == "cookie-prefix":
            hit = any(n.startswith(key) for n in cookie_names)
        elif kind == "title-contains":
            hit = key in (title or "").lower()
        elif kind == "body-contains":
            hit = key in body_low
        elif kind == "body-regex":
            hit = re.search(c["key"], body_low) is not None
        if hit:
            found.append({"vendor": c["vendor"], "tier": c["tier"], "clue": c["label"], "means": c["means"],
                          "source": c["source"], "source_kind": c["source_kind"]})
    return found


TIER_ORDER = {"decisive": 0, "transit": 1, "possible": 2}


def clue_verdict(site):
    """Fixed three-tier vocabulary (survey section 6D)."""
    best = {}
    refused_seen = False
    for cond in site.get("conditions", {}).values():
        for a in cond.get("attempts", []):
            refused_seen = refused_seen or a["outcome"] in REFUSED
            for v in a.get("vendor_clues", []):
                if a["outcome"] not in REFUSED and v["tier"] == "decisive":
                    continue
                cur = best.get(v["vendor"])
                if cur is None or TIER_ORDER[v["tier"]] < TIER_ORDER[cur]:
                    best[v["vendor"]] = v["tier"]
    if not best:
        return ["no vendor clue"]
    out = []
    for vendor, tier in sorted(best.items(), key=lambda kv: TIER_ORDER[kv[1]]):
        if tier == "decisive":
            out.append("answered by %s (documented marker)" % vendor)
        elif tier == "transit":
            out.append("served through %s; %s" % (vendor, "refuser not identified" if refused_seen else "no refusal seen"))
        else:
            out.append("possible %s (undocumented marker)" % vendor)
    return out


def summarise_condition(attempts):
    outcomes = [a["outcome"] for a in attempts]
    statuses = [a["status"] for a in attempts]
    uniq = sorted(set(outcomes))
    return {"statuses": statuses, "outcomes": outcomes,
            "stable": len(uniq) == 1, "summary": uniq[0] if len(uniq) == 1 else "intermittent: " + ", ".join(uniq)}


def compare_conditions(site):
    c = site.get("conditions", {})
    if "unsigned" in c and "signed" in c and c["unsigned"]["attempts"] and c["signed"]["attempts"]:
        same = c["unsigned"]["summary"]["outcomes"] == c["signed"]["summary"]["outcomes"] and \
               c["unsigned"]["summary"]["statuses"] == c["signed"]["summary"]["statuses"]
        return {"sequences_match": same,
                "note": ("signed and unsigned sequences matched. Unless the self-test in this report shows the key is known to a verifier, "
                         "this does not show that signing is useless at this site; it shows nothing either way"
                         if same else
                         "signed and unsigned sequences differed in this run; with three attempts each this is an "
                         "observation, not a measured effect of signing")}
    return None


REFUSED = {"refused", "challenge", "200-challenge-page", "rate-limited", "auth-required"}


def control_note(site):
    c = site.get("conditions", {})
    if not c.get("control", {}).get("attempts") or not c.get("unsigned", {}).get("attempts"):
        return None
    ctl = c["control"]["attempts"][0]["outcome"]
    ours = c["unsigned"]["summary"]["summary"]
    ok = {"delivered", "delivered-feed", "200-unconfirmed"}
    if ctl in ("not-found", "server-error") and ours.startswith(ctl):
        return "both the named agent and a generic HTTP client received %s: check the URL before reading anything into it" % ctl
    if ctl in ok and ours not in ok:
        return "a generic, honestly labelled HTTP client from the same address received %s while the named agent received %s: the difference follows the User-Agent, not the address" % (ctl, ours)
    if ctl not in ok and ours not in ok:
        return "a generic HTTP client from the same address was also not served (%s): the refusal is not specific to the agent's name; address range, non-browser clients in general, or the URL itself remain possible" % ctl
    if ctl not in ok and ours in ok:
        return "the named agent was served while a generic HTTP client from the same address was not (%s)" % ctl
    return "a generic HTTP client from the same address was served as well"


ACC_TEST = "the agent's own request, from the operator's own network, returns the expected content on 3 of 3 attempts"


def next_steps(site, routes, profile=None):
    """Rule-suggested next steps, each with who acts, what they need and how to tell it worked. Order:
    what a public thread already established for this site, a documented alternative for this site, the
    site owner, then a vendor programme only if the operator can use one. A reviewer confirms or replaces
    these before a reading ships; 'next_steps_reviewed' stays false until then."""
    profile = profile or {}
    can_apply = profile.get("can_apply_to_programmes", True)
    out = []
    rep = site.get("reported") or {}
    evasive = ("flaresolverr", "solver", "spoof", "custom user agent", "override the user agent", "ua override", "user agent to", "user-agent to", "feed's user agent", "firefox user agent", "browser user agent", "browser ua", "proxy", "proxies", "headless", "cookie", "vpn", "impersonat", "rss-bridge", "disabling http/2", "through openrss", "curl subprocess")
    if rep.get("route_mentioned") and any(k in rep["route_mentioned"].lower() for k in evasive):
        out.append({"step": "the source thread mentions a workaround that defeats or disguises past the site's protection; we do not pass such workarounds on, and they are not a route",
                    "who_acts": None, "needs": None, "acceptance_test": None, "source": rep.get("report_url"), "basis": "policy: no evasion advice"})
    elif rep.get("route_mentioned"):
        out.append({"step": "a public thread already records a route for this site: " + rep["route_mentioned"].rstrip("."),
                    "who_acts": "see the thread", "needs": None, "acceptance_test": ACC_TEST,
                    "source": rep.get("report_url"), "basis": "reported in the source thread; not re-tested by us"})
    dom = site["host"].lower()
    apex = dom[4:] if dom.startswith("www.") else dom
    for k in routes.get("sites", {}):
        if apex == k or apex.endswith("." + k):
            for r in routes["sites"][k]:
                out.append(dict(r, basis="known documented route for this site"))
    robots = site.get("robots", {})
    if robots.get("robots_refused"):
        vend = sorted({v["vendor"] for v in robots.get("fetch", {}).get("vendor_clues", []) if v["tier"] != "possible"})
        out.append({"step": "the site refused the agent at robots.txt itself%s; the route is the site owner (note in the appendix), and the site stays excluded until robots.txt can be read"
                            % ((" (answered through " + ", ".join(vend) + ")") if vend else ""),
                    "who_acts": "operator, then site owner", "needs": "the readiness items listed in this report",
                    "acceptance_test": "robots.txt is served to the agent; then " + ACC_TEST, "source": None, "basis": "robots.txt refused"})
        return out
    if robots.get("policy_unknown"):
        out.append({"step": "robots.txt could not be reached from our network, so nothing was requested; repeat from the operator's own network before concluding anything",
                    "who_acts": "operator", "needs": None, "acceptance_test": "robots.txt is read and the URL evaluated",
                    "source": "https://www.rfc-editor.org/rfc/rfc9309.html#section-2.3.1.4", "basis": "robots unreachable"})
        return out
    if robots.get("decision") == "not-requested":
        out.append({"step": "robots.txt excludes this URL for the agent; treat the site as excluded unless the owner changes the file or offers another route. We do not suggest any way around it",
                    "who_acts": "operator", "needs": None, "acceptance_test": "the URL is removed from the agent's list, or the owner's file changes",
                    "source": "https://www.rfc-editor.org/rfc/rfc9309.html#section-2.2.2", "basis": "robots verdict"})
        return out
    outcomes, vendors = set(), {}
    for cname, cond in site.get("conditions", {}).items():
        if cname == "control":
            continue
        for a in cond["attempts"]:
            outcomes.add(a["outcome"])
            if a["outcome"] in REFUSED:
                for v in a.get("vendor_clues", []):
                    cur = vendors.get(v["vendor"])
                    if cur is None or TIER_ORDER[v["tier"]] < TIER_ORDER[cur["tier"]]:
                        vendors[v["vendor"]] = v
    if outcomes & REFUSED:
        out.append({"step": "write to the site owner with the agent's identifiers (note in the appendix); every vendor in this report leaves the final say to the site owner, and owners in the source threads did make exceptions when asked",
                    "who_acts": "operator, then site owner", "needs": "the readiness items listed in this report",
                    "acceptance_test": ACC_TEST, "source": None, "basis": "general"})
        for v, clue in vendors.items():
            for r in routes.get("vendors", {}).get(v, []):
                if r["who_acts"].startswith("operator") and not can_apply:
                    continue  # a self-hosted reader has no product-wide identity a vendor programme can verify
                if clue["tier"] != "decisive" and r["who_acts"].startswith("operator"):
                    continue  # a transit marker does not show that vendor decided, so its programme may not change anything
                out.append(dict(r, basis="%s clue seen (%s, %s tier)" % (v, clue["clue"], clue["tier"])))
    elif outcomes & {"not-found"}:
        out.append({"step": "the URL returned not-found; confirm the address before any other step",
                    "who_acts": "operator", "needs": "the current URL", "acceptance_test": "the URL returns the expected content to any client",
                    "source": None, "basis": "general"})
    elif outcomes & {"server-error"}:
        out.append({"step": "the site answered with a server error to every client we used, including the control; that is the site's own fault condition or a block dressed as one, and we cannot tell which. Repeat later and from the operator's network",
                    "who_acts": "operator", "needs": None, "acceptance_test": ACC_TEST, "source": None, "basis": "general"})
    elif outcomes & {"transport-failure"}:
        out.append({"step": "our client could not complete the connection; this identifies no cause. Repeat from the operator's own network",
                    "who_acts": "operator", "needs": None, "acceptance_test": ACC_TEST, "source": None, "basis": "general"})
    elif outcomes & {"200-unconfirmed", "200-marker-missing"}:
        out.append({"step": "a 200 without a content marker does not confirm the intended page arrived; supply a phrase expected on the page and we read it again",
                    "who_acts": "operator", "needs": "one phrase expected on the page", "acceptance_test": "the phrase is found", "source": None, "basis": "general"})
    else:
        out.append({"step": "no refusal seen from our vantage. That does not predict the operator's network: refusals by address range are common and invisible from here. Run the same command from the network the agent runs on and compare",
                    "who_acts": "operator", "needs": "python 3 and this instrument, or our help running it", "acceptance_test": "the two vantages agree, or the difference is recorded",
                    "source": None, "basis": "vantage limit"})
    return out


# ---------------------------------------------------------------- run

def robots_for(url, scope_token, ua):
    parts = urlsplit(url)
    robots_url = "%s://%s/robots.txt" % (parts.scheme, parts.netloc)
    rec, body = fetch(robots_url, ua, keep_bytes=ROBOTS_BYTES)
    st = rec.get("status")
    try:
        rec["vendor_clues"] = vendor_clues(rec, load_json("vendor_clues.json"), body[:HEAD_BYTES].decode("utf-8", "replace").lower(),
                                           body_facts(body[:HEAD_BYTES]).get("title"))
    except OSError:
        rec["vendor_clues"] = []
    out = {"fetch": rec, "robots_url": robots_url, "evaluator": "rfc9309.py (longest match, * and $ supported)"}
    if st == 200 and "<html" not in body[:500].decode("utf-8", "replace").lower():
        text = body.decode("utf-8-sig", "replace")
        groups = rfc9309.parse(text)
        _GROUPS[robots_url] = groups
        out["policy_basis"] = "parsed"
        out["robots_text"] = text[:60000]
        out["robots_sha256"] = hashlib.sha256(body).hexdigest()
        out["robots_bytes_read"] = len(body)
        out["crawl_delay_lines"] = [l.strip() for l in text.splitlines() if l.strip().lower().startswith("crawl-delay")][:10]
        out["verdicts"] = {t: rfc9309.evaluate(groups, t, url) for t in dict.fromkeys([scope_token, OWN_TOKEN, READING_TOKEN, CONTROL_TOKEN, "*", "GPTBot", "ClaudeBot"])}
        out["named"] = {t: any(rfc9309.agent_token(t) in g["agents"] for g in groups) for t in (scope_token, OWN_TOKEN)}
        delays = []
        for line in out["crawl_delay_lines"]:
            try:
                delays.append(float(line.split(":", 1)[1].split("#", 1)[0].strip()))
            except ValueError:
                pass
        out["crawl_delay_s"] = max(delays) if delays else None  # the largest value in the file, whichever group: the polite reading
    elif st == 200 and (body_facts(body[:HEAD_BYTES]).get("challenge_markers") or any(v["tier"] == "decisive" or v["vendor"] == "Anubis" for v in rec.get("vendor_clues", []))):
        out["policy_basis"] = ("robots.txt request was answered with status 200 and a challenge or interstitial page instead of a robots file, so the policy could not be "
                               "read by us; treated as a refusal, and no page request is made")
        out["robots_refused"] = True
        out["policy_unknown"] = True
        out["verdicts"] = {t: {"allowed": False, "basis": "unknown: robots.txt was answered with a challenge page", "matched_rule": None} for t in (scope_token, OWN_TOKEN, "*")}
    elif st == 200:
        out["policy_basis"] = "200 with an HTML body, not a robots file: treated as unavailable (no restrictions), stated as an assumption"
        out["verdicts"] = {t: {"allowed": True, "basis": out["policy_basis"], "matched_rule": None} for t in (scope_token, OWN_TOKEN, "*")}
    elif st is not None and (st in (401, 403, 429) or (rec.get("headers") or {}).get("cf-mitigated") or "x-amzn-waf-action" in (rec.get("headers") or {})):
        ctl, _ = fetch(robots_url, CONTROL_UA, keep_bytes=2000)
        out["control_fetch"] = {"status": ctl.get("status"), "requested_at_utc": ctl["requested_at_utc"], "requests_made": ctl.get("requests_made", 1)}
        out["policy_basis"] = ("robots.txt request was itself refused (status %s), so the policy could not be read by us. RFC 9309 2.3.1.3 would let a crawler treat a 4xx "
                               "as no restrictions; we do not: a site that refuses the agent at robots.txt has answered, and no page request is made. "
                               "A generic HTTP client asking for the same file received %s" % (st, ctl.get("status") if ctl.get("status") is not None else "no response"))
        out["robots_refused"] = True
        out["policy_unknown"] = True
        out["verdicts"] = {t: {"allowed": False, "basis": "unknown: robots.txt was refused", "matched_rule": None} for t in (scope_token, OWN_TOKEN, "*")}
    elif st is not None and 400 <= st < 500:
        refused = False
        out["policy_basis"] = ("robots.txt request was itself refused (%s%s), so the file could not be read by us; RFC 9309 2.3.1.3 treats a 4xx as unavailable, meaning no restrictions"
                               % (st, ", challenge" if rec.get("headers", {}).get("cf-mitigated") == "challenge" else "")) if refused else                               "unavailable (%s): no restrictions per RFC 9309 2.3.1.3" % st
        out["robots_refused"] = refused
        out["verdicts"] = {t: {"allowed": True, "basis": out["policy_basis"], "matched_rule": None} for t in (scope_token, OWN_TOKEN, "*")}
    else:
        out["policy_basis"] = "unreachable (%s): policy unknown, treated as complete disallow per RFC 9309 2.3.1.4" % (st or rec.get("error"))
        out["verdicts"] = {t: {"allowed": False, "basis": out["policy_basis"], "matched_rule": None} for t in (scope_token, OWN_TOKEN, "*")}
    v = out["verdicts"]
    allowed = v[scope_token]["allowed"] and v[OWN_TOKEN]["allowed"] and v.get(READING_TOKEN, {"allowed": True})["allowed"]
    out["control_allowed"] = v.get(CONTROL_TOKEN, {"allowed": True})["allowed"]
    out["decision"] = "requested" if allowed else "not-requested"
    if not allowed:
        who = [t for t in (scope_token, OWN_TOKEN, READING_TOKEN) if t in v and not v[t]["allowed"]]
        if out.get("robots_refused"):
            out["decision_reason"] = "robots.txt was refused to the agent, so the policy is unknown and the refusal is itself the observation; no page request made"
        elif out["policy_basis"].startswith("unreachable"):
            out["decision_reason"] = "robots.txt could not be reached, so the policy is unknown; no page request made"
            out["policy_unknown"] = True
        else:
            out["decision_reason"] = "robots.txt verdict is disallow for " + " and ".join(dict.fromkeys(who)) + "; no page request made"
    return out


_GROUPS = {}  # robots_url -> parsed groups from the complete file as fetched (the stored robots_text is an archive copy and may be truncated)


def make_hop_check(scope_token, ua, cache, control=False):
    """Before a redirect is followed, the exact target is evaluated for every token the request actually
    carries: the customer's token, ours and the reading token for named requests; the control client's
    token for the control request."""
    tokens = (CONTROL_TOKEN, OWN_TOKEN) if control else (scope_token, OWN_TOKEN, READING_TOKEN)

    def hop_allowed(nxt):
        parts = urlsplit(nxt)
        key = parts.scheme + "://" + parts.netloc.lower()
        if key not in cache:
            cache[key] = robots_for(nxt, scope_token, ua)
            cache[key]["fetched_for_redirect"] = True
        r = cache[key]
        if r.get("policy_basis") == "parsed":
            groups = _GROUPS.get(r["robots_url"])
            if groups is None:
                groups = rfc9309.parse(r.get("robots_text") or "")
            bad = [t for t in tokens if not rfc9309.evaluate(groups, t, nxt)["allowed"]]
            return (not bad), ("allowed by that host's robots.txt" if not bad else "that host's robots.txt disallows the target for " + ", ".join(bad))
        if r.get("policy_unknown") or r.get("robots_refused"):
            return False, r.get("decision_reason", "policy unknown")
        return True, "robots.txt unavailable there (" + str(r.get("policy_basis", ""))[:60] + ")"
    return hop_allowed


def run(scope, outdir, vantage=None):
    clue_table, routes = load_json("vendor_clues.json"), load_json("routes.json")
    ua = effective_ua(scope)
    attempts_n = int(scope.get("attempts", 3))
    spacing = float(scope.get("spacing_s", 2.0))
    conditions = scope.get("conditions", ["control", "unsigned", "signed"])
    accept = scope.get("accept") or DEFAULT_ACCEPT
    priv = kid = wba = None
    signing_note = None
    if "signed" in conditions:
        try:
            import wba
            priv = wba.load_private_key(KEY_PATH)
            kid = wba.thumbprint(wba.public_jwk(priv.public_key()))
        except Exception as e:  # no key or no crypto library on this machine: an operator-side run is unsigned
            conditions = [c for c in conditions if c != "signed"]
            signing_note = "signed condition dropped on this machine: %s" % (type(e).__name__)
    reading = {"instrument": VERSION, "reading_id": scope["reading_id"], "customer": scope["customer"],
               "agent_token": scope["agent_token"], "user_agent_supplied": scope.get("user_agent"),
               "ua_mode": scope.get("ua_mode", "appended"), "user_agent_sent": ua,
               "signing": {"agent_url": AGENT_URL, "keyid": kid,
                           "note": "our own key and directory; recognition by any destination is not assumed"} if kid else None,
               "attempts_per_condition": attempts_n, "spacing_s": spacing, "conditions": conditions,
               "accept_header_sent": accept, "control_user_agent": CONTROL_UA if "control" in conditions else None,
               "vantage": vantage or scope.get("vantage", DEFAULT_VANTAGE), "signing_note": signing_note, "operator_profile": scope.get("operator_profile"),
               "request_budget_per_site": 1 + (1 if "control" in conditions else 0) + attempts_n * len([c for c in conditions if c != "control"]),
               "request_ceiling_per_host": 10,
               "tls_trust_store": tls_context()[1], "started_utc": now_utc(), "sites": []}
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "reading.json")
    reset_host_budget()  # before the first request of the run, so the self-test is counted too
    if kid:
        sig = wba.sign_request(priv, kid, "GET", SELFTEST_URL, AGENT_URL)
        st_rec, _ = fetch(SELFTEST_URL, ua, sig)
        reading["signing"]["self_test"] = {"url": SELFTEST_URL, "status": st_rec.get("status"), "requested_at_utc": st_rec["requested_at_utc"],
                                           "signature_input": sig.get("Signature-Input"),
                                           "meaning": "Cloudflare's public test endpoint: 200 = signature valid and key known, 401 = well formed but key unknown to Cloudflare, 400 = malformed"}
    robots_cache = {}
    hop_check = make_hop_check(scope["agent_token"], ua, robots_cache)
    hop_check_control = make_hop_check(scope["agent_token"], ua, robots_cache, control=True)
    for s in scope["sites"]:
        url = s["url"]
        host = urlsplit(url).netloc
        print(now_utc(), host, flush=True)
        site = {"url": url, "host": host, "label": s.get("label"), "source": s.get("source"),
                "expect_marker": s.get("expect_marker")}
        site["robots"] = robots_for(url, scope["agent_token"], ua)
        robots_cache.setdefault(urlsplit(url).scheme + "://" + urlsplit(url).netloc.lower(), site["robots"])
        delay = site["robots"].get("crawl_delay_s")
        site_spacing = max(spacing, min(delay, MAX_CRAWL_DELAY)) if delay else spacing
        site["spacing_s"] = site_spacing
        if delay and delay > MAX_CRAWL_DELAY:
            site["spacing_note"] = "robots.txt asks for a crawl delay of %s s; we waited %s s between requests and say so" % (delay, MAX_CRAWL_DELAY)
        targets = {"control": url, "named": url}  # a redirect learned by one kind of request is never reused by the other
        time.sleep(site_spacing)
        site["conditions"] = {}
        if site["robots"]["decision"] == "requested":
            for c in conditions:
                site["conditions"][c] = {"attempts": []}
            for rep in range(attempts_n):  # interleaved so time-of-request is not confounded with condition
                for c in conditions:
                    if c == "control" and (rep > 0 or not site["robots"].get("control_allowed", True)):
                        continue  # one control request per site; none where robots.txt disallows the control's own token
                    kind = "control" if c == "control" else "named"
                    check = hop_check_control if c == "control" else hop_check
                    target = targets[kind]
                    if target != url:
                        ok, note = check(target)  # the shortcut is re-checked for this request's own tokens every time
                        if not ok:
                            target = targets[kind] = url
                    extra = wba.sign_request(priv, kid, "GET", target, AGENT_URL) if c == "signed" else None
                    rec, body = fetch(target, CONTROL_UA if c == "control" else ua, extra, hop_allowed=check, accept=accept)
                    hops = rec.get("redirects") or []
                    if target == url and hops and all(h["status"] in (301, 308) for h in hops) and rec.get("status") is not None and not rec.get("redirect_stopped"):
                        targets[kind] = rec["final_url"]  # permanent redirect: later attempts of the same kind go straight there
                        if kind == "named":
                            site["resolved_url"] = rec["final_url"]
                    facts = body_facts(body, s.get("expect_marker"))
                    rec.update(rep=rep, body_facts=facts, outcome=classify_attempt(rec, facts),
                               vendor_clues=vendor_clues(rec, clue_table, body.decode("utf-8", "replace").lower(), facts.get("title")))
                    site["conditions"][c]["attempts"].append(rec)
                    time.sleep(site_spacing)
            for c in conditions:
                site["conditions"][c]["summary"] = summarise_condition(site["conditions"][c]["attempts"])
        site["requests_to_host"] = _HOST_COUNTS.get(authority_key(url), 0)  # this authority only; redirect targets are counted under their own host in requests_by_host
        site["reported"] = s.get("reported")
        site["comparison"] = compare_conditions(site)
        site["clue_verdict"] = clue_verdict(site)
        site["control_note"] = control_note(site)
        site["next_steps"] = next_steps(site, routes, scope.get("operator_profile"))
        site["next_steps_reviewed"] = False
        reading["sites"].append(site)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(reading, f, indent=1)
    reading["finished_utc"] = now_utc()
    reading["requests_by_host"] = dict(_HOST_COUNTS)  # counted before each request started, every host including redirect targets
    reading["request_ceiling_per_host"] = HOST_CEILING
    reading["ceiling_enforced_before_request"] = True  # written only by versions that check the counter before every request
    hashes = {}
    for st in reading["sites"]:
        h = st["robots"].get("robots_sha256")
        if h:
            hashes.setdefault(h, []).append(st.get("label") or st["host"])
    for st in reading["sites"]:
        same = [x for x in hashes.get(st["robots"].get("robots_sha256"), []) if x != (st.get("label") or st["host"])]
        if same:
            st["robots"]["identical_file_at"] = same
    reading["denominators"] = denominators(reading)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reading, f, indent=1)
    return path


def reinterpret(reading):
    """Recompute everything derived (outcomes, clues, summaries, verdicts, next steps) from the stored
    observations, with the current clue and route tables. No network. Body-only clues found at run time
    are kept, because bodies are not stored. Reviewed next steps are left alone."""
    clue_table, routes = load_json("vendor_clues.json"), load_json("routes.json")
    body_kinds = {c["label"] for c in clue_table["clues"] if c["where"] in ("body-contains", "body-regex")}
    for site in reading["sites"]:
        for cond in site.get("conditions", {}).values():
            for a in cond.get("attempts", []):
                facts = a.get("body_facts", {})
                kept = [v for v in a.get("vendor_clues", []) if v["clue"] in body_kinds]
                fresh = vendor_clues(a, clue_table, "", facts.get("title"))
                seen = {v["clue"] for v in fresh}
                a["vendor_clues"] = fresh + [v for v in kept if v["clue"] not in seen]
                a["outcome"] = classify_attempt(a, facts)
            if cond.get("attempts"):
                cond["summary"] = summarise_condition(cond["attempts"])
        site["comparison"] = compare_conditions(site)
        site["clue_verdict"] = clue_verdict(site)
        site["control_note"] = control_note(site)
        if not site.get("next_steps_reviewed"):
            site["next_steps"] = next_steps(site, routes, reading.get("operator_profile"))
    reading["denominators"] = denominators(reading)
    reading["reinterpreted_utc"] = now_utc()
    return reading


def body_is_challenge(robots):
    return any(v.get("tier") == "decisive" for v in robots.get("fetch", {}).get("vendor_clues", []))


def audit(reading):
    """The pre-ship checks the first Challenger asked for (research/process/challenger-access-reading-
    instrument-2026-09-18.md, 'Discriminating test'), computed from the reading itself. Returns a list of
    failures; an empty list is required before delivery."""
    fails = []
    for s in reading["sites"]:
        r = s["robots"]
        name = s.get("label") or s["host"]
        if r["decision"] == "requested" and (body_is_challenge(r) or any(not x.get("allowed", True) for k, x in r["verdicts"].items() if k in (READING_TOKEN,))):
            fails.append("%s: page requested although robots.txt was answered with a challenge, or our reading token is disallowed" % name)
        if r["fetch"].get("status") != 200 and r["decision"] == "requested" and not str(r.get("policy_basis", "")).startswith("unavailable"):
            fails.append("%s: page requested although robots.txt was not read (%s)" % (name, r["fetch"].get("status")))
        if r.get("robots_refused") and any(v.get("allowed") for v in r["verdicts"].values()):
            fails.append("%s: robots.txt was refused but a verdict says allowed" % name)
        times = sorted(a["requested_at_utc"] for c in s.get("conditions", {}).values() for a in c["attempts"] if a.get("requested_at_utc"))
        need = min(r.get("crawl_delay_s") or 0, MAX_CRAWL_DELAY)
        if need and len(times) > 1:
            t = [datetime.strptime(x, "%Y-%m-%dT%H:%M:%SZ") for x in times]
            gap = min((b - a).total_seconds() for a, b in zip(t, t[1:]))
            if gap + 1 < need:  # timestamps are whole seconds
                fails.append("%s: smallest gap %.0f s is under the crawl delay %.0f s" % (name, gap, need))
        if s.get("requests_to_host") is not None and s["requests_to_host"] > reading.get("request_ceiling_per_host", 10) and not reading.get("requests_by_host"):
            fails.append("%s: %d requests exceed the stated ceiling" % (name, s["requests_to_host"]))
        if s.get("next_steps") and not s.get("next_steps_reviewed"):
            fails.append("%s: next steps not reviewed" % name)
    for host, n in (reading.get("requests_by_host") or {}).items():
        if n > reading.get("request_ceiling_per_host", 10):
            fails.append("%s: %d requests exceed the stated ceiling" % (host, n))
    return fails


def denominators(reading):
    sites = reading["sites"]
    d = {"sites": len(sites),
         "robots_parsed": sum(1 for s in sites if s["robots"].get("policy_basis") == "parsed"),
         "not_requested_by_robots": sum(1 for s in sites if s["robots"]["decision"] == "not-requested")}
    for c in reading["conditions"]:
        att = [a for s in sites for a in s["conditions"].get(c, {}).get("attempts", [])]
        d[c + "_attempts"] = len(att)
        tally = {}
        for a in att:
            tally[a["outcome"]] = tally.get(a["outcome"], 0) + 1
        d[c + "_outcomes"] = tally
    return d


OK_OUTCOMES = {"delivered", "delivered-feed", "200-unconfirmed"}


def compare(ours, theirs):
    """Two readings of the same scope from two vantages, one row per site. No cause is inferred from a
    difference; the row says what differed."""
    idx = {s["url"]: s for s in theirs["sites"]}
    rows = []
    for s in ours["sites"]:
        t = idx.get(s["url"])

        def word(site):
            if site is None:
                return "not in that reading"
            if site["robots"]["decision"] == "not-requested":
                return "refused at robots.txt" if site["robots"].get("robots_refused") else ("robots.txt unreachable" if site["robots"].get("policy_unknown") else "excluded by robots.txt")
            c = site["conditions"].get("unsigned") or {}
            return c.get("summary", {}).get("summary", "not requested")
        a, b = word(s), word(t)
        if t is None:
            verdict = "only one vantage"
        elif a == b:
            verdict = "same at both vantages"
        elif (a in OK_OUTCOMES) != (b in OK_OUTCOMES):
            verdict = "DIFFERS: served at one vantage and not the other. Observed difference only: the readings were taken at different times and the two environments were not otherwise shown to be equal, so the cause is unresolved"
        else:
            verdict = "differs in kind; both not served"
        rows.append({"site": s.get("label") or s["host"], "url": s["url"], "ours": a, "theirs": b, "verdict": verdict})
    return {"ours": {"vantage": ours.get("vantage"), "started_utc": ours["started_utc"], "user_agent_sent": ours["user_agent_sent"]},
            "theirs": {"vantage": theirs.get("vantage"), "started_utc": theirs["started_utc"], "user_agent_sent": theirs["user_agent_sent"]},
            "same_user_agent": ours["user_agent_sent"] == theirs["user_agent_sent"], "rows": rows}


def compare_md(cmp):
    out = ["# Two vantages, side by side", "",
           "- First vantage: %s (from %s UTC)" % (cmp["ours"]["vantage"], cmp["ours"]["started_utc"]),
           "- Second vantage: %s (from %s UTC)" % (cmp["theirs"]["vantage"], cmp["theirs"]["started_utc"]),
           "- Same User-Agent at both: %s" % ("yes" if cmp["same_user_agent"] else "NO; differences below may follow the User-Agent as well as the network"), "",
           "| Site | First vantage, unsigned | Second vantage, unsigned | Reading |", "|---|---|---|---|"]
    for r in cmp["rows"]:
        out.append("| %s | %s | %s | %s |" % (r["site"], r["ours"], r["theirs"], r["verdict"]))
    n = sum(1 for r in cmp["rows"] if r["verdict"].startswith("DIFFERS"))
    out += ["", "%d of %d sites were served at one vantage and not the other. The readings were not concurrent (start times above), and a site's rules can change between them; network, address, timing and, where the User-Agents differ, the User-Agent all remain possible explanations." % (n, len(cmp["rows"])), ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "check"):
        p = sub.add_parser(name)
        p.add_argument("scope")
        if name == "run":
            p.add_argument("--out")
            p.add_argument("--vantage", help="one line describing the network this run is made from")
    p = sub.add_parser("render")
    p.add_argument("reading")
    p = sub.add_parser("compare")
    p.add_argument("ours")
    p.add_argument("theirs")
    a = ap.parse_args(argv)
    if a.cmd == "compare":
        with open(a.ours, encoding="utf-8") as f1, open(a.theirs, encoding="utf-8") as f2:
            cmp = compare(json.load(f1), json.load(f2))
        dest = os.path.join(os.path.dirname(a.ours), "two-vantages.md")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(compare_md(cmp))
        print(dest)
        return 0
    if a.cmd == "render":
        import render_reading
        with open(a.reading, encoding="utf-8") as f:
            rd = reinterpret(json.load(f))
        with open(a.reading, "w", encoding="utf-8") as f:
            json.dump(rd, f, indent=1)
        print(render_reading.render_files(a.reading))
        return 0
    with open(a.scope, encoding="utf-8") as f:
        scope = json.load(f)
    errs = check_scope(scope)
    if errs:
        print("scope errors:\n  " + "\n  ".join(errs))
        return 2
    if a.cmd == "check":
        print("scope ok:", len(scope["sites"]), "sites; User-Agent that would be sent:", effective_ua(scope))
        return 0
    outdir = a.out or os.path.join(HERE, "readings", scope["reading_id"])
    path = run(scope, outdir, a.vantage)
    import render_reading
    print(render_reading.render_files(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
