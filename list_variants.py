import urllib.request
import re

for i in range(14):
    url = f"https://db.pokemongohub.net/pokemon/sitemap/{i}.xml"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    try:
        with urllib.request.urlopen(req) as response:
            data = response.read().decode('utf-8')
            links = re.findall(r'<loc>(.*?)</loc>', data)

            mewtwo_links = [l for l in links if '/pokemon/150' in l]
            if mewtwo_links:
                print(f"Found in {i}.xml:")
                for ml in mewtwo_links:
                    print(ml)

    except Exception as e:
        print(f"Error {i}:", e)
