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
  Protecție anti-halucinație: AI-ul are voie doar să SCURTEZE căutarea. Orice
  sugestie care conține cuvinte/coduri care nu apar în textul tău e respinsă și
  se caută cu textul original. Dacă termenul AI nu găsește nimic la un furnizor,
  se reîncearcă automat cu textul original. UI-ul arată ce s-a căutat efectiv.
  Configurare în .env: GEMINI_API_KEY, DEEPSEEK_API_KEY (fallback), opțional
  GEMINI_MODELS (listă separată prin virgulă, încercate în ordine când unul își
  termină cota; implicit gemini-3.5-flash-lite,gemini-3.1-flash-lite) și
  DEEPSEEK_MODEL (implicit deepseek-chat).

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
* Mondoplast (mondoplast.ro) — Răzuire activă (căutare POST). Se folosește prețul
  CU TVA (site-ul afișează implicit fără TVA).
* eMAG (emag.ro) — Link-only (blochează cererile automate cu HTTP 501 / timeout).
* URY Shop (ury.ro) — Link-only direct (site-ul folosește client-side rendering
  prin Algolia InstantSearch; produsele nu există în codul HTML de pe server).
* NOAA Concept (noaa.ro) — B2B (necesită login pentru prețuri, returnează link).
* ATU Tech (a2t.ro) — Răzuire prin API-ul de catalog al site-ului (prețuri, stoc).
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
