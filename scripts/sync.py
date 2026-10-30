#!/usr/bin/env python3
"""Synchronize source files via collector into the real-data GeoJSON used by UI.

One-off: python3 scripts/sync.py
Repeated (terminal stays running): python3 scripts/sync.py --watch --interval 21600
Never replaces a non-empty dataset with an empty result when all sources fail.
"""
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
COLLECT = ROOT / 'scripts' / 'collect.py'
OUT = ROOT / 'scripts' / 'output'
DEST = ROOT / 'data' / 'places.geojson'
STATUS = ROOT / 'data' / 'sync_status.json'

def sync(refresh=False):
    args=[sys.executable,str(COLLECT)]
    if refresh: args+=['--refresh']
    proc=subprocess.run(args,cwd=str(COLLECT.parent),timeout=390, text=True,capture_output=True)
    print(proc.stdout)
    if proc.stderr:print(proc.stderr,file=sys.stderr)
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    summary_file=OUT/'summary.json'
    summary=json.loads(summary_file.read_text('utf-8')) if summary_file.exists() else {}
    official=OUT/'chernivtsi_accessibility.geojson'
    osm=OUT/'osm_tags.geojson'
    features=[]
    for path in (official,osm):
        if not path.exists():continue
        try:
            doc=json.loads(path.read_text('utf-8'))
            for f in doc.get('features',[]):
                props=f.get('properties',{})
                geom=f.get('geometry',{})
                if geom.get('type')!='Point':continue
                if not (props.get('name') or (props.get('raw_properties') or {}).get('name')):continue
                # OSM shapes without names are not POIs; do not invent names.
                xy=geom.get('coordinates',[])
                if len(xy)<2 or not 25.78 <= xy[0] <= 26.07 or not 48.21 <= xy[1] <= 48.40:continue
                features.append(f)
        except (OSError,ValueError,TypeError) as e:print(f'Skip {path}: {e}',file=sys.stderr)
    seen=set();deduped=[]
    for f in features:
        p=f.get('properties',{})
        k=(p.get('source_id'),p.get('osm_id') or p.get('source_record_id'),tuple(f['geometry']['coordinates'][:2]))
        if k in seen:continue
        seen.add(k);deduped.append(f)
    previous=0
    try:previous=len(json.loads(DEST.read_text('utf-8')).get('features',[]))
    except (OSError,ValueError):pass
    published=False
    if deduped:
        payload={'type':'FeatureCollection','features':deduped,'metadata':{'downloaded_utc':now,'claim':'Source records only. Accessibility not independently verified.','osm_license':'ODbL attribution required'}}
        tmp=DEST.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        tmp.replace(DEST)
        published=True
    state={'last_attempt_utc':now,'last_success_utc':now if published else None,'published':published,'place_count':len(deduped) if published else previous,'previous_count':previous,'raw_summary':summary.get('totals',{}),'source_errors':{k:v['error'] for k,v in summary.get('sources',{}).items() if 'error' in v},'note':'Zero new records never wipes a previous published dataset. Check source_errors.'}
    if STATUS.exists() and not published:
        try:state['last_success_utc']=json.loads(STATUS.read_text('utf-8')).get('last_success_utc')
        except ValueError:pass
    STATUS.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Published={published}; features={len(deduped)}; previous={previous}; source errors={len(state["source_errors"])}')
    return published

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--watch',action='store_true')
    parser.add_argument('--interval',type=int,default=21600)
    parser.add_argument('--refresh',action='store_true')
    ns=parser.parse_args()
    if ns.watch:
        while True:
            try:sync(refresh=True)
            except Exception as e:print('Sync error:',e,file=sys.stderr)
            time.sleep(max(300,ns.interval))
    else:sync(refresh=ns.refresh)
