"""Developer-only audit. Read datasets; never mutate or synchronize them."""
import argparse
import collections
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
FIELDS={'wheelchair':('wheelchair','wheelchair'),'entrance':('accessible_entrance','entrance:wheelchair'),'ramp':('ramp','ramp'),'stairs':('stairs','stairs'),'elevator':('elevator','elevator'),'toilet':('accessible_toilet','toilets:wheelchair')}
KNOWN={'yes','no','limited','partial','designated','так','ні','частково'}
def load(path,revision=None):
    if revision:return json.loads(subprocess.check_output(['git','show',f'{revision}:{path}'],cwd=ROOT))
    return json.loads((ROOT/path).read_text('utf-8'))
def coverage(revision=None):
    rows={}
    for path in ['data/places.geojson','data/osm_snapshot.geojson']:
        for f in load(path,revision)['features']:
            p=f.get('properties',{});key=p.get('id') or f"{p.get('source_id','file')}:{p.get('source_record_id',p.get('osm_id',f.get('id')))}";rows[key]=p
    counts=collections.Counter();sources=collections.Counter();dataset_dates=collections.Counter();observed_dates=collections.Counter();missing_any=0;missing_all=0;attribute_evidence={k:[] for k in FIELDS}
    for p in rows.values():
        raw=p.get('raw_properties') or p;known=0;sources[p.get('source_id','unknown')]+=1;dataset_dates[p.get('source_date') or 'unknown']+=1;observed_dates[p.get('observed_at') or 'unknown']+=1
        for key,(normalized,osm) in FIELDS.items():
            value=p.get(normalized,raw.get(osm));value=str(value).strip().lower() if value is not None else ''
            if value in KNOWN:
                counts[key]+=1;known+=1
                attribute_evidence[key].append({'record':p.get('source_record_id'),'source_url':p.get('source_url'),'observed_at':p.get('observed_at'),'value':value})
        missing_any+=known<len(FIELDS);missing_all+=known==0
    photos=load('data/place_photos.json',revision)
    return {'total_places':len(rows),'known_attributes':{k:counts[k] for k in FIELDS},'places_with_curated_photos':sum(k in rows for k in photos),'curated_photo_assets':sum(len(v) for k,v in photos.items() if k in rows),'records_missing_any_attribute':missing_any,'records_missing_all_attributes':missing_all,'sources':dict(sources),'dataset_dates':dict(dataset_dates),'physical_observation_dates':dict(observed_dates),'attribute_evidence':attribute_evidence}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    report={'before':coverage('3800641'),'after':coverage(),'additional_datasets_imported':[],'note':'Unknowns remain unknown. Source snapshot dates are not physical observation dates. No automatic matching by distance.'}
    content=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:Path(args.output).write_text(content,encoding='utf-8')
    print(json.dumps({k:{key:value for key,value in report[k].items() if key!='attribute_evidence'} for k in ['before','after']},ensure_ascii=False,indent=2))
