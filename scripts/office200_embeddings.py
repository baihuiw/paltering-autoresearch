"""Read-only embedding pass over the frozen office200 replies. No subject/judge calls."""
import argparse,base64,collections,fcntl,hashlib,json,os,sqlite3,time,urllib.request,urllib.error
from pathlib import Path
import numpy as np
import tiktoken
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'runs/office200_20260925'
RUN=ROOT/'runs/office200_embeddings_20260928'
MODEL='text-embedding-3-large'; API_MODEL='openai/text-embedding-3-large'; ENDPOINT='https://openrouter.ai/api/v1/embeddings'; RATE=.13/1_000_000; CAP=2.0; DIM=3072

def save(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def digest(x):return hashlib.sha256(x.encode()).hexdigest()
def prepare():
 RUN.mkdir(exist_ok=True); enc=tiktoken.get_encoding('cl100k_base')
 raw=SOURCE/'review/kimi_full_cases.json';rows=json.loads(raw.read_text())['cases'];slots={x['id']:x for x in json.loads((SOURCE/'slots.json').read_text())}
 items=[];inputs=[];unique={};seen=set();counts=collections.Counter()
 def add(kind,input_text,**meta):
  text=input_text
  assert text.strip(); h=digest(MODEL+'\n'+text)
  if h not in unique:
   tokens=len(enc.encode(text,disallowed_special=()));assert 0<tokens<=8191,(kind,tokens)
   unique[h]=len(inputs);inputs.append({'sha256':h,'text':text,'tokens':tokens,'bytes':len(text.encode())})
  items.append({'view':kind,'input_index':unique[h],**meta})
 metadata=[]
 for c in rows:
  slot=slots[c['scenario']];q=c['question'];reply=c['reply'];inp=json.loads((SOURCE/'episodes'/c['episode']/'judge_input.json').read_text())
  qc=c['qwen'].get('category');kc=c['kimi'].get('category');out=qc if qc==kc else ('missing_review' if c['kimi'].get('status')!='completed' else 'disagreement');counts[out]+=1
  meta={k:c[k] for k in ['episode','scenario','model','title','question','reply','conclusion','split']};meta.update(outcome=out,qwen=qc,kimi=kc,family=slot['family'],topic=slot['topic'])
  metadata.append(meta);add('whole_reply',reply,episode=c['episode']);add('question_reply','Question: '+q+'\nReply: '+reply,episode=c['episode'])
  for u in inp['reply_units']:add('question_unit','Question: '+q+'\nReply segment: '+u['text'],episode=c['episode'],unit_id=u['id'],text=u['text'])
  if c['scenario'] not in seen:
   ev='\n'.join(u['text'] for rec in inp['incident_records'] for u in rec['units']);add('evidence_once',ev,scenario=c['scenario']);seen.add(c['scenario'])
 payload={'model':MODEL,'dimensions':DIM,'source_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'items':items,'inputs':inputs,'replies':metadata}
 p=RUN/'inputs.json'
 if p.exists():assert json.loads(p.read_text())==payload,'Frozen inputs changed; stop'
 else:save(p,payload)
 manifest={'source_sha256':payload['source_sha256'],'input_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'model':MODEL,'dimensions':DIM,'cap_usd':CAP,'price_usd_per_million_tokens':.13,'api':ENDPOINT,'provider':'OpenAI only through OpenRouter; no provider fallback','credential_source':'OPENROUTER_API_KEY environment, never saved','replies':len(rows),'scenarios':len(seen),'outcomes':dict(counts),'items_by_view':dict(collections.Counter(x['view'] for x in items)),'unique_inputs':len(inputs),'unique_input_tokens':sum(x['tokens'] for x in inputs),'expected_usd':sum(x['tokens'] for x in inputs)*RATE,'max_input_tokens':max(x['tokens'] for x in inputs),'encoder_input_rule':'Only saved reply, question, and incident evidence text. No model name, judge label, rationale, researcher conclusion, or tactic annotation appended.','analysis_rule':'Exploratory fixed PCA and cosine neighbors; compare saved joint honest/paltering/false_assertion labels with balanced logistic regression, fixed C=1, five scenario-family folds seed 42. All near-duplicate ward variants stay in same fold. Include lexical/question-only and topic/style controls. No classifier hyperparameter tuning against test labels. Existing labels are not independent human validation.'}
 save(RUN/'manifest.json',manifest)
 if not (RUN/'approval.json').exists():save(RUN/'approval.json',{'approved_by':'user','request':'ok, do the word embedding with text-embedding-3-large.','date':'2026-09-28','budget_usd':CAP,'scope':'All four proposed text views, direct OpenAI embeddings, local analysis and website results. No new subject, judge, reader or rewrite generations.'})
 print(json.dumps(manifest),flush=True);return payload

def state(db,completed,total):
 spend=db.execute('SELECT coalesce(sum(amount),0) FROM calls').fetchone()[0]
 reported=db.execute("SELECT coalesce(sum(amount),0) FROM calls WHERE status='ok'").fetchone()[0]
 s={'completed_unique_inputs':completed,'total_unique_inputs':total,'accounted_usd':spend,'reported_token_cost_usd':reported,'unknown_reservations_usd':spend-reported,'cap_usd':CAP,'updated_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};save(RUN/'state.json',s);return s

def run():
 data=prepare();key=os.environ.get('OPENROUTER_API_KEY');assert key,'OPENROUTER_API_KEY unavailable'
 db=sqlite3.connect(RUN/'budget.sqlite');db.execute('CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,status TEXT,amount REAL,tokens INTEGER,request_id TEXT)');db.commit()
 cache=RUN/'batches';cache.mkdir(exist_ok=True);inputs=data['inputs'];batches=[];ids=[];nt=0
 # Small first batch verifies authentication while doing real, cacheable work.
 for i,x in enumerate(inputs):
  limit=8 if not batches else 128
  if ids and (len(ids)>=limit or nt+x['tokens']>50000):batches.append(ids);ids=[];nt=0
  ids.append(i);nt+=x['tokens']
 if ids:batches.append(ids)
 completed=0
 for bi,ids in enumerate(batches):
  stem=f'{bi:04d}';npy=cache/(stem+'.npy');meta=cache/(stem+'.json')
  if npy.exists() and meta.exists():
   m=json.loads(meta.read_text());assert m['indices']==ids;assert np.load(npy,mmap_mode='r').shape==(len(ids),DIM);completed+=len(ids);continue
  tokens=sum(inputs[i]['tokens'] for i in ids);bound=sum(inputs[i]['bytes'] for i in ids)*RATE+.00001
  body=json.dumps({'model':API_MODEL,'input':[inputs[i]['text'] for i in ids],'encoding_format':'base64','provider':{'only':['openai'],'allow_fallbacks':False,'max_price':{'prompt':.13,'completion':0}}}).encode()
  for attempt in range(3):
   cid=f'{stem}-{attempt}';old=db.execute('SELECT status FROM calls WHERE id=?',(cid,)).fetchone()
   if old:
    if old[0]=='pending':raise RuntimeError('Unresolved pending API call; inspect before recovery')
    continue
   db.execute('BEGIN IMMEDIATE');spent=db.execute('SELECT coalesce(sum(amount),0) FROM calls').fetchone()[0]
   if spent+bound>CAP:db.rollback();state(db,completed,len(inputs));raise RuntimeError('Budget cap reached')
   db.execute('INSERT INTO calls VALUES(?,?,?,?,?)',(cid,'pending',bound,None,None));db.commit();state(db,completed,len(inputs))
   req=urllib.request.Request(ENDPOINT,data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(req,timeout=120) as res:response=json.load(res);request_id=res.headers.get('x-request-id','')
    assert response.get('model') in (MODEL,API_MODEL), 'Unexpected model returned'
    emb=sorted(response['data'],key=lambda x:x['index']);assert [x['index'] for x in emb]==list(range(len(ids)))
    arr=np.array([(np.frombuffer(base64.b64decode(x['embedding']),dtype='<f4') if isinstance(x['embedding'],str) else np.array(x['embedding'],dtype=np.float32)) for x in emb]);assert arr.shape==(len(ids),DIM);assert np.isfinite(arr).all();assert np.allclose(np.linalg.norm(arr,axis=1),1,atol=.01)
    used=response['usage']['total_tokens'];cost=response['usage'].get('cost',used*RATE);assert cost<=bound,'Usage exceeds reserved maximum'
    np.save(npy,arr);save(meta,{'indices':ids,'model':response['model'],'dimensions':DIM,'local_tokens':tokens,'usage':response['usage'],'cost_usd':cost,'request_id':request_id,'response_id':response.get('id'),'provider':response.get('provider','OpenAI (request pinned)'),'api':ENDPOINT,'vector_sha256':hashlib.sha256(npy.read_bytes()).hexdigest()})
    db.execute('UPDATE calls SET status=?,amount=?,tokens=?,request_id=? WHERE id=?',('ok',cost,used,request_id,cid));db.commit();completed+=len(ids);s=state(db,completed,len(inputs));print(json.dumps({'batch':bi+1,'batches':len(batches),**s}),flush=True);break
   except Exception as ex:
    code=ex.code if isinstance(ex,urllib.error.HTTPError) else None
    # Do not log credential-bearing requests, raw provider errors, or headers.
    db.execute('UPDATE calls SET status=? WHERE id=?',('failed_unknown_charge',cid));db.commit();save(cache/(cid+'.error.json'),{'type':type(ex).__name__,'http_status':code,'reservation_usd_retained':bound});print(json.dumps({'batch':bi+1,'attempt':attempt+1,'error':type(ex).__name__,'http_status':code}),flush=True)
    if code in (400,401,403,404):raise RuntimeError('API request rejected; saved safe error metadata') from None
    if attempt==2:raise RuntimeError('Three technical failures; cached progress retained') from None
    time.sleep(10*(attempt+1))
  else:raise RuntimeError('Retry slots exhausted; inspect safe error metadata')
 matrix=np.empty((len(inputs),DIM),dtype=np.float32)
 for bi,ids in enumerate(batches):matrix[ids]=np.load(cache/f'{bi:04d}.npy')
 np.save(RUN/'embeddings.npy',matrix);s=state(db,completed,len(inputs));s.update(status='completed',embedding_sha256=hashlib.sha256((RUN/'embeddings.npy').read_bytes()).hexdigest());save(RUN/'state.json',s);print(json.dumps(s),flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('command',choices=['prepare','run']);args=ap.parse_args();RUN.mkdir(exist_ok=True)
 with (RUN/'worker.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if args.command=='prepare':prepare()
  else:run()
