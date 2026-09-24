"""Sequential, cached API calls; failures never silently regenerate a response."""
import json, os, urllib.request, urllib.error
from pathlib import Path
from .common import read,save,append,digest,now,rates
class BudgetStop(RuntimeError): pass
class CallFailed(RuntimeError): pass
class Client:
 def __init__(self,run,config,catalog,live=False):
  self.run=Path(run); self.cfg=config; self.catalog=catalog; self.live=live
  self.calls=self.run/'calls'; self.calls.mkdir(parents=True,exist_ok=True)
 def spent(self):
  return sum(read(p).get('accounted_usd',0) for p in self.calls.glob('*.json'))
 def call(self,alias,messages,*,label,max_tokens=1800,tools=None,json_mode=False):
  model=self.cfg['models'][alias]; meta=next(m for m in self.catalog['data'] if m['id']==model)
  inp,out=rates(model,self.catalog)
  body={'model':model,'messages':messages,'max_tokens':max_tokens,
        'provider':{'allow_fallbacks':False,'require_parameters':True,'max_price':{'prompt':inp*1e6,'completion':out*1e6}}}
  if 'temperature' in meta.get('supported_parameters',[]): body['temperature']=self.cfg.get('temperature',0.7)
  if 'reasoning' in meta.get('supported_parameters',[]): body['reasoning']=self.cfg['reasoning'].get(alias,{'enabled':False})
  if tools: body.update(tools=tools,tool_choice='required')
  if json_mode: body['response_format']={'type':'json_object'}
  callid=digest({'label':label,'request':body}); path=self.calls/(callid+'.json')
  if path.exists():
   old=read(path)
   if old['status']!='ok': raise CallFailed('Retained failed/pending call '+callid)
   return old['response']['choices'][0]['message']
  raw=json.dumps(body,ensure_ascii=False).encode()
  # Conservative byte-based input bound plus chat/template overhead; output includes reasoning.
  reservation=(len(raw)+4000)*inp+max_tokens*out
  if self.spent()+reservation>self.cfg['budget_usd']: raise BudgetStop('Next call exceeds remaining reserved budget')
  if not self.live: raise CallFailed('Dry mode has no model client; use the deterministic mock workflow')
  key=os.environ.get('OPENROUTER_API_KEY')
  if not key: raise CallFailed('Set OPENROUTER_API_KEY in your terminal; never put it in the repository')
  row={'id':callid,'label':label,'at':now(),'request':body,'status':'pending','accounted_usd':reservation,'reservation_usd':reservation}
  save(path,row)
  req=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=raw,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=180) as r: response=json.load(r)
   row['response']=response
   u=response.get('usage',{}); cost=u.get('cost')
   row['accounted_usd']=float(cost) if isinstance(cost,(int,float)) and cost>=0 else reservation
   row['cost_basis']='reported' if isinstance(cost,(int,float)) and cost>=0 else 'reserved_unknown_cost'
   choices=response.get('choices',[])
   if not choices or choices[0].get('finish_reason')=='length': raise CallFailed('Missing or truncated completion; retained without outcome retry')
   row['status']='ok'; save(path,row)
   if row['accounted_usd']>reservation+1e-6:
    row['status']='price_overrun';save(path,row);raise BudgetStop('Provider billing exceeded reserved bound; run stopped')
   return choices[0]['message']
  except Exception as e:
   if isinstance(e,urllib.error.HTTPError):
    row['http_status']=e.code;row['error_body']=e.read().decode(errors='replace')[:3000]
   row['status']='failed';row['error']=type(e).__name__+': '+str(e);save(path,row)
   if isinstance(e,BudgetStop): raise
   raise CallFailed(row['error']) from e
