#!/usr/bin/env python3
"""
Stáhne aktuální tabulku + úspěšnost hráčů a rozpis (výsledky) pro VŠECHNY ligy
1.–7. (soutěže 8328–8334) z pinec.info, naparsuje a zapíše do bloku
AUTO:CURRENT v index.html jako objekt CURRENT_ALL (klíč = číslo ligy).

Mapování týmů/hráčů:
- ligy 1–5,7: názvy týmů + soupisky se berou přímo z dat OTHER_LEAGUES v index.html
  (jsou z pinecu, takže sedí; navíc fuzzy fallback pro drobné odchylky zkratek),
- liga 6: naše vlastní zobrazované názvy → ruční aliasy + soupiska (níže).

Bezpečnostní pravidla (per liga i celek):
- když se na pinec nedosáhne / PDF je prázdné / naparsuje 0 týmů -> pro danou ligu
  se PONECHAJÍ poslední dobrá data (nepřepisujeme transientní chybou),
- když jsou nová data shodná s uloženými -> NIC se nezapíše (žádný commit),
- 'updated' se u ligy mění jen při reálné změně jejích dat.
"""
import subprocess, re, os, json, sys, unicodedata, difflib
from datetime import datetime, timezone

# LETOS soutěže (= i soupisky) podle LINKS.txt
SOUTEZ = {"1": "8328", "2": "8329", "3": "8330", "4": "8331", "5": "8332", "6": "8333", "7": "8334"}
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

# ---- liga 6: naše zobrazované názvy se liší od pinecu -> ruční aliasy + soupiska ----
L6_ALIASES = [
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
]
L6_ROSTER = {
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

def build_maps():
    """Z index.html sestaví per-ligu: aliasy názvů týmů, soupisky a kanonické názvy."""
    html = open(INDEX, encoding='utf-8').read()
    m = re.search(r'const OTHER_LEAGUES = (\{.*\});', html)
    other = json.loads(m.group(1))
    team_alias, roster, names = {}, {}, {}
    for lg, teams in other.items():
        ta, rn, nm = {}, {}, {}
        for t in teams:
            ta[norm(t['name'])] = t['n']
            nm[t['n']] = t['name']
            rn[t['n']] = {norm(p[0]): p[0] for p in (t.get('roster') or [])}
        team_alias[lg], roster[lg], names[lg] = ta, rn, nm
    # liga 6 (ruční)
    team_alias["6"] = {norm(a): n for a, n in L6_ALIASES}
    roster["6"] = {n: {norm(x): x for x in ns} for n, ns in L6_ROSTER.items()}
    names["6"] = {}  # pro 6 spoléháme na aliasy, ne na fuzzy
    return team_alias, roster, names

# tabulka (standings):  "1. BBB A 18 18 0 0 0 143:37 72"  (poz. tým U V R P K [skóre body])
# ve 2-sloupcovém PDF pozicím 6-10 skóre/body chybí -> nekotvíme na ně, stačí poz.+5 čísel.
STAND = re.compile(r'^\s*(\d+)\.\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)(?:\s|$)')
# úspěšnost: "1. Rajčan Michal Hravsonauti A 17 51 47 4 148:24 92,16 %"  (jméno+tým U Z V P míčky [%])
# spodní pásmo (pod 50 %) je bez procent -> % je nepovinné.
PLAYER = re.compile(r'^\s*\d+\.\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s*:\s*\d+(?:\s+[\d,]+\s*%)?')
# nadpis oddělující tabulku od úspěšnosti hráčů ("Od 100% do 50% odehraných utkání ...")
PSECT = re.compile(r'odehran\w* utk', re.IGNORECASE)
# rozpis:  "541 Út 23.09.2025 16:00 Domácí... Hosté... 3 : 7 12 : 23"  (id ... tým1 tým2 skóre sety)
# čas může být "16:00", "-", nebo úplně prázdný -> celý časový token je nepovinný.
ROW = re.compile(r'^\s*\d+\s+\S+\s+\d{2}\.\d{2}\.\d{4}\s+(?:(?:[\d:]+|-)\s+)?(.+?)\s+(\d+)\s*:\s*(\d+)\s+(\d+)\s*:\s*(\d+)\s*$')
RND = re.compile(r'(\d+)\.\s*kolo stupně')

def match_team(nteam, aliases, alist, names):
    """Přiřadí normalizovaný název týmu k našemu číslu (přesně, suffixem, nebo fuzzy)."""
    if not nteam:
        return None
    if nteam in aliases:
        return aliases[nteam]
    for a in alist:
        if nteam == a or nteam.endswith(' ' + a) or a.endswith(' ' + nteam):
            return aliases[a]
    best, bestsc = None, 0.0
    for num, cname in names.items():
        sc = difflib.SequenceMatcher(None, nteam, norm(cname)).ratio()
        if sc > bestsc:
            bestsc, best = sc, num
    return best if bestsc >= 0.82 else None

def fetch_pdf(kind, soutez):
    """kind = 'tabulka' | 'rozpis'. Vrátí text PDF, nebo None při chybě/prázdnu."""
    tag = {"tabulka": "tab", "rozpis": "roz"}[kind]
    sh(f'curl -s -m 40 -A "Mozilla/5.0" -c cj.txt '
       f'"https://www.pinec.info/htm/{kind}/?soutez={soutez}" -o /dev/null')
    code = sh(f'curl -s -m 60 -A "Mozilla/5.0" -w "%{{http_code}}" -b cj.txt '
             f'-e "https://www.pinec.info/htm/{kind}/?soutez={soutez}" '
             f'"https://www.pinec.info/pdf/{kind}/?soutez={soutez}&order=" -o {tag}.pdf').stdout.strip()
    size = os.path.getsize(f"{tag}.pdf") if os.path.exists(f"{tag}.pdf") else 0
    print(f"  {kind}: HTTP {code}, PDF {size} B")
    if size < 1500:
        return None
    return sh(f'pdftotext -enc UTF-8 -layout {tag}.pdf -').stdout

def parse_tabulka(text, aliases, roster, names):
    teams, players = {}, {}
    alist = sorted(aliases.keys(), key=len, reverse=True)
    plist = sorted(((pn, orig, num) for num, d in roster.items() for pn, orig in d.items()),
                   key=lambda x: len(x[0]), reverse=True)
    in_players = False  # nejdřív tabulka, po nadpisu úspěšnost hráčů
    for line in text.splitlines():
        if PSECT.search(line):
            in_players = True
            continue
        if in_players:  # řádek úspěšnosti hráče
            m = PLAYER.match(line)
            if not m:
                continue
            nameteam, U, Z, V, P = m.groups()
            nt = norm(nameteam)
            for pn, orig, num in plist:  # hledáme hráče podle prefixu (soupiska)
                if nt == pn or nt.startswith(pn + ' '):
                    players.setdefault(str(num), {})[orig] = [int(V), int(P)]
                    break
        else:  # řádek tabulky
            m = STAND.match(line)
            if not m:
                continue
            pos, team, U, V, R, P, K = m.groups()
            tn = match_team(norm(team), aliases, alist, names)
            if tn:
                teams[str(tn)] = {"pos": int(pos), "w": int(V), "d": int(R), "l": int(P)}
    return teams, players

def parse_results(text, aliases, names):
    alist = sorted(aliases.keys(), key=len, reverse=True)
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
        for a in alist:
            if nt.endswith(' ' + a):
                away = aliases[a]
                home = match_team(nt[:len(nt) - len(a)].strip(), aliases, alist, names)
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
    r'(/\* ===== AUTO:CURRENT:START.*?===== \*/\s*\nconst CURRENT_ALL = )(.*?)(;\s*\n/\* ===== AUTO:CURRENT:END ===== \*/)',
    re.S)

def scrape_league(lg, team_alias, roster, names):
    """Vrátí dict {teams, players, results} pro ligu, nebo None při nedostupnosti."""
    aliases, rn, nm = team_alias[lg], roster[lg], names[lg]
    text = fetch_pdf("tabulka", SOUTEZ[lg])
    if text is None:
        return None
    teams, players = parse_tabulka(text, aliases, rn, nm)
    if len(teams) == 0:
        print(f"  0 týmů — ligu {lg} přeskakuji (chráním poslední data).")
        return None
    rtext = fetch_pdf("rozpis", SOUTEZ[lg])
    results = parse_results(rtext, aliases, nm) if rtext is not None else None
    print(f"  liga {lg}: {len(teams)} týmů, {sum(len(v) for v in players.values())} hráčů, "
          f"{'—' if results is None else sum(len(v) for v in results.values())} zápasů")
    return {"teams": teams, "players": players, "results": results}

def main():
    team_alias, roster, names = build_maps()

    html = open(INDEX, encoding='utf-8').read()
    m = BLOCK.search(html)
    if not m:
        print("CHYBA: značky AUTO:CURRENT nenalezeny v index.html", file=sys.stderr)
        return 1
    try:
        old_all = json.loads(m.group(2))
    except Exception:
        old_all = {}

    new_all = dict(old_all)  # start z posledních dobrých dat
    changed = False
    for lg in SOUTEZ:
        print(f"--- {lg}. liga (soutěž {SOUTEZ[lg]}) ---")
        scraped = scrape_league(lg, team_alias, roster, names)
        if scraped is None:
            continue  # ponech stará data pro tuto ligu
        old = old_all.get(lg, {})
        # výsledky: při chybě stažení rozpisu ponech staré
        if scraped["results"] is None:
            scraped["results"] = old.get("results", {})
        same = (old.get("teams") == scraped["teams"]
                and old.get("players") == scraped["players"]
                and old.get("results") == scraped["results"])
        if same:
            print(f"  liga {lg}: beze změny.")
            continue
        scraped["updated"] = now_str()
        new_all[lg] = scraped
        changed = True
        print(f"  liga {lg}: AKTUALIZOVÁNO ({scraped['updated']}).")

    if not changed:
        print("Žádná liga se nezměnila — žádný zápis, žádný commit.")
        return 0

    # zachovej pořadí lig 1..7 a týmů podle čísla
    ordered = {}
    for lg in sorted(new_all, key=lambda x: int(x)):
        d = new_all[lg]
        d = {
            "updated": d.get("updated"),
            "teams": {k: d["teams"][k] for k in sorted(d.get("teams", {}), key=int)},
            "players": d.get("players", {}),
            "results": d.get("results", {}),
        }
        ordered[lg] = d

    new_json = json.dumps(ordered, ensure_ascii=False)
    out = html[:m.start(2)] + new_json + html[m.end(2):]
    open(INDEX, 'w', encoding='utf-8', newline='').write(out)
    print("Zapsáno CURRENT_ALL.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
