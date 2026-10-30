import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import photos

class PhotoTests(unittest.TestCase):
    def setUp(self): photos.CACHE.clear()
    def test_wikidata_and_commons_attribution(self):
        entity={'entities':{'Q42':{'labels':{'en':{'value':'Douglas Adams'}},'claims':{'P625':[{'mainsnak':{'datavalue':{'value':{'latitude':48.29,'longitude':25.94}}}}], 'P18':[{'mainsnak':{'datavalue':{'value':'Douglas Adams.jpg'}}}]}}}}
        image={'query':{'pages':{'1':{'imageinfo':[{'thumburl':'https://thumb.wikimedia.org/example.jpg','descriptionurl':'https://commons.wikimedia.org/wiki/File:Example.jpg','extmetadata':{'LicenseShortName':{'value':'CC BY-SA 4.0'},'Artist':{'value':'<b>Author</b>'}}}]}}}}
        with patch('photos.request_json',side_effect=[entity,image]) as req:
            result=photos.resolve(wikidata='Q42',name='Douglas Adams',lat=48.29,lon=25.94)
            self.assertEqual(result['artist'],'Author');self.assertEqual(result['license'],'CC BY-SA 4.0')
            self.assertEqual(photos.resolve(wikidata='Q42',name='Douglas Adams',lat=48.29,lon=25.94),result);self.assertEqual(req.call_count,2)
    def test_bad_reference_or_untrusted_media_rejected(self):
        with self.assertRaises(ValueError):photos.resolve(wikidata='https://evil.example')
        with self.assertRaises(ValueError):photos.resolve(filename='https://evil.example')
        data={'query':{'pages':{'1':{'imageinfo':[{'url':'https://evil.example/a.jpg','descriptionurl':'https://commons.wikimedia.org/wiki/File:A.jpg','extmetadata':{'LicenseShortName':{'value':'CC0'}}}]}}}}
        with patch('photos.request_json',return_value=data): self.assertIsNone(photos.resolve(filename='File:A.jpg'))
    def test_wikidata_mismatch_is_rejected(self):
        entity={'entities':{'Q42':{'labels':{'uk':{'value':'Сусідній сквер'}},'claims':{'P625':[{'mainsnak':{'datavalue':{'value':{'latitude':48.29,'longitude':25.94}}}}], 'P18':[{'mainsnak':{'datavalue':{'value':'park.jpg'}}}]}}}}
        with patch('photos.request_json',return_value=entity):
            self.assertIsNone(photos.resolve(wikidata='Q42',name='Пам’ятник Сидору Воробкевичу',lat=48.29,lon=25.94))

    def test_no_image(self):
        with patch('photos.request_json',return_value={'query':{'pages':{'-1':{'missing':''}}}}):self.assertIsNone(photos.resolve(filename='File:missing.jpg'))
if __name__=='__main__':unittest.main()
