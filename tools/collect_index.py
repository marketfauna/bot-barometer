#!/usr/bin/env python3
"""
Agent Economy Index - public-data collector.

Research-only. Fetches public, login-free pages and APIs and writes:
    data/YYYY-MM-DD.json            full snapshot (raw counts, derived ratios, URLs fetched)
    data/index-log.csv              flat history: date, series, key, value

Paths are relative to the repository root (the parent of tools/), so this runs
unchanged from a local checkout or from GitHub Actions: python tools/collect_index.py

Standard library only (urllib, re, json, csv, gzip, statistics).
Run on Windows with:  set PYTHONIOENCODING=utf-8 && python collect_index.py

Series
  1. freelancer_bids_by_category   Freelancer.com public category listings (bids per project, budgets)
  2. exit_listing_ai_share         micro-SaaS exit marketplaces: share of front-page listings mentioning AI
  3. github_bounty_synthetic_share GitHub search API: open issues labelled "bounty", repo concentration
  4. hn_supply_demand              HN monthly "Freelancer? Seeking freelancer?" thread: SEEKING WORK vs SEEKING FREELANCER

Every series is wrapped so that a failure in one never aborts the run.
"""

import csv
import datetime as dt
import gzip
import html
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------- config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_CSV = os.path.join(DATA_DIR, "index-log.csv")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
HOST_DELAY_SECONDS = 2.0
TIMEOUT_SECONDS = 30

FREELANCER_CATEGORIES = [
    "python",
    "javascript",
    "data-entry",
    "wordpress",
    "web-scraping",
    "graphic-design",
    "copywriting",
    "video-editing",
]
FREELANCER_URL = "https://www.freelancer.com/jobs/{}/"

EXIT_MARKETPLACES = [
    ("microns", "https://www.microns.io/"),
    ("indiemaker", "https://indiemaker.co/"),
    ("buymicrostartups", "https://buymicrostartups.com/"),
    ("acquirebase", "https://acquirebase.com/"),
]

GITHUB_SEARCH_URL = (
    "https://api.github.com/search/issues"
    "?q=label:bounty+is:issue+is:open&sort=created&order=desc&per_page=100"
)
GITHUB_SYNTHETIC_KEYWORDS = ["bounty", "bounties", "plaza", "claude", "agent", "gpt"]

HN_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=%22Seeking%20freelancer%22&tags=ask_hn&hitsPerPage=30"
)
HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{}"
HN_TITLE_PREFIX = "ask hn: freelancer? seeking freelancer?"

AI_TERMS_RE = re.compile(r"\b(ai|gpt|llm|llms|agent|agents|agentic|claude)\b", re.I)

# --------------------------------------------------------------------------- fetch layer

_last_hit_by_host = {}
_urls_fetched = []


def _log(msg):
    print(msg, flush=True)


def fetch(url, accept="text/html,application/json;q=0.9,*/*;q=0.8"):
    """
    Return dict(status, text, error). Never raises.
    Enforces HOST_DELAY_SECONDS between requests to the same host.
    """
    host = urllib.parse.urlparse(url).netloc
    last = _last_hit_by_host.get(host)
    if last is not None:
        wait = HOST_DELAY_SECONDS - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)

    result = {"url": url, "status": None, "text": "", "error": None, "headers": {}}
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read()
            result["status"] = resp.status
            result["headers"] = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        result["error"] = "HTTP {}".format(e.code)
        try:
            body = e.read()
            result["headers"] = {k.lower(): v for k, v in e.headers.items()}
        except Exception:
            body = b""
    except Exception as e:  # URLError, socket timeout, SSL, anything
        result["error"] = "{}: {}".format(type(e).__name__, e)
        body = b""
    finally:
        _last_hit_by_host[host] = time.monotonic()

    if result["headers"].get("content-encoding", "") == "gzip" or body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
    try:
        result["text"] = body.decode("utf-8", errors="replace")
    except Exception:
        result["text"] = ""

    _urls_fetched.append({"url": url, "status": result["status"], "error": result["error"]})
    _log("  GET {} -> {}{}".format(url, result["status"], " ({})".format(result["error"]) if result["error"] else ""))
    return result


# --------------------------------------------------------------------------- helpers

def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def pct(n, d):
    return round(n / d, 4) if d else None


def describe(values):
    if not values:
        return {"median": None, "mean": None, "p90": None}
    vals = sorted(values)
    idx = min(len(vals) - 1, int(round(0.9 * (len(vals) - 1))))
    return {
        "median": statistics.median(vals),
        "mean": round(statistics.fmean(vals), 2),
        "p90": vals[idx],
    }


def parse_money(text):
    """
    Best-effort parse of a Freelancer price string such as
    '$479', '$25 - $50 / hr', '€30 - €250 EUR', '₹1500 INR', 'A$30 - A$250 AUD'.
    Returns dict(currency, low, high, hourly, is_range, raw).
    """
    raw = (text or "").strip()
    out = {"raw": raw, "currency": None, "low": None, "high": None, "hourly": False, "is_range": False}
    if not raw:
        return out
    out["hourly"] = bool(re.search(r"/\s*hr|per hour|hourly", raw, re.I))

    code = re.search(r"\b([A-Z]{3})\b", raw)
    if code:
        out["currency"] = code.group(1)
    else:
        sym = re.match(r"\s*([A-Z]{0,2}\$|€|£|₹|¥|R\$|C\$|A\$|S\$|HK\$|NZ\$|MX\$)", raw)
        symbol_map = {
            "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY",
            "R$": "BRL", "C$": "CAD", "A$": "AUD", "S$": "SGD", "HK$": "HKD",
            "NZ$": "NZD", "MX$": "MXN",
        }
        if sym:
            out["currency"] = symbol_map.get(sym.group(1), sym.group(1))

    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", raw)]
    if nums:
        out["low"] = nums[0]
        out["high"] = nums[1] if len(nums) > 1 else nums[0]
        out["is_range"] = len(nums) > 1
    return out


def series_result(status, error=None, **fields):
    d = {"status": status, "error": error}
    d.update(fields)
    return d


# --------------------------------------------------------------------------- series 1: Freelancer

def parse_freelancer_page(text):
    """Return list of per-card dicts. Cards are server-rendered <div class="JobSearchCard-item-inner">."""
    cards = re.split(r'<div class="JobSearchCard-item-inner"', text)[1:]
    parsed = []
    for card in cards:
        title = re.search(r'JobSearchCard-primary-heading-link[^>]*>\s*(.*?)\s*</a>', card, re.S)
        bids = re.search(r'JobSearchCard-secondary-entry">\s*(\d+)\s*bids?', card)
        price = re.search(r'JobSearchCard-secondary-price">\s*([^<]+)', card)
        price_txt = price.group(1).strip() if price else ""
        # Freelancer shows "Avg Bid" once a project has bids; the posted budget range only when it has none.
        price_kind = "avg_bid" if re.search(r'JobSearchCard-secondary-avgBid', card) else "budget"
        money = parse_money(price_txt)
        parsed.append({
            "title": strip_tags(title.group(1))[:120] if title else None,
            "bids": int(bids.group(1)) if bids else None,
            "price_raw": price_txt or None,
            "price_kind": price_kind if price_txt else None,
            "currency": money["currency"],
            "low": money["low"],
            "high": money["high"],
            "hourly": money["hourly"],
            "is_range": money["is_range"],
        })
    return parsed


def collect_freelancer():
    out = {"status": "ok", "error": None, "categories": {}}
    n_ok = 0
    for cat in FREELANCER_CATEGORIES:
        url = FREELANCER_URL.format(cat)
        r = fetch(url)
        entry = {"url": url, "http_status": r["status"]}
        if r["status"] != 200:
            entry.update(status="blocked", error=r["error"] or "HTTP {}".format(r["status"]))
            out["categories"][cat] = entry
            continue
        try:
            cards = parse_freelancer_page(r["text"])
        except Exception as e:
            entry.update(status="parse_failed", error="{}: {}".format(type(e).__name__, e))
            out["categories"][cat] = entry
            continue
        if not cards:
            js_only = "JobSearchCard" not in r["text"]
            entry.update(status="parse_failed",
                         error="no project cards found" + (" (page looks JS-only)" if js_only else ""))
            out["categories"][cat] = entry
            continue

        bids = [c["bids"] for c in cards if c["bids"] is not None]
        priced = [c for c in cards if c["low"] is not None]
        fixed = [c for c in priced if not c["hourly"]]
        usd_fixed = [c for c in fixed if c["currency"] == "USD"]
        under_50 = [c for c in usd_fixed if c["high"] is not None and c["high"] < 50]
        currencies = {}
        for c in priced:
            currencies[c["currency"] or "unknown"] = currencies.get(c["currency"] or "unknown", 0) + 1
        stats = describe(bids)
        entry.update(
            status="ok",
            error=None,
            n_projects=len(cards),
            n_with_bid_count=len(bids),
            median_bids=stats["median"],
            mean_bids=stats["mean"],
            p90_bids=stats["p90"],
            min_bids=min(bids) if bids else None,
            max_bids=max(bids) if bids else None,
            n_with_price=len(priced),
            n_fixed_price=len(fixed),
            n_hourly=len(priced) - len(fixed),
            n_price_is_avg_bid=sum(1 for c in priced if c["price_kind"] == "avg_bid"),
            n_price_is_budget_range=sum(1 for c in priced if c["price_kind"] == "budget"),
            n_usd_fixed=len(usd_fixed),
            n_under_50usd=len(under_50),
            share_with_budget_under_50usd=pct(len(under_50), len(usd_fixed)),
            currencies=currencies,
            cards=cards,
        )
        out["categories"][cat] = entry
        n_ok += 1

    if n_ok == 0:
        out["status"] = "blocked"
        out["error"] = "no category page parsed"
    elif n_ok < len(FREELANCER_CATEGORIES):
        out["error"] = "{} of {} categories failed".format(len(FREELANCER_CATEGORIES) - n_ok, len(FREELANCER_CATEGORIES))
    # cross-category aggregate
    all_bids = [c["bids"] for cat in out["categories"].values() for c in cat.get("cards", []) if c["bids"] is not None]
    agg = describe(all_bids)
    out["aggregate"] = {
        "n_projects": sum(cat.get("n_projects", 0) for cat in out["categories"].values()),
        "median_bids": agg["median"],
        "mean_bids": agg["mean"],
        "p90_bids": agg["p90"],
    }
    return out


# --------------------------------------------------------------------------- series 2: exit marketplaces

def parse_microns(text):
    cards = re.findall(r'class="listing-card"[^>]*>.*?listing-card-link', text, re.S)
    items = []
    for c in cards:
        t = re.search(r'h5-heading listings">(.*?)</h5>', c, re.S)
        b = re.search(r'body-text s-light[^"]*">(.*?)</div>', c, re.S)
        items.append({"title": strip_tags(t.group(1) if t else ""), "blurb": strip_tags(b.group(1) if b else "")})
    return items


def parse_indiemaker(text):
    cards = re.findall(r'<a class="im-card".*?</a>', text, re.S)
    items = []
    for c in cards:
        t = re.search(r'im-card__name">(.*?)</h3>', c, re.S)
        cat = re.search(r'im-card__cat">(.*?)</span>', c, re.S)
        items.append({"title": strip_tags(t.group(1) if t else ""), "blurb": strip_tags(cat.group(1) if cat else "")})
    return items


def parse_buymicrostartups(text):
    cards = re.findall(r'shadow-card card-lift[^>]*>.*?</a>', text, re.S)
    items = []
    for c in cards:
        t = re.search(r'<h3[^>]*>(.*?)</h3>', c, re.S)
        b = re.search(r'<p class="[^"]*line-clamp[^"]*">(.*?)</p>', c, re.S)
        items.append({"title": strip_tags(t.group(1) if t else ""), "blurb": strip_tags(b.group(1) if b else "")})
    return items


def parse_acquirebase(text):
    cards = re.findall(r'<div class="card position-relative h-100">.*?asking-price.*?</div>\s*</div>\s*</div>', text, re.S)
    items = []
    for c in cards:
        t = re.search(r'stretched-link">\s*<strong>(.*?)</strong>', c, re.S)
        b = re.search(r'description">(.*?)</p>', c, re.S)
        items.append({"title": strip_tags(t.group(1) if t else ""), "blurb": strip_tags(b.group(1) if b else "")})
    return items


EXIT_PARSERS = {
    "microns": parse_microns,
    "indiemaker": parse_indiemaker,
    "buymicrostartups": parse_buymicrostartups,
    "acquirebase": parse_acquirebase,
}


def collect_exit_marketplaces():
    out = {"status": "ok", "error": None, "sites": {}}
    total_n = total_ai = 0
    n_ok = 0
    for name, url in EXIT_MARKETPLACES:
        r = fetch(url)
        entry = {"url": url, "http_status": r["status"]}
        if r["status"] != 200:
            entry.update(status="blocked", error=r["error"] or "HTTP {}".format(r["status"]))
            out["sites"][name] = entry
            continue
        try:
            items = EXIT_PARSERS[name](r["text"])
        except Exception as e:
            entry.update(status="parse_failed", error="{}: {}".format(type(e).__name__, e))
            out["sites"][name] = entry
            continue
        items = [i for i in items if i["title"]]
        if not items:
            entry.update(status="parse_failed", error="no listings found (markup changed or JS-only)")
            out["sites"][name] = entry
            continue
        for i in items:
            i["mentions_ai"] = bool(AI_TERMS_RE.search(i["title"] + " " + i["blurb"]))
        n_ai = sum(1 for i in items if i["mentions_ai"])
        entry.update(status="ok", error=None, n_listings=len(items), n_ai=n_ai,
                     share_ai=pct(n_ai, len(items)), listings=items)
        out["sites"][name] = entry
        total_n += len(items)
        total_ai += n_ai
        n_ok += 1
    if n_ok == 0:
        out["status"] = "blocked"
        out["error"] = "no marketplace parsed"
    elif n_ok < len(EXIT_MARKETPLACES):
        out["error"] = "{} of {} sites failed".format(len(EXIT_MARKETPLACES) - n_ok, len(EXIT_MARKETPLACES))
    out["aggregate"] = {"n_sites_ok": n_ok, "n_listings": total_n, "n_ai": total_ai, "share_ai": pct(total_ai, total_n)}
    return out


# --------------------------------------------------------------------------- series 3: GitHub bounties

def collect_github_bounties():
    r = fetch(GITHUB_SEARCH_URL, accept="application/vnd.github+json")
    out = {"url": GITHUB_SEARCH_URL, "http_status": r["status"],
           "rate_limit_remaining": r["headers"].get("x-ratelimit-remaining")}
    if r["status"] != 200:
        out.update(status="blocked", error=r["error"] or "HTTP {}".format(r["status"]))
        return out
    try:
        data = json.loads(r["text"])
        items = data.get("items", [])
    except Exception as e:
        out.update(status="parse_failed", error="{}: {}".format(type(e).__name__, e))
        return out
    if not items:
        out.update(status="parse_failed", error="search returned zero items")
        return out

    repo_counts = {}
    for it in items:
        full = it.get("repository_url", "").replace("https://api.github.com/repos/", "")
        repo_counts[full] = repo_counts.get(full, 0) + 1

    def synthetic(full_name):
        name = full_name.lower()
        return any(k in name for k in GITHUB_SYNTHETIC_KEYWORDS)

    n_synth = sum(cnt for full, cnt in repo_counts.items() if synthetic(full))
    top = sorted(repo_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    created = sorted(it.get("created_at", "") for it in items)
    out.update(
        status="ok", error=None,
        total_count_reported=data.get("total_count"),
        n_issues=len(items),
        n_distinct_repos=len(repo_counts),
        n_synthetic_issues=n_synth,
        synthetic_share=pct(n_synth, len(items)),
        n_synthetic_repos=sum(1 for full in repo_counts if synthetic(full)),
        top_repos=[{"repo": full, "n_issues": cnt, "synthetic": synthetic(full)} for full, cnt in top],
        top1_share=pct(top[0][1], len(items)) if top else None,
        oldest_created_in_page=created[0] if created else None,
        newest_created_in_page=created[-1] if created else None,
        keywords=GITHUB_SYNTHETIC_KEYWORDS,
    )
    return out


# --------------------------------------------------------------------------- series 4: HN freelancer thread

def collect_hn_supply_demand():
    r = fetch(HN_SEARCH_URL, accept="application/json")
    out = {"search_url": HN_SEARCH_URL, "http_status": r["status"]}
    if r["status"] != 200:
        out.update(status="blocked", error=r["error"] or "HTTP {}".format(r["status"]))
        return out
    try:
        hits = json.loads(r["text"]).get("hits", [])
    except Exception as e:
        out.update(status="parse_failed", error="{}: {}".format(type(e).__name__, e))
        return out

    threads = [h for h in hits if (h.get("title") or "").strip().lower().startswith(HN_TITLE_PREFIX)]
    if not threads:
        out.update(status="parse_failed", error="no thread title matched prefix")
        return out
    threads.sort(key=lambda h: h.get("created_at", ""), reverse=True)
    latest_month = threads[0]["created_at"][:7]
    same_month = [h for h in threads if h["created_at"][:7] == latest_month]
    # Duplicates get posted some months; take the one with the most comments as canonical.
    chosen = max(same_month, key=lambda h: h.get("num_comments") or 0)
    month_match = re.search(r"\(([A-Za-z]+ \d{4})\)", chosen.get("title", ""))

    item_url = HN_ITEM_URL.format(chosen["objectID"])
    r2 = fetch(item_url, accept="application/json")
    out.update(
        thread_id=chosen["objectID"],
        thread_title=chosen.get("title"),
        thread_author=chosen.get("author"),
        thread_created_at=chosen.get("created_at"),
        month=month_match.group(1) if month_match else latest_month,
        num_comments_reported=chosen.get("num_comments"),
        same_month_candidates=[{"id": h["objectID"], "author": h.get("author"), "num_comments": h.get("num_comments")} for h in same_month],
        item_url=item_url,
        item_http_status=r2["status"],
    )
    if r2["status"] != 200:
        out.update(status="blocked", error=r2["error"] or "HTTP {}".format(r2["status"]))
        return out
    try:
        children = json.loads(r2["text"]).get("children", [])
    except Exception as e:
        out.update(status="parse_failed", error="{}: {}".format(type(e).__name__, e))
        return out

    seeking_work = seeking_freelancer = other = deleted = 0
    for c in children:
        txt = strip_tags(c.get("text") or "")
        if not txt:
            deleted += 1
            continue
        head = txt[:40].upper()
        if head.startswith("SEEKING WORK"):
            seeking_work += 1
        elif head.startswith("SEEKING FREELANCER"):
            seeking_freelancer += 1
        else:
            other += 1
    out.update(
        status="ok", error=None,
        n_top_level=len(children),
        seeking_work=seeking_work,
        seeking_freelancer=seeking_freelancer,
        other=other,
        deleted_or_empty=deleted,
        work_per_freelancer_ratio=round(seeking_work / seeking_freelancer, 3) if seeking_freelancer else None,
        seeking_work_share=pct(seeking_work, seeking_work + seeking_freelancer),
    )
    return out


# --------------------------------------------------------------------------- log rows

def log_rows(date, series):
    rows = []

    def add(name, key, value):
        if value is None or isinstance(value, (dict, list)):
            return
        rows.append([date, name, key, value])

    fl = series["freelancer_bids_by_category"]
    add("freelancer_bids_by_category", "status", fl.get("status"))
    for cat, e in fl.get("categories", {}).items():
        add("freelancer_bids_by_category", cat + ".status", e.get("status"))
        for k in ("n_projects", "median_bids", "mean_bids", "p90_bids", "n_usd_fixed", "n_under_50usd", "share_with_budget_under_50usd"):
            add("freelancer_bids_by_category", cat + "." + k, e.get(k))
    for k, v in fl.get("aggregate", {}).items():
        add("freelancer_bids_by_category", "all." + k, v)

    ex = series["exit_listing_ai_share"]
    add("exit_listing_ai_share", "status", ex.get("status"))
    for site, e in ex.get("sites", {}).items():
        add("exit_listing_ai_share", site + ".status", e.get("status"))
        for k in ("n_listings", "n_ai", "share_ai"):
            add("exit_listing_ai_share", site + "." + k, e.get(k))
    for k, v in ex.get("aggregate", {}).items():
        add("exit_listing_ai_share", "all." + k, v)

    gh = series["github_bounty_synthetic_share"]
    for k in ("status", "total_count_reported", "n_issues", "n_distinct_repos", "n_synthetic_issues", "synthetic_share", "n_synthetic_repos", "top1_share"):
        add("github_bounty_synthetic_share", k, gh.get(k))
    for i, t in enumerate(gh.get("top_repos", []), 1):
        add("github_bounty_synthetic_share", "top{}.repo".format(i), t["repo"])
        add("github_bounty_synthetic_share", "top{}.n_issues".format(i), t["n_issues"])

    hn = series["hn_supply_demand"]
    for k in ("status", "thread_id", "month", "n_top_level", "seeking_work", "seeking_freelancer", "other", "work_per_freelancer_ratio", "seeking_work_share"):
        add("hn_supply_demand", k, hn.get(k))
    return rows


# --------------------------------------------------------------------------- main

def run_series(name, fn):
    _log("[{}]".format(name))
    try:
        return fn()
    except Exception as e:  # last-resort guard; individual fetches already catch
        _log("  !! {} crashed: {}: {}".format(name, type(e).__name__, e))
        return series_result("parse_failed", "{}: {}".format(type(e).__name__, e))


def retired_series(reason):
    """A series that is no longer collected; the reason is published with every snapshot."""
    return {"status": "retired", "error": None, "reason": reason, "retired_on": "2026-09-10"}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.makedirs(DATA_DIR, exist_ok=True)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()  # UTC so local and Actions runs stamp the same day
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    series = {
        # Retired 2026-09-10 before the first scheduled run: the sources' terms bar automated access
        # (Freelancer.com terms s.33; Microns, IndieMaker s.1.14.3, BuyMicroStartups, AcquireBase terms).
        # The collectors stay in the file for the record; they are not called. Two manual data points
        # (2026-09-09, 2026-09-10) remain in data/ as history.
        "freelancer_bids_by_category": retired_series("Freelancer.com terms s.33 bar robots, spiders, scrapers and other automated access; retired 2026-09-10 before the first scheduled run"),
        "exit_listing_ai_share": retired_series("Microns, IndieMaker, BuyMicroStartups and AcquireBase terms bar crawling or scraping; retired 2026-09-10 before the first scheduled run"),
        "github_bounty_synthetic_share": run_series("github_bounty_synthetic_share", collect_github_bounties),
        "hn_supply_demand": run_series("hn_supply_demand", collect_hn_supply_demand),
    }

    snapshot = {
        "date": today,
        "generated_at_utc": started,
        "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "series": series,
        "urls_fetched": _urls_fetched,
    }
    json_path = os.path.join(DATA_DIR, today + ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    rows = log_rows(today, series)
    # Idempotent per day: a re-run on the same date (e.g. a manual workflow_dispatch) replaces
    # that day's rows instead of appending a duplicate block.
    kept = []
    if os.path.exists(LOG_CSV):
        with open(LOG_CSV, newline="", encoding="utf-8") as f:
            kept = [r for r in csv.reader(f) if r and r[0] != "date" and r[0] != today]
    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "series", "key", "value"])
        w.writerows(kept)
        w.writerows(rows)

    _log("")
    _log("wrote {}".format(json_path))
    _log("appended {} rows to {}".format(len(rows), LOG_CSV))
    for name, s in series.items():
        _log("  {:32s} {}{}".format(name, s.get("status"), "  ({})".format(s.get("error")) if s.get("error") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
