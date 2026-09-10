"""Zero-cost market watch: snapshot public listing pages and append a dated row per listing.

Reads only public pages. No login, no forms, no contact. Run daily; diff rows over time.
Output: watch/listings-YYYY-MM-DD.json (raw captures) and watch/watch-log.csv (one row per listing per run).
Paths are relative to the repository root (the parent of tools/): python tools/watch_listings.py
"""
import csv, hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HERE = Path(__file__).resolve().parent.parent  # repo root
OUT = HERE / "watch"
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

FREELANCER = {
    "gbstudio-overlay": "https://www.freelancer.com/projects/game-development/gbstudio-overlay-image-integration",
    "windows-cis-hardening": "https://www.freelancer.com/projects/windows-server/windows-cis-hardening",
    "sheets-call-routing": "https://www.freelancer.com/projects/google-sheets/google-sheets-call-routing-automation",
    "composer-dag": "https://www.freelancer.com/projects/data-processing/composer-dag-for-data-ingestion",
    "import-pdf-bank": "https://www.freelancer.com/projects/google-sheets/import-pdf-bank-transactions",
    "fix-bing-indexing": "https://www.freelancer.com/projects/seo/fix-bing-indexing-issue",
    "winomkar-data-entry": "https://www.freelancer.com/projects/automation/automate-winomkar-data-entry",
}
FLIPPA = {
    "remote-work-rebels": "https://flippa.com/12761258",
    "concealed-carry-society": "https://flippa.com/13446183",
    "my-kind-of-meeple": "https://flippa.com/13816202",
    "cofonts": "https://flippa.com/13706273",
    "flippa-13933449-speisekarte-NOT-nyevents": "https://flippa.com/13933449",  # 2026-09-09: this ID is Speisekartemenus.de, not New York Events; NY Events listing ID unknown
    "flippa-11226620": "https://flippa.com/11226620",
    "flippa-11836890": "https://flippa.com/11836890",
    "flippa-12005809": "https://flippa.com/12005809",
    "flippa-12286007": "https://flippa.com/12286007",
    "flippa-12383685": "https://flippa.com/12383685",
    "flippa-12884918": "https://flippa.com/12884918",
    "flippa-13463497": "https://flippa.com/13463497",
    "flippa-13551982": "https://flippa.com/13551982",
}

def fetch(url):
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except HTTPError as e:
        return e.code, ""
    except URLError as e:
        return 0, str(e)

def grab(pattern, text, flags=re.I | re.S):
    m = re.search(pattern, text, flags)
    return (m.group(1).strip() if m else "")

def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()

def parse_freelancer(html):
    text = strip_tags(html)
    return {
        "title": grab(r"<title>(.*?)</title>", html),
        "status": grab(r"\b(Open|Closed|Awarded|Completed|In Progress|Cancelled)\b", text[:20000]),
        "budget": grab(r"((?:AUD|USD|GBP|EUR|CAD|INR|\$|£|€)\s?[\d,]+(?:\.\d+)?\s?[-–]\s?(?:AUD|USD|GBP|EUR|CAD|INR|\$|£|€)?\s?[\d,]+(?:\.\d+)?)", text),
        "bids": grab(r"(\d+)\s+(?:freelancers?\s+are\s+bidding|bids?|proposals?)", text),
        "avg_bid": grab(r"(?:Average bid|avg bid)[^\d]{0,20}([A-Z$£€]{0,3}\s?[\d,]+(?:\.\d+)?)", text),
        "awarded_to": grab(r"awarded to\s+([A-Za-z0-9_@ .-]{2,40})", text),
        "time_left": grab(r"(\d+\s+(?:days?|hours?|minutes?)\s+left)", text),
    }

def parse_flippa(html):
    text = strip_tags(html)
    return {
        "title": grab(r"<title>(.*?)</title>", html),
        "status": grab(r"\b(Sold|Ended|Auction ended|Reserve not met|Reserve met|Buy It Now|Auction|Open to offers|Under offer|Closed|Listing (?:ended|expired))\b", text[:30000]),
        # Classified listings render "Asking Price (Classified) USD $orig USD $current Reduced N%"; take the last price before "Reduced"/"Inquire".
        "price": (grab(r"Asking Price[^$]{0,40}(?:USD\s?\$[\d,]+\s+)?USD\s?(\$[\d,]+)\s+(?:Reduced|Inquire|Make)", text)
                  or grab(r"(?:Current bid|Buy it now|BIN)[^\d$]{0,20}(\$\s?[\d,]+)", text)),
        "orig_price": grab(r"Asking Price[^$]{0,40}USD\s?(\$[\d,]+)\s+USD\s?\$[\d,]+\s+Reduced", text),
        "reduced": grab(r"(Reduced \d+%)", text),
        "bids": grab(r"(\d+)\s+bids?\b", text),
        "time_left": grab(r"((?:\d+\s+(?:days?|hours?|minutes?)\s*)+(?:left|remaining))", text),
        "reserve": grab(r"(Reserve (?:not )?met)", text),
    }

def main():
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    day = ts[:10]
    raw = {}
    rows = []
    for source, table, parser in (("freelancer", FREELANCER, parse_freelancer), ("flippa", FLIPPA, parse_flippa)):
        for key, url in table.items():
            status, html = fetch(url)
            fields = parser(html) if status == 200 else {}
            digest = hashlib.sha256(strip_tags(html).encode()).hexdigest()[:16] if html else ""
            raw[key] = {"url": url, "http": status, "sha16": digest, "fields": fields, "len": len(html)}
            rows.append({"ts": ts, "source": source, "key": key, "url": url, "http": status, "sha16": digest, **{k: fields.get(k, "") for k in ("title", "status", "budget", "price", "orig_price", "reduced", "bids", "avg_bid", "awarded_to", "time_left", "reserve")}})
            time.sleep(2)
    (OUT / f"listings-{day}.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    log = OUT / "watch-log.csv"
    new = not log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['source']:10} {r['key']:24} http={r['http']} status={r['status']!r} price={r['price'] or r['budget']!r} bids={r['bids']!r} left={r['time_left']!r}")

if __name__ == "__main__":
    main()
