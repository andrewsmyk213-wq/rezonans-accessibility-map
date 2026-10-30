#!/usr/bin/env python3
"""Збір відкритих даних для мапи доступності Чернівців.

Run: python3 collect.py
No third-party Python dependencies. Requires internet on user's machine.
The map bbox is an approximate filter, NOT the administrative border.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
import urllib.parse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'raw'
OUT = ROOT / 'output'
RAW.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

# Approximate city search rectangle, NOT an official city boundary.
# GeoJSON inside this rectangle needs review if near the administrative edge.
BBOX = (25.78, 48.21, 26.07, 48.40)  # west, south, east, north

SOURCES = [
    {
        'key': 'state_establishments', 'category': 'заклади', 'date': '2025-12',
        'url': 'https://data.gov.ua/dataset/546b7215-44f3-42eb-bf16-f74c9883a0b8/resource/f67b18b4-736a-4fd9-89ed-4b3fdfb59003/download/establishments.geojson',
        'landing': 'https://data.gov.ua/dataset/38997a1f-2e86-4bd7-9054-cd9cd206d825',
        'file': 'establishments.geojson'
    },
    {
        'key': 'state_stops', 'category': 'зупинки', 'date': '2025-12',
        'url': 'https://data.gov.ua/dataset/546b7215-44f3-42eb-bf16-f74c9883a0b8/resource/4c85cfa8-7267-477b-9b35-c4bba17304ef/download/stops.geojson',
        'landing': 'https://data.gov.ua/dataset/38997a1f-2e86-4bd7-9054-cd9cd206d825',
        'file': 'stops.geojson'
    },
    {
        'key': 'state_pathways', 'category': 'вулиці/маршрути', 'date': '2025-12',
        'url': 'https://data.gov.ua/dataset/546b7215-44f3-42eb-bf16-f74c9883a0b8/resource/64ce1c8a-fe22-4db8-931d-09e8cfaf11c6/download/pathways.geojson',
        'landing': 'https://data.gov.ua/dataset/38997a1f-2e86-4bd7-9054-cd9cd206d825',
        'file': 'pathways.geojson'
    },
    {
        'key': 'oblast_cnap', 'category': 'ЦНАП', 'date': '2026-07-01',
        'url': 'https://data.gov.ua/dataset/41f2db65-e54a-4357-b758-fecf6d57820c/resource/f2223fc9-ddce-4ac0-953a-716254b11c8b/download/cnapaccessibilityregistry.json',
        'landing': 'https://data.gov.ua/dataset/0b5b492d-cf84-4444-9997-3fa3d5d40758',
        'file': 'cnapaccessibilityregistry.json'
    },
    {
        'key': 'oblast_libraries', 'category': 'бібліотека', 'date': '2026-07-07',
        'url': 'https://data.gov.ua/dataset/8a240c69-29ad-4e28-b9f6-f1a8ba13c91c/resource/1dcbc431-06cb-4e53-b492-3e25cebbb740/download/cvlibrariesbarrierfree.json',
        'landing': 'https://data.gov.ua/dataset/21640874-5362-4dc3-a2b2-26c6dfec6d6a',
        'file': 'cvlibrariesbarrierfree.json'
    },
    {
        'key': 'city_accessibility_2025', 'category': 'міські будівлі', 'date': '2025-01-24',
        'url': 'https://data.gov.ua/dataset/48d24525-2432-4366-ba0a-31d42433b163/resource/64a4bbc1-373e-4293-b528-95927655e497/download/buildings_2025-01-24.csv',
        'landing': 'https://data.gov.ua/dataset/c1a9b0fe-a9b9-4a9d-a150-831f7bbe86bf',
        'file': 'buildings_2025-01-24.csv'
    },
]

# These are sensitive-use locations; opt in by passing --include-points.
OPTIONAL_SOURCES = [
    {
        'key': 'oblast_points', 'category': 'пункти незламності', 'date': '2026-08-26',
        'url': 'https://data.gov.ua/dataset/ff20d3d8-d384-4230-bbd2-a6623711cb7b/resource/c7b1bad9-3b4e-4f8b-a2f4-4757ebf2e6de/download/pointinvincibility.json',
        'landing': 'https://data.gov.ua/dataset/538d77ae-f0ed-461e-8f35-ed910ea8094a',
        'file': 'pointinvincibility.json'
    }
]

USER_AGENT = 'Rezonans-Hackathon-AccessibilityResearch/1.0 (open data; attribution in outputs)'

def fetch(url: str, path: Path):
    if path.exists() and path.stat().st_size > 40 and '--refresh' not in sys.argv:
        return f'cached {path.stat().st_size} bytes'
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
    temp = path.with_name(path.name + '.part')
    with urllib.request.urlopen(req, timeout=100) as resp, temp.open('wb') as f:
        shutil.copyfileobj(resp, f)
    if temp.stat().st_size < 30:
        raise ValueError('Downloaded file is suspiciously small')
    # Reject error pages misreported as successful downloads.
    with temp.open('rb') as f:
        head = f.read(256).lstrip().lower()
    if head.startswith(b'<!doctype html') or head.startswith(b'<html'):
        temp.unlink(missing_ok=True)
        raise ValueError('Server returned an HTML page rather than data')
    temp.replace(path)
    return f'downloaded {path.stat().st_size} bytes'


def load_any(path: Path):
    if path.suffix.lower() in ('.json', '.geojson'):
        with path.open('r', encoding='utf-8-sig') as f:
            return json.load(f)
    # Detect CSV delimiter and character set; some Ukrainian datasets use cp1251.
    raw = path.read_bytes()
    for enc in ('utf-8-sig', 'cp1251'):
        try:
            text = raw.decode(enc)
            sample = text[:6000]
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ';' if sample.count(';') > sample.count(',') else ','
            return list(csv.DictReader(text.splitlines(), delimiter=delimiter))
        except UnicodeDecodeError:
            continue
    raise ValueError('CSV encoding unsupported')


def iter_records(obj):
    if isinstance(obj, list):
        for v in obj:
            if isinstance(v, dict):
                yield v
        return
    if isinstance(obj, dict):
        if obj.get('type') == 'FeatureCollection':
            yield from (r for r in obj.get('features', []) if isinstance(r, dict))
        elif obj.get('type') == 'Feature':
            yield obj
        else:
            for key in ('data','items','records','results','features','centers','cnaps','libraries','buildings'):
                if isinstance(obj.get(key), list):
                    yield from (r for r in obj[key] if isinstance(r, dict))
                    return
            # catch other unrecognized collections while ignoring schema dictionaries
            for val in obj.values():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    yield from (r for r in val if isinstance(r, dict))
                    return


def flatten_numbers(coords):
    if isinstance(coords, (list, tuple)):
        if len(coords) >= 2 and all(isinstance(x, (int,float)) for x in coords[:2]):
            yield float(coords[0]), float(coords[1])
        else:
            for val in coords:
                yield from flatten_numbers(val)


def inside(x, y):
    return BBOX[0] <= x <= BBOX[2] and BBOX[1] <= y <= BBOX[3]


def get_geometry(record):
    geom = record.get('geometry')
    if isinstance(geom, dict) and geom.get('type') and geom.get('coordinates') is not None:
        return geom
    return None


def find_coord(row):
    """Only extract coordinates, never geocode/impute coordinates."""
    names = {str(k).lower().replace('_','').replace('-',''): v for k,v in row.items()}
    lat = next((names.get(n) for n in ('lat','latitude','широта','geolatitude','gpslat','y') if names.get(n) is not None), None)
    lon = next((names.get(n) for n in ('lon','lng','long','longitude','довгота','geolongitude','gpslon','x') if names.get(n) is not None), None)
    try:
        if lat is not None and lon is not None:
            pair = float(str(lon).replace(',','.').strip()), float(str(lat).replace(',','.').strip())
            if 20 <= pair[0] <= 41 and 43 <= pair[1] <= 53:
                return list(pair)
    except (ValueError, TypeError):
        pass
    for key in ('coordinates','coordinate','coords','location','geolocation','geo','координати','gps'):
        val = names.get(key)
        if isinstance(val, dict):
            parsed = find_coord(val)
            if parsed:
                return parsed
        if isinstance(val, (list,tuple)) and len(val)>=2:
            try:
                p = [float(val[0]),float(val[1])]
                if 43 <= p[0] <= 53 and 20 <= p[1] <= 41:
                    p.reverse()
                if 20 <= p[0] <= 41 and 43 <= p[1] <= 53:
                    return p
            except (TypeError,ValueError): pass
        if isinstance(val, str):
            matches = re.findall(r'\d{2}\.\d+', val.replace(',','.'))
            if len(matches)>=2:
                p = list(map(float,matches[:2]))
                if 43 <= p[0] <= 53 and 20 <= p[1] <= 41:
                    p.reverse()
                if 20 <= p[0] <= 41 and 43 <= p[1] <= 53:
                    return p
    return None


def value_for(props, names):
    index = {str(k).casefold().replace('_','').replace('-','').replace(' ',''): v for k,v in props.items()}
    for name in names:
        key = name.casefold().replace('_','').replace('-','').replace(' ','')
        if key in index and index[key] not in (None, ''):
            return index[key]
    return None


def contains_city(props):
    # City string is distinct from "Чернівецька область". Does not prove geometry.
    s = ' '.join(str(v) for v in props.values() if isinstance(v, (str,int,float)))
    return bool(re.search(r'Чернівці\b|Chernivtsi\b|Czernowitz\b',s,re.I))


def extract_name(props):
    v = value_for(props,['name','назва','назвазакладу','objectname','facilityname','title','institutionname','найменування','institution'])
    return str(v) if v is not None else None


def attr_yes_no(props, aliases):
    v = value_for(props,aliases)
    if isinstance(v,bool): return 'yes' if v else 'no'
    if v is None: return 'unknown'
    s = str(v).strip().casefold()
    if s in ('так','yes','true','1','наявний','наявна','є','обладнано'): return 'yes'
    if s in ('ні','no','false','0','немає','відсутній','відсутня'): return 'no'
    return 'unknown'


def normalized(rec, src, i):
    props = rec.get('properties',{}) if rec.get('type')=='Feature' else rec
    if not isinstance(props,dict): return None
    geo = get_geometry(rec)
    coords = list(flatten_numbers(geo.get('coordinates',[]))) if geo else []
    if geo:
        is_local = any(inside(x,y) for x,y in coords)
        # Polygon spanning bbox without interior vertex may require separate GIS clipping.
        point_coords = coords[0] if geo.get('type') == 'Point' and coords else None
        geom = geo
    else:
        point_coords = find_coord(props)
        is_local = inside(*point_coords) if point_coords else contains_city(props)
        geom = {'type':'Point','coordinates':point_coords} if point_coords and is_local else None
    if not is_local: return None
    outprops = {
        'source_record_id': str(rec.get('id') or props.get('id') or i),
        'source_id':src['key'], 'source_url':src['landing'],
        'source_date':src['date'], 'name':extract_name(props),
        'category_from_source':src['category'],
        'accessibility_overall_raw':value_for(props,['accessibility','accessibilityStatus','accessibilityLevel','wheelchair','barrierFree','status','ступінь безбарєрності','рівень доступності']),
        'ramp':attr_yes_no(props,['ramp','hasRamp','ramps','пандус','наявність пандусу']),
        'accessible_toilet':attr_yes_no(props,['accessibleToilet','disabledToilet','toiletForDisabled','вбиральня для осіб з інвалідністю']),
        'wheelchair':attr_yes_no(props,['wheelchair','wheelchairAccessible']),
        'geo_filter':'approximate_bbox_not_city_boundary' if geom else 'city_name_without_coordinates',
        'raw_properties':props,
    }
    return {'type':'Feature','geometry':geom,'properties':outprops}


def export():
    sources = SOURCES + (OPTIONAL_SOURCES if '--include-points' in sys.argv else [])
    summary = {'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
               'location_filter':'approximate bbox; not official border',
               'bbox_wsen':BBOX,'sources':{},'cautions':[
                    'Unknown accessibility is NOT accessible.',
                    'Downloaded datasets may contain outdated or unverified reports.',
                    'OSM-derived fields need ODbL attribution and licence review if merged.',
                    'Never label routes as safe from these point datasets.'
               ]}
    features=[]
    uncoded=[]
    for src in sources:
        raw_file = RAW/src['file']
        info = {'download_url':src['url'],'source_url':src['landing'],'source_date':src['date']}
        try:
            try:
                info['download_status']=fetch(src['url'],raw_file)
            except Exception as fetch_error:
                if raw_file.exists() and raw_file.stat().st_size > 40:
                    info['download_status']=f'using stale cached file after download failure: {fetch_error}'
                else:
                    raise
            records = list(iter_records(load_any(raw_file)))
            info['all_records']=len(records)
            info['first_record_keys']=list((records[0].get('properties',{}) if records[0].get('type')=='Feature' else records[0]).keys())[:50] if records else []
            local_records=0; map_records=0
            for i,rec in enumerate(records):
                result=normalized(rec,src,i)
                if result is None: continue
                local_records+=1
                if result['geometry'] is not None:
                    features.append(result); map_records+=1
                else:
                    uncoded.append(result['properties'])
            info['local_candidates']=local_records
            info['geocoded_for_map']=map_records
            info['no_coordinates']=local_records-map_records
            print(f"OK {src['key']}: {map_records} map features, {local_records-map_records} without coordinates")
        except Exception as exc:
            info['error']=str(exc)
            print(f"ERROR {src['key']}: {exc}",file=sys.stderr)
        summary['sources'][src['key']]=info

    # OSM is a separate dataset with ODbL; do not silently merge it into official data.
    osm_url='https://overpass.kumi.systems/api/interpreter'
    q='''[out:json][timeout:90];(
 nwr["wheelchair"](48.21,25.78,48.40,26.07);
 nwr["highway"="steps"](48.21,25.78,48.40,26.07);
 nwr["kerb"](48.21,25.78,48.40,26.07);
 nwr["ramp"](48.21,25.78,48.40,26.07);
 nwr["tactile_paving"](48.21,25.78,48.40,26.07);
 nwr["highway"="elevator"](48.21,25.78,48.40,26.07);
);out center tags;'''
    (OUT/'osm_overpass_query.txt').write_text(q,encoding='utf-8')
    osm_features=[]
    try:
        req=urllib.request.Request(osm_url,data=urllib.parse.urlencode({'data':q}).encode('utf-8'),headers={'User-Agent':USER_AGENT,'Content-Type':'application/x-www-form-urlencoded'},method='POST')
        with urllib.request.urlopen(req,timeout=110) as resp:
            osm_data=json.load(resp)
        for item in osm_data.get('elements',[]):
            xy=item.get('center',item)
            x,y=xy.get('lon'),xy.get('lat')
            if x is None or y is None or not inside(x,y): continue
            osm_features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[x,y]},'properties':{
                'source_id':'openstreetmap','osm_type':item.get('type'),'osm_id':item.get('id'),
                'geo_interpretation':'point for node; approximate center for way/relation',
                'source_url':'https://www.openstreetmap.org/copyright',
                'name':item.get('tags',{}).get('name'),'raw_properties':item.get('tags',{})}})
        (OUT/'osm_tags.geojson').write_text(json.dumps({'type':'FeatureCollection','features':osm_features},ensure_ascii=False,indent=2),encoding='utf-8')
        summary['osm']={'status':'ok','items':len(osm_features),'note':'ODbL licence; shown separately'}
    except Exception as exc:
        summary['osm']={'status':'failed','error':str(exc),'note':'Query saved to osm_overpass_query.txt for manual use'}

    (OUT/'chernivtsi_accessibility.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,indent=2),encoding='utf-8')
    with (OUT/'requires_geocoding.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['source_id','source_record_id','name','category_from_source','source_url','raw_properties'])
        w.writeheader()
        for r in uncoded:
            w.writerow({k:json.dumps(r[k],ensure_ascii=False) if k=='raw_properties' else r.get(k) for k in w.fieldnames})
    summary['totals']={'official_geojson_features':len(features),'city_name_no_coordinates':len(uncoded),'osm_tagged_features':len(osm_features)}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\nDONE:',OUT)
    print(json.dumps(summary['totals'],ensure_ascii=False,indent=2))
    if not features:
        print('NOTE: No mappable official features. Check source errors in output/summary.json.')

if __name__=='__main__':
    export()
