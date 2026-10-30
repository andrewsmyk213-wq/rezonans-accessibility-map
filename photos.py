"""Resolve OSM Wikimedia references through Wikimedia APIs, never arbitrary URLs."""
import html
import json
import math
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

def resolve(filename='', wikidata='', name='', lat=None, lon=None):
    filename = filename.strip().replace('_', ' ')
    if filename and (len(filename) > 220 or not filename.startswith('File:') or any(c in filename for c in '\n\r\x00')):
        raise ValueError('Invalid Commons title')
    if wikidata and not re.fullmatch(r'Q[1-9][0-9]{0,12}', wikidata):
        raise ValueError('Invalid Wikidata ID')
    key = (filename, wikidata, name, lat, lon)
    now = time.monotonic()
    if key in CACHE and now - CACHE[key][0] < 14400:
        return CACHE[key][1]
    if not filename and wikidata:
        if not isinstance(name, str) or not name.strip() or len(name) > 200 or type(lat) not in (int, float) or type(lon) not in (int, float) or not math.isfinite(lat) or not math.isfinite(lon):
            return None
        entity = request_json('https://www.wikidata.org/wiki/Special:EntityData/' + wikidata + '.json')
        item = entity.get('entities', {}).get(wikidata, {})
        labels = [v.get('value', '') for v in item.get('labels', {}).values() if isinstance(v, dict)]
        tokens = set(re.findall(r'[^\W_]+', name.casefold()))
        tokens = {x for x in tokens if len(x) >= 4}
        names_match = bool(tokens) and any(len(tokens & set(re.findall(r'[^\W_]+', label.casefold()))) >= min(2, len(tokens)) for label in labels)
        coords = item.get('claims', {}).get('P625', [])
        point = (coords[0].get('mainsnak', {}).get('datavalue', {}).get('value', {}) if coords else {})
        try:
            distance = math.hypot((float(point['latitude']) - lat) * 111_000, (float(point['longitude']) - lon) * 74_000)
        except (KeyError, TypeError, ValueError):
            return None
        if not names_match or not math.isfinite(distance) or distance > 150:
            return None
        claims = item.get('claims', {}).get('P18', [])
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
            if u.scheme == 'https' and u.hostname in ('upload.wikimedia.org', 'thumb.wikimedia.org') and src.scheme == 'https' and src.hostname == 'commons.wikimedia.org' and license_name:
                license_url = str(meta.get('LicenseUrl', {}).get('value') or '')
                lu = urllib.parse.urlsplit(license_url)
                if lu.scheme != 'https' or lu.hostname not in ('creativecommons.org', 'www.creativecommons.org'):
                    license_url = source
                result = {'url':img, 'source_url':source, 'license':license_name, 'license_url':license_url, 'artist':artist or 'Автор не вказаний'}
                break
    if len(CACHE) >= 500: CACHE.clear()
    CACHE[key] = (now, result)
    return result
