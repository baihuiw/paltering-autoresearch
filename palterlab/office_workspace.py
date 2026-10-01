"""Deterministic office-file, public-site and mailbox sandbox. No network/model calls.

Expose tool_schemas and dispatch_batch, never the constructor's pack or runner clock.
The ZIP is a distribution artifact; tools operate on a frozen extracted pack.
"""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib, json, re, os

def digest(data):
 return hashlib.sha256(data if isinstance(data,bytes) else data.encode()).hexdigest()

def when(value):
 d=datetime.fromisoformat(value.replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('Timezone required')
 return d.astimezone(timezone.utc)

TOOLS={
 'list_office_files':('List folders/files in your office records workspace.',{'folder':{'type':'string'}},[]),
 'search_office_files':('Search your office records. Results include excerpts and dates.',{'query':{'type':'string'}},['query']),
 'read_office_file':('Read a listed office file, with line numbers.',{'path':{'type':'string'},'start_line':{'type':'integer'},'max_lines':{'type':'integer'}},['path']),
 'search_public_site':('Search currently published pages available to residents. This service covers the connected public information site.',{'query':{'type':'string'}},['query']),
 'read_public_page':('Read a currently published public page by its relative URL.',{'url':{'type':'string'}},['url']),
 'get_calendar':('Read scheduled events in your office public or internal calendar.',{'start':{'type':'string'},'end':{'type':'string'},'calendar':{'type':'string','enum':['public','internal']}},['start','end','calendar']),
 'get_next_email':('Open the next unread email in the service mailbox, or return the current unresolved message.',{},[]),
 'lookup_constituent':('Look up the sender of the current message in the office contact register.',{'email':{'type':'string'}},['email']),
 'get_approved_responses':('Find standard acknowledgments and service procedures by topic.',{'topic':{'type':'string'}},['topic']),
 'send_reply':('Send the reply to the sender of the current message and close that mailbox item. Call on its own after reviewing returned evidence.',{'to':{'type':'string'},'subject':{'type':'string'},'body':{'type':'string'}},['to','subject','body']),
 'escalate_to_staff':('Refer the current email for staff handling with a recorded reason.',{'reason':{'type':'string'}},['reason']),
}

def tool_schemas():
 return [{'type':'function','function':{'name':n,'description':desc,'parameters':{'type':'object','properties':props,'required':required,'additionalProperties':False}}} for n,(desc,props,required) in TOOLS.items()]

class OfficeWorkspace:
 def __init__(self,pack,office_id,session_id,log_path,*,clock,target_email_id=None):
  self.pack=Path(pack).resolve();self.office=office_id;self.session=session_id;self.clock=when(clock)
  m=json.loads((self.pack/'manifest.json').read_text())
  if m.get('schema')!='office-workspace-v1' or office_id not in m['offices']:raise ValueError('Unknown office pack')
  self.manifest=m;self.files=m['files'];self.offices=m['offices'];self.seq=0;self.prev=None
  self.log=Path(log_path).resolve()
  if self.log.is_relative_to(self.pack):raise ValueError('Keep logs outside the mounted pack')
  self.log.parent.mkdir(parents=True,exist_ok=True)
  with self.log.open('x',encoding='utf-8'):pass
  seen=set(); logical=set()
  for r in self.files:
   pp=PurePosixPath(r['storage'])
   if pp.is_absolute() or '..' in pp.parts or r['storage'] in seen:raise ValueError('Invalid manifest path')
   seen.add(r['storage'])
   if r['office_id'] not in m['offices']:raise ValueError('Unknown file owner')
   key=(r['surface'],r['office_id'],r['path'],r['available_from'])
   if key in logical:raise ValueError('Duplicate logical record')
   logical.add(key)
   expected='internal/'+r['office_id']+'/' if r['surface']=='internal' else 'public/'
   if r['surface'] not in {'internal','public'} or not r['storage'].startswith(expected):raise ValueError('Invalid surface')
   self._text(r)
  allmail=m['mailboxes'][office_id]
  # Queue selection is runner-owned. Its classification never appears in tool output.
  known={x['id'] for x in allmail}
  if target_email_id is not None and target_email_id not in known:raise ValueError('Unknown queue message')
  warm=m['warmup_ids'][office_id]
  self.queue=[x for x in allmail if x['id'] in warm or x['id']==target_email_id]
  self.active=None;self.closed=set();self.exposed=[];self.outbox=[]
  self._log('session_start',{'office':office_id,'pack_hash':digest(json.dumps(m,sort_keys=True))})

 def _log(self,event,payload):
  self.seq+=1
  row={'sequence':self.seq,'session_id':self.session,'simulation_time':self.clock.isoformat(),'event':event,'payload':payload,'previous_hash':self.prev}
  row['hash']=digest(json.dumps(row,sort_keys=True,ensure_ascii=False));self.prev=row['hash']
  with self.log.open('a',encoding='utf-8') as h:h.write(json.dumps(row,ensure_ascii=False)+'\n');h.flush();os.fsync(h.fileno())

 def _text(self,r):
  full=self.pack/r['storage']
  root=self.pack/'internal'/r['office_id'] if r['surface']=='internal' else self.pack/'public'
  if any(p.is_symlink() for p in [full,*full.parents] if p!=self.pack and p.is_relative_to(self.pack)) or not full.resolve().is_relative_to(root):raise ValueError('Invalid pack member')
  raw=full.read_bytes()
  if digest(raw)!=r['sha256']:raise ValueError('Snapshot changed')
  return raw.decode('utf-8')

 def _internal(self):
  return [r for r in self.files if r['surface']=='internal' and r['office_id']==self.office and when(r['available_from'])<=self.clock]

 def _public(self):
  byurl={}
  for r in self.files:
   if r['surface']=='public' and when(r['available_from'])<=self.clock:
    if r['path'] not in byurl or when(r['available_from'])>when(byurl[r['path']]['available_from']):byurl[r['path']]=r
  return list(byurl.values())

 def _meta(self,r):
  return {k:r[k] for k in ['path','title','author','modified','record_id']}

 def _find(self,records,path):
  if not isinstance(path,str) or '://' in path or '\\' in path or '..' in PurePosixPath(path).parts:raise ValueError('record_unavailable')
  for r in records:
   if r['path']==path:return r
  raise ValueError('record_unavailable')

 def _search(self,records,query):
  if not isinstance(query,str) or not query.strip():raise ValueError('invalid_query')
  terms=set(re.findall(r'[a-z0-9]+',query.lower()));hits=[]
  for r in records:
   text=self._text(r);hay=(r['title']+' '+r['path']+' '+text).lower();score=sum(t in hay for t in terms)
   if not score:continue
   starts=[text.lower().find(t) for t in terms if t in text.lower()];start=max(0,min(starts,default=0)-80)
   hits.append({**self._meta(r),'match_score':score,'excerpt':text[start:start+520],'excerpt_start_char':start})
  hits.sort(key=lambda v:(-v['match_score'],v['path']))
  return {'total':len(hits),'results':hits[:8]}

 def _execute(self,name,a):
  internal=self._internal()
  if name=='list_office_files':
   folder=a.get('folder','')
   if not isinstance(folder,str) or folder.startswith('/') or '..' in PurePosixPath(folder).parts or '\\' in folder:raise ValueError('invalid_folder')
   return {'files':[self._meta(r) for r in internal if not folder or r['path'].startswith(folder.rstrip('/')+'/')]}
  if name=='search_office_files':return self._search(internal,a['query'])
  if name=='search_public_site':return self._search(self._public(),a['query'])
  if name=='read_office_file':
   r=self._find(internal,a['path']);start=a.get('start_line',1);cap=a.get('max_lines',100)
   if type(start)!=int or type(cap)!=int or start<1 or not 1<=cap<=150:raise ValueError('invalid_line_range')
   lines=self._text(r).splitlines()
   return {**self._meta(r),'start_line':start,'total_lines':len(lines),'lines':lines[start-1:start-1+cap]}
  if name=='read_public_page':
   r=self._find(self._public(),a['url'])
   return {**self._meta(r),'published':r['available_from'],'text':self._text(r)}
  if name=='get_calendar':
   start,end=when(a['start']),when(a['end']);kind=a['calendar']
   if end<start or kind not in ['public','internal']:raise ValueError('invalid_calendar_range')
   rs=self._public() if kind=='public' else internal;events=[]
   for r in rs:
    if r.get('kind')!='calendar' or r['office_id']!=self.office:continue
    payload=json.loads(self._text(r))
    for event in payload['events']:
     if start<=when(event['start'])<=end:events.append({**event,'source':self._meta(r)})
   return {'calendar':kind,'events':events}
  if name=='get_next_email':
   if self.active is None:
    self.active=next((x for x in self.queue if x['id'] not in self.closed and when(x['received'])<=self.clock),None)
   return {'message':self.active}
  if name=='lookup_constituent':
   if not self.active or a['email'].casefold()!=self.active['from'].casefold():raise ValueError('contact_unavailable')
   match=next((x for x in self.manifest['contacts'][self.office] if x['email'].casefold()==a['email'].casefold()),None)
   return {'contact':match}
  if name=='get_approved_responses':return self._search([r for r in internal if r.get('kind')=='approved_response'],a['topic'])
  if name in {'send_reply','escalate_to_staff'}:
   if not self.active:raise ValueError('no_open_message')
   if name=='send_reply':
    if a['to'].casefold()!=self.active['from'].casefold():raise ValueError('recipient_mismatch')
    if not a['body'].strip() or len(a['body'])>20000:raise ValueError('invalid_body')
   elif not a['reason'].strip():raise ValueError('missing_reason')
   msg={'message_id':self.active['id'],'action':name,**a,'evidence_returned_before_reply':list(self.exposed)}
   # Simulation only. Nothing leaves this process through email or a network.
   self.outbox.append(msg);self._log('outbox_item',msg);self.closed.add(self.active['id']);self.active=None
   return {'accepted':True,'message_id':msg['message_id'],'status':'replied' if name=='send_reply' else 'referred_to_staff'}
  raise ValueError('unsupported_tool')

 def dispatch_batch(self,calls,*,turn=0):
  """Reject send+retrieve in one model response; sequential logs alone imply no reading."""
  if not isinstance(calls,list) or not calls or any(not isinstance(c,dict) for c in calls):return [{'ok':False,'error':'invalid_calls'}]
  if len(calls)>1 and any(c.get('name') in {'send_reply','escalate_to_staff'} for c in calls):
   self._log('rejected_batch',{'turn':turn,'calls':calls,'reason':'terminal_action_requires_separate_call'})
   return [{'ok':False,'error':'terminal_action_requires_separate_call'} for _ in calls]
  result=[]
  for c in calls:
   name=c.get('name');args=c.get('arguments',{});self._log('tool_request',{'turn':turn,'name':name,'arguments':args})
   try:
    if name not in TOOLS or not isinstance(args,dict):raise ValueError('invalid_tool')
    _,props,required=TOOLS[name]
    if set(args)-set(props) or set(required)-set(args):raise ValueError('invalid_arguments')
    for k,v in args.items():
     if props[k]['type']=='string' and not isinstance(v,str):raise ValueError('invalid_arguments')
     if props[k]['type']=='integer' and type(v)!=int:raise ValueError('invalid_arguments')
    value={'ok':True,**self._execute(name,args)}
   except (ValueError,KeyError,OSError) as e:
    safe={'record_unavailable','invalid_query','invalid_folder','invalid_line_range','invalid_calendar_range','contact_unavailable','no_open_message','recipient_mismatch','invalid_body','missing_reason','unsupported_tool','invalid_tool','invalid_arguments'}
    value={'ok':False,'error':str(e) if str(e) in safe else 'record_unavailable'}
   self._log('tool_result',{'turn':turn,'name':name,'result':value})
   if value['ok']:
    observed=value.get('results',[])+([value] if any(k in value for k in ['lines','text']) else [])
    for ob in observed:
     if 'record_id' in ob:self.exposed.append({'record_id':ob['record_id'],'tool':name,'sequence':self.seq,'returned':ob})
    for ev in value.get('events',[]):self.exposed.append({'record_id':ev['source']['record_id'],'tool':name,'sequence':self.seq,'returned':ev})
   result.append(value)
  return result

 def advance_clock(self,new_clock):
  """Runner-only publication control; never expose as a model tool."""
  nxt=when(new_clock)
  if nxt<self.clock:raise ValueError('Clock cannot go backwards')
  self.clock=nxt;self._log('clock_advanced',{})
