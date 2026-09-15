/* Cloudflare page/referrer measurement. Site token is public, never an API key. */
(() => {
  const token = document.currentScript?.getAttribute('data-site-token');
  if (!token || !['marketfauna.com', 'www.marketfauna.com'].includes(location.hostname)) return;
  const exclusionKey = 'marketfauna-analytics-excluded';
  const excludedHere = new URLSearchParams(location.search).get('analytics') === 'off';
  let excludedSession = false;
  try {
    if (excludedHere) sessionStorage.setItem(exclusionKey, '1');
    excludedSession = sessionStorage.getItem(exclusionKey) === '1';
  } catch (_) { /* With storage unavailable, the current URL still opts out. */ }
  if (excludedHere || excludedSession) return;
  const beacon = document.createElement('script');
  beacon.type = 'module';
  beacon.src = 'https://static.cloudflareinsights.com/beacon.min.js';
  beacon.setAttribute('data-cf-beacon', JSON.stringify({token}));
  document.head.appendChild(beacon);
})();
