import json
from pathlib import Path
import unittest
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import server

class CuratedPhotosTests(unittest.TestCase):
    def test_every_curated_image_has_exact_place_and_public_file(self):
        doc=json.loads((root/'data/place_photos.json').read_text())
        places=json.loads((root/'data/osm_snapshot.geojson').read_text())['features']
        ids={f["properties"]["source_id"]+':'+f["properties"]["source_record_id"] for f in places}
        self.assertGreaterEqual(len(doc),5)
        for place,photos in doc.items():
            self.assertIn(place,ids)
            for photo in photos:
                self.assertIn(photo['url'],server.PUBLIC)
                self.assertTrue((root/photo['url'].lstrip('/')).read_bytes().startswith(b'\xff\xd8'))
                self.assertTrue(photo['source_url'].startswith('https://commons.wikimedia.org/'))
                self.assertTrue(photo['license_url'].startswith('https://creativecommons.org/'))
                self.assertTrue(photo['artist'] and photo['license'] and photo['label'])

if __name__=='__main__': unittest.main()
