#!/usr/bin/env python3
"""
PoC: ověří, jestli z prostředí (GitHub Action) dosáhneme na pinec.info,
stáhne PDF export tabulky, naparsuje pořadí + V/R/P a vypíše do logu.
Zatím NIC nemění v index.html — jen dokazuje, že pipeline funguje.
"""
import subprocess, re, os

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def fetch_pdf(soutez, outpdf):
    cj = f"cj_{soutez}.txt"
    # 1) navštívíme hlavní stránku ligy -> získáme session cookie
    sh(f'curl -s -m 40 -A "Mozilla/5.0" -c {cj} '
       f'"https://www.pinec.info/htm/tabulka/?soutez={soutez}" -o /dev/null')
    # 2) s toutéž session stáhneme PDF export (parametr soutez tam funguje spolehlivě)
    r = sh(f'curl -s -m 60 -A "Mozilla/5.0" -w "%{{http_code}}" -b {cj} '
           f'-e "https://www.pinec.info/htm/tabulka/?soutez={soutez}" '
           f'"https://www.pinec.info/pdf/tabulka/?soutez={soutez}&order=" -o {outpdf}')
    return r.stdout.strip()

def pdftext(pdf):
    return sh(f'pdftotext -layout "{pdf}" -').stdout

# řádek tabulky: "1. BBB A 18 18 0 0 0 143:37 72"  (poz. tým U V R P K skóre body)
# POZOR: PDF má 2 sloupce a pdftotext -layout je slepí na jeden řádek, takže za
# body může být další text (výsledky kol) -> nekotvíme konec řádku ($), jen body.
STAND = re.compile(r'^\s*(\d+)\.\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+\d+\s*:\s*\d+\s+(\d+)(?:\s|$)')

def parse(text):
    out = []
    for line in text.splitlines():
        m = STAND.match(line)
        if m:
            pos, team, U, V, R, P, body = m.groups()
            out.append((int(pos), team.strip(), int(V), int(R), int(P), int(body)))
    return out

def main():
    targets = [
        ("8333", "6. liga smíšená 2026/27 (aktuální – ověření dosažitelnosti)"),
        ("8271", "6. liga muži, loňská (ověření parsování na reálných datech)"),
    ]
    ok = True
    for soutez, label in targets:
        pdf = f"tab_{soutez}.pdf"
        code = fetch_pdf(soutez, pdf)
        size = os.path.getsize(pdf) if os.path.exists(pdf) else 0
        print(f"\n=== soutěž {soutez} — {label} ===")
        print(f"    HTTP {code or '(žádná odpověď)'}, PDF {size} B")
        if size < 1500:
            print("    ⚠️  malý/žádný PDF — buď na pinec nedosáhneme (blokace), "
                  "nebo je soutěž ještě prázdná (sezóna nezačala).")
            continue
        teams = parse(pdftext(pdf))
        print(f"    naparsováno týmů: {len(teams)}")
        for pos, team, v, r, p, body in teams:
            print(f"     {pos:>2}. {team:<26} {v}-{r}-{p}   ({body} b)")
        if soutez == "8271" and len(teams) != 10:
            ok = False
    print("\n--- Shrnutí ---")
    print("Pokud výše vidíš u 8271 naparsovaných 10 týmů se správnými čísly,")
    print("znamená to, že GitHub na pinec DOSÁHNE a parsování funguje → můžeme")
    print("postavit plnou verzi, která data zapíše do index.html.")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
