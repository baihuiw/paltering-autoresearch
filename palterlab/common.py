import hashlib, json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
def data_root(): return DATA
def use_data(path):
 global DATA
 DATA=Path(path)
def now(): return datetime.now(timezone.utc).isoformat()
def read(path): return json.loads(Path(path).read_text())
def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def save(path,obj):
 p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix=p.name+'.',suffix='.tmp',dir=p.parent)
 with os.fdopen(fd,'w') as f:
  f.write(json.dumps(obj,indent=2,ensure_ascii=False));f.flush();os.fsync(f.fileno())
 os.replace(name,p)
def append(path,obj):
 p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('a') as f: f.write(json.dumps(obj,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())
def rows(path): return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()] if Path(path).exists() else []
def parse(text):
 if not isinstance(text,str): raise ValueError('Missing structured response')
 try: return json.loads(text)
 except ValueError: return json.loads(text[text.index('{'):text.rindex('}')+1])
def case_by_id(): return {x['case_id']:x for x in read(DATA/'cases.json')}
def records(case):
 m=read(DATA/'library/manifest.json'); ids=set(case['evidence_records'])
 return [{**r,'text':(DATA/'library/drive'/r['path']).read_text()} for r in m['files'] if r.get('record_id') in ids or (r['kind']=='policies' and any(i.rsplit('-',1)[0] in r['record_id'] for i in ids))]
def rates(model,catalog):
 m=next((m for m in catalog['data'] if m['id']==model),None)
 if m is None: raise ValueError('Model absent from frozen catalog: '+model)
 p=m['pricing']; variants=[p]+p.get('overrides',[])
 return max(float(v.get('prompt',p['prompt'])) for v in variants), max(float(v.get('completion',p['completion'])) for v in variants)
