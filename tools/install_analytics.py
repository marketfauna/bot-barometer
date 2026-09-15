"""Install the public Web Analytics site token; no API credentials or account access.

Run with --site-token from Cloudflare's public JS snippet, then build/publish.
Without a saved token, page generation makes no analytics changes.
"""
import argparse
import html
import json
from pathlib import Path
import re
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'analytics-site.json'
START = '<!-- Marketfauna analytics -->'
END = '<!-- /Marketfauna analytics -->'

def apply_analytics(page, source):
    if not CONFIG.exists():
        return page
    token = json.loads(CONFIG.read_text(encoding='utf-8'))['public_site_token']
    if not re.fullmatch(r'[a-zA-Z0-9_-]{16,128}', token):
        raise ValueError('Expected the public token from the Web Analytics snippet')
    page = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\s*', '', page, flags=re.S)
    snippet = f'{START}\n<script defer src="/analytics.js" data-site-token="{html.escape(token, quote=True)}"></script>\n{END}\n'
    if '</body>' not in page:
        raise ValueError(f'Missing closing body in {source}')
    page = page.replace('</body>', snippet + '</body>', 1)
    # A submitted email's subject is attribution evidence; this is NOT click tracking.
    subject = quote('Marketfauna inquiry - ' + source, safe='')
    page = page.replace('href="mailto:hello@marketfauna.com"', f'href="mailto:hello@marketfauna.com?subject={subject}"')
    return page

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-token', required=True, help='PUBLIC site token; never a Cloudflare API credential')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{16,128}', args.site_token):
        parser.error('Use only the public site token from the beacon snippet')
    CONFIG.write_text(json.dumps({'provider':'Cloudflare Web Analytics', 'hostname':'marketfauna.com', 'public_site_token':args.site_token}, indent=2)+'\n', encoding='utf-8', newline='\n')
    for path in [ROOT/'index.html', ROOT/'briefs.html', ROOT/'bot.html', *sorted((ROOT/'issues').glob('*.html'))]:
        name = path.relative_to(ROOT).as_posix()
        path.write_text(apply_analytics(path.read_text(encoding='utf-8'), name), encoding='utf-8', newline='\n')
        print('Prepared', name)
