"""Export only published office pages; never copy an entire runner pack to a site."""
import argparse, hashlib, json
from datetime import datetime
from pathlib import Path, PurePosixPath

def ts(s):
 d=datetime.fromisoformat(s.replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('Timezone required')
 return d

def export(pack,at,out):
 pack=Path(pack).resolve();m=json.loads((pack/'manifest.json').read_text());chosen={}
 for r in m['files']:
  if r['surface']!='public' or ts(r['available_from'])>ts(at):continue
  if r['path'] not in chosen or ts(r['available_from'])>ts(chosen[r['path']]['available_from']):chosen[r['path']]=r
 records=[]
 for r in sorted(chosen.values(),key=lambda r:r['path']):
  f=pack/r['storage'];pp=PurePosixPath(r['storage'])
  if not r['storage'].startswith('public/') or '..' in pp.parts or f.is_symlink() or not f.resolve().is_relative_to(pack/'public'):raise ValueError('Invalid public source')
  raw=f.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('Changed public source')
  records.append({k:r[k] for k in ['record_id','path','title','author','modified','available_from','kind','sha256']}|{'text':raw.decode(),'access':'public'})
 payload={'schema':'office-public-snapshot-v1','as_of':at,'office':{'title':'Office of the Mayor','official':'Janine Kowalczyk','place':'Rochester, New York','term_start':m['offices']['rochester_mayor']['term_start']},'records':records}
 out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
 return payload
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--pack',type=Path,required=True);p.add_argument('--at',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();d=export(a.pack,a.at,a.out);print(f'Exported {len(d["records"])} published pages; no internal files or future versions.')
