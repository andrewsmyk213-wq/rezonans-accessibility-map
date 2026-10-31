import unittest
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import coverage_audit
class CoverageTests(unittest.TestCase):
    def test_source_coverage_is_not_inflated(self):
        r=coverage_audit.coverage()
        self.assertEqual(r['total_places'],157)
        self.assertEqual(r['known_attributes']['wheelchair'],157)
        self.assertEqual(r['known_attributes']['entrance'],0)
        self.assertEqual(r['known_attributes']['ramp'],0)
        self.assertEqual(r['physical_observation_dates'],{'unknown':157})
        self.assertEqual(r['places_with_curated_photos'],5)
        self.assertEqual(r['curated_photo_assets'],6)
if __name__=='__main__':unittest.main()
