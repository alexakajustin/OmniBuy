"""Detailed inspection of DIPOL, MBD, URY, NOAA."""
import requests
from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# --- DIPOL: product detail ---
print("="*60, "DIPOL")
r = requests.get('https://www.dipolnet.com/search?q=keystone', timeout=15, headers=headers)
soup = BeautifulSoup(r.text, 'lxml')
items = soup.select('div.product')
if items:
    print(f"Found {len(items)} products")
    print("First item HTML (500 chars):")
    print(str(items[0])[:500])
    print()

# --- MBD: page structure ---
print("="*60, "MBD")
r = requests.get('https://www.mbd.ro/?post_type=product&s=keystone', timeout=15, headers=headers)
soup = BeautifulSoup(r.text, 'lxml')
# Look for product data in the page
for sel in ['div.product', '.product-small', '.products', '.shop-product', '.woocommerce', 
            'ul.products', '.product-grid', 'main', '#main', '.content-area']:
    items = soup.select(sel)
    if items:
        print(f"MBD sel='{sel}' count={len(items)}")
        print("First (300 chars):", str(items[0])[:300])
        break
else:
    # Show body content areas
    main = soup.select_one('main, #main, .content, .site-main, #content')
    if main:
        print("MBD main content (500 chars):")
        print(main.get_text()[:500])

# --- URY: page structure ---
print("="*60, "URY")
r = requests.get('https://www.ury.ro/cauta/?search=keystone', timeout=15, headers=headers)
soup = BeautifulSoup(r.text, 'lxml')
for sel in ['div.product', '.product-small', 'li.product', '.product-thumb', '.product-layout',
            '.product-item', '.card-product', '.products-grid', '.search-results']:
    items = soup.select(sel)
    if items:
        print(f"URY sel='{sel}' count={len(items)}")
        print("First (400 chars):", str(items[0])[:400])
        break
else:
    main = soup.select_one('#content, main, .content, .site-content')
    if main:
        print("URY main text (500 chars):")
        print(main.get_text()[:500])

# --- NOAA ---
print("="*60, "NOAA")
r = requests.get('https://www.noaa.ro/cautare/cauta?q=keystone', timeout=15, headers=headers)
soup = BeautifulSoup(r.text, 'lxml')
for sel in ['div.product', '.product-small', 'li.product', '.product-thumb',
            '.product-layout', '.product-item', '[itemtype*=Product]', '.card',
            '.search-result', '.products', 'article']:
    items = soup.select(sel)
    if items:
        print(f"NOAA sel='{sel}' count={len(items)}")
        print("First (400 chars):", str(items[0])[:400])
        break
else:
    main = soup.select_one('#content, main, .content, body')
    if main:
        text = main.get_text(strip=True)
        print("NOAA body text (500 chars):", text[:500])

# --- Lanberg correct URL ---
print("="*60, "LANBERG")
for url in ['https://lanberg.pl/search?query=keystone', 'https://pl.lanberg.eu/search?query=keystone', 
            'https://lanberg.eu/search?query=keystone']:
    try:
        r = requests.get(url, timeout=10, headers=headers)
        print(f"Lanberg URL={url} status={r.status_code} final={r.url[:80]}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            for sel in ['div.product', '.product-item', 'li.product', '.card', 'article']:
                items = soup.select(sel)
                if items:
                    print(f"  sel='{sel}' count={len(items)}")
                    print("  First (300 chars):", str(items[0])[:300])
                    break
    except Exception as e:
        print(f"Lanberg {url} ERROR: {e}")

# --- Mondoplast POST ---
print("="*60, "MONDOPLAST")
r = requests.post('https://www.mondoplast.ro/search.php', data={'tosearch': 'keystone'}, timeout=15, headers=headers)
soup = BeautifulSoup(r.text, 'lxml')
print(f"Mondoplast status={r.status_code} final_url={r.url}")
for sel in ['div.product', '.product-item', 'table tr', '.prodBox', 'a[href*="/p/"]',
            '.produse', '.mainarea a', 'div.mainarea']:
    items = soup.select(sel)
    if items:
        print(f"Mondo sel='{sel}' count={len(items)}")
        if sel == 'div.mainarea':
            print("Mainarea text (800 chars):", items[0].get_text()[:800])
        else:
            print("First (400 chars):", str(items[0])[:400])
        break
