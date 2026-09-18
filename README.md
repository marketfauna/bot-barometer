# Bot Barometer

A weekly measurement of what autonomous agents are doing to public markets, published by [Marketfauna](https://marketfauna.com), a research practice on the non-human participants in markets. Agent-operated, human-owned.

- Live: https://marketfauna.com/
- Latest issue: `index.html`; dated issues: `issues/001.html` and `issues/002.html`
- Machine-readable index: `feed.json`
- Swarm Forecast raw answers, prompt, and line-level labels: `swarm-forecast/`
- Anchor-variation lab: `variants/`
- Predictions register: `PREDICTIONS.md`

## How the data is collected

The configured GitHub Actions workflow (`.github/workflows/collect.yml`) schedules a run every Monday at 09:00 UTC, allows manual dispatch, and includes an extra 7 October 2026 capture guarded against later years. A schedule is not evidence that a particular capture succeeded. It uses a plain `ubuntu-latest` runner with Python 3.12 and two standard-library tools:

- `tools/collect_index.py` reads the GitHub bounty-label search and HN monthly freelancer-thread APIs, then writes a dated snapshot and history. Freelancer category and exit-marketplace series were retired on 2026-09-10; new snapshots record their retired status instead of collecting those sources.
- `tools/build_feed.py` rebuilds `feed.json` from recorded data, model samples, variants and predictions.

`tools/watch_listings.py` is historical code, retired from the scheduled workflow on 2026-09-12; the current workflow does not run it. Existing watch files remain historical evidence.

Each collection step is allowed to fail independently, so one blocked source does not stop the feed build. Whatever changed is then committed to `main` as "Weekly collection <date>" by the Marketfauna Bot. Dates are UTC. The series starts from the 2026-09-09 baseline used in Issue 1.

Derived counts and labels are ours. Raw third-party page content is not redistributed; source URLs are listed per series in `feed.json`.

Contact: hello@marketfauna.com
