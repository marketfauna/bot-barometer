"""Readable report for an Agent Access Reading (no network). Produces reading.md and reading.html next
to reading.json. Every interpretive sentence is generated from a field in the JSON, so the two agree.
Report shape follows research/field/access-reading-comparables-2026-09-18.md section 6F: summary table
first, site detail, then method, limits, prerequisites, appendix and sources."""
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

NOT_200 = ["that the body was the intended content, unless the row says content was confirmed",
           "that the next request, another path, a higher rate or another time of day will pass",
           "that another network will be treated the same way",
           "that the site consents: robots.txt and the site's terms still govern, and this report does not read terms",
           "that the agent is verified anywhere"]
NOT_403 = ["which layer refused: a vendor's edge, the site's own firewall or the application",
           "that the User-Agent was the reason; the control row narrows this but does not settle it",
           "that the refusal is permanent"]
LIMITS = [
    "Vantage: %(vantage)s. Vendors that validate bots by address will never match our address to the customer's bot, in either direction.",
    "The requests were sent by us. A User-Agent is not the customer's egress addresses, session or signing identity.",
    "Vendor clues say which product answered. They do not establish why a request was refused.",
    "Three attempts per condition can show that a response was stable or intermittent in this run. They cannot measure an effect of any one condition.",
    "Validity: one vantage point, one URL per site, the dates shown. Site rules change without notice. This is a dated reading, not monitoring.",
    "Requests: robots.txt, one control and the named conditions make %(budget)s per site before redirects. A counter checked before every request, redirect targets included, stops any request that would be the eleventh to one host in this reading; the most any one host received was %(max_requests)s. Requests were at least %(spacing).1f s apart, and slower where robots.txt carried a crawl delay.",
    "The control request uses a generic, honestly labelled HTTP client, not a browser User-Agent. We do not present as a browser, so the control separates 'this agent name' from 'any non-browser client at this address', and cannot show what a browser would receive.",
    "Nothing in this report suggests disguising the agent, rotating addresses or solving challenges, and we will not advise it.",
]


def _seq(cond):
    if not cond or not cond.get("attempts"):
        return "not requested"
    parts = [str(a["status"]) if a.get("status") is not None else "fail" for a in cond["attempts"]]
    return ", ".join(parts) + " (" + cond["summary"]["summary"] + ")"


def _clues(site, refused_only=False):
    seen = {}
    for c in site.get("conditions", {}).values():
        for a in c.get("attempts", []):
            for v in a.get("vendor_clues", []):
                seen.setdefault((v["vendor"], v["clue"]), v)
    order = {"decisive": 0, "transit": 1, "possible": 2}
    return sorted(seen.values(), key=lambda v: (order.get(v.get("tier"), 3), v["vendor"]))


def _robots_line(site, token):
    r = site["robots"]
    v = r["verdicts"].get(token)
    if not v:
        return ""
    word = "unknown" if r.get("policy_unknown") else ("allowed" if v["allowed"] else "disallowed")
    rule = v.get("matched_rule")
    tail = (" by line %d, `%s: %s`" % (rule["line"], rule["kind"], rule["pattern"])) if rule else ""
    return "`%s`: %s%s (%s)" % (token, word, tail, v["basis"])


def _attempt_lines(site):
    """Identical attempts within a condition are folded into one line; nothing is averaged."""
    out = []
    for cname, c in site["conditions"].items():
        groups = []
        for a in c["attempts"]:
            h = a.get("headers", {}) or {}
            key = (a.get("status"), a["outcome"], h.get("content-type", "").split(";")[0], a.get("body_sha256"), a.get("final_url"), a.get("error"))
            if groups and groups[-1][0] == key:
                groups[-1][1].append(a)
            else:
                groups.append((key, [a]))
        for key, items in groups:
            a = items[0]
            h = a.get("headers", {}) or {}
            f = a.get("body_facts", {}) or {}
            times = ", ".join(x.get("requested_at_utc", "")[11:19] for x in items)
            bits = ["%s, %d of %d identical (%s UTC)" % (cname, len(items), len(c["attempts"]), times) if len(items) > 1 else "%s (%s UTC)" % (cname, times),
                    "status %s" % (a.get("status") if a.get("status") is not None else "none"), a["outcome"]]
            if h.get("content-type"):
                bits.append("content-type %s" % h["content-type"].split(";")[0])
            bits.append("%d bytes read, sha256 %s" % (a.get("body_bytes_read", 0), (a.get("body_sha256") or "")[:12]))
            if f.get("title"):
                bits.append("title %r" % f["title"])
            for k in ("retry-after", "age", "cf-cache-status", "x-cache"):
                if h.get(k):
                    bits.append("%s %s" % (k, h[k]))
            if a.get("final_url") and a["final_url"] != site["url"]:
                bits.append("final URL %s" % a["final_url"])
            if a.get("redirect_stopped"):
                bits.append(a["redirect_stopped"])
            if a.get("error"):
                bits.append("client error: %s" % a["error"])
            out.append("- " + "; ".join(bits))
    return out


def _clue_line(v):
    if v.get("source"):
        src = " [source, %s](%s)" % (v.get("source_kind", "source"), v["source"])
    elif v.get("source_kind") == "self-evident":
        src = " (no document cited: the response names the vendor itself)"
    else:
        src = " (no source found; treat as hearsay)"
    return "- %s, %s tier: %s; %s.%s" % (v["vendor"], v.get("tier", "?"), v["clue"], v.get("means", ""), src)


def site_block(site, token):
    lines = ["### " + (site.get("label") or site["host"]), "", "URL read: " + site["url"]]
    if site.get("source"):
        lines.append("")
        lines.append("Why it is on the panel: " + site["source"])
    rp = site.get("reported") or {}
    if rp.get("cause_established_quote"):
        lines.append("")
        lines.append("What that thread established: \"%s\"" % rp["cause_established_quote"])
    r = site["robots"]
    meta = "status %s" % r["fetch"].get("status")
    if r.get("robots_sha256"):
        meta += ", %d bytes, sha256 %s" % (r.get("robots_bytes_read", 0), r["robots_sha256"][:12])
    lines += ["", "**Declared policy.** %s fetched %s (%s). %s. Evaluated for this exact URL under RFC 9309 (longest match wins)." % (
        r["robots_url"], r["fetch"].get("requested_at_utc"), meta, r.get("policy_basis", "")[0].upper() + r.get("policy_basis", "")[1:]), ""]
    for t in dict.fromkeys([token, "MarketfaunaBot", "*", "GPTBot", "ClaudeBot"]):
        line = _robots_line(site, t)
        if line:
            lines.append("- " + line)
    if r.get("identical_file_at"):
        lines.append("- the same robots.txt, byte for byte, is served at %s; a stock file from shared software is the likeliest reason, which we did not confirm" % ", ".join(r["identical_file_at"]))
    if r.get("crawl_delay_lines"):
        lines.append("- the file carries %s (not part of RFC 9309; some verification programmes expect it to be honoured)" % ", ".join("`%s`" % x for x in r["crawl_delay_lines"][:3]))
    if r["decision"] == "not-requested":
        lines += ["", "**Observed.** No page request was made. " + r.get("decision_reason", "")[0].upper() + r.get("decision_reason", "")[1:] + "."]
        rc = r.get("fetch", {}).get("vendor_clues") or []
        if rc:
            lines += ["", "**Clues on the robots.txt response, not causes**", ""] + [_clue_line(v) for v in rc]
    else:
        lines += ["", "**Observed, per attempt**", ""] + _attempt_lines(site)
        notes = []
        if site.get("control_note"):
            notes.append("Control: " + site["control_note"] + ".")
        if site.get("comparison"):
            notes.append("Signed versus unsigned: " + site["comparison"]["note"] + ".")
        if notes:
            lines += [""] + ["- " + n for n in notes]
        clues = _clues(site)
        lines += ["", "**Clues, not causes.** " + "; ".join(site.get("clue_verdict") or ["no vendor clue"]) + ".", ""]
        lines += [_clue_line(v) for v in clues]
        meta2 = ["%d requests reached this host in all, redirects included" % site["requests_to_host"]] if site.get("requests_to_host") else []
        if site.get("spacing_s"):
            meta2.append("requests %.0f s apart" % site["spacing_s"])
        if site.get("spacing_note"):
            meta2.append(site["spacing_note"])
        if site.get("resolved_url"):
            meta2.append("the first answer was a permanent redirect, so later attempts went straight to %s" % site["resolved_url"])
        if meta2:
            lines += ["", "Conduct: " + "; ".join(meta2) + "."]
    steps = site.get("next_steps", [])
    if steps:
        lines += ["", "**Next step**" + ("" if site.get("next_steps_reviewed") else " (rule-suggested, not yet reviewed)"), ""]
        for s in steps:
            src = (" [source](%s)" % s["source"]) if s.get("source") else ""
            line = "- %s.%s" % (s["step"][0].upper() + s["step"][1:], src)
            extra = []
            if s.get("who_acts"):
                extra.append("Who acts: %s" % s["who_acts"])
            if s.get("needs"):
                extra.append("needs: %s" % s["needs"])
            if s.get("acceptance_test"):
                extra.append("done when: %s" % s["acceptance_test"])
            if s.get("basis") and s["basis"].startswith("reported"):
                extra.append(s["basis"])
            if s.get("source_status") and s["source_status"] not in ("read 2026-09-18",):
                extra.append("source status: %s" % s["source_status"])
            lines.append(line + ((" " + "; ".join(extra) + ".") if extra else ""))
    return "\n".join(lines)


def _short_step(site):
    steps = site.get("next_steps", [])
    if not steps:
        return "none recorded"
    s = steps[0]
    who = (" (" + s["who_acts"] + ")") if s.get("who_acts") else ""
    text = s["step"].split(";")[0]
    return (text[:110] + "...") if len(text) > 113 else text + who


def overview_rows(reading):
    rows = []
    tok = reading["agent_token"]
    for s in reading["sites"]:
        r = s["robots"]
        pol = ("refused at robots.txt (%s)" % r["fetch"].get("status")) if r.get("robots_refused") else ("unknown (unreachable)" if r.get("policy_unknown") else ("allowed" if r["verdicts"][tok]["allowed"] else "disallowed"))
        name = s.get("label") or s["host"]
        if r["decision"] == "not-requested":
            rc = sorted({v["vendor"] for v in (r.get("fetch", {}).get("vendor_clues") or []) if v["tier"] != "possible"})
            rows.append((name, pol, "not requested", "not requested", "not requested", ("on robots.txt: " + ", ".join(rc)) if rc else "n/a", _short_step(s)))
            continue
        c = s["conditions"]
        rows.append((name, pol, _seq(c.get("control")), _seq(c.get("unsigned")), _seq(c.get("signed")),
                     "; ".join(s.get("clue_verdict") or ["no vendor clue"]), _short_step(s)))
    return rows


def signing_statements(reading):
    """Only what the record supports: whether a signed condition ran, and what the self-test returned."""
    sg = reading.get("signing")
    if "signed" not in reading.get("conditions", []) or not sg:
        why = reading.get("signing_note")
        return ["No signed requests were made in this reading%s. Nothing here bears on Web Bot Auth." % ((" (" + why + ")") if why else "")]
    st = (sg.get("self_test") or {}).get("status")
    base = "The signed requests used our own key and directory."
    if st == 200:
        return [base + " Cloudflare's public test endpoint accepted the signature and knew the key at the time of this reading; that says nothing about any other verifier or about any site's own rules."]
    if st == 401:
        return [base + " Cloudflare's public test endpoint answered 401, which it documents as a well-formed signature from a key it does not know; we have no evidence that any other verifier knows the key either. Identical signed and unsigned results therefore say nothing about what a recognised key would receive."]
    if st is None:
        return [base + " The signature self-test was not completed in this run, so whether any verifier knows the key is unrecorded here."]
    return [base + " The signature self-test returned status %s, which is neither of the two documented outcomes; treat the signed results as uninterpreted." % st]


def render_md(reading):
    tok = reading["agent_token"]
    d = reading.get("denominators", {})
    routes = {}
    try:
        with open(os.path.join(HERE, "routes.json"), encoding="utf-8") as f:
            routes = json.load(f)
    except OSError:
        pass
    import reading as _R
    fails = _R.audit(reading)
    banner = ["**NOT READY TO DELIVER. Pre-ship audit failures:**", ""] + ["- " + f for f in fails] + [""] if fails else []
    out = ["# Agent Access Reading: " + reading["customer"], ""] + banner + [
           "Reading %s. Requests made %s to %s UTC by %s." % (reading["reading_id"], reading["started_utc"], reading.get("finished_utc", "unfinished"), reading["instrument"]), "",
           "## Overview", "",
           "| Site | robots.txt for %s | Control | Unsigned | Signed | Vendor clue | First next step |" % tok, "|---|---|---|---|---|---|---|"]
    for row in overview_rows(reading):
        out.append("| " + " | ".join(str(x).replace("|", "/") for x in row) + " |")
    if d:
        out += ["", "Counts: %d sites; robots.txt parsed at %d; %d not requested (robots.txt verdict, or policy unreachable)." % (d["sites"], d["robots_parsed"], d["not_requested_by_robots"])]
        for c in reading["conditions"]:
            out.append("%s attempts %d: %s." % (c.capitalize(), d.get(c + "_attempts", 0), ", ".join("%s %d" % kv for kv in sorted(d.get(c + "_outcomes", {}).items())) or "none"))
    out += ["", "## How it was read", "",
            "- Agent token evaluated in robots.txt: `%s`" % tok,
            "- User-Agent sent: `%s` (mode: %s)" % (reading["user_agent_sent"], reading["ua_mode"])]
    if reading.get("control_user_agent"):
        out.append("- Control User-Agent: `%s`" % reading["control_user_agent"])
    out += ["- Accept header: `%s`" % reading.get("accept_header_sent", ""),
            "- Vantage: %s" % reading.get("vantage", "not recorded"),
            "- Attempts: %d per named condition, interleaved, %.1f s apart; conditions: %s" % (reading["attempts_per_condition"], reading["spacing_s"], ", ".join(reading["conditions"]))]
    if reading.get("tls_trust_store"):
        out.append("- TLS verification: %s" % reading["tls_trust_store"])
    sg = reading.get("signing")
    if sg:
        out.append("- Signing: Web Bot Auth (RFC 9421, Ed25519), key id `%s`, directory %s; %s" % (sg["keyid"], sg["agent_url"], sg["note"]))
        st = sg.get("self_test")
        if st:
            out.append("- Signature self-test at %s: status %s at %s (%s). Signature-Input sent: `%s`" % (st["url"], st["status"], st["requested_at_utc"], st["meaning"], st.get("signature_input")))
    fmt = {"vantage": reading.get("vantage", "not recorded"), "budget": reading.get("request_budget_per_site", "8"), "spacing": reading["spacing_s"],
           "max_requests": max(list((reading.get("requests_by_host") or {}).values()) or [x.get("requests_to_host") or 0 for x in reading["sites"]] or [0]) or "not recorded"}
    out += ["", "## What this reading is not", ""] + ["- " + (x % fmt) for x in LIMITS] + ["- " + x for x in signing_statements(reading)]
    out += ["", "HTTP 200 is an HTTP observation, not permission. A 200 does not show:", ""] + ["- " + x for x in NOT_200]
    out += ["", "A 403 does not show:", ""] + ["- " + x for x in NOT_403]
    if routes.get("readiness"):
        out += ["", "## What every recognition route asks the operator for", ""] + ["- " + x[0].upper() + x[1:] for x in routes["readiness"]]
    out += ["", "## Site by site", ""]
    for s in reading["sites"]:
        out += [site_block(s, tok), ""]
    if routes.get("owner_paragraph"):
        out += ["## Appendix: a note to a site owner", "", routes["owner_paragraph"], ""]
    out += ["Marketfauna, hello@marketfauna.com"]
    return "\n".join(out) + "\n"


def _md_to_html(md):
    """Small, sufficient converter for the constructs this report uses."""
    import re
    def inline(t):
        t = html.escape(t, quote=False)
        t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        return t
    lines, out, in_ul, in_table = md.split("\n"), [], False, False
    for ln in lines:
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if set(ln.replace("|", "").strip()) <= set("-"):
                continue
            if not in_table:
                out.append('<div class="tw"><table><thead><tr>' + "".join("<th>%s</th>" % inline(c) for c in cells) + "</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</tbody></table></div>")
            in_table = False
        if ln.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append("<li>%s</li>" % inline(ln[2:]))
            continue
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if ln.startswith("### "):
            out.append("<h3>%s</h3>" % inline(ln[4:]))
        elif ln.startswith("## "):
            out.append("<h2>%s</h2>" % inline(ln[3:]))
        elif ln.startswith("# "):
            out.append("<h1>%s</h1>" % inline(ln[2:]))
        elif ln.strip():
            out.append("<p>%s</p>" % inline(ln))
    if in_ul:
        out.append("</ul>")
    if in_table:
        out.append("</tbody></table></div>")
    return "\n".join(out)


CSS = """:root{--bg:#f6f7f9;--fg:#14171c;--mut:#4f5865;--line:#d5d9e0;--acc:#1c5cab;--code:#eceef2}
@media (prefers-color-scheme:dark){:root{--bg:#15171b;--fg:#f1f2f4;--mut:#b5bcc7;--line:#30353d;--acc:#86b6ef;--code:#1e2127}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 Georgia,serif}
main{max-width:900px;margin:0 auto;padding:28px 16px 64px}
h1,h2,h3{font-family:Arial,Helvetica,sans-serif;line-height:1.2;text-wrap:balance}
h1{font-size:30px}h2{font-size:21px;margin-top:36px;border-top:2px solid var(--fg);padding-top:14px}h3{font-size:18px;margin-top:30px;border-top:1px solid var(--line);padding-top:12px}
a{color:var(--acc)}code{font:13px Consolas,monospace;background:var(--code);padding:1px 4px;border-radius:3px;word-break:break-all}
.tw{overflow-x:auto}table{border-collapse:collapse;font:14px Arial,sans-serif;width:100%}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
ul{padding-left:20px}li{margin:3px 0}p,li{max-width:74ch}"""


def render_html(reading):
    body = _md_to_html(render_md(reading))
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Agent Access Reading %s</title><style>%s</style></head><body><main>%s</main></body></html>"
            % (html.escape(reading["reading_id"]), CSS, body))


def render_files(json_path):
    with open(json_path, encoding="utf-8") as f:
        reading = json.load(f)
    base = os.path.dirname(json_path)
    with open(os.path.join(base, "reading.md"), "w", encoding="utf-8") as f:
        f.write(render_md(reading))
    with open(os.path.join(base, "reading.html"), "w", encoding="utf-8") as f:
        f.write(render_html(reading))
    return os.path.join(base, "reading.md")
