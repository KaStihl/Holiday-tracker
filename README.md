# Holiday tracker (Dovolenka tracker)

Flight-tracker štýl sledovania first minute / last minute dovoleniek na **leto 2027** (júl–august):
1 dospelý + 2 deti (10 a 12 r.), 7–14 nocí, **letecky z Bratislavy/Viedne** alebo **autom so 2 psami**,
budget ~3 000 €, preferované All Inclusive.

**Výsledok:** [`dovolenka.html`](dovolenka.html) – jeden súbor so všetkými dátami. Stiahnite ho
(*Download raw file*) a otvorte dvojklikom v prehliadači, funguje aj offline. Obnovuje sa 2× denne.

## Ako to funguje
- `scraper/` – Python (requests + BeautifulSoup). Každá cestovka má adaptér v `scraper/adapters/`.
  Kritériá sú v `scraper/config.py`. `run.py` filtruje, skóruje, deduplikuje a drží históriu cien.
- `site/` – zdroj stránky (HTML/CSS/JS). `scraper/build_html.py` z neho a z `site/data/offers.json`
  poskladá samostatný `dovolenka.html`.
- `.github/workflows/refresh.yml` – 2× denne (04:17 a 16:17 UTC): testy → scraping → commit dát →
  `dovolenka.html` → commit → e-mail s digestom.

## Zdroje
| Cestovka | Režim |
|---|---|
| Satur.sk | sťahované ponuky (letecky z BTS, autom vrátane „so psom“) |
| Čedok.sk | sťahované ponuky (letecky z BTS a VIE) |
| TIP travel | sťahované, keď zverejnia leto 2027 |
| Invia, Kartago, Fischer, Exim, Blue Style, Seneca, Koala, Firo | len odkazy (zákaz sťahovania / robots.txt / JavaScript) |

Ceny zo Satur, Čedok a TIP sú **orientačné** (cena za osobu pri 2 dospelých × 3) – vždy overte u cestovky. Výnimka: pri ~35 najlepších AI/UAI ponukách Čedoku tracker zisťuje z detailu ponuky **presnú cenu pre 1 dospelého + 2 deti** (odznak „presná cena 1+2“, v e-maile ✓, v dátach `price_exact: true` a pôvodný odhad v `price_approx`).

## E-maily
Po každom behu, keď pribudne nová AI ponuka do budgetu alebo niečo zlacnie o ≥ 50 €, workflow vytvorí
**GitHub issue** so štítkom `dovolenka` – GitHub ho pošle e-mailom vlastníkovi repozitára
(Watch → All activity, a e-mailové notifikácie zapnuté v GitHub Settings → Notifications).

Voliteľne aj priamy e-mail cez SMTP: v Settings → Secrets and variables → Actions pridajte
`MAIL_USERNAME` (napr. Gmail adresa), `MAIL_PASSWORD` (Gmail app password) a voliteľne `MAIL_TO`.
E-mail má `dovolenka.html` v prílohe.

Ručne: Actions → Refresh → Run workflow (zaškrtnite „Poslať kompletný prehľad“).

## Lokálne
```bash
pip install -r scraper/requirements.txt
python -m pytest -q scraper/tests
python scraper/run.py            # všetky zdroje
python scraper/build_html.py     # -> dovolenka.html, otvorte v prehliadači
```
