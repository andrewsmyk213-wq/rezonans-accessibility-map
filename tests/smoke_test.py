"""Browser smoke tests with synthetic fixture, never published as real records."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import re, json
root=Path(__file__).resolve().parents[1]
html=(root/'index.html').read_text()
html=re.sub(r'<link[^>]*rel="stylesheet"[^>]*>', '', html)
html=re.sub(r'<script[^>]*src="[^"]+"[^>]*></script>', '', html)
fixture={'type':'FeatureCollection','features':[
 {'type':'Feature','geometry':{'type':'Point','coordinates':[25.94,48.29]},'properties':{'name':'ТЕСТОВИЙ ЦНАП — НЕ РЕАЛЬНИЙ ОБʼЄКТ','source_id':'test_fixture','source_record_id':'1','category_from_source':'ЦНАП','wheelchair':'yes','ramp':'yes','accessible_toilet':'unknown','source_date':'2026-10-30'}},
 {'type':'Feature','geometry':{'type':'Point','coordinates':[25.95,48.29]},'properties':{'name':'ТЕСТОВА АПТЕКА — НЕ РЕАЛЬНИЙ ОБʼЄКТ','source_id':'test_fixture','source_record_id':'2','category_from_source':'аптеки','wheelchair':'no','ramp':'no'}}
]}
stub="""<script>window.fetch = async function(url){if(String(url).includes('data/places.geojson'))return {ok:true,json:async()=>(TEST_FIXTURE)};return {ok:false,json:async()=>({error:'offline fixture'})}};</script>""".replace('TEST_FIXTURE',json.dumps(fixture,ensure_ascii=False))
html=html.replace('</head>',f'<style>{(root/"styles.css").read_text()}</style></head>')
html=html.replace('</body>',stub+f'<script>{(root/"app.js").read_text()}</script></body>')
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for width,height in [(390,844),(1440,900)]:
        page=browser.new_page(viewport={'width':width,'height':height})
        errors=[]
        page.on('pageerror',lambda ex: errors.append(str(ex)))
        page.set_content(html,wait_until='domcontentloaded',timeout=7000)
        page.wait_for_timeout(120)
        assert '2 із 2' in page.locator('#panelBody').inner_text(), page.locator('#panelBody').inner_text()[:300]
        page.locator('[data-place="test_fixture:1"]').first.evaluate('(e)=>e.click()')
        assert 'ТЕСТОВИЙ ЦНАП' in page.locator('#panelBody').inner_text()
        page.locator('[data-action="save"]').evaluate('(e)=>e.click()')
        assert 'ТЕСТОВИЙ ЦНАП' in page.locator('#panelBody').inner_text()
        page.locator('#openNeeds').evaluate('(e)=>e.click()')
        assert 'Мої потреби' in page.locator('#modalTitle').inner_text()
        page.locator('#closeModal').evaluate('(e)=>e.click()')
        page.locator('[data-tab="saved"]').evaluate('(e)=>e.click()')
        assert 'Збережені місця' in page.locator('h1').inner_text()
        assert not errors, errors
        print(f'PASS: {width}×{height} view, import, detail, saved, needs; {len(errors)} JS errors')
        page.screenshot(path=str(root/f'preview_test_{width}.png'),animations='disabled')
        page.close()
    browser.close()
