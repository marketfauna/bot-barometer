# Agent access reading instrument

Reads how named public URLs answer an honestly identified, non-browser request, and writes `reading.json`, `reading.md` and `reading.html`. Python 3.7 or later, standard library only. Run from your own network it makes the control and unsigned requests; the signed condition needs a key and drops itself without one.

    python reading.py check scopes/your-scope.json
    python reading.py run scopes/your-scope.json --out out --vantage "one line describing your network"
    python reading.py compare ours/reading.json yours/reading.json

Scope fields are documented at the top of `reading.py`. Conduct, in short: robots.txt is evaluated under RFC 9309 for the exact URL and governs; a refused or unreachable robots.txt ends the site; every redirect of a page request is checked first; crawl delays are honoured up to 30 seconds; at most ten requests reach any host; bodies and cookie values are not stored; nothing here disguises the client or attempts a challenge. `python -m unittest test_reading` runs the offline tests. Who is asking: https://marketfauna.com/bot.html
