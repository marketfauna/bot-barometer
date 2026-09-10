"""Build feed.json at the repository root: the whole index in one machine-readable file, so agents can read it directly.
Stdlib only. Run after collect_index.py and after any sample or prediction update: python tools/build_feed.py
Inputs (all relative to the repo root): data/YYYY-MM-DD.json, swarm-forecast/claude-*.json and swarm-forecast/openai-*.json,
variants/variants-*.json, PREDICTIONS.md."""
import json, csv, re
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent.parent  # repo root
out = {"name": "Bot Barometer", "publisher": "Marketfauna", "contact": "hello@marketfauna.com", "schema": 1, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
       "license_note": "Derived counts and labels are ours. Raw third-party page content is not redistributed; source URLs are listed per series.",
       "issues": [], "series": {}, "swarm_forecast": {}, "anchor_variation": {}, "predictions": []}

# collector snapshots
for f in sorted((HERE / "data").glob("????-??-??.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    day = d.get("date", f.stem)
    s = d.get("series", {})
    b = s.get("freelancer_bids_by_category", {})
    out["series"].setdefault("freelancer_bids_by_category", []).append({
        "date": day, "status": b.get("status"),
        "categories": {k: {kk: v.get(kk) for kk in ("n_projects", "median_bids", "mean_bids", "p90_bids", "share_with_budget_under_50usd", "url")} for k, v in (b.get("categories") or {}).items()}})
    c = s.get("exit_listing_ai_share", {})
    out["series"].setdefault("exit_listing_ai_keyword_share", []).append({
        "date": day, "status": c.get("status"),
        "sites": {k: {kk: v.get(kk) for kk in ("n_listings", "n_ai", "share_ai", "url")} for k, v in (c.get("sites") or {}).items()}})
    g = s.get("github_bounty_synthetic_share", {})
    out["series"].setdefault("github_bounty_board_named_repo_share", []).append({
        "date": day, "status": g.get("status"), "n_issues": g.get("n_issues"), "n_distinct_repos": g.get("n_distinct_repos"),
        "board_named_share": g.get("synthetic_share"), "total_count_reported": g.get("total_count_reported"), "top_repos": g.get("top_repos"), "url": g.get("url")})
    h = s.get("hn_supply_demand", {})
    out["series"].setdefault("hn_freelancer_thread", []).append({
        "date": day, "status": h.get("status"), "thread_id": h.get("thread_id"), "month": h.get("month"),
        "seeking_work": h.get("seeking_work"), "seeking_freelancer": h.get("seeking_freelancer"), "url": h.get("item_url")})

# swarm forecast samples
swarm_files = sorted((HERE / "swarm-forecast").glob("claude-*.json")) + sorted((HERE / "swarm-forecast").glob("openai-*.json"))
for f in swarm_files:
    d = json.loads(f.read_text(encoding="utf-8"))
    out["swarm_forecast"][f.stem] = {k: d.get(k) for k in ("lineage", "date", "prompt", "tiers", "taxonomy", "counts_by_tier", "counts_total", "samples_mentioning_by_tier", "unsupported_credential_flag_lines_by_tier", "correction_log", "observations")}

# anchor variation
for f in sorted((HERE / "variants").glob("variants-*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    out["anchor_variation"][f.stem] = d

# predictions
pm = (HERE / "PREDICTIONS.md")
if pm.exists():
    for line in pm.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(P\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
        if m:
            out["predictions"].append({"id": m.group(1), "prediction": m.group(2), "resolves_by": m.group(3), "resolver": m.group(4), "status": re.sub(r"\*+", "", m.group(5))})

out["issues"].append({"number": 1, "week_of": "2026-09-08", "published": "2026-09-09", "url": "https://claude.ai/code/artifact/a81aea76-0925-4606-9318-1b6cdfd7bf1f"})
(HERE / "feed.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print("feed.json written:", {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in out.items() if k != "license_note"})
