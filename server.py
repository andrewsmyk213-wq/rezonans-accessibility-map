#!/usr/bin/env python3
"""Public beta HTTP server for Rezonans.

Whitelisted static files only. Route proxy remains optional. Community reports are
DISABLED unless a persistent storage directory is explicitly configured.
This is a pilot service, not a completed production platform.
"""
import argparse
from collections import defaultdict, deque
import datetime as dt
import json
import math
import os
import pathlib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import osm
import photos

ROOT = pathlib.Path(__file__).resolve().parent
API_KEY = os.environ.get('ORS_API_KEY', '').strip()
STORAGE_DIR = os.environ.get('REPORTS_STORAGE_DIR', '').strip()
PENDING = pathlib.Path(STORAGE_DIR) / 'reports_pending.jsonl' if STORAGE_DIR else None
PUBLIC = {
    '/', '/index.html', '/app.js', '/styles.css', '/sw.js',
    '/manifest.webmanifest', '/assets/favicon.svg',
    '/assets/app-icon-192.png', '/assets/app-icon-512.png',
    '/data/places.geojson', '/data/sync_status.json', '/data/osm_snapshot.geojson', '/data/place_photos.json',
    '/assets/place_photos/chernivtsi-station.jpg', '/assets/place_photos/chernivtsi-station-entrance.jpg', '/assets/place_photos/celan-monument.jpg', '/assets/place_photos/hakman-monument.jpg', '/assets/place_photos/franz-monument.jpg', '/assets/place_photos/trade-institute.jpg',
}
LOCK = threading.Lock()
LIMITS = defaultdict(deque)


def classify_route_error(exc):
    """Classify bounded upstream errors without returning or logging their body."""
    try:
        raw = exc.read(8193)
        if len(raw) > 8192:
            raw = b''
        detail = json.loads(raw) if raw else {}
        error = detail.get('error', '') if isinstance(detail, dict) else ''
        if isinstance(error, dict):
            error = error.get('message', '')
        message = error.casefold() if isinstance(error, str) else ''
    except (OSError, ValueError, TypeError):
        message = ''
    if exc.code in (403, 429) and any(term in message for term in ('quota', 'rate limit', 'too many requests', 'request limit', 'daily limit')):
        return 'quota', 'Ліміт запитів OpenRouteService вичерпано. Перевірте квоту та спробуйте пізніше.'
    if exc.code == 429:
        return 'rate_limit', 'Забагато запитів до OpenRouteService. Спробуйте пізніше.'
    if exc.code == 401:
        return 'authentication', 'OpenRouteService не прийняв облікові дані. Перевірте серверний ключ.'
    if exc.code == 403:
        return 'access_denied', 'OpenRouteService відмовив у доступі. Перевірте ключ, дозволи та денну квоту.'
    if exc.code == 404:
        return 'endpoint', 'Маршрутний endpoint або профіль OpenRouteService недоступний. Перевірте конфігурацію сервера.'
    if exc.code in (400, 413, 422):
        return 'request_rejected', 'OpenRouteService відхилив запит або обмеження маршруту. Спробуйте інші точки.'
    return 'upstream_error', 'Маршрутний сервіс тимчасово недоступний. Спробуйте пізніше.'


def admitted(category, ip, max_per_minute):
    now = time.monotonic()
    key = (category, ip)
    with LOCK:
        samples = LIMITS[key]
        while samples and samples[0] < now - 60:
            samples.popleft()
        if len(samples) >= max_per_minute:
            return False
        samples.append(now)
        # Avoid unbounded key growth on long running servers.
        if len(LIMITS) > 5000:
            for k, v in list(LIMITS.items()):
                if not v or v[-1] < now-60:
                    del LIMITS[k]
        return True


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Permissions-Policy', 'camera=(), microphone=()')
        super().end_headers()

    def json_reply(self, code, obj):
        value = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(value)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(value)

    def route_path(self):
        return urllib.parse.urlsplit(self.path).path

    def do_GET(self):
        p = self.route_path()
        if p == '/api/health':
            return self.json_reply(200, {
                'service': 'rezonans',
                'status': 'ok',
                'route_configured': bool(API_KEY),
                'reports_enabled': bool(PENDING),
            })
        if p == '/api/photo':
            if not admitted('photo', self.client_address[0], 30):
                return self.json_reply(429, {'error': 'Забагато запитів'})
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            try:
                name = params.get('name', [''])[0]
                lat = float(params['lat'][0]) if 'lat' in params else None
                lon = float(params['lon'][0]) if 'lon' in params else None
                result = photos.resolve(params.get('file', [''])[0], params.get('wikidata', [''])[0], name, lat, lon)
                return self.json_reply(200, {'photo': result})
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError, KeyError, AttributeError):
                return self.json_reply(200, {'photo': None})
        if p == '/api/osm':
            if not admitted('osm', self.client_address[0], 20):
                return self.json_reply(429, {'error': 'Забагато запитів. Спробуйте пізніше.'})
            try:
                return self.json_reply(200, osm.get_osm())
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
                return self.json_reply(502, {'error': 'OpenStreetMap тимчасово недоступний. Спробуйте ще раз пізніше.'})
        if p not in PUBLIC:
            return self.send_error(404, 'Not found')
        return super().do_GET()

    def do_HEAD(self):
        if self.route_path() not in PUBLIC:
            return self.send_error(404, 'Not found')
        return super().do_HEAD()

    def read_body(self):
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            return None
        if not 0 < size <= 4096 or 'application/json' not in self.headers.get('Content-Type', ''):
            return None
        try:
            return json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            return None

    def do_POST(self):
        p = self.route_path()
        if p not in ('/api/route', '/api/reports'):
            return self.json_reply(404, {'error': 'Endpoint не знайдено'})
        if not admitted(p, self.client_address[0], 10 if p == '/api/route' else 4):
            return self.json_reply(429, {'error': 'Забагато запитів. Спробуйте пізніше.'})
        if p == '/api/reports' and not PENDING:
            return self.json_reply(503, {'error': 'Приймання повідомлень поки вимкнене: постійне сховище ще не налаштовано.'})
        if p == '/api/route' and not API_KEY:
            return self.json_reply(503, {'error': 'Маршрутизатор не налаштовано: потрібен серверний ORS_API_KEY'})
        body = self.read_body()
        if not isinstance(body, dict):
            return self.json_reply(400, {'error': 'Некоректний JSON або надто великий запит'})
        if p == '/api/reports':
            if not all(isinstance(body.get(k), str) for k in ('place_id', 'type', 'description')):
                return self.json_reply(400, {'error': 'Необхідно вказати об’єкт, тип і опис'})
            description = body['description'].strip()
            if not (10 <= len(description) <= 600) or body['type'] not in ('steps', 'ramp', 'entrance', 'surface', 'other'):
                return self.json_reply(400, {'error': 'Некоректний опис або тип повідомлення'})
            try:
                lat, lon = float(body.get('lat')), float(body.get('lon'))
                if not (math.isfinite(lat) and math.isfinite(lon)):
                    raise ValueError()
            except (TypeError, ValueError):
                return self.json_reply(400, {'error': 'Координати відсутні'})
            if not (48.21 <= lat <= 48.40 and 25.78 <= lon <= 26.07):
                return self.json_reply(400, {'error': 'Точка поза робочою зоною'})
            record = {
                'received_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'status': 'pending',
                'place_id': body['place_id'][:180],
                'place_name': str(body.get('place_name', ''))[:180],
                'type': body['type'], 'description': description,
                'lat': lat, 'lon': lon,
            }
            try:
                PENDING.parent.mkdir(parents=True, exist_ok=True)
                with LOCK:
                    with PENDING.open('a', encoding='utf-8') as file:
                        file.write(json.dumps(record, ensure_ascii=False) + '\n')
            except OSError:
                return self.json_reply(503, {'error': 'Сховище тимчасово недоступне. Повідомлення не збережене.'})
            return self.json_reply(201, {'status': 'pending', 'message': 'Збережено на перевірку'})
        if body.get('profile') != 'wheelchair' or not all(isinstance(body.get(k), list) for k in ('start', 'end')):
            return self.json_reply(400, {'error': 'Некоректний профіль або точки маршруту'})
        if type(body.get('avoid_steps', False)) is not bool:
            return self.json_reply(400, {'error': 'Некоректний параметр уникнення сходів'})
        try:
            coords = [[float(x) for x in body[k]] for k in ('start', 'end')]
            if any(len(v) != 2 or not all(math.isfinite(x) for x in v) or not 25.7 <= v[0] <= 26.2 or not 48.15 <= v[1] <= 48.45 for v in coords):
                raise ValueError()
        except (TypeError, ValueError):
            return self.json_reply(400, {'error': 'Некоректні координати'})
        route_request = {'coordinates': coords}
        if body.get('avoid_steps', False):
            route_request['options'] = {'avoid_features': ['steps']}
        req = urllib.request.Request(
            'https://api.heigit.org/openrouteservice/v2/directions/wheelchair/geojson',
            data=json.dumps(route_request).encode('utf-8'),
            headers={'Authorization': API_KEY, 'Content-Type': 'application/json',
                     'Accept': 'application/json', 'User-Agent': 'Rezonans-Pilot/2.1'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=18) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('Відповідь маршрутизатора завелика')
            payload = json.loads(raw)
            features = payload.get('features') or []
            if not features:
                raise ValueError('Маршрут не знайдено')
            item = features[0]
            summary = item.get('properties', {}).get('summary', {})
            geometry = item['geometry']
            points = geometry.get('coordinates') if geometry.get('type') == 'LineString' else None
            if not isinstance(points, list) or len(points) < 2 or any(not isinstance(point, list) or len(point) < 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point[:2]) or not (25.7 <= point[0] <= 26.2 and 48.15 <= point[1] <= 48.45) for point in points):
                raise ValueError('Некоректна геометрія маршруту')
            if any(type(summary.get(k)) not in (int, float) or not math.isfinite(summary[k]) or summary[k] < 0 for k in ('distance', 'duration')):
                raise ValueError('Некоректні дані маршруту')
            return self.json_reply(200, {
                'geometry': geometry,
                'distance_m': summary.get('distance'),
                'duration_s': summary.get('duration'),
                'verified_accessibility': False,
                'source': 'OpenRouteService wheelchair profile',
            })
        except urllib.error.HTTPError as ex:
            category, message = classify_route_error(ex)
            return self.json_reply(502, {'error': message, 'code': category, 'upstream_status': ex.code})
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError, TypeError, AttributeError):
            return self.json_reply(502, {'error': 'Не вдалося отримати маршрут від зовнішнього сервісу'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8080')))
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    print(f'Rezonans running on {args.host}:{args.port}', flush=True)
    print('Routing enabled:', bool(API_KEY), '| Persistent reports enabled:', bool(PENDING), flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
