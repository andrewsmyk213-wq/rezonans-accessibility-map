import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import photos

class PhotoTests(unittest.TestCase):
    def setUp(self): photos.CACHE.clear()
    def test_wikidata_and_commons_attribution(self):
        entity={'entities':{'Q42':{'claims':{'P18':[{'mainsnak':{'datavalue':{'value':'Douglas Adams.jpg'}}}]}}}}
        image={'query':{'pages':{'1':{'imageinfo':[{'thumburl':'https://upload.wikimedia.org/example.jpg','descriptionurl':'https://commons.wikimedia.org/wiki/File:Example.jpg','extmetadata':{'LicenseShortName':{'value':'CC BY-SA 4.0'},'Artist':{'value':'<b>Author</b>'}}}]}}}}
        with patch('photos.request_json',side_effect=[entity,image]) as req:
            result=photos.resolve(wikidata='Q42')
            self.assertEqual(result['artist'],'Author');self.assertEqual(result['license'],'CC BY-SA 4.0')
            self.assertEqual(photos.resolve(wikidata='Q42'),result);self.assertEqual(req.call_count,2)
    def test_bad_reference_or_untrusted_media_rejected(self):
        with self.assertRaises(ValueError):photos.resolve(wikidata='https://evil.example')
        with self.assertRaises(ValueError):photos.resolve(filename='https://evil.example')
        data={'query':{'pages':{'1':{'imageinfo':[{'url':'https://evil.example/a.jpg','descriptionurl':'https://commons.wikimedia.org/wiki/File:A.jpg','extmetadata':{'LicenseShortName':{'value':'CC0'}}}]}}}}
        with patch('photos.request_json',return_value=data): self.assertIsNone(photos.resolve(filename='File:A.jpg'))
    def test_no_image(self):
        with patch('photos.request_json',return_value={'query':{'pages':{'-1':{'missing':''}}}}):self.assertIsNone(photos.resolve(filename='File:missing.jpg'))
if __name__=='__main__':unittest.main()
