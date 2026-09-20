"""Render the reviewed Issue 2 copy in the existing Issue 1 layout (stdlib only)."""
from pathlib import Path
import html
import json
import re
from install_analytics import apply_analytics

ROOT = Path(__file__).resolve().parent.parent
template = (ROOT / 'issues/001.html').read_text(encoding='utf-8')
draft = (ROOT / 'issues/002-draft.md').read_text(encoding='utf-8')
sample = json.loads((ROOT / 'swarm-forecast/week2/claude-2026-09-14.json').read_text(encoding='utf-8'))
parts = re.split(r'^## (.+)\n', draft, flags=re.M)
sections = dict(zip(parts[1::2], parts[2::2]))

def inline(text):
    text = html.escape(text)
    def code_link(match):
        value = html.unescape(match[1])
        if value.startswith(('data/', 'swarm-forecast/')) and '*' not in value:
            return '<a href="https://marketfauna.com/' + html.escape(value, quote=True) + '"><code>' + match[1] + '</code></a>'
        return '<code>' + match[1] + '</code>'
    text = re.sub(r'`([^`]+)`', code_link, text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = text.replace('marketfauna.com/bot.html', '<a href="https://marketfauna.com/bot.html">bot purpose page</a>')
    text = text.replace('pull request 4132', '<a href="https://github.com/OpenTermsArchive/contrib-declarations/pull/4132">pull request 4132</a>')
    return text

def markdown(text):
    """The draft uses only paragraphs, flat lists and pipe tables."""
    output = []
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = block.splitlines()
        if all(line.startswith('|') for line in lines):
            rows = []
            for i, line in enumerate(lines):
                if i == 1 and re.fullmatch(r'[|:\-\s]+', line):
                    continue
                tag = 'th' if i == 0 else 'td'
                rows.append('<tr>' + ''.join(f'<{tag}>{inline(cell.strip())}</{tag}>' for cell in line.strip('|').split('|')) + '</tr>')
            output.append('<div class="tablewrap"><table>' + ''.join(rows) + '</table></div>')
        elif all(line.startswith('- ') for line in lines):
            output.append('<ul class="obs">' + ''.join('<li>' + inline(line[2:]) + '</li>' for line in lines) + '</ul>')
        else:
            output.append('<p>' + inline(' '.join(lines)) + '</p>')
    return '\n'.join(output)

def section(eyebrow, title, body, anchor):
    return f'<section id="{anchor}"><div class="eyebrow">{eyebrow}</div><h2>{title}</h2>\n{body}\n</section>'

head = template[:template.index('<body>')]
head = head.replace('<title>Bot Barometer</title>', '<title>Bot Barometer · Issue 2</title>')
head = head.replace('</style>', '.meta b{min-width:0;overflow-wrap:anywhere}.meta{grid-template-columns:minmax(0,1fr) minmax(0,2fr)}\n@media(max-width:760px){.wrap{padding:24px 16px 56px}}\n</style>')
head = head.replace('</head>', '<link rel="canonical" href="https://marketfauna.com/issues/002.html">\n</head>')
mast = template[template.index('  <header'):template.index('  <div class="stats">')]
mast = mast.replace('Issue 1 · Week of 8 September', 'Issue 2 · Week of 15 September').replace('<b>1 week</b>', '<b>2 weeks</b>')
mast = mast.replace("Issue 1 opens it with one provider's models and five public-market observations.", 'The second sample, what changed, and where the evidence stops.')
page = [head, '<body><div class="wrap">', mast]
page.append('<nav class="mono" aria-label="Issue archive"><a href="https://marketfauna.com/issues/001.html">Issue 1 · 8 September</a> · Issue 2 · 15 September · <a href="/tools/">Tools and worked examples</a></nav>')
page.append('<div class="stats">')
tiles = [
    ('29%', 'of strategy lines sell to other agents: 26 of 90 under the original coding, up from 9 of 90. It is the largest category on that coding; the mixed-buyer sensitivity changes the ranking.'),
    ('21%', "sell the human’s signature, down from 46%. Haiku put 6 of its 30 lines here this week, compared with 28 last week."),
    ('52%', 'of the newest 100 GitHub bounty-label issues sit in board-named repositories, down from 86% on 10 September and 78% on 9 September.')]
page.extend(f'<div class="stat"><div class="n">{n}</div><div class="l">{inline(text)}</div></div>' for n, text in tiles)
page.append('</div>')
coverage = sections['Coverage change (must appear near the top, before Series A)']
page.append('<aside class="note"><b>Coverage change · two series retired, not zero</b>' + markdown(coverage) + '</aside>')

a = sections['Series A, Swarm Forecast: week 2 against week 1']
a = a.replace('Paragraphs (keep the Issue 1 voice; each claim points at the table):\n\n', '')
a = a.replace('Fig. 1 data, lines by category and tier (week 2, with week 1 in brackets):', 'Fig. 1. Lines by category and requested tier alias. Week 2 counts, with week 1 in brackets. Resolved model versions were not recorded.')
a = a.replace('Unit of analysis and OpenAI-lineage lines: unchanged from Issue 1 (30 answers, not 90 trials; OpenAI lineage N=0, same reason).', 'Unit of analysis: thirty answers, not ninety independent trials; three lines from one answer are correlated. Fresh-context isolation is reported by the runner, not verifiable from answer files. OpenAI lineage N=0: a comparable independent fresh-context run has not been made; sampling from this already-exposed Codex task would not be comparable.')
chart = '<div class="fig"><div class="legend"><span style="--c:var(--s1)">Haiku 4.5</span><span style="--c:var(--s2)">Sonnet 5</span><span style="--c:var(--s3)">Opus 5</span></div><div class="scrollcue">Chart scrolls sideways; the table below includes both weeks.</div><div class="chartwrap"><div id="chart-taxonomy"></div></div></div>'
sources = '<p class="mono">Sources: <a href="https://marketfauna.com/swarm-forecast/prompt.txt">prompt</a> · <a href="https://github.com/marketfauna/bot-barometer/tree/main/swarm-forecast/week2">week 2 raw answers</a> · <a href="https://marketfauna.com/swarm-forecast/week2/ledger-2026-09-14.jsonl">labels and hashes</a> · <a href="https://marketfauna.com/swarm-forecast/week2/claude-2026-09-14.json">counts, sensitivity and caveats</a> · <a href="https://marketfauna.com/swarm-forecast/claude-2026-09-09.json">week 1 counts</a></p>'
page.append(section('Series A · Swarm Forecast', 'The second sample changes the ranking', chart + markdown(a) + sources, 'series-a'))
page.append(section('Lab · Anchor variation', 'No new sample this week', '<p>The original controlled prompt variations and their labels remain in <a href="https://marketfauna.com/issues/001.html">Issue 1</a>. P10 remains Wrong.</p>', 'lab'))
for key, title, label, anchor in [
    ('Series B, Marketplace crowding: retired', 'Marketplace crowding · retired', 'Series B', 'series-b'),
    ('Series C, Exit boards: retired', 'Exit boards · retired', 'Series C', 'series-c')]:
    copy = sections[key].strip().removeprefix('One line: ').replace(' No chart.', '')
    page.append(section(label, title, markdown(copy), anchor))
d_table = '| Capture | Board-named issues / 100 | Top repository | Reported total open |\n|---|---|---|---|\n| 9 September | 78 | 32% | 4,323 |\n| 10 September | 86 | 56% | 4,360 |\n| 14 September | 52 | 35% | 4,388 |'
d = sections['Series D, Bounty boards'].replace("Paragraph: this week's", "This week's")
page.append(section('Series D · Bounty boards', 'A different newest-100 window', markdown(d_table) + markdown(d), 'series-d'))
e_table = '| Capture | Top-level posts | Seeking work | Seeking freelancer | Other |\n|---|---|---|---|---|\n| 9 September | 18 | 17 | 0 | 1 |\n| 14 September | 23 | 22 | 0 | 1 |'
e = sections['Series E, Supply and demand'].replace('Paragraph: five', 'Five')
page.append(section('Series E · Supply and demand', 'Five more supply posts in the selected thread', markdown(e_table) + markdown(e) + '<p><a href="https://news.ycombinator.com/item?id=49522905">Selected September freelancer thread</a></p>', 'series-e'))
page.append(section('Also this week', 'Changes to the collection and contribution work', markdown(sections['Also this week']), 'also'))
page.append(section('Register', 'One wrong, two unresolvable, ten open', markdown(sections['Register']) + '<p><a href="https://github.com/marketfauna/bot-barometer/blob/main/PREDICTIONS.md">Full prediction wording and resolution register</a></p>', 'predictions'))
method = sections['Method and denominators'].split('Footer changes:')[0]
page.append(section('Method and denominators', 'How the numbers were made', markdown(method), 'method'))
page.append('<footer><div>Bot Barometer is published by Marketfauna. The series began 2026-09-09. Published 2026-09-15; model sample and API capture dated 2026-09-14.</div><div class="mono" style="margin-top:8px">Contact: <a href="mailto:hello@marketfauna.com">hello@marketfauna.com</a> · <a href="https://marketfauna.com/feed.json">Machine-readable feed</a> · <a href="https://github.com/marketfauna/bot-barometer">Source repository</a><br>Next issue: week of 22 September. Next weekly sample: target 2026-09-21 09:00 UTC, actual start and end recorded. Next release-day sample: on the next frontier model release from either lineage.</div></footer></div><div class="tip" id="tip"></div>')

# Reuse the original interactive chart, without the retired-series fill routine.
script = template[template.index('const TAXO ='):template.index('function fillCollector')]
script = re.sub(r'const COUNTS = \{.*?\n\};', 'const COUNTS = ' + json.dumps(sample['counts_by_tier']) + ';', script, flags=re.S)
script = script.replace('Spend the $10k on distribution', 'Distribution and trust (coding changed)').replace('Spend on distribution', 'Distribution and trust')
script = script.replace('// Fig 1: stacked', 'TAXO.sort((a,b)=>TIERS.reduce((n,[k])=>n+COUNTS[k][b[0]]-COUNTS[k][a[0]],0));\n\n// Fig 1: stacked')
page.append('<script>' + script + '</script></body></html>')
result = '\n'.join(page)
for path in ('index.html', 'issues/002.html'):
    (ROOT / path).write_text(apply_analytics(result, path), encoding='utf-8', newline='\n')
print('Wrote index.html and issues/002.html')
