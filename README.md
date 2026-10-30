# Holiday tracker (Dovolenka tracker)

Flight-tracker štýl sledovania first minute / last minute dovoleniek. Čo sa hľadá (osoby, vek detí, termín,
počet nocí, budget, strop ceny, letiská, auto/psy, strava, destinácie vrátane exotiky) je v
[`nastavenia.yml`](nastavenia.yml) – predvolene leto 2027 (júl–august), 1 dospelý + 2 deti (10 a 12 r.),
7–14 nocí, letecky z Bratislavy/Viedne alebo autom so 2 psami, budget ~3 000 €, strop 6 000 €, All Inclusive,
Európa + Egypt/Tunisko/Maroko + vzdialené destinácie (SAE, Omán, Maldivy, Thajsko, Mexiko, Dominikánska rep., …).

## Zmena nastavení (aj z mobilu)
1. Na github.com otvorte [`nastavenia.yml`](nastavenia.yml) → ceruzka ✏️ (Edit).
2. Zmeňte hodnoty (vysvetlivky sú priamo v súbore) → **Commit changes** do vetvy `main`.
3. Push spustí workflow **Refresh** (Actions) – o ~10–15 minút je nový `dovolenka.html`.
   Chybná hodnota (napr. zlý dátum) = červený beh s popisom chyby v kroku „Unit tests“/„Scrape“.
   Ručne sa dá beh spustiť aj cez Actions → Refresh → Run workflow (`workflow_dispatch`).

**Výsledok:** [`dovolenka.html`](dovolenka.html) – jeden súbor so všetkými dátami. Stiahnite ho
(*Download raw file*) a otvorte dvojklikom v prehliadači, funguje aj offline. Obnovuje sa 2× denne.

## Ako to funguje
- `scraper/` – Python (requests + BeautifulSoup). Každá cestovka má adaptér v `scraper/adapters/`.
  Kritériá sú v `nastavenia.yml` (načíta a overí ich `scraper/config.py`). `run.py` filtruje, skóruje, deduplikuje a drží históriu cien.
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
| Kartago Tours, Fischer | sťahované ponuky (JSON vyhľadávania, letecky z BTS a VIE, **presné ceny pre 1 dospelého + 2 deti**) |
| _Vzdialené destinácie_ | Kartago/Fischer: krajiny z `nastavenia.yml`, ktoré sú v predaji (ID destinácií z ich API); Čedok a Satur: 1 stránka na krajinu (najlacnejšie termíny) |
| Exim Tours | len odkaz – eximtours.sk presmerúva na kartago.sk (ponuky prichádzajú cez Kartago) |
| Invia, Blue Style, Seneca, Koala, Firo | len odkazy (zákaz sťahovania / robots.txt / JavaScript) |

Ceny zo Satur, Čedok a TIP sú **orientačné** (cena za osobu pri 2 dospelých × počet osôb z nastavení; v dátach
`price_note`) – vždy overte u cestovky. Kartago a Fischer počítajú cenu priamo pre zostavu z `nastavenia.yml`
(dospelí + deti s vekom), sú teda presné. Výnimka: pri ~30 najlepších ponukách Čedoku s preferovanou stravou tracker
zisťuje z detailu ponuky **presnú cenu pre nastavenú zostavu** (v e-maile ✓, v dátach `price_exact: true` a pôvodný
odhad v `price_approx`). Každá ponuka má aj `continent` (Európa, Afrika, Blízky východ, Ázia, Indický oceán,
Karibik a Amerika).

## Sledované hotely
`sledovane_hotely` v `nastavenia.yml` = zoznam názvov (stačí časť, bez ohľadu na diakritiku/veľkosť písmen; slová
hotel/resort/spa/& sa ignorujú – `scraper/watch.py`). Zhodné ponuky dostanú v dátach `watched: "<názov>"`, zostávajú aj
nad `price_cap` (do 2× stropu, `over_cap: true`, na stránke „nad strop“) a v akejkoľvek strave. Na stránke sú hore
v sekcii ⭐ Sledované hotely (najlacnejšia ponuka každého hotela v každej cestovke, alebo „zatiaľ bez ponuky“ s odkazmi),
filter „⭐ Len sledované hotely“ a ⭐ na kartách; týždenný e-mail ich má ako prvú sekciu so zmenou ceny od minulého.

Cielené dohľadanie (`watch(cfg, terms, hints)` v adaptéroch, ≤ 10 požiadaviek na cestovku a beh, robots.txt platí):
žiadna z cestoviek nemá názvové vyhľadávanie, ktoré robots.txt povoľuje (Satur `/ajax`, Čedok `/api` sú zakázané,
Kartago/Fischer API názov ignoruje). Preto sa číta celá ponuka **miesta/krajiny, kde bol hotel už videný**
(tento alebo minulý beh, ktorákoľvek cestovka): Satur – zoznam miesta `/dovolenka/<krajina>/<miesto>` (napr. Side,
Evrenseki), Čedok – všetky strany krajiny, Kartago/Fischer – všetky hotely krajiny bez filtra stravy. Hotel, ktorý ešte
nikde nebol videný, sa ukáže, keď sa objaví v bežne sťahovaných zoznamoch.

## E-maily
**Raz týždenne, v pondelok ráno** príde súhrn: top 10 ponúk All Inclusive do budgetu, nové ponuky a
zlacnenia o ≥ 50 € od minulého súhrnu. Workflow ho vytvorí ako **GitHub issue** so štítkom `dovolenka`
(starší sa zatvorí) – GitHub ho pošle e-mailom vlastníkovi repozitára
(Watch → All activity, a e-mailové notifikácie zapnuté v GitHub Settings → Notifications).

Voliteľne aj priamy e-mail cez SMTP: v Settings → Secrets and variables → Actions pridajte
`MAIL_USERNAME` (napr. Gmail adresa), `MAIL_PASSWORD` (Gmail app password) a voliteľne `MAIL_TO`.
E-mail má `dovolenka.html` v prílohe.

Ručne hneď: Actions → Refresh → Run workflow (zaškrtnite „Poslať týždenný prehľad hneď“).

## Lokálne
```bash
pip install -r scraper/requirements.txt
python -m pytest -q scraper/tests
python scraper/run.py            # všetky zdroje
python scraper/build_html.py     # -> dovolenka.html, otvorte v prehliadači
```
