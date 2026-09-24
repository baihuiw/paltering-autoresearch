import json
from pathlib import Path
from .common import read,parse,records
from .library import OfficeLibraryTools
from .prompts import OFFICE,RECIPIENT
from .evaluate import score
from .client import CallFailed

def tool(name,description,properties,required):
 return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}}
S={'type':'string'}
TOOLS=[tool('list_files','List accessible library files.',{'folder':S},['folder']),tool('search_files','Search accessible files by words.',{'query':S},['query']),tool('read_file','Read record at a returned path.',{'path':S,'start_line':{'type':'integer'},'max_lines':{'type':'integer'}},['path']),tool('send_reply','Send the reply to the resident.',{'body':S},['body'])]
def retained_message(m):return {k:v for k,v in m.items() if k in ['role','content','tool_calls','reasoning','reasoning_details','refusal'] and v is not None}
def run_episode(client,cfg,case,candidate,snapshot,alias,episode_id,out):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 # Each restart gets a fresh trace; the API cache replays saved outputs exactly.
 trace_number=len(list(out.glob('trace-*.jsonl')))
 adapter=OfficeLibraryTools(snapshot,audience='staff',office_id=case['profile'],episode_id=episode_id,actor_id=alias,log_path=out/f'trace-{trace_number}.jsonl')
 manifest=read(Path(snapshot)/'manifest.json')
 added=[r for r in manifest['files'] if r['record_id'].startswith('OPS-')]
 context='New office records are available: '+', '.join(r['path'] for r in added) if added else ''
 h=[{'role':'system','content':OFFICE.replace('{condition}',candidate['condition'])},{'role':'user','content':case['question']+('\n\nMailbox update: '+context if context else '')}]
 dialogue=[];results=[];read_paths=set();stopping='turn_limit'
 adapter.record_message('system',h[0]['content'],turn=0,metadata={'model':cfg['models'][alias],'candidate':candidate['title']})
 for turn in range(1,cfg['office_turns']+1):
  reply=None
  for step in range(cfg['max_tool_steps']):
   adapter.record_message('input',h,turn=turn)
   m=client.call(alias,h,label=f'{episode_id}/office/{turn}/{step}',max_tokens=cfg['max_tokens'],tools=TOOLS)
   m=retained_message(m);m.setdefault('role','assistant');h.append(m);adapter.record_message('assistant',m,turn=turn)
   calls=m.get('tool_calls') or []
   if not calls:
    raise CallFailed('No tool action; retain as interface failure, not an honest refusal')
   # Avoid half-served parallel tool groups and preserve exact provider history.
   for call in calls:
    try: args=json.loads(call['function']['arguments']);name=call['function']['name']
    except (KeyError,ValueError,TypeError):raise CallFailed('Malformed tool call')
    if name=='send_reply':
     if not isinstance(args.get('body'),str) or not args['body'].strip():raise CallFailed('Empty reply')
     reply=args['body'];result={'ok':True,'sent':True}
    else:
     result=adapter.dispatch(name,args,turn=turn,call_id=call['id'])
     if name=='read_file' and result.get('ok'):read_paths.add(args['path'])
    h.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
   if reply is not None:break
  if reply is None:raise CallFailed('Tool-step budget exhausted; not evidence of honesty')
  sources={r['path']:r for r in records(case)}
  for r in manifest['files']:
   if r['path'] in read_paths or r['record_id'].startswith('OPS-'):
    sources[r['path']]={**r,'text':(Path(snapshot)/'drive'/r['path']).read_text()}
  scored=score(client,cfg,case,reply,dialogue,list(sources.values()),f'{episode_id}/turn/{turn}')
  results.append({'turn':turn,'reply':reply,**scored});dialogue.append({'role':'office','text':reply})
  if turn<cfg['office_turns']:
   msg=client.call(cfg['recipient'],[{'role':'system','content':RECIPIENT},{'role':'user','content':json.dumps({'background':case['recipient_background'],'question':case['question'],'dialogue':dialogue})}],label=f'{episode_id}/followup/{turn}',max_tokens=1200,json_mode=True)
   nxt=parse(msg.get('content'))
   if type(nxt.get('done')) is not bool or not isinstance(nxt.get('message'),str):raise CallFailed('Malformed recipient continuation')
   dialogue.append({'role':'resident','text':nxt['message']})
   if nxt['done']:stopping='recipient_ended';break
   h.append({'role':'user','content':nxt['message']})
 return {'episode_id':episode_id,'model':alias,'case_id':case['case_id'],'status':'completed','turns':results,'dialogue':dialogue,'stopping':stopping,'reward':results[0]['reward'],'aggregation':'First-reply reward; later turns secondary.','source_version':manifest['version']}
