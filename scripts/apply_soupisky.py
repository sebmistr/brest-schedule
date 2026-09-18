#!/usr/bin/env python3
# Aplikuje čerstvá data (fresh_soupisky.json) na OTHER_LEAGUES v index.html:
# u týmu se změněným rosterem přepíše soupisku (se pohlavím, wl=null -> doplní loni_enrich),
# u změněné herny přepíše venue. 6. ligu (ROSTERS) neřeší.
import re, json, unicodedata
import os as _os
INDEX=_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "index.html")
_SD=_os.path.dirname(_os.path.abspath(__file__))
def norm(s):
    s=unicodedata.normalize('NFKD',s); s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+',' ',re.sub(r'["“”]','',s).lower()).strip()

fresh=json.load(open(_os.path.join(_SD,'fresh_soupisky.json'),encoding='utf-8'))
html=open(INDEX,encoding='utf-8').read()
m=re.search(r'(const OTHER_LEAGUES = )(\{.*\})(;)', html)
other=json.loads(m.group(2))
applied=[]
for lg in other:  # '1','2','3','4','5','7','8'
    ftl={norm(t['name']):t for t in fresh.get(lg,[])}
    for team in other[lg]:
        ft=ftl.get(norm(team['name']))
        if not ft or not ft['roster']:
            continue
        fn=[r[0] for r in ft['roster']]; cn=[r[0] for r in team['roster']]
        if [norm(x) for x in fn]!=[norm(x) for x in cn]:
            team['roster']=[[r[0], r[1], None] for r in ft['roster']]
            applied.append(f"L{lg} {team['name']}: roster -> {fn}")
        if ft['venue'] and norm(ft['venue'])!=norm(team.get('venue','')):
            applied.append(f"L{lg} {team['name']}: venue '{team.get('venue','')}' -> '{ft['venue']}'")
            team['venue']=ft['venue']

newjson=json.dumps(other, ensure_ascii=False, separators=(',',':'))
open(INDEX,'w',encoding='utf-8',newline='').write(html[:m.start(2)]+newjson+html[m.end(2):])
print("APLIKOVÁNO:")
for a in applied: print("  ",a)
print(f"celkem {len(applied)} úprav")
