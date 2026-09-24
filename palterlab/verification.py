"""Recipient-selected retrieval. Belief probes never enter this trajectory."""
import json
from pathlib import Path
from .information import RecipientLibraryTools
from .prompts import VERIFY
from .client import CallFailed

def tool(name,description,properties,required):
 return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}}
S={'type':'string'}
RETRIEVAL_TOOLS=[tool('list_files','List accessible library files.',{'folder':S},['folder']),tool('search_files','Search accessible files by words.',{'query':S},['query']),tool('read_file','Read record at a returned path.',{'path':S,'start_line':{'type':'integer'},'max_lines':{'type':'integer'}},['path'])]
LOOKUP_TOOLS=RETRIEVAL_TOOLS+[tool('finish_lookup','Finish checking records; no further lookup.',{},[])]
def retained_message(m):return {k:v for k,v in m.items() if k in ['role','content','tool_calls','reasoning','reasoning_details','refusal'] and v is not None}

def lookup(client,cfg,case,snapshot,alias,prompt,label,out):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 trace=len(list(out.glob('lookup-*.jsonl')))
 adapter=RecipientLibraryTools(snapshot,case_id=case['case_id'],episode_id=label,actor_id=alias,log_path=out/f'lookup-{trace}.jsonl')
 h=[{'role':'system','content':VERIFY},{'role':'user','content':json.dumps(prompt)}]
 returned=[];read_paths=[];actions=0;status='budget_reached'
 # A separate final decision step can choose finish after the last read.
 for step in range(cfg['verification_steps']+1):
  m=retained_message(client.call(alias,h,label=label+f'/lookup/{step}',max_tokens=900,tools=LOOKUP_TOOLS));m.setdefault('role','assistant')
  h.append(m);adapter.record_message('assistant',m,turn=step)
  calls=m.get('tool_calls') or []
  if not calls:raise CallFailed('Recipient lookup returned no tool action')
  finish=False
  for call in calls:
   try:name=call['function']['name'];args=json.loads(call['function']['arguments'])
   except (KeyError,TypeError,ValueError):raise CallFailed('Malformed lookup action')
   if name=='finish_lookup':result={'ok':True,'finished':True};finish=True
   elif actions>=cfg['verification_steps']:result={'ok':False,'error':'lookup_budget_exhausted'}
   else:
    actions+=1;result=adapter.dispatch(name,args,turn=step,call_id=call['id'])
    returned.append({'tool':name,'arguments':args,'result':result})
    if name=='read_file' and result.get('ok'):read_paths.append(args['path'])
   h.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
  if finish:status='finished';break
  if actions>=cfg['verification_steps']:break
 return {'status':status,'actions':actions,'read_paths':sorted(set(read_paths)),'returned':returned,'history':h,'note':'One optional lookup trajectory; subsequent belief draws share its evidence.'}
