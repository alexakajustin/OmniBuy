import time, requests
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
found = False

for i in range(5):
    print(f"Attempt {i+1}...")
    r = s.get('https://ury.ro/cauta/?search=rj45', timeout=10)
    soup = BeautifulSoup(r.text, 'lxml')
    items = soup.select(".prds") or soup.select(".prds-content")
    if items:
        print(f"Found {len(items)} products!")
        found = True
        break
    time.sleep(0.5)

if not found:
    print("Never found products in HTML")
