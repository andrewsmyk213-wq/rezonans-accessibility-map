"""Resolve OSM Wikimedia references through Wikimedia APIs, never arbitrary URLs."""
import html
import json
import re
import time
import urllib.parse
import urllib.request

CACHE = {}
UA = 'Rezonans-Chernivtsi/2.4 (accessibility city map; contact: https://github.com/andrewsmyk213-wq/rezonans-accessibility-map)'

def request_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=7) as response:
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError('Media response too large')
    return json.loads(data)

def clean(value):
    return html.unescape(re.sub(r'<[^>]*>', '', str(value or ''))).strip()[:300]

def resolve(filename='', wikidata=''):
    filename = filename.strip().replace('_', ' ')
    if filename and (len(filename) > 220 or not filename.startswith('File:') or any(c in filename for c in '\n\r\x00')):
        raise ValueError('Invalid Commons title')
    if wikidata and not re.fullmatch(r'Q[1-9][0-9]{0,12}', wikidata):
        raise ValueError('Invalid Wikidata ID')
    key = (filename, wikidata)
    now = time.monotonic()
    if key in CACHE and now - CACHE[key][0] < 14400:
        return CACHE[key][1]
    if not filename and wikidata:
        entity = request_json('https://www.wikidata.org/wiki/Special:EntityData/' + wikidata + '.json')
        claims = entity.get('entities', {}).get(wikidata, {}).get('claims', {}).get('P18', [])
        if claims:
            name = claims[0].get('mainsnak', {}).get('datavalue', {}).get('value')
            if isinstance(name, str) and len(name) <= 200 and not any(c in name for c in '\n\r\x00'):
                filename = 'File:' + name
    result = None
    if filename:
        query = urllib.parse.urlencode({'action':'query','format':'json','prop':'imageinfo','iiprop':'url|extmetadata','iiurlwidth':'800','titles':filename})
        payload = request_json('https://commons.wikimedia.org/w/api.php?' + query)
        pages = payload.get('query', {}).get('pages', {})
        for page in pages.values():
            info = (page.get('imageinfo') or [{}])[0]
            img = info.get('thumburl') or info.get('url') or ''
            source = info.get('descriptionurl') or ''
            u, src = urllib.parse.urlsplit(img), urllib.parse.urlsplit(source)
            meta = info.get('extmetadata') or {}
            license_name = clean(meta.get('LicenseShortName', {}).get('value'))
            artist = clean(meta.get('Artist', {}).get('value'))
            if u.scheme == 'https' and u.hostname == 'upload.wikimedia.org' and src.scheme == 'https' and src.hostname == 'commons.wikimedia.org' and license_name:
                result = {'url':img, 'source_url':source, 'license':license_name, 'artist':artist or 'Автор не вказаний'}
                break
    if len(CACHE) >= 500: CACHE.clear()
    CACHE[key] = (now, result)
    return result
