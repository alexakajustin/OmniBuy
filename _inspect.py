import requests
from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
headers = {'User-Agent': 'Mozilla/5.0'}

# Mondoplast
print('--- Mondoplast ---')
r = requests.get('https://www.mondoplast.ro/search-keystone', headers=headers)
soup = BeautifulSoup(r.text, 'lxml')
items = soup.select('table tr')
for item in items:
    a = item.select_one('a[href*="/p/"]')
    if a:
        print(item.get_text(separator=' | ', strip=True))
        print('HTML:', str(item)[:300])
        break

# Lanberg
print('--- Lanberg ---')
r = requests.get('https://lanberg.eu/search?query=keystone', headers=headers)
soup = BeautifulSoup(r.text, 'lxml')
items = soup.select('.product-list__item')
if items:
    print(items[0].get_text(separator=' | ', strip=True))

# DIPOL
print('--- DIPOL ---')
r = requests.get('https://www.dipolnet.com/search?q=keystone', headers=headers)
soup = BeautifulSoup(r.text, 'lxml')
items = soup.select('div.product')
if items:
    print(items[0].get_text(separator=' | ', strip=True))
