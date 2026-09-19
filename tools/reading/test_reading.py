"""Offline tests for the delivery instrument. Run: python -m unittest test_reading -v"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rfc9309
import reading as R
import render_reading as RR


class Robots(unittest.TestCase):
    def test_longest_match_allow_beats_shorter_disallow(self):
        # RFC 9309 section 5.2 style example
        txt = "User-agent: *\nDisallow: /example/page/disallowed.gif\nAllow: /example/page/\nDisallow: /example/\n"
        self.assertTrue(rfc9309.evaluate(txt, "foobot", "https://x.test/example/page/index.html")["allowed"])
        self.assertFalse(rfc9309.evaluate(txt, "foobot", "https://x.test/example/page/disallowed.gif")["allowed"])
        self.assertFalse(rfc9309.evaluate(txt, "foobot", "https://x.test/example/other")["allowed"])

    def test_file_order_does_not_matter(self):
        # urllib.robotparser answers False here (first match); the RFC answer is True
        txt = "User-agent: *\nDisallow: /\nAllow: /feed/\n"
        self.assertTrue(rfc9309.evaluate(txt, "reader", "https://x.test/feed/rss.xml")["allowed"])
        self.assertFalse(rfc9309.evaluate(txt, "reader", "https://x.test/about")["allowed"])

    def test_tie_goes_to_allow(self):
        txt = "User-agent: *\nDisallow: /a\nAllow: /a\n"
        self.assertTrue(rfc9309.evaluate(txt, "b", "https://x.test/a")["allowed"])

    def test_wildcard_and_end_anchor(self):
        txt = "User-agent: *\nDisallow: /*.php$\nDisallow: /private*/secret\n"
        self.assertFalse(rfc9309.evaluate(txt, "b", "https://x.test/index.php")["allowed"])
        self.assertTrue(rfc9309.evaluate(txt, "b", "https://x.test/index.php?x=1")["allowed"])
        self.assertFalse(rfc9309.evaluate(txt, "b", "https://x.test/private-zone/secret/file")["allowed"])

    def test_named_group_replaces_wildcard_group(self):
        txt = "User-agent: *\nDisallow: /\n\nUser-agent: Iframely\nAllow: /\n"
        self.assertTrue(rfc9309.evaluate(txt, "Iframely", "https://x.test/p")["allowed"])
        self.assertFalse(rfc9309.evaluate(txt, "Other", "https://x.test/p")["allowed"])
        v = rfc9309.evaluate(txt, "iframely", "https://x.test/p")
        self.assertIn("named group", v["basis"])

    def test_multiple_agents_share_a_group_and_groups_merge(self):
        txt = "User-agent: a\nUser-agent: b\nDisallow: /x\n\nUser-agent: a\nDisallow: /y\n"
        self.assertFalse(rfc9309.evaluate(txt, "a", "https://x.test/y")["allowed"])
        self.assertFalse(rfc9309.evaluate(txt, "a", "https://x.test/x")["allowed"])
        self.assertTrue(rfc9309.evaluate(txt, "b", "https://x.test/y")["allowed"])

    def test_empty_disallow_allows_everything(self):
        self.assertTrue(rfc9309.evaluate("User-agent: *\nDisallow:\n", "b", "https://x.test/any")["allowed"])

    def test_percent_encoding_normalised(self):
        txt = "User-agent: *\nDisallow: /a%2Db/\n"  # %2D is '-', an unreserved character
        self.assertFalse(rfc9309.evaluate(txt, "b", "https://x.test/a-b/c")["allowed"])

    def test_matched_rule_reports_line(self):
        v = rfc9309.evaluate("# c\nUser-agent: *\nDisallow: /z\n", "b", "https://x.test/z1")
        self.assertEqual(v["matched_rule"], {"kind": "disallow", "pattern": "/z", "line": 3})

    # the five cases the first Challenger found failing (2026-09-18)
    def test_bom_does_not_drop_first_group(self):
        self.assertFalse(rfc9309.evaluate("\ufeffUser-agent: *\nDisallow: /\n", "MarketfaunaBot", "https://e.org/feed")["allowed"])
        self.assertFalse(rfc9309.evaluate(b"\xef\xbb\xbfUser-agent: *\nDisallow: /\n", "MarketfaunaBot", "https://e.org/feed")["allowed"])

    def test_user_agent_line_with_version_or_star_matches_product_token(self):
        txt = "User-agent: MarketfaunaBot/1.0\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        self.assertFalse(rfc9309.evaluate(txt, "MarketfaunaBot", "https://e.org/feed")["allowed"])
        self.assertFalse(rfc9309.evaluate("User-agent: MarketfaunaBot*\nDisallow: /\n", "MarketfaunaBot", "https://e.org/feed")["allowed"])
        self.assertTrue(rfc9309.evaluate("User-agent: Bot\nDisallow: /\n", "MarketfaunaBot", "https://e.org/feed")["allowed"])

    def test_query_percent_encoding_is_normalised_like_the_pattern(self):
        self.assertFalse(rfc9309.evaluate("User-agent: *\nDisallow: /s?q=~x\n", "B", "https://e.org/s?q=%7Ex")["allowed"])
        self.assertFalse(rfc9309.evaluate("User-agent: *\nDisallow: /s?u=%2Fa\n", "B", "https://e.org/s?u=%2fa")["allowed"])

    def test_product_token(self):
        self.assertEqual(rfc9309.product_token("Iframely/1.3.1 (+https://iframely.com/docs/about)"), "Iframely")


class Scope(unittest.TestCase):
    def base(self):
        return {"reading_id": "t", "customer": "Test & Co", "agent_token": "TestBot", "user_agent": "TestBot/2.0 (+https://t.example)",
                "sites": [{"url": "https://a.example/feed"}]}

    def test_ok_and_appended_ua_is_honest(self):
        s = self.base()
        self.assertEqual(R.check_scope(s), [])
        ua = R.effective_ua(s)
        self.assertTrue(ua.startswith("TestBot/2.0"))
        self.assertIn("MarketfaunaReading/1.0", ua)
        self.assertIn("reading for Test  Co", ua)

    def test_verbatim_needs_authorisation(self):
        s = self.base(); s["ua_mode"] = "verbatim"
        self.assertTrue(any("verbatim_authorized_by" in e for e in R.check_scope(s)))
        s["verbatim_authorized_by"] = "J. Doe, email of 2026-09-20"
        self.assertEqual(R.check_scope(s), [])
        self.assertEqual(R.effective_ua(s), s["user_agent"])

    def test_limits(self):
        s = self.base(); s["sites"] = [{"url": "https://h%d.example/" % i} for i in range(26)]
        self.assertTrue(any("more than 25" in e for e in R.check_scope(s)))
        s = self.base(); s["sites"] = [{"url": "https://a.example/1"}, {"url": "https://a.example/2"}]
        self.assertTrue(any("one URL per site" in e for e in R.check_scope(s)))
        s = self.base(); s["sites"] = [{"url": "https://user:pw@a.example/"}]
        self.assertTrue(any("credentials" in e for e in R.check_scope(s)))


class Interpretation(unittest.TestCase):
    def test_classify(self):
        f = R.body_facts(b"<html><title>Just a moment...</title>cf-chl</html>")
        self.assertEqual(R.classify_attempt({"status": 403, "headers": {"cf-mitigated": "challenge"}}, f), "challenge")
        self.assertEqual(R.classify_attempt({"status": 403, "headers": {}}, R.body_facts(b"Forbidden")), "refused")
        self.assertEqual(R.classify_attempt({"status": 429, "headers": {}}, {}), "rate-limited")
        self.assertEqual(R.classify_attempt({"status": None, "error": "x"}, {}), "transport-failure")
        self.assertEqual(R.classify_attempt({"status": 200, "headers": {}}, R.body_facts(b"<?xml version='1.0'?><rss version='2.0'>")), "delivered-feed")
        self.assertEqual(R.classify_attempt({"status": 200, "headers": {}}, R.body_facts(b"<title>Home</title>")), "200-unconfirmed")
        self.assertEqual(R.classify_attempt({"status": 200, "headers": {}}, R.body_facts(b"<title>Home</title> hello world", "Hello World")), "delivered")
        self.assertEqual(R.classify_attempt({"status": 200, "headers": {}}, R.body_facts(b"<title>x</title>", "absent")), "200-marker-missing")
        self.assertEqual(R.classify_attempt({"status": 200, "headers": {}}, R.body_facts(b"<title>Just a moment...</title>")), "200-challenge-page")

    def test_vendor_clues_are_sourced_and_cookie_values_never_kept(self):
        table = R.load_json("vendor_clues.json")
        rec = {"headers": {"cf-ray": "abc", "cf-mitigated": "challenge", "set-cookie-names": ["datadome", "_pxhd"]}}
        got = {(v["vendor"], v["clue"]) for v in R.vendor_clues(rec, table)}
        self.assertIn(("Cloudflare", "cf-mitigated: challenge"), got)
        self.assertIn(("DataDome", "datadome cookie set"), got)
        self.assertIn(("HUMAN (PerimeterX)", "_px* cookie set"), got)
        tiers = {v["clue"]: v["tier"] for v in R.vendor_clues(rec, table)}
        self.assertEqual(tiers["cf-mitigated: challenge"], "decisive")
        self.assertEqual(tiers["cf-ray header"], "transit")
        body = R.vendor_clues({"headers": {}}, table, "<h1>error code: 1020</h1> vercel security checkpoint")
        self.assertEqual({v["vendor"] for v in body}, {"Cloudflare", "Vercel"})
        for c in table["clues"]:
            self.assertIn(c["tier"], ("decisive", "transit", "possible"))
            if c["tier"] != "possible" and c["source_kind"] != "self-evident":
                self.assertTrue(c["source"], c["label"])

        class Msg:
            def items(self):
                return [("Set-Cookie", "session=SECRETVALUE; Path=/"), ("Server", "x")]
        h = R._headers_record(Msg())
        self.assertEqual(h["set-cookie-names"], ["session"])
        self.assertNotIn("SECRETVALUE", json.dumps(h))

    def test_comparison_wording_never_claims_an_effect(self):
        mk = lambda sts: {"attempts": [{"status": s, "outcome": "refused" if s == 403 else "200-unconfirmed"} for s in sts]}
        site = {"conditions": {"unsigned": mk([403, 403, 403]), "signed": mk([200, 200, 200])}}
        for c in site["conditions"].values():
            c["summary"] = R.summarise_condition(c["attempts"])
        note = R.compare_conditions(site)["note"]
        self.assertIn("not a measured effect", note)
        site["conditions"]["signed"] = mk([403, 403, 403]); site["conditions"]["signed"]["summary"] = R.summarise_condition(site["conditions"]["signed"]["attempts"])
        self.assertIn("does not show that signing is useless", R.compare_conditions(site)["note"])

    def test_next_steps_for_robots_exclusion_and_refusal(self):
        routes = R.load_json("routes.json")
        site = {"host": "www.example.org", "robots": {"decision": "not-requested"}, "conditions": {}}
        self.assertIn("excluded", R.next_steps(site, routes)[0]["step"])
        site = {"host": "blog.example.org", "robots": {"decision": "requested"},
                "conditions": {"unsigned": {"attempts": [{"outcome": "challenge", "vendor_clues": [
                    {"vendor": "Cloudflare", "tier": "decisive", "clue": "cf-mitigated: challenge", "means": "m", "source": "u"}]}]}}}
        steps = R.next_steps(site, routes)
        self.assertTrue(any("Cloudflare" in s["basis"] for s in steps))
        self.assertTrue(all("step" in s for s in steps))
        self.assertTrue(all(s.get("who_acts") and s.get("acceptance_test") for s in steps))

    def test_control_note_separates_name_from_address(self):
        mk = lambda out, n=1: {"attempts": [{"status": 0, "outcome": out}] * n, "summary": {"summary": out}}
        site = {"conditions": {"control": mk("200-unconfirmed"), "unsigned": mk("refused", 3)}}
        self.assertIn("follows the User-Agent", R.control_note(site))
        site = {"conditions": {"control": mk("challenge"), "unsigned": mk("challenge", 3)}}
        self.assertIn("not specific to the agent's name", R.control_note(site))

    def test_cloudflare_block_page_is_refused_and_decisive(self):
        table = R.load_json("vendor_clues.json")
        facts = R.body_facts(b"<title>Attention Required! | Cloudflare</title> captcha challenge-platform")
        rec = {"status": 403, "headers": {"cf-ray": "x", "server": "cloudflare"}}
        self.assertEqual(R.classify_attempt(rec, facts), "refused")
        tiers = {v["tier"] for v in R.vendor_clues(rec, table, "", facts["title"]) if v["vendor"] == "Cloudflare"}
        self.assertIn("decisive", tiers)

    def test_self_hosted_operator_is_not_sent_to_vendor_programmes(self):
        routes = R.load_json("routes.json")
        cf = {"vendor": "Cloudflare", "tier": "decisive", "clue": "cf-mitigated: challenge", "means": "m", "source": "u"}
        site = {"host": "x.example", "robots": {"decision": "requested"}, "reported": {"route_mentioned": "owner exempted the feed URLs", "report_url": "https://t.example/1"},
                "conditions": {"unsigned": {"attempts": [{"outcome": "challenge", "vendor_clues": [cf]}]}}}
        steps = R.next_steps(site, routes, {"can_apply_to_programmes": False})
        self.assertIn("public thread already records", steps[0]["step"])
        self.assertFalse(any("Bot Submission Form" in s["step"] for s in steps))
        self.assertTrue(any("Bot Submission Form" in s["step"] for s in R.next_steps(site, routes, {"can_apply_to_programmes": True})))

    def test_evasive_thread_workarounds_are_not_relayed(self):
        site = {"host": "x.example", "robots": {"decision": "requested"}, "reported": {"route_mentioned": "FlareSolverr extension solved the challenge", "report_url": "u"},
                "conditions": {"unsigned": {"attempts": [{"outcome": "challenge", "vendor_clues": []}]}}}
        steps = R.next_steps(site, R.load_json("routes.json"))
        self.assertNotIn("flaresolverr", json.dumps(steps).lower())
        self.assertIn("do not pass such workarounds on", steps[0]["step"])

    def test_served_site_is_never_called_done(self):
        site = {"host": "x.example", "robots": {"decision": "requested"}, "conditions": {"unsigned": {"attempts": [{"outcome": "delivered-feed", "vendor_clues": []}]}}}
        self.assertIn("does not predict the operator's network", R.next_steps(site, R.load_json("routes.json"))[0]["step"])

    def test_audit_catches_the_first_reading_faults(self):
        v = {"allowed": True, "basis": "x", "matched_rule": None}
        site = {"host": "h", "label": "h", "robots": {"fetch": {"status": 403}, "decision": "requested", "policy_basis": "robots.txt request was itself refused", "verdicts": {"*": v},
                                                     "robots_refused": True, "crawl_delay_s": 10},
                "conditions": {"unsigned": {"attempts": [{"requested_at_utc": "2026-09-18T21:00:00Z"}, {"requested_at_utc": "2026-09-18T21:00:02Z"}]}},
                "requests_to_host": 15, "next_steps": [{"step": "x"}], "next_steps_reviewed": False}
        fails = R.audit({"sites": [site]})
        self.assertEqual(len(fails), 5, fails)

    def test_two_vantages_report_a_difference_without_a_cause(self):
        def rd(summary, vant):
            return {"vantage": vant, "started_utc": "t", "user_agent_sent": "UA", "sites": [
                {"url": "https://a.example/f", "host": "a.example", "label": None, "robots": {"decision": "requested"},
                 "conditions": {"unsigned": {"summary": {"summary": summary}}}}]}
        cmp = R.compare(rd("delivered-feed", "home line"), rd("refused", "cloud host"))
        self.assertTrue(cmp["rows"][0]["verdict"].startswith("DIFFERS"))
        md = R.compare_md(cmp)
        self.assertIn("1 of 1 sites", md)
        self.assertNotIn("because", md.lower())
        self.assertEqual(R.compare(rd("refused", "a"), rd("refused", "b"))["rows"][0]["verdict"], "same at both vantages")

    def test_robots_answered_with_a_200_challenge_page_is_a_refusal(self):
        # the second Challenger's discriminating test (2026-09-18)
        import reading as mod
        html_challenge = b"<html><head><title>Just a moment...</title></head><body>Verify you are human</body></html>"
        calls = []

        def fake_fetch(url, ua, extra=None, **kw):
            calls.append(url)
            return {"url": url, "requested_at_utc": "2026-09-18T22:00:00Z", "status": 200, "headers": {"content-type": "text/html"}, "requests_made": 1}, html_challenge
        real = mod.fetch
        mod.fetch = fake_fetch
        try:
            r = mod.robots_for("https://x.example/feed", "TestBot", "UA")
        finally:
            mod.fetch = real
        self.assertEqual(r["decision"], "not-requested")
        self.assertTrue(r["robots_refused"])
        self.assertFalse(any(v["allowed"] for v in r["verdicts"].values()))

    def test_reading_token_and_control_token_are_honoured(self):
        import reading as mod
        txt = b"User-agent: MarketfaunaReading\nDisallow: /\n\nUser-agent: python-urllib\nDisallow: /\n\nUser-agent: *\nAllow: /\n"

        def fake_fetch(url, ua, extra=None, **kw):
            return {"url": url, "requested_at_utc": "t", "status": 200, "headers": {"content-type": "text/plain"}, "requests_made": 1}, txt
        real = mod.fetch
        mod.fetch = fake_fetch
        try:
            r = mod.robots_for("https://x.example/feed", "TestBot", "UA")
        finally:
            mod.fetch = real
        self.assertEqual(r["decision"], "not-requested")
        self.assertFalse(r["control_allowed"])
        self.assertIn("MarketfaunaReading", r["decision_reason"])

    def test_compare_never_names_a_cause_even_with_same_user_agent(self):
        def rd(summary, ua, start):
            return {"vantage": "v", "started_utc": start, "user_agent_sent": ua, "sites": [
                {"url": "https://a.example/f", "host": "a.example", "label": None, "robots": {"decision": "requested"},
                 "conditions": {"unsigned": {"summary": {"summary": summary}}}}]}
        for ua2 in ("UA", "OtherUA"):
            cmp = R.compare(rd("delivered-feed", "UA", "2026-09-18T21:00:00Z"), rd("refused", ua2, "2026-09-19T09:00:00Z"))
            text = (cmp["rows"][0]["verdict"] + R.compare_md(cmp)).lower()
            self.assertNotIn("follows the network", text)
            self.assertNotIn("otherwise the same", text)
            self.assertIn("cause is unresolved", text)
            self.assertIn("not concurrent", text)
        self.assertIn("NO; differences", R.compare_md(R.compare(rd("refused", "UA", "t1"), rd("refused", "OtherUA", "t2"))))

    def test_eleventh_request_to_a_host_never_starts(self):
        import reading as mod
        started = []

        class FakeResp:
            status = 302

            def __init__(self, url):
                self.headers = {"Location": url + "x"}

            def read(self, n=-1):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class FakeOpener:
            def open(self, req, timeout=None):
                started.append(req.full_url)
                return FakeResp(req.full_url)
        real_build = mod.urllib.request.build_opener
        mod.urllib.request.build_opener = lambda *a, **k: FakeOpener()
        mod._TLS = (None, "test")
        try:
            mod.reset_host_budget()
            recs = []
            for _ in range(4):  # each call would follow up to six same-host temporary redirects
                rec, _ = mod.fetch("https://loop.example/a", "UA")
                recs.append(rec)
            other, _ = mod.fetch("https://other.example/a", "UA", max_hops=0)
        finally:
            mod.urllib.request.build_opener = real_build
            mod._TLS = None
        self.assertEqual(sum(1 for u in started if "loop.example" in u), 10)
        self.assertTrue(any(r.get("budget_stopped") for r in recs))
        self.assertEqual(mod.classify_attempt([r for r in recs if r.get("budget_stopped")][0], {}), "budget-stop")
        self.assertEqual(sum(1 for u in started if "other.example" in u), 1)  # a separate host keeps its own budget
        self.assertEqual(mod._HOST_COUNTS["loop.example"], 10)

    def test_redirect_target_disallowed_for_the_reading_token_is_never_requested(self):
        import reading as mod
        robots = b"User-agent: MarketfaunaReading\nDisallow: /private/\n\nUser-agent: python-urllib\nDisallow: /ctl/\n\nUser-agent: *\nAllow: /\n"
        cache = {}
        real = mod.fetch
        mod.fetch = lambda url, ua, extra=None, **kw: ({"url": url, "requested_at_utc": "t", "status": 200, "headers": {"content-type": "text/plain"}, "requests_made": 1}, robots)
        try:
            cache["https://x.example"] = mod.robots_for("https://x.example/feed", "TestBot", "UA")
        finally:
            mod.fetch = real
        named = mod.make_hop_check("TestBot", "UA", cache)
        ctl = mod.make_hop_check("TestBot", "UA", cache, control=True)
        self.assertEqual(named("https://x.example/private/feed")[0], False)
        self.assertIn("MarketfaunaReading", named("https://x.example/private/feed")[1])
        self.assertEqual(named("https://x.example/ctl/feed")[0], True)
        self.assertEqual(ctl("https://x.example/ctl/feed")[0], False)
        self.assertEqual(ctl("https://x.example/private/feed")[0], True)
        # and fetch() does not start the request when the check refuses
        started = []

        class Resp:
            status = 302
            headers = {"Location": "/private/feed"}

            def read(self, n=-1):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class Opener:
            def open(self, req, timeout=None):
                started.append(req.full_url)
                return Resp()
        rb = mod.urllib.request.build_opener
        mod.urllib.request.build_opener = lambda *a, **k: Opener()
        mod._TLS = (None, "test")
        try:
            mod.reset_host_budget()
            rec, _ = mod.fetch("https://x.example/feed", "UA", hop_allowed=named)
        finally:
            mod.urllib.request.build_opener = rb
            mod._TLS = None
        self.assertEqual(started, ["https://x.example/feed"])
        self.assertIn("not followed", rec["redirect_stopped"])

    def test_signing_statements_follow_the_record(self):
        base = {"conditions": ["control", "unsigned"], "signing": None, "signing_note": "signed condition dropped on this machine: FileNotFoundError"}
        t = " ".join(RR.signing_statements(base))
        self.assertIn("No signed requests were made", t)
        self.assertNotIn("401", t)
        signed = {"conditions": ["unsigned", "signed"], "signing": {"keyid": "k", "agent_url": "u", "note": "n", "self_test": {"status": 401}}}
        self.assertIn("answered 401", " ".join(RR.signing_statements(signed)))
        signed["signing"]["self_test"]["status"] = 200
        self.assertIn("accepted the signature", " ".join(RR.signing_statements(signed)))
        signed["signing"]["self_test"] = {"status": None}
        self.assertIn("not completed", " ".join(RR.signing_statements(signed)))
        signed["signing"]["self_test"] = {"status": 400}
        self.assertIn("uninterpreted", " ".join(RR.signing_statements(signed)))

    def test_aws_waf_202_is_not_delivery(self):
        self.assertEqual(R.classify_attempt({"status": 202, "headers": {"x-amzn-waf-action": "challenge"}}, {}), "challenge")

    def test_no_route_ever_suggests_evasion(self):
        blob = json.dumps(R.load_json("routes.json")).lower()
        for bad in ("proxy", "rotate", "spoof", "solver", "headless", "residential"):
            self.assertNotIn(bad, blob)


class Rendering(unittest.TestCase):
    def fixture(self):
        att = lambda st, out, clues=(): {"status": st, "outcome": out, "final_url": "https://a.example/feed", "vendor_clues": list(clues),
                                         "body_facts": {"title": "T", "challenge_markers": []}}
        cf = {"vendor": "Cloudflare", "tier": "decisive", "clue": "cf-mitigated: challenge", "means": "Cloudflare served a challenge", "source": "https://developers.cloudflare.com/x", "source_kind": "vendor-doc"}
        v = lambda ok: {"allowed": ok, "basis": "wildcard group", "matched_rule": None if ok else {"kind": "disallow", "pattern": "/", "line": 2}}
        s1 = {"url": "https://a.example/feed", "host": "a.example", "label": None, "source": "https://github.com/x/y/issues/1",
              "robots": {"robots_url": "https://a.example/robots.txt", "fetch": {"requested_at_utc": "2026-09-18T21:00:00Z"}, "policy_basis": "parsed",
                         "decision": "requested", "verdicts": {"TestBot": v(True), "MarketfaunaBot": v(True), "*": v(True)}},
              "conditions": {"unsigned": {"attempts": [att(403, "challenge", [cf])] * 3}, "signed": {"attempts": [att(403, "challenge", [cf])] * 3}},
              "next_steps": [{"step": "ask the owner", "source": None, "basis": "general"}], "next_steps_reviewed": False}
        for c in s1["conditions"].values():
            c["summary"] = R.summarise_condition(c["attempts"])
        s1["comparison"] = R.compare_conditions(s1)
        s1["clue_verdict"] = R.clue_verdict(s1)
        s2 = {"url": "https://b.example/", "host": "b.example", "label": "B", "source": None,
              "robots": {"robots_url": "https://b.example/robots.txt", "fetch": {"requested_at_utc": "2026-09-18T21:00:05Z"}, "policy_basis": "parsed",
                         "decision": "not-requested", "decision_reason": "robots.txt verdict is disallow for TestBot; no page request made",
                         "verdicts": {"TestBot": v(False), "MarketfaunaBot": v(True), "*": v(True)}},
              "conditions": {}, "comparison": None, "next_steps": [], "next_steps_reviewed": False}
        rd = {"instrument": R.VERSION, "reading_id": "t-1", "customer": "Test", "agent_token": "TestBot", "user_agent_sent": "TestBot/2 MarketfaunaReading/1.0",
              "ua_mode": "appended", "attempts_per_condition": 3, "spacing_s": 2.0, "conditions": ["unsigned", "signed"],
              "signing": {"keyid": "kid", "agent_url": "https://d.example", "note": "our own key"},
              "started_utc": "2026-09-18T21:00:00Z", "finished_utc": "2026-09-18T21:01:00Z", "sites": [s1, s2]}
        rd["denominators"] = R.denominators(rd)
        return rd

    def test_markdown_carries_limits_sources_and_review_flag(self):
        md = RR.render_md(self.fixture())
        self.assertIn("HTTP 200 is an HTTP observation, not permission", md)
        self.assertIn("403, 403, 403 (challenge)", md)
        self.assertIn("No page request was made", md)
        self.assertIn("rule-suggested, not yet reviewed", md)
        self.assertIn("[source, vendor-doc](https://developers.cloudflare.com/x)", md)
        self.assertIn("answered by Cloudflare (documented marker)", md)
        self.assertIn("A 403 does not show", md)
        self.assertIn("we will not advise it", md)
        self.assertIn("https://github.com/x/y/issues/1", md)
        self.assertNotIn("because of", md.lower())  # no causal language anywhere in generated prose

    def test_html_is_wellformed_enough_and_escapes(self):
        rd = self.fixture()
        rd["customer"] = "<script>x</script>"
        h = RR.render_html(rd)
        self.assertNotIn("<script>x", h)
        self.assertEqual(h.count("<table>"), h.count("</table>"))
        self.assertEqual(h.count("<ul>"), h.count("</ul>"))


if __name__ == "__main__":
    unittest.main()
