"""Bounded Overpass access and conversion; OSM tags are not field verification."""
import datetime
import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

URLS = ('https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter', 'https://overpass.nchc.org.tw/api/interpreter')
BOUNDS = (48.253, 25.860, 48.331, 26.012)
QUERY = '[out:json][timeout:20];(nwr["name"]["wheelchair"](48.253,25.860,48.331,26.012);nwr["name"]["ramp"](48.253,25.860,48.331,26.012);nwr["name"]["amenity"~"^(pharmacy|hospital|clinic|doctors|dentist|townhall|post_office|police|community_centre|social_facility|library|school|university|college|cafe|restaurant|fast_food|food_court|pub|bar|bank|atm|cinema|theatre|toilets)$"](48.253,25.860,48.331,26.012);nwr["name"]["shop"](48.253,25.860,48.331,26.012);nwr["name"]["office"](48.253,25.860,48.331,26.012);nwr["name"]["tourism"~"^(hotel|hostel|guest_house|museum|attraction)$"](48.253,25.860,48.331,26.012);nwr["name"]["leisure"~"^(park|playground|garden|sports_centre)$"](48.253,25.860,48.331,26.012);nwr["name"]["public_transport"="platform"](48.253,25.860,48.331,26.012);nwr["name"]["highway"="bus_stop"](48.253,25.860,48.331,26.012););out center tags;'
MAX_BYTES = 4_000_000
TTL = 4 * 60 * 60
_lock = threading.Lock()
_cached = None
_cached_at = 0.0


def normalize(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('elements'), list):
        raise ValueError('Invalid Overpass response')
    features = []
    for item in payload['elements']:
        if not isinstance(item, dict):
            continue
        tags = item.get('tags')
        if not isinstance(tags, dict):
            continue
        name = tags.get('name:uk') or tags.get('name')
        kind, identifier = item.get('type'), item.get('id')
        point = item.get('center') if kind != 'node' else item
        if not isinstance(name, str) or not name.strip() or kind not in ('node', 'way', 'relation') or type(identifier) is not int or identifier <= 0 or not isinstance(point, dict):
            continue
        lat, lon = point.get('lat'), point.get('lon')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (lat, lon)):
            continue
        south, west, north, east = BOUNDS
        if not (south <= lat <= north and west <= lon <= east):
            continue
        features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                         'properties': {'name': name.strip(), 'source_id': 'openstreetmap',
                                        'source_record_id': f'{kind}/{identifier}',
                                        'source_url': f'https://www.openstreetmap.org/{kind}/{identifier}',
                                        'raw_properties': tags}})
    return {'type': 'FeatureCollection', 'features': features,
            'metadata': {'source': 'OpenStreetMap', 'license': 'ODbL',
                         'source_updated_at': (payload.get('osm3s') or {}).get('timestamp_osm_base'),
                         'downloaded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         'verification': 'OSM contributor tags; not independently verified',
                         'bbox': list(BOUNDS)}}


def get_osm():
    global _cached, _cached_at
    with _lock:
        if _cached is not None and time.monotonic() - _cached_at < TTL:
            return _cached
        data = urllib.parse.urlencode({'data': QUERY}).encode('utf-8')
        last_error = None
        for url in URLS:
            try:
                request = urllib.request.Request(url, data=data, headers={'User-Agent': 'Rezonans/2.3 (Chernivtsi accessibility map)', 'Accept': 'application/json'})
                with urllib.request.urlopen(request, timeout=12) as response:
                    raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError('Overpass response too large')
                result = normalize(json.loads(raw))
                if not result['features']:
                    raise ValueError('Overpass returned no places')
                _cached, _cached_at = result, time.monotonic()
                return result
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError) as exc:
                last_error = exc
        raise ValueError('Overpass unavailable') from last_error
