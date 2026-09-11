#!/usr/bin/env python3
# Jednorázově doplní do OTHER_LEAGUES v index.html loňská data:
#  - team.last = {lg,pos,w,d,l}  (loňská liga + umístění týmu)
#  - hráč wl = [výhry, prohry]   (loňská individuální bilance, párováno jménem)
# Zdroj: LONI tabulky pinec.info (soutěže ~8266-8273), ligu detekujeme z hlavičky PDF.
import subprocess, re, os, json, unicodedata, difflib, sys

INDEX = os.path.join(os.path.dirname(__file__), "..", "index.html")
SP = os.path.dirname(os.path.abspath(__file__))
CAND_IDS = [8266, 8267, 8268, 8269, 8270, 8271, 8272, 8273]

def sh(c): return subprocess.run(c, shell=True, capture_output=True, encoding='utf-8', errors='replace').stdout or ''

def norm(s):
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.replace('"', '').replace('“', '').replace('”', '').lower()
    s = re.sub(r'\s+', ' ', s).strip().rstrip('.').strip()
    return s

STAND = re.compile(r'^\s*(\d+)\.\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)(?:\s|$)')
PLAYER = re.compile(r'^\s*\d+\.\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s*:\s*\d+(?:\s+[\d,]+\s*%)?')
PSECT = re.compile(r'odehran\w* utk', re.IGNORECASE)
LIGA = re.compile(r'(\d+)\.\s*liga')

def fetch(soutez):
    sh(f'curl -s -m 40 -A "Mozilla/5.0" -c {SP}/cj.txt "https://www.pinec.info/htm/tabulka/?soutez={soutez}" -o /dev/null')
    sh(f'curl -s -m 60 -A "Mozilla/5.0" -b {SP}/cj.txt -e "https://www.pinec.info/htm/tabulka/?soutez={soutez}" '
       f'"https://www.pinec.info/pdf/tabulka/?soutez={soutez}&order=" -o {SP}/l_{soutez}.pdf')
    f = f"{SP}/l_{soutez}.pdf"
    if not os.path.exists(f) or os.path.getsize(f) < 1500:
        return None
    return sh(f'pdftotext -enc UTF-8 -layout {f} -')

# LONI datové struktury
loni_stand = {}   # lg -> {norm_team: {pos,w,d,l,name}}
loni_players = [] # {lg, full_norm, name_raw, w, l}

for sid in CAND_IDS:
    text = fetch(sid)
    if not text:
        print(f"  soutěž {sid}: nedostupná/prázdná", file=sys.stderr); continue
    # liga z hlavičky
    lg = None
    for l in text.splitlines()[:5]:
        m = LIGA.search(l)
        if m:
            lg = int(m.group(1)); break
    if lg is None:
        print(f"  soutěž {sid}: liga nezjištěna", file=sys.stderr); continue
    in_pl = False
    st = loni_stand.setdefault(lg, {})
    nteams = nplay = 0
    for line in text.splitlines():
        if PSECT.search(line):
            in_pl = True; continue
        if in_pl:
            m = PLAYER.match(line)
            if not m: continue
            nameteam, U, Z, V, P = m.groups()
            loni_players.append({'lg': lg, 'full_norm': norm(nameteam), 'w': int(V), 'l': int(P)})
            nplay += 1
        else:
            m = STAND.match(line)
            if not m: continue
            pos, team, U, V, R, P, K = m.groups()
            st[norm(team)] = {'pos': int(pos), 'w': int(V), 'd': int(R), 'l': int(P), 'name': team.strip()}
            nteams += 1
    print(f"  soutěž {sid} -> {lg}. liga: {nteams} týmů, {nplay} hráčů", file=sys.stderr)

# ---- načti OTHER_LEAGUES z index.html ----
html = open(INDEX, encoding='utf-8').read()
m = re.search(r'(const OTHER_LEAGUES = )(\{.*\})(;)', html)
other = json.loads(m.group(2))

# přejmenování klubů mezi sezónami (letošní -> loňský název, normalizovaně)
RENAMES = [('pingpoint slatina', 'st slatina')]

def best_team(name):
    """Najdi loňský tým (přes všechny ligy) nejlépe odpovídající názvu."""
    queries = [norm(name)]
    for a, b in RENAMES:
        if a in queries[0]:
            queries.append(queries[0].replace(a, b))
    best, bestsc, bestlg = None, 0.0, None
    for nn in queries:
        for lg, teams in loni_stand.items():
            for tnorm, rec in teams.items():
                sc = difflib.SequenceMatcher(None, nn, tnorm).ratio()
                if sc > bestsc:
                    bestsc, best, bestlg = sc, rec, lg
    return (best, bestlg, bestsc)

def player_wl(pnorm, ref_team_norm):
    """Loňská bilance hráče podle jména; při shodě jmen rozliš podle týmu (klub)."""
    cands = [e for e in loni_players if e['full_norm'] == pnorm or e['full_norm'].startswith(pnorm + ' ')]
    if not cands:
        return None
    if len(cands) == 1:
        return [cands[0]['w'], cands[0]['l']]
    # víc kandidátů (stejné jméno) -> vyber podle podobnosti zbytku (tým) s ref týmem
    ref = ref_team_norm or ''
    def score(e):
        rest = e['full_norm'][len(pnorm):].strip()
        return difflib.SequenceMatcher(None, rest, ref).ratio()
    cands.sort(key=score, reverse=True)
    if ref and score(cands[0]) >= 0.5:
        return [cands[0]['w'], cands[0]['l']]
    return None  # nejednoznačné -> raději nic

stats = {'teams_last': 0, 'players_wl': 0, 'players_total': 0}
for lg, teams in other.items():
    for t in teams:
        rec, rlg, sc = best_team(t['name'])
        ref_team_norm = None
        if rec and sc >= 0.86:
            t['last'] = {'lg': rlg, 'pos': rec['pos'], 'w': rec['w'], 'd': rec['d'], 'l': rec['l']}
            ref_team_norm = norm(rec['name'])
            stats['teams_last'] += 1
        for r in (t.get('roster') or []):
            stats['players_total'] += 1
            wl = player_wl(norm(r[0]), ref_team_norm or norm(t['name']))
            if wl:
                r[2] = wl
                stats['players_wl'] += 1

new_json = json.dumps(other, ensure_ascii=False, separators=(',', ':'))
out = html[:m.start(2)] + new_json + html[m.end(2):]
open(INDEX, 'w', encoding='utf-8', newline='').write(out)
print(f"\nHOTOVO: last u {stats['teams_last']} týmů, wl u {stats['players_wl']}/{stats['players_total']} hráčů.", file=sys.stderr)
