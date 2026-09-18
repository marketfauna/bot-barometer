"""Writes vendor_clues.json and routes.json from one reviewed source, so every entry keeps its tier and source.
Source of the entries: research/field/access-reading-comparables-2026-09-18.md sections 5 and 6."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CF_DET = "https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/"
CF_HDR = "https://developers.cloudflare.com/fundamentals/reference/http-headers/"
CF_1X = "https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/"
AWS_CH = "https://docs.aws.amazon.com/waf/latest/developerguide/waf-captcha-and-challenge-actions.html"
VER_FW = "https://vercel.com/docs/vercel-firewall/firewall-concepts"
HUM_CK = "https://docs.humansecurity.com/applications/cookies"
DD_API = "https://docs.datadome.co/reference/validate-request"
W00F = "https://github.com/EnableSecurity/wafw00f/tree/master/wafw00f/plugins"


def c(vendor, tier, where, key, label, means, source, kind, value=None):
    d = {"vendor": vendor, "tier": tier, "where": where, "key": key, "label": label, "means": means,
         "source": source, "source_kind": kind}
    if value is not None:
        d["value"] = value
    return d


CLUES = {
    "note": "Tiers follow research/field/access-reading-comparables-2026-09-18.md section 6D. decisive = a documented marker "
            "that this vendor made the decision on this response. transit = the response passed through or was instrumented by "
            "the vendor; the refusal may still come from the site's own server. possible = marker known only from third-party "
            "reports. source_kind: vendor-doc, third-party, none. A clue never establishes why a request was refused.",
    "surveyed": "2026-09-18",
    "clues": [
        c("Cloudflare", "decisive", "header-value", "cf-mitigated", "cf-mitigated: challenge", "Cloudflare served a challenge page on this response", CF_DET, "vendor-doc", "challenge"),
        c("Cloudflare", "decisive", "body-regex", r"error code: 10(0[6-9]|1[0-9]|20)", "Cloudflare 1xxx error code in the body", "Cloudflare itself refused the request; the code says which kind of rule", CF_1X, "vendor-doc"),
        c("Cloudflare", "decisive", "title-contains", "attention required! | cloudflare", "block page titled 'Attention Required! | Cloudflare'", "a Cloudflare-branded block page; the page names the vendor itself. This page usually reflects a rule the site owner set, which a vendor programme would not override", None, "self-evident"),
        c("Vercel", "decisive", "header-value", "x-vercel-mitigated", "x-vercel-mitigated: challenge", "a Vercel-named mitigation header on the response; the header names the vendor itself. We did not find it in the Vercel documentation we read", None, "self-evident", "challenge"),
        c("Anubis", "possible", "body-contains", "making sure you&#39;re not a bot", "Anubis interstitial text", "the open-source Anubis proof-of-work gate, which the site owner runs and configures", "https://github.com/TecharoHQ/anubis", "third-party"),
        c("Anubis", "possible", "body-contains", "within.website/x/cmd/anubis", "Anubis asset path in the body", "the open-source Anubis proof-of-work gate, which the site owner runs and configures", "https://github.com/TecharoHQ/anubis", "third-party"),
        c("Cloudflare", "transit", "header-present", "cf-ray", "cf-ray header", "the response passed through Cloudflare", CF_HDR, "vendor-doc"),
        c("AWS WAF", "decisive", "header-present", "x-amzn-waf-action", "x-amzn-waf-action header", "AWS WAF answered with a challenge or CAPTCHA action (HTTP 202 or 405); this is not delivery", AWS_CH, "vendor-doc"),
        c("Amazon CloudFront", "transit", "header-present", "x-amz-cf-id", "x-amz-cf-id header", "the response passed through CloudFront; AWS WAF may or may not be attached", W00F, "third-party"),
        c("Vercel", "decisive", "body-contains", "vercel security checkpoint", "Vercel Security Checkpoint page", "Vercel's firewall served its challenge page, which scripts cannot pass", VER_FW, "vendor-doc"),
        c("Vercel", "transit", "header-present", "x-vercel-id", "x-vercel-id header", "the response was served by Vercel", W00F, "third-party"),
        c("HUMAN (PerimeterX)", "decisive", "body-contains", "press & hold", "Press & Hold block page", "HUMAN served its block page", "https://www.humansecurity.com/ai-agent-verification/", "vendor-doc"),
        c("HUMAN (PerimeterX)", "transit", "cookie-prefix", "_px", "_px* cookie set", "the HUMAN sensor is present on this site", HUM_CK, "vendor-doc"),
        c("Imperva", "decisive", "body-contains", "incapsula incident id", "Incapsula incident ID in the body", "Imperva served a block page", W00F, "third-party"),
        c("Imperva", "transit", "cookie-prefix", "incap_ses", "incap_ses cookie set", "the site is behind Imperva Cloud WAF", W00F, "third-party"),
        c("Imperva", "transit", "cookie-prefix", "visid_incap", "visid_incap cookie set", "the site is behind Imperva Cloud WAF", W00F, "third-party"),
        c("DataDome", "transit", "cookie-prefix", "datadome", "datadome cookie set", "the DataDome module is in the request path", DD_API, "vendor-doc"),
        c("DataDome", "possible", "header-present", "x-datadome", "x-datadome header", "reported by third parties as DataDome; not confirmed in vendor documentation", None, "none"),
        c("Akamai", "transit", "header-value", "server", "server: AkamaiGHost", "the response was generated by an Akamai edge server; not proof that Bot Manager decided", W00F, "third-party", "akamaighost"),
        c("Akamai", "possible", "cookie-prefix", "_abck", "_abck cookie set", "reported by third parties as Akamai Bot Manager; not confirmed in vendor documentation", None, "none"),
        c("Akamai", "possible", "cookie-prefix", "bm_sz", "bm_sz cookie set", "reported by third parties as Akamai Bot Manager; not confirmed in vendor documentation", None, "none"),
        c("Fastly", "possible", "header-value", "x-served-by", "x-served-by: cache-*", "commonly set by Fastly; says nothing about who refused", None, "none", "cache-"),
        c("Kasada", "possible", "header-prefix", "x-kpsdk", "x-kpsdk-* header", "reported by third parties as Kasada; no vendor documentation found", None, "none"),
        c("F5 BIG-IP", "possible", "body-contains", "the requested url was rejected. please consult with your administrator", "F5 'requested URL was rejected' page", "reported as a BIG-IP application-firewall policy block; vendor page not read", None, "none"),
    ],
}

ACC = "after the change, the agent's own request returns the expected content on 3 of 3 attempts"


def r(step, who, needs, accept, source, status="read 2026-09-18"):
    return {"step": step, "who_acts": who, "needs": needs, "acceptance_test": accept, "source": source, "source_status": status}


NO_ROUTE = "no public operator route found as of 2026-09-18; the route is the site owner"
ROUTES = {
    "note": "Documented routes by which an identified bot's operator, or the site owner, can change the outcome. 'No operator "
            "route found' is a dated finding. No entry ever suggests disguising the agent, rotating addresses or solving challenges.",
    "surveyed": "2026-09-18",
    "vendors": {
        "Cloudflare": [
            r("apply to Cloudflare's verified bots or signed agents programme through the Bot Submission Form in a Cloudflare account; approval is Cloudflare's decision and no site is obliged to admit a verified bot",
              "operator", "a Cloudflare account; a product-token User-Agent with an information page; published IP ranges or a Web Bot Auth key directory",
              "Cloudflare lists the bot; then " + ACC, "https://developers.cloudflare.com/bots/concepts/bot/verified-bots/"),
            r("ask the site owner to add a WAF custom rule that skips bot protections for this agent; Cloudflare's documentation says Bot Fight Mode cannot be bypassed or skipped by WAF custom rules or Page Rules, and that exceptions need Super Bot Fight Mode, which supports Skip rules",
              "site owner", "the agent's User-Agent token and information page; IP ranges or key directory if the owner wants to match on them",
              ACC, "https://developers.cloudflare.com/bots/get-started/bot-fight-mode/")],
        "AWS WAF": [r("no public operator form exists; the site owner can allow the agent by label or scope-down rule, and AWS Support can be asked for a bot classification; Web Bot Auth is honoured from Bot Control rule group version 4.0",
                      "site owner", "the agent's User-Agent token; the Bot Control category it falls in (content fetcher, page preview, monitoring)",
                      ACC, "https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-bot.html")],
        "DataDome": [r("apply through DataDome's bot and AI agent verification form (stated review time 3 to 5 business days); a dedicated User-Agent plus one authentication method is required (Web Bot Auth, reverse DNS, static IPs, dynamic IP file or private AS)",
                       "operator", "a dedicated User-Agent; one of the five authentication methods",
                       "DataDome confirms verification; then " + ACC, "https://datadome.co/resources/bot-and-ai-agent-verification/")],
        "Vercel": [r("submit the bot at bots.fyi/new-bot (name, description, documentation URL, verification instructions, contact); Vercel verifies by IP, reverse DNS or Web Bot Auth",
                     "operator", "a documentation page for the bot; one verification method",
                     "the bot appears in Vercel's directory; then " + ACC, "https://vercel.com/docs/bot-management")],
        "HUMAN (PerimeterX)": [r("HUMAN publishes an AI agent verification form; we could not read it (it served HUMAN's own challenge to us), so this route is unconfirmed; the site owner can also allow the agent under HUMAN's known bots and crawlers policy",
                                 "operator or site owner", "an identity HUMAN accepts (not confirmed by us)", ACC,
                                 "https://docs.humansecurity.com/applications/known-bots-and-crawlers", "form not read")],
        "Akamai": [r("no public operator form found as of 2026-09-18; Akamai writes that it validates Web Bot Auth signatures at the edge by discovering the key directory; the practical route is the site owner",
                     "site owner", "the agent's User-Agent token, information page, and key directory or IP list", ACC,
                     "https://www.akamai.com/blog/security/redefine-trust-web-bot-authentication")],
        "Imperva": [r(NO_ROUTE, "site owner", "the agent's User-Agent token, information page, and IP list", ACC, None, "none found")],
        "Kasada": [r(NO_ROUTE, "site owner", "the agent's User-Agent token and information page", ACC, None, "none found")],
        "F5 BIG-IP": [r(NO_ROUTE, "site owner", "the agent's User-Agent token and information page", ACC, None, "none found")],
        "Fastly": [r(NO_ROUTE, "site owner", "the agent's User-Agent token and information page", ACC, None, "none found")],
    },
    "sites": {
        "npmjs.com": [r("use the documented npm registry API at registry.npmjs.org instead of the website", "operator",
                        "nothing beyond the package names", "the registry endpoint returns JSON for a known package",
                        "https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md", "to verify")],
    },
    "owner_paragraph": "Hello. We operate <agent name>, which <one-line purpose>. It identifies itself with the User-Agent token <token> "
                       "(details: <info URL>) and requests <URL pattern> at most <rate>. Requests from it to your site are currently answered "
                       "with <status>. If you are willing to allow it, the identifiers are: User-Agent token <token>; <IP ranges at URL, or "
                       "reverse DNS pattern, or Web Bot Auth key directory URL>. If you would rather it did not visit, tell us and we will "
                       "exclude your site. Contact: <address>.",
    "readiness": ["a product-token User-Agent that names the agent and links to an information page",
                  "a public information page stating purpose, request rate, robots.txt stance, how to block it, and a contact",
                  "at least one verifiable identity: a stable IP list at a URL, reverse DNS, or a Web Bot Auth key directory"],
}

if __name__ == "__main__":
    for name, data in (("vendor_clues.json", CLUES), ("routes.json", ROUTES)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    print(len(CLUES["clues"]), "clues;", len(ROUTES["vendors"]), "vendor routes")
