================================================================================
BESTBUYTOOL — PRICE SCRAPER ENGINE & COMPARATOR
================================================================================

BestBuyTool este un motor avansat de căutare, comparare și agregare de prețuri
dezvoltat special pentru achiziții și procurement B2B/B2C din România și Polonia.
Acesta interoghează simultan multiple site-uri de furnizori (atât din România,
cât și din Polonia), normalizează prețurile în RON, aplică filtre inteligente
de relevanță și afișează ofertele sortate crescător după preț.

--------------------------------------------------------------------------------
1. CARACTERISTICI PRINCIPALE
--------------------------------------------------------------------------------

* CĂUTARE CONCURENTĂ ÎN TIMP REAL:
  Aplicația rulează căutările în paralel pe toți furnizorii selectați folosind
  un ThreadPoolExecutor. Acest lucru reduce timpul de așteptare la cel mai mic
  numitor comun (de obicei, sub 2-3 secunde).

* DETECȚIE AUTOMATĂ "BEST BUY":
  Identifică cel mai ieftin produs din listă care are un preț valid (> 0) și
  îl afișează evidențiat într-un banner special ("Cel Mai Bun Preț").

* CONVERSIE VALUTARĂ AUTOMATĂ:
  Actualizează automat cursurile de schimb valutar pentru EUR și PLN prin API-ul
  oficial al Băncii Naționale (sau fallback intern) și convertește toate prețurile
  in RON pentru o comparare directă. Prețul în moneda originală este păstrat și
  afișat sub formă de text secundar.

* INTEGRARE INTELIGENTĂ AI (GEMINI):
  Include un mod opțional de "AI Fine-Tuning" care folosește LLM (Gemini) pentru
  optimizarea termenilor de căutare introduși de utilizator (de exemplu, extrage
  coduri de produs/SKU din interogări complexe pentru a nu genera 0 rezultate).

* CONTROL AGRESIVITATE SCRAPING (WEB SCRAPING vs. LINK-ONLY):
  - Web Scraping Activ (Bifat): Răzuiește paginile magazinelor pentru a extrage
    produse, prețuri și stocuri.
  - Web Scraping Dezactivat (Debifat): Generază instantaneu link-uri de căutare
    directe sortate pentru fiecare magazin (fără a trimite zeci de cereri web,
    evitând blocarea IP-ului și economisind trafic).

* COLECTARE HYBRID (FALLBACK AUTOMAT):
  Dacă un magazin protejat prin Cloudflare/firewall sau un magazin tip B2B (care
  necesită login pentru afișarea prețurilor) returnează 0 rezultate la scraping,
  aplicația nu îl lasă gol, ci returnează automat un link direct către căutarea
  pe site-ul respectiv pentru a permite utilizatorului să verifice manual.

* FILTRU DE RELEVANȚĂ INTELIGENT:
  Filtrează produsele parazite (de exemplu, accesorii ieftine sau produse
  recomandate de motorul de căutare al magazinului care nu au legătură cu termenul
  căutat). Filtrul este adaptiv: dacă este prea agresiv, se dezactivează automat.

* FILTRARE DUPĂ ȚARĂ ȘI INTERVAL DE PREȚ:
  Permite selectarea rapidă a magazinelor după țară (România/Polonia) și filtrarea
  rezultatelor pe un interval de preț definit de utilizator (preț minim / maxim).

* EXPORT ÎN FORMAT EXCEL (CSV):
  Permite descărcarea tuturor rezultatelor agregate într-un fișier CSV compatibil
  cu Excel printr-un singur click.

--------------------------------------------------------------------------------
2. COMPORTAMENTUL FURNIZORILOR (SITE-URI INTEGRATE)
--------------------------------------------------------------------------------

Aplicația folosește strategii diferite în funcție de tipul fiecărui site:

* Conectica (conectica.ro) — Răzuire activă completă (prețuri, stocuri, link-uri).
* DIPOL (dipolnet.com) — Răzuire activă completă.
* Mondoplast (mondoplast.ro) — Răzuire activă (folosește căutare de tip POST).
* eMAG (emag.ro) — Răzuire activă completă.
* URY Shop (ury.ro) — Link-only direct (site-ul folosește client-side rendering
  prin Algolia InstantSearch; produsele nu există în codul HTML de pe server).
* NOAA Concept (noaa.ro) — B2B (necesită login pentru prețuri, returnează link).
* ATU Tech (a2t.ro) — Link-only direct (API-ul lor intern de căutare este protejat).
* Lanberg (pl.lanberg.eu) — Link-only direct (site de producător, nu afișează prețuri).

--------------------------------------------------------------------------------
3. MOD DE PORNIRE ȘI UTILIZARE
--------------------------------------------------------------------------------

1. Instalează dependențele din consolă:
   pip install fastapi uvicorn curl_cffi beautifulsoup4 lxml requests

2. Pornește aplicația:
   python main.py web

3. Deschide browser-ul la adresa:
   http://127.0.0.1:8000
================================================================================
