import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import osm
import server


class OSMTests(unittest.TestCase):
    def setUp(self):
        osm._cached = None
        osm._cached_at = 0

    def test_normalization_preserves_source_and_skips_invalid(self):
        payload = {'elements': [
            {'type': 'node', 'id': 12, 'lat': 48.29, 'lon': 25.94, 'tags': {'name': 'Тест', 'wheelchair': 'limited', 'addr:street': 'Тестова'}},
            {'type': 'way', 'id': 13, 'center': {'lat': 48.3, 'lon': 25.95}, 'tags': {'name': 'Інший тест', 'ramp': 'yes'}},
            {'type': 'node', 'id': 14, 'lat': 48.29, 'lon': 25.94, 'tags': {'wheelchair': 'yes'}},
            {'type': 'node', 'id': 15, 'lat': 50, 'lon': 25.94, 'tags': {'name': 'Поза межами', 'wheelchair': 'yes'}},
            {'type': 'node', 'id': 16, 'lat': 48.29, 'lon': 25.94, 'tags': {'name': 'Без тегів'}},
        ]}
        doc = osm.normalize(payload)
        self.assertEqual(len(doc['features']), 2)
        place = doc['features'][0]
        self.assertEqual(place['geometry']['coordinates'], [25.94, 48.29])
        self.assertEqual(place['properties']['source_url'], 'https://www.openstreetmap.org/node/12')
        self.assertEqual(place['properties']['raw_properties']['wheelchair'], 'limited')
        self.assertEqual(place['properties']['raw_properties']['addr:street'], 'Тестова')
        self.assertEqual(osm.normalize({'elements': []})['features'], [])
        with self.assertRaises(ValueError): osm.normalize({})

    def test_successful_cache_and_size_limit(self):
        class Response(io.BytesIO):
            pass
        with patch('osm.urllib.request.urlopen', return_value=Response(b'{"elements":[]}')) as upstream:
            self.assertEqual(osm.get_osm(), osm.get_osm())
            self.assertEqual(upstream.call_count, 1)
        osm._cached = None
        with patch('osm.MAX_BYTES', 2), patch('osm.urllib.request.urlopen', return_value=Response(b'123')):
            with self.assertRaises(ValueError): osm.get_osm()

    def test_api_health_osm_and_upstream_error(self):
        http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:%d' % http.server_port
        try:
            self.assertEqual(json.load(urlopen(base + '/api/health'))['status'], 'ok')
            with patch('osm.get_osm', return_value={'type': 'FeatureCollection', 'features': []}):
                self.assertEqual(json.load(urlopen(base + '/api/osm'))['features'], [])
            with patch('osm.get_osm', side_effect=URLError('offline')):
                with self.assertRaises(HTTPError) as err: urlopen(base + '/api/osm')
                self.assertEqual(err.exception.code, 502)
            with self.assertRaises(HTTPError) as err: urlopen(base + '/osm.py')
            self.assertEqual(err.exception.code, 404)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

if __name__ == '__main__': unittest.main()
