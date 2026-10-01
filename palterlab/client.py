"""Cached OpenRouter calls with atomic, durable reservations and bounded concurrency."""
import json, os, sqlite3, threading, time, urllib.request, urllib.error
from pathlib import Path
from contextlib import contextmanager
from .common import read,save,now,rates,digest
class BudgetStop(RuntimeError): pass
class StageBudgetStop(BudgetStop): pass
class CallFailed(RuntimeError): pass
class Client:
 def __init__(self,run,config,catalog,live=False):
  self.run=Path(run);self.cfg=config;self.catalog=catalog;self.live=live;self.stage='discovery'
  self.calls=self.run/'calls';self.calls.mkdir(parents=True,exist_ok=True)
  self.db=self.run/'budget.sqlite';self.guard=threading.Lock();self.locks={}
  self.slots=threading.BoundedSemaphore(config.get('concurrency',1))
  self.alias_locks={a:threading.Lock() for a in config['models']};self.next_start={}
  with self.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY,stage TEXT,amount REAL,status TEXT)')
   # Import old sequential caches only when there is no ledger yet.
   if not db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0]:
    for p in self.calls.glob('*.json'):
     r=read(p);db.execute('INSERT OR IGNORE INTO ledger VALUES(?,?,?,?)',(r['id'],r.get('stage','discovery'),r.get('accounted_usd',0),r['status']))
 @contextmanager
 def connect(self):
  db=sqlite3.connect(self.db,timeout=60)
  try:
   with db:yield db
  finally:db.close()
 @contextmanager
 def request_slot(self,alias):
  with self.alias_locks[alias]:
   delay=self.next_start.get(alias,0)-time.monotonic()
   if delay>0:time.sleep(delay)
   self.next_start[alias]=time.monotonic()+self.cfg.get('request_interval_seconds',{}).get(alias,0)
   with self.slots:yield
 def spent(self,stage=None):
  with self.connect() as db:
   q='SELECT COALESCE(SUM(amount),0) FROM ledger';args=()
   if stage:q+=' WHERE stage=?';args=(stage,)
   return db.execute(q,args).fetchone()[0]
 def reserve(self,cid,amount):
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT 1 FROM ledger WHERE id=?',(cid,)).fetchone():raise CallFailed('Unresolved previous reservation; no automatic outcome retry')
   total=db.execute('SELECT COALESCE(SUM(amount),0) FROM ledger').fetchone()[0]
   if total+amount>min(self.cfg['budget_usd'],self.cfg.get('effective_budget_usd',self.cfg['budget_usd'])):raise BudgetStop('Next reservation exceeds total budget')
   used=db.execute('SELECT COALESCE(SUM(amount),0) FROM ledger WHERE stage=?',(self.stage,)).fetchone()[0]
   if self.stage=='discovery' and used+amount>self.cfg.get('discovery_budget_usd',self.cfg['budget_usd']):raise StageBudgetStop('Discovery allocation reached; preserve confirmation reserve')
   db.execute('INSERT INTO ledger VALUES(?,?,?,?)',(cid,self.stage,amount,'pending'))
 def settle(self,cid,amount,status):
  with self.connect() as db:db.execute('UPDATE ledger SET amount=?,status=? WHERE id=?',(amount,status,cid))
 def call(self,alias,messages,*,label,max_tokens=1800,tools=None,json_mode=False):
  model=self.cfg['models'][alias];meta=next(m for m in self.catalog['data'] if m['id']==model);inp,out=rates(model,self.catalog)
  body={'model':model,'messages':messages,'max_tokens':max_tokens,'provider':{'allow_fallbacks':False,'require_parameters':True,'max_price':{'prompt':inp*1e6,'completion':out*1e6}}}
  route=self.cfg.get('provider_routes',{}).get(alias)
  if route:body['provider']['only']=[route]
  params=meta.get('supported_parameters',[])
  if 'temperature' in params:body['temperature']=self.cfg.get('temperature',0.7)
  if 'reasoning' in params:body['reasoning']=self.cfg.get('reasoning',{}).get(alias,{'enabled':False})
  if tools:body.update(tools=tools,tool_choice=self.cfg.get('tool_choice_by_model',{}).get(alias,'required'))
  if json_mode and 'response_format' in params:body['response_format']={'type':'json_object'}
  cid=digest({'label':label,'request':body});path=self.calls/(cid+'.json')
  with self.guard:lock=self.locks.setdefault(cid,threading.Lock())
  with lock:
   recovery=False;old=None
   if path.exists():
    old=read(path)
    if old['status']=='ok':return old['response']['choices'][0]['message']
    epoch=self.cfg.get('rate_limit_recovery_epoch',0)
    recovery=bool(epoch and old.get('http_status')==429 and not old.get('response') and old.get('recovery_epoch',0)<epoch)
    if not recovery:raise CallFailed('Retained failed/pending call '+cid)
    save(self.calls/'attempts'/(old.get('attempt_id',cid).replace(':','_')+'.json'),old)
   if not self.live:raise CallFailed('Dry client cannot make API requests')
   key=os.environ.get('OPENROUTER_API_KEY')
   if not key:raise CallFailed('OPENROUTER_API_KEY is not set')
   raw=json.dumps(body,ensure_ascii=False).encode();reservation=(len(raw)+4000)*inp+max_tokens*out
   # Retries are limited to explicit transport rejection, never model output.
   for attempt in range(1 if recovery else self.cfg.get('technical_retries',1)+1):
    aid=(cid+f':recovery{self.cfg["rate_limit_recovery_epoch"]}') if recovery else (cid if attempt==0 else cid+f':retry{attempt}')
    with self.request_slot(alias):
     self.reserve(aid,reservation)
     row={'id':cid,'attempt_id':aid,'attempt':attempt,'label':label,'at':now(),'stage':self.stage,'request':body,'status':'pending','accounted_usd':reservation,'reservation_usd':reservation}
     if recovery:row['recovery_epoch']=self.cfg['rate_limit_recovery_epoch'];row['previous_attempt_id']=old.get('attempt_id',cid)
     save(path,row);retry=False
     req=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=raw,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
     try:
      with urllib.request.urlopen(req,timeout=180) as r:response=json.load(r)
      row['response']=response;cost=response.get('usage',{}).get('cost')
      known=isinstance(cost,(int,float)) and cost>=0
      row['accounted_usd']=float(cost) if known else reservation;row['cost_basis']='reported' if known else 'reserved_unknown_cost'
      if isinstance(response.get('error'),dict):
       row['provider_error_code']=response['error'].get('code')
       raise CallFailed('Provider error '+str(response['error'].get('code'))+': '+str(response['error'].get('message','Unspecified upstream error')))
      choices=response.get('choices',[])
      if row['accounted_usd']>reservation+1e-6:raise BudgetStop('Provider billing exceeded reserved bound; stopped')
      if not choices or choices[0].get('finish_reason')=='length':raise CallFailed('Missing/truncated completion; no output retry')
      row['status']='ok';save(path,row);self.settle(aid,row['accounted_usd'],'ok')
      return choices[0]['message']
     except Exception as e:
      if isinstance(e,urllib.error.HTTPError):
       row['http_status']=e.code;row['error_body']=e.read().decode(errors='replace')[:3000]
       retry=not recovery and e.code in (429,502,503,504) and attempt<self.cfg.get('technical_retries',1)
       try:delay=min(60,max(self.cfg.get('retry_backoff_seconds',2),float(e.headers.get('Retry-After','2'))))
       except (ValueError,TypeError):delay=self.cfg.get('retry_backoff_seconds',2)
      row['status']='failed';row['error']=type(e).__name__+': '+str(e);save(path,row)
      self.settle(aid,row['accounted_usd'],'failed')
      save(self.calls/'attempts'/(aid.replace(':','_')+'.json'),row)
      if isinstance(e,BudgetStop):raise
      if not retry:raise CallFailed(row['error']) from e
    time.sleep(delay)
