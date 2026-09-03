#!/usr/bin/env python3
"""
Stáhne aktuální tabulku + úspěšnost hráčů 6. ligy (soutěž 8333) z pinec.info,
naparsuje a zapíše do bloku AUTO:CURRENT v index.html.

Bezpečnostní pravidla:
- když se na pinec nedosáhne / PDF je prázdné / naparsuje 0 týmů -> NIC nepřepíše
  (aby se transientní chybou nesmazala poslední dobrá data),
- když jsou nová data shodná s uloženými -> NIC nezapíše (žádný commit),
- timestamp 'updated' se mění jen při reálné změně dat.
"""
import subprocess, re, os, json, sys, unicodedata
from datetime import datetime, timezone

SOUTEZ = "8333"
INDEX = os.path.join(os.path.dirname(__file__), "..", "index.html")

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def norm(s):
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.replace('"', '').replace('“', '').replace('”', '').lower()
    s = re.sub(r'\s+', ' ', s).strip()
    s = s.rstrip('.').strip()
    return s

# název týmu z pinecu (normalizovaný) -> naše číslo týmu
TEAM_MAP = {}
for alias, num in [
    ('PingPoint Slatina F', 1), ('ST Slatina F', 1),
    ('Orel Bohunice C', 2),
    ('Hraví Baristé A', 3), ('Hraví Baristé', 3),
    ('PingPoint Slatina E', 4), ('ST Slatina G', 4),
    ('Sokol Komín C', 5),
    ('Orel Masaryk. čtvrť B', 6), ('Orel Masarykova čtvrť B', 6),
    ('Orel Řečkovice A', 7),
    ('Staré páky A', 8),
    ('SKP Kometa C', 9),
    ('Hravsonauti A', 10),
]:
    TEAM_MAP[norm(alias)] = num

# naše soupisky – kvůli namapování hráčů z úspěšnosti na přesná jména
ROSTER = {
    1: ['Smejkal Petr', 'Vlach Vlastimil', 'Vlach Radim'],
    2: ['Musil Josef', 'Kročil František', 'Novoměstský Zdeněk', 'Lapúník Michal', 'Chytil Jakub'],
    3: ['Hloušek Roman', 'Holubko Michal', 'Dufka Milan', 'Kadlic Šimon'],
    4: ['Tichý Roman', 'Pišl Milan', 'Klein Michal', 'Šutera Ondřej', 'Mahrík Martin'],
    5: ['Kružík Bořivoj', 'Blažek Miloš', 'Dorúšek Petr', 'Daniel Otakar', 'Hrúza Petr', 'Uhlíř Petr'],
    6: ['Crhán Jiří', 'Drlík Václav', 'Kovács Peter', 'Šustr Josef'],
    7: ['Matoušek Jan', 'Novák Boris', 'Irein Martin', 'Šlemr Václav'],
    8: ['Hanák Vladimír', 'Pavliš Drahoslav', 'Pavliš Oldřich', 'Jonášek Martin', 'Machálek Lubomír'],
    9: ['Mrázek Miloš', 'Sobota Tomáš', 'Novosad Květoslav', 'Nešpor Bohumil', 'Bednář Martin'],
    10: ['Buriánek Michal', 'Šimků Sebastian', 'Suchánek Lukáš', 'Rajčan Michal'],
}
ROSTER_NORM = {tn: {norm(n): n for n in names} for tn, names in ROSTER.items()}

# tabulka:   "1. BBB A 18 18 0 0 0 143:37 72"  (poz. tým U V R P K skóre body)
# 2-sloupcové PDF slepuje řádky -> nekotvíme konec.
STAND = re.compile(r'^\s*(\d+)\.\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+\d+\s*:\s*\d+\s+(\d+)(?:\s|$)')
# úspěšnost: "1. Rajčan Michal Hravsonauti A 17 51 47 4 148 : 24 92,16 %"
#            poz. jméno+tým                 U  Z  V  P  míčky      %
PLAYER = re.compile(r'^\s*\d+\.\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s*:\s*\d+\s+[\d,]+\s*%')
# rozpis:  "541 Út 23.09.2025 16:00 Domácí... Hosté... 3 : 7 12 : 23"  (čas může být "-")
#          id                       tým1     tým2      skóre  sety
ROW = re.compile(r'^\s*\d+\s+\S+\s+\d{2}\.\d{2}\.\d{4}\s+(?:[\d:]+|-)\s+(.+?)\s+(\d+)\s*:\s*(\d+)\s+(\d+)\s*:\s*(\d+)\s*$')
RND = re.compile(r'(\d+)\.\s*kolo stupně')

def fetch_text():
    sh(f'curl -s -m 40 -A "Mozilla/5.0" -c cj.txt '
       f'"https://www.pinec.info/htm/tabulka/?soutez={SOUTEZ}" -o /dev/null')
    code = sh(f'curl -s -m 60 -A "Mozilla/5.0" -w "%{{http_code}}" -b cj.txt '
             f'-e "https://www.pinec.info/htm/tabulka/?soutez={SOUTEZ}" '
             f'"https://www.pinec.info/pdf/tabulka/?soutez={SOUTEZ}&order=" -o tab.pdf').stdout.strip()
    size = os.path.getsize("tab.pdf") if os.path.exists("tab.pdf") else 0
    print(f"HTTP {code}, PDF {size} B")
    if size < 1500:
        return None
    return sh('pdftotext -layout tab.pdf -').stdout

def parse(text):
    teams, players = {}, {}
    aliases = sorted(TEAM_MAP.keys(), key=len, reverse=True)  # delší napřed
    for line in text.splitlines():
        if '%' in line:  # řádek úspěšnosti hráče
            m = PLAYER.match(line)
            if not m:
                continue
            nameteam, U, Z, V, P = m.groups()
            nt = norm(nameteam)
            for a in aliases:
                if nt == a or nt.endswith(' ' + a):
                    tn = TEAM_MAP[a]
                    pnorm = nt[:len(nt) - len(a)].strip()
                    exact = ROSTER_NORM.get(tn, {}).get(pnorm)
                    if exact:
                        players.setdefault(str(tn), {})[exact] = [int(V), int(P)]
                    break
        else:  # řádek tabulky
            m = STAND.match(line)
            if m:
                pos, team, U, V, R, P, body = m.groups()
                tn = TEAM_MAP.get(norm(team))
                if tn:
                    teams[str(tn)] = {"pos": int(pos), "w": int(V), "d": int(R), "l": int(P)}
    return teams, players

def fetch_rozpis():
    sh(f'curl -s -m 40 -A "Mozilla/5.0" -c cj.txt '
       f'"https://www.pinec.info/htm/rozpis/?soutez={SOUTEZ}" -o /dev/null')
    code = sh(f'curl -s -m 60 -A "Mozilla/5.0" -w "%{{http_code}}" -b cj.txt '
             f'-e "https://www.pinec.info/htm/rozpis/?soutez={SOUTEZ}" '
             f'"https://www.pinec.info/pdf/rozpis/?soutez={SOUTEZ}&order=" -o roz.pdf').stdout.strip()
    size = os.path.getsize("roz.pdf") if os.path.exists("roz.pdf") else 0
    print(f"rozpis HTTP {code}, PDF {size} B")
    if size < 1500:
        return None
    return sh('pdftotext -layout roz.pdf -').stdout

def parse_results(text):
    aliases = sorted(TEAM_MAP.keys(), key=len, reverse=True)
    results, rnd = {}, None
    for line in text.splitlines():
        h = RND.search(line)
        if h:
            rnd = int(h.group(1)); continue
        if rnd is None:
            continue
        m = ROW.match(line)
        if not m:
            continue
        ha, sc_h, sc_a, se_h, se_a = m.groups()
        nt = norm(ha)
        home = away = None
        for a in aliases:
            if nt.endswith(' ' + a):
                away = TEAM_MAP[a]
                home = TEAM_MAP.get(norm(nt[:len(nt) - len(a)]))
                break
        if home and away:
            results.setdefault(str(rnd), {})[str(home)] = {
                "a": away, "sc": [int(sc_h), int(sc_a)], "se": [int(se_h), int(se_a)]}
    return results

def now_str():
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.now(ZoneInfo("Europe/Prague"))
    except Exception:
        dt = datetime.now(timezone.utc)
    return f"{dt.day}. {dt.month}. {dt.year} {dt.hour:02d}:{dt.minute:02d}"

BLOCK = re.compile(
    r'(/\* ===== AUTO:CURRENT:START.*?===== \*/\s*\nconst CURRENT = )(.*?)(;\s*\n/\* ===== AUTO:CURRENT:END ===== \*/)',
    re.S)

def main():
    text = fetch_text()
    if text is None:
        print("PDF prázdné/nedostupné — data ponechána beze změny.")
        return 0
    teams, players = parse(text)
    npl = sum(len(v) for v in players.values())
    print(f"naparsováno: {len(teams)} týmů, {npl} hráčů s daty")
    if len(teams) == 0:
        print("0 týmů (přenos / prázdná soutěž) — NEpřepisuji, chráním poslední data.")
        return 0

    html = open(INDEX, encoding='utf-8').read()
    m = BLOCK.search(html)
    if not m:
        print("CHYBA: značky AUTO:CURRENT nenalezeny v index.html", file=sys.stderr)
        return 1
    try:
        old = json.loads(m.group(2))
    except Exception:
        old = None

    # výsledky z rozpisu; při chybě stažení ponech stará data
    rtext = fetch_rozpis()
    results = parse_results(rtext) if rtext is not None else (old or {}).get("results", {})
    print(f"výsledky: {len(results)} kol, {sum(len(v) for v in results.values())} zápasů")

    new_teams = {k: teams[k] for k in sorted(teams, key=int)}
    new = {"updated": None, "teams": new_teams, "players": players, "results": results}

    unchanged = (old is not None
                 and old.get("teams") == new["teams"]
                 and old.get("players") == new["players"]
                 and old.get("results") == new["results"])
    if unchanged:
        print("Data se nezměnila — žádný zápis, žádný commit.")
        return 0

    new["updated"] = now_str()
    new_json = json.dumps(new, ensure_ascii=False)
    out = html[:m.start(2)] + new_json + html[m.end(2):]
    open(INDEX, 'w', encoding='utf-8', newline='').write(out)
    print("Data AKTUALIZOVÁNA:", new["updated"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
