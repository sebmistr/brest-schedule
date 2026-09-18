#!/usr/bin/env python3
# Znovu stáhne soupisky všech 8 lig a porovná s daty v index.html (rosteru, vedoucí, herna).
import re, subprocess, json, unicodedata, difflib, sys

import os as _os
INDEX = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "index.html")
_SD = _os.path.dirname(_os.path.abspath(__file__))
SOUTEZ = {1:8328,2:8329,3:8330,4:8331,5:8332,6:8333,7:8334,8:8335}

def sh(c): return subprocess.run(c, shell=True, capture_output=True, encoding='utf-8', errors='replace').stdout or ''
def norm(s):
    s = unicodedata.normalize('NFKD', s); s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', re.sub(r'["“”]', '', s).lower()).strip()

SPEC = {'tecka':'.','zavinac':'@','plus':'+'}
def deob(frag):
    frag = re.sub(r'<span class="str-([a-z0-9]+)">.*?</span>', lambda m: SPEC.get(m.group(1), m.group(1)), frag, flags=re.S)
    return re.sub(r'\s+','', re.sub(r'<[^>]+>','',frag))
def fmtphone(p):
    p=p.replace('+420',''); return f"{p[0:3]} {p[3:6]} {p[6:9]}" if p.isdigit() and len(p)==9 else p

DAYMAP={'po':'pondělí','út':'úterý','st':'středa','čt':'čtvrtek','pá':'pátek','so':'sobota','ne':'neděle'}
def parse_herna(s):
    s=s.strip(); m=re.search(r'^(.*?),\s*((?:po|út|st|čt|pá|so|ne)[^,]*?)\s+(\d{1,2}[:.]\d{2}[^,]*)$', s)
    if not m: return s,'',''
    days=[DAYMAP[d] for d in re.findall(r'po|út|st|čt|pá|so|ne', re.sub(r'\([^)]*\)','',m.group(2)))]
    return m.group(1).strip(), ' / '.join(dict.fromkeys(days)), m.group(3).strip().replace('.',':')

def scrape(sz):
    h = sh(f'curl -s -m 40 -A "Mozilla/5.0" "https://www.pinec.info/htm/svaz/soupisky/?soutez={sz}"')
    rows = re.findall(r'<td class="c w20">(\d+)\.</td>(.*?)(?=<td class="c w20">\d+\.|</table>)', h, re.S)
    teams=[]
    for _,body in rows:
        nm=re.search(r'muzstvoId=(\d+)[^>]*>([^<]+)</a>', body)
        if not nm: continue
        mid,name=nm.group(1),nm.group(2).strip()
        lead=re.search(r'<div class="b">([^<]+)</div>', body)
        ph=re.search(r'<span class="phone">(.*?)</span>\s*<br', body, re.S)
        em=re.search(r'<span class="email">(.*?)</td>', body, re.S)
        hn=re.search(r'Herna:</span>\s*([^<]+)<', body)
        v,d,t=parse_herna(hn.group(1)) if hn else ('','','')
        roster=[]
        for _try in range(3):  # detail stránka občas timeoutne -> retry
            dt=sh(f'curl -s -m 30 -A "Mozilla/5.0" "https://www.pinec.info/htm/svaz/kluby/muzstva/detail/?muzstvoId={mid}&soutez={sz}&svaz=431706"')
            roster=[[p.strip(), 'Z' if c in ('pink','red') else 'M'] for c,p in re.findall(r'ico-color-(\w+).*?hraci/detail/\?hracId=\d+[^>]*>([^<]+)</a>', dt, re.S)]
            if roster: break
        teams.append({'name':name,'lead':lead.group(1).strip() if lead else '',
                      'tel':fmtphone(deob(ph.group(1))) if ph else '','mail':deob(em.group(1)) if em else '',
                      'venue':v,'day':d,'time':t,'roster':roster})
    return teams

# ---- current data from index.html ----
html=open(INDEX,encoding='utf-8').read()
other=json.loads(re.search(r'const OTHER_LEAGUES = (\{.*\});', html).group(1))
# L6: names from L6_TEAMS, rosters from ROSTERS
l6names={}
for m in re.finditer(r"\{n:(\d+), name:'([^']+)'", html):
    l6names[int(m.group(1))]=m.group(2)
rosters6={}
rblock=re.search(r'const ROSTERS = \{(.*?)\n\};', html, re.S).group(1)+'\n'
for m in re.finditer(r'(\d+):\[(.*?)\],?\n', rblock):
    names=re.findall(r"\['([^']+)'", m.group(2))
    rosters6[int(m.group(1))]=names

def current_teams(lg):
    """vrátí {norm(name): (roster_names, lead, venue, day, time, display_name)}"""
    out={}
    if lg==6:
        for n,nm in l6names.items():
            out[norm(nm)]=(rosters6.get(n,[]), '', '', '', '', nm)
    else:
        for t in other[str(lg)]:
            lead=t['players'][0]['name'] if t.get('players') else ''
            out[norm(t['name'])]=([r[0] for r in t['roster']], lead, t.get('venue',''), t.get('day',''), t.get('time',''), t['name'])
    return out

def bestmatch(nn, keys):
    if nn in keys: return nn
    best,sc=None,0.0
    for k in keys:
        r=difflib.SequenceMatcher(None,nn,k).ratio()
        if r>sc: sc,best=r,k
    return best if sc>=0.8 else None

changes=0; fresh_all={}
for lg in range(1,9):
    fresh=scrape(SOUTEZ[lg]); cur=current_teams(lg); fresh_all[lg]=fresh
    print(f"\n===== {lg}. liga ({len(fresh)} týmů na pinecu, {len(cur)} v appce) =====", file=sys.stderr)
    curkeys=list(cur.keys())
    for ft in fresh:
        k=bestmatch(norm(ft['name']), curkeys)
        if not k:
            print(f"  [NOVÝ/NESPÁROVANÝ TÝM] {ft['name']} — roster {ft['roster']}", file=sys.stderr); changes+=1; continue
        cr, clead, cv, cd, ctime, cdisp = cur[k]
        diffs=[]
        if not ft['roster']:
            print(f"  [FETCH FAIL] {cdisp}: soupisku se nepodařilo stáhnout (přeskakuji)", file=sys.stderr); continue
        fresh_names=[r[0] for r in ft['roster']]
        addp=[p for p in fresh_names if norm(p) not in {norm(x) for x in cr}]
        delp=[p for p in cr if norm(p) not in {norm(x) for x in fresh_names}]
        if addp: diffs.append(f"+hráči {addp}")
        if delp: diffs.append(f"-hráči {delp}")
        if lg!=6 and clead and ft['lead'] and norm(clead)!=norm(ft['lead']): diffs.append(f"vedoucí '{clead}'->'{ft['lead']}'")
        if lg!=6 and cv and ft['venue'] and norm(cv)!=norm(ft['venue']): diffs.append(f"herna '{cv}'->'{ft['venue']}'")
        if diffs:
            changes+=1
            print(f"  [ZMĚNA] {cdisp}: " + " | ".join(diffs), file=sys.stderr)
print(f"\n===== CELKEM změn/nesrovnalostí: {changes} =====", file=sys.stderr)
json.dump(fresh_all, open(_os.path.join(_SD,'fresh_soupisky.json'),'w',encoding='utf-8'), ensure_ascii=False)
print("čerstvá data uložena -> fresh_soupisky.json", file=sys.stderr)
