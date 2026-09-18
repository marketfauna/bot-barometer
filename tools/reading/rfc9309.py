"""Minimal RFC 9309 robots.txt evaluator (stdlib only).

Why not urllib.robotparser: it applies rules in file order and has no support for the '*' and '$'
special characters, so it can disagree with RFC 9309 section 2.2.2 (longest match wins; on a tie the
allow rule wins). A delivered reading must say what the file means under the published standard.

Scope: groups, user-agent matching (case-insensitive product-token match, '*' fallback), allow and
disallow with '*' and '$', longest-match precedence, percent-encoding normalisation of the path as far
as section 2.2.2 requires for comparison. Not handled: crawl-delay and sitemap are retained as raw
lines but not interpreted; files larger than 500 KiB are truncated at that size as the RFC permits.
"""
import re
from urllib.parse import urlsplit, quote, unquote

MAX_BYTES = 500 * 1024


def _norm_path(p):
    """Normalise for comparison: decode unreserved percent-escapes, keep reserved ones, upper-case hex."""
    if not p:
        return "/"
    out = []
    i = 0
    while i < len(p):
        c = p[i]
        if c == "%" and i + 2 < len(p) and re.fullmatch(r"[0-9A-Fa-f]{2}", p[i + 1:i + 3] or ""):
            ch = chr(int(p[i + 1:i + 3], 16))
            if re.fullmatch(r"[A-Za-z0-9\-._~]", ch):
                out.append(ch)
            else:
                out.append("%" + p[i + 1:i + 3].upper())
            i += 3
        else:
            out.append(c if ord(c) < 128 else quote(c))
            i += 1
    return "".join(out)


def _pattern_to_regex(pat):
    pat = _norm_path(pat) if pat else ""
    anchored = pat.endswith("$")
    if anchored:
        pat = pat[:-1]
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in pat)
    return re.compile("^" + rx + ("$" if anchored else ""))


def parse(text):
    """Return a list of groups: {'agents': [tokens], 'rules': [(kind, pattern, line_no)]}."""
    if isinstance(text, bytes):
        text = text[:MAX_BYTES].decode("utf-8-sig", "replace")
    text = text.lstrip("\ufeff")  # a byte-order mark must not hide the first group
    groups, cur, last_was_agent = [], None, False
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key == "user-agent":
            if cur is None or not last_was_agent:
                cur = {"agents": [], "rules": []}
                groups.append(cur)
            cur["agents"].append(agent_token(val))
            last_was_agent = True
        elif key in ("allow", "disallow"):
            last_was_agent = False
            if cur is None:
                continue  # rule before any user-agent line is ignored
            cur["rules"].append((key, val, n))
        else:
            # other records (sitemap, crawl-delay, host) do not end a group's agent run per common practice
            # but RFC 9309 says only user-agent lines start groups; treat as neutral.
            pass
    return groups


def agent_token(value):
    """Product token of a user-agent line value or of a User-Agent string: the leading run of token
    characters, lower-cased, so 'FooBot/1.0' and 'FooBot*' both name 'foobot' (RFC 9309 2.2.1; the same
    truncation Google's reference parser applies). Digits are kept because real tokens use them."""
    value = (value or "").strip()
    if value.startswith("*"):
        return "*"
    m = re.match(r"[A-Za-z0-9_\-]+", value)
    return m.group(0).lower() if m else value.lower()


def _select_rules(groups, token):
    """Section 2.2.1: merge all groups matching the product token; else all '*' groups; else none."""
    token = agent_token(token)
    named = [g for g in groups if any(a != "*" and a == token for a in g["agents"])]
    if named:
        chosen, basis = named, "named group"
    else:
        star = [g for g in groups if "*" in g["agents"]]
        chosen, basis = star, ("wildcard group" if star else "no applicable group")
    rules = [r for g in chosen for r in g["rules"]]
    return rules, basis


def evaluate(text_or_groups, token, url):
    """Return dict: allowed (bool), basis, matched_rule (kind, pattern, line) or None."""
    groups = parse(text_or_groups) if isinstance(text_or_groups, (str, bytes)) else text_or_groups
    parts = urlsplit(url)
    path = _norm_path((parts.path or "/") + (("?" + parts.query) if parts.query else ""))
    if path == "/robots.txt":
        return {"allowed": True, "basis": "robots.txt itself is always fetchable", "matched_rule": None}
    rules, basis = _select_rules(groups, token)
    best = None
    for kind, pat, line in rules:
        if pat == "":
            continue  # empty disallow/allow matches nothing
        if _pattern_to_regex(pat).match(path):
            length = len(_norm_path(pat))
            cand = (length, 1 if kind == "allow" else 0, kind, pat, line)
            if best is None or cand[:2] > best[:2]:
                best = cand
    if best is None:
        return {"allowed": True, "basis": basis + "; no rule matches this path", "matched_rule": None}
    return {"allowed": best[2] == "allow", "basis": basis + "; longest match wins (RFC 9309 2.2.2)",
            "matched_rule": {"kind": best[2], "pattern": best[3], "line": best[4]}}


def product_token(user_agent_or_token):
    """First product token of a User-Agent string, e.g. 'Iframely/1.3.1 (+https://...)' -> 'Iframely'."""
    m = re.match(r"\s*([A-Za-z0-9_\-]+)", user_agent_or_token or "")
    return m.group(1) if m else ""
