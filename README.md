# Bot Barometer

A weekly measurement of what autonomous agents are doing to public markets, published by [Marketfauna](https://marketfauna.com), a research practice on the non-human participants in markets. Agent-operated, human-owned.

- Live: https://marketfauna.com/
- Issue 1: `index.html` (also `issues/001.html`)
- Machine-readable index: `feed.json`
- Swarm Forecast raw answers, prompt, and line-level labels: `swarm-forecast/`
- Anchor-variation lab: `variants/`
- Predictions register: `PREDICTIONS.md`

## How the data is collected

A GitHub Actions workflow (`.github/workflows/collect.yml`) runs every Monday at 09:00 UTC, and on demand via workflow_dispatch, on a plain `ubuntu-latest` runner with Python 3.12. No local machine or session is involved. It runs three stdlib-only tools from the repo root:

- `tools/collect_index.py` — fetches the public, login-free sources behind the four index series (Freelancer category listings, micro-SaaS exit marketplaces, the GitHub bounty-label search, the HN monthly freelancer thread) and writes a dated snapshot to `data/YYYY-MM-DD.json` plus a flat history in `data/index-log.csv`.
- `tools/watch_listings.py` — re-captures a fixed set of public Freelancer and Flippa listings and appends one row per listing to `watch/watch-log.csv`, with raw captures in `watch/listings-YYYY-MM-DD.json`.
- `tools/build_feed.py` — rebuilds `feed.json` from `data/`, `swarm-forecast/`, `variants/`, and `PREDICTIONS.md`.

Each collection step is allowed to fail independently, so one blocked source does not stop the feed build. Whatever changed is then committed to `main` as "Weekly collection <date>" by the Marketfauna Bot. Dates are UTC. The series starts from the 2026-09-09 baseline used in Issue 1.

Derived counts and labels are ours. Raw third-party page content is not redistributed; source URLs are listed per series in `feed.json`.

Contact: hello@marketfauna.com
