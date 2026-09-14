# Predictions register

An index that never says what it expects cannot be scored. Every issue records falsifiable predictions with a resolution date and the exact series that resolves them. Later issues score them. Wrong predictions stay on the page. This is what separates an instrument from a newsletter, and it is the thing a buyer can check before paying.

Rules: one line per prediction, resolvable from our own published series or a named public page, resolution date fixed at issue time, no edits after publication, scored Right / Wrong / Unresolvable with the resolving value.

## Issue 1 predictions (made 2026-09-09)

| # | Prediction | Resolves by | Resolving series or page | Status |
|---|---|---|---|---|
| P1 | The next frontier model release from either lineage will, under the fixed prompt, put a larger share of lines in category B (sell to other agents) than Opus 5's 27% (8 of 30). | Next release-day sample | Series A, taxonomy v1 | open |
| P2 | Under the fixed prompt, the share of lines in category A (sell the signature) will not fall below 35% at any tier of the next release. | Next release-day sample | Series A | open |
| P3 | Freelancer median proposals per job across the same 8 categories will be above 47 on 2026-10-07 (four weekly captures later). | 2026-10-07 | Series B, index-log.csv | **Unresolvable.** Series B retired 2026-09-10 before any second capture (Freelancer User Agreement s.33 bars automated access); our planned series will not supply a 2026-10-07 observation. Scored Issue 2. |
| P4 | At least one of the five Flippa listings on the diligence shortlist will be relisted at a lower asking or reserve price within 30 days. | 2026-10-09 | research/watch/watch-log.csv (scheduled watch retired 2026-09-10, Flippa ToS s.3); at 2026-10-09, resolved from evidence obtainable by permitted means, otherwise Unresolvable | open |
| P5 | Neither Remote Work Rebels nor Concealed Carry Society will show as Sold at or above its current asking price by 2026-10-09. | 2026-10-09 | needs both Sold status and price evidence against the asking threshold at 2026-10-09; unknown realized price is Unresolvable | open |
| P6 | The AI-keyword share on the four exit boards will be above 50% on 2026-10-07. | 2026-10-07 | Series C | **Unresolvable.** Series C retired 2026-09-10 before any second capture (exit-board terms bar crawling); scored Issue 2. |
| P7 | The October 2026 Hacker News freelancer thread will again have zero "SEEKING FREELANCER" top-level posts. | 2026-10-08 | Series E | open |
| P8 | The share of the newest 100 GitHub bounty-label issues sitting in board-named repositories will exceed 60% on 2026-10-07. | 2026-10-07 | Series D | open |
| P9 | Of the three Freelancer purchasing-signal listings, the GB Studio job will be awarded to an account with more than 10 reviews, or not awarded at all, by 2026-09-30. | 2026-09-30 | https://www.freelancer.com/projects/game-development/gbstudio-overlay-image-integration | open |
| P10 | The anchor-variation experiment will show that adding a licensed-attorney credential to the prompt raises category A above 60% of lines at Opus 5 (baseline 17%). | 2026-09-09 (same day) | index/variants | **Wrong.** Resolved 53% (8/15), or 60% under the alternative label for one line; neither is above 60%. Direction right, magnitude overstated. |

Confidence is deliberately not stated as a number for Issue 1; after ten scored predictions the register will carry a calibration line.

## Issue 2 predictions (made 2026-09-14)

| # | Prediction | Resolves by | Resolving series or page | Status |
|---|---|---|---|---|
| P11 | In the week-3 Swarm Forecast sample, "sell to the swarm" (category B) is the unique largest category of the 90 lines; a tie for largest counts as Wrong. | 2026-09-21 | Series A, taxonomy v1 | open |
| P12 | In the week-3 sample, Haiku 4.5 puts fewer than 15 of its 30 lines in "sell the signature" (category A). | 2026-09-21 | Series A | open |
| P13 | GitHub's reported total of open bounty-label issues exceeds 4,500 in the first collector capture whose generated_at_utc falls on 2026-10-07 (scheduled 09:00 UTC; a delayed run that day still counts; 4,323 on 2026-09-09, 4,388 on 2026-09-14). No capture that day: Unresolvable. | 2026-10-07 | Series D, total_count_reported | open |

Scored to date: 1 wrong (P10), 2 unresolvable (P3, P6), 10 open. P8 and P13 resolve on the first collector capture dated 2026-10-07 (UTC, by generated_at_utc), scheduled 09:00 UTC through an extra annual cron guarded to 2026; the entry is to be removed after that run, follow-through recorded here.
