# Site measurement

Status, 2026-09-15: integration prepared and locally tested; **not collecting yet**. The actual public site token from the shared Cloudflare account is pending. No live dashboard receipt has been verified.

Selected Cloudflare Web Analytics for browser page/referrer measurement on the existing GitHub Pages site. The shared account is also being set up for the bot key directory; no second analytics account, DNS move or proxy migration is needed for the manual snippet. Selection can change if that dependency or measurement quality makes it unsuitable.

## Activation and acceptance

1. In the existing Cloudflare account, Web Analytics → Add a site → marketfauna.com → Manage site. Obtain the **public site token** from the JS snippet. Never put an API token, private signing key or password into these files.
2. Run `python tools/install_analytics.py --site-token PUBLIC_SITE_TOKEN`. It creates the public analytics-site.json and adds one loader to the homepage, issue archives, briefs and bot purpose page. The issue builder preserves the integration on regeneration. Existing brief/check request subjects stay intact; bare contact links get a page-specific inquiry subject.
3. Run `node --test tools/test_analytics.cjs`, inspect the diff, and publish the changes. Check the live loader and configuration against the deployment.
4. Make one deliberately recorded, non-excluded acceptance visit; verify its page/date in the actual dashboard after ingestion. Record the timestamp/path as synthetic and exclude it from any audience claim. A local passing test or loaded script is not proof of collection. Document data access and the observed coverage in the operational record before reporting completion.

## Excluding our own checks

For normal public-site browser checks, first navigate with `?analytics=off` (or `&analytics=off` if a query already exists). The loader suppresses the beacon before loading it and persists exclusion in sessionStorage for later navigations in that tab session. Start a separate unexcluded session only for the labeled acceptance visit. If session storage is denied, each check URL must carry the exclusion parameter. Localhost/previews are excluded by the production-hostname allowlist. No IP blacklist or stable visitor identifier is maintained by our code.

## What the figures mean

- Page/referrer counts are browser measurements, not verified humans, buyers or complete readership. Script blockers and non-JavaScript readers are missing. Reporting can be sampled; preserve the dashboard/API's measurement semantics.
- Cloudflare Web Analytics currently has no custom-event or UTM support. Do not invent contact-click totals or POST synthetic events to its RUM endpoint. Page-specific email subjects and existing request subjects can provide evidence of **received inquiries**, not clicks, unique visitors or full funnel attribution.
- Plain feed.json, raw-data and other machine downloads are outside client-side measurement. GitHub repository views/clones measure the repository, not Pages traffic. Deployment success is publication evidence, not reads.
- Private Claude artifacts, the external OTA PR and Flippa pages are not controlled web properties on which this script can measure visits. Outreach/replies/bounces, accepted work, invoices/payment and effort belong in their respective operational records. No consolidated conversion rate exists yet.
- Contact email signatures already point to marketfauna.com; this is a potential referral route even though no deliberate newsletter/social distribution campaign has occurred.

Official documentation checked 2026-09-15: [manual setup](https://developers.cloudflare.com/web-analytics/get-started/), [limits, custom events, UTM and sampling](https://developers.cloudflare.com/web-analytics/faq/).
