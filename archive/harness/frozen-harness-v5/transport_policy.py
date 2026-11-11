"""Strict wire compatibility and bounded context; no tools execute here."""
import copy,json,re

def valid(value,schema):
 if 'anyOf' in schema:return any(valid(value,x) for x in schema['anyOf'])
 if 'enum' in schema and value not in schema['enum']:return False
 if 'const' in schema and value!=schema['const']:return False
 kind=schema.get('type')
 if kind=='string':return isinstance(value,str)
 if kind=='boolean':return type(value)==bool
 if kind in ['number','integer']:return type(value) in ([int] if kind=='integer' else [int,float])
 if kind=='array':return isinstance(value,list) and all(valid(x,schema.get('items',{})) for x in value)
 if kind=='object':
  return isinstance(value,dict) and set(schema.get('required',[]))<=value.keys() and value.keys()<=schema.get('properties',{}).keys() and all(valid(v,schema['properties'][k]) for k,v in value.items())
 return True

def xml_tool(text,tools):
 """Accept one complete native function block, never prose or partial output.

 Some local responses omit only the outer opening <tool_call> marker. The
 closing marker and function/parameter grammar must still be complete and
 match one currently offered function's exact schema. No XML evaluator is used.
 """
 match=re.fullmatch(r'\s*(?:<tool_call>\s*)?<function=([A-Za-z_][A-Za-z0-9_]*)>\s*(.*?)\s*</function>\s*</tool_call>\s*',text,re.S)
 if not match:return None
 name,body=match.groups();function=next((x['function'] for x in tools if x.get('type')=='function' and x.get('function',{}).get('name')==name),None)
 if function is None:return None
 schema=function.get('parameters',{});arguments={};position=0
 parameter=re.compile(r'\s*<parameter=([A-Za-z_][A-Za-z0-9_]*)>\s*\n?(.*?)\n?</parameter>',re.S)
 while body[position:].strip():
  item=parameter.match(body,position)
  if not item:return None
  key,value=item.groups()
  if key in arguments or key not in schema.get('properties',{}):return None
  field=schema['properties'][key]
  if field.get('type')=='string':
   # Remove only formatting's first/final newline, preserving source escapes.
   raw=body[item.start():item.end()];value=raw.split('>',1)[1].rsplit('</parameter>',1)[0]
   if value.startswith('\n'):value=value[1:]
   if value.endswith('\n'):value=value[:-1]
  else:
   try:value=json.loads(value)
   except Exception:return None
  arguments[key]=value;position=item.end()
 if not valid(arguments,schema):return None
 return {'name':name,'arguments':arguments}

def size(payload):return len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode())

def bounded_context(body,maximum=48000):
 """Keep system, newest user instruction and complete recent tool exchanges.

 The underlying runner stays at32K tokens. Old round trips and old large tool
 dumps are omitted only from the model view; original requests/sessions remain
 archived. Current source and TASK/public driver remain available on disk.
 """
 out=copy.deepcopy(body);messages=out.get('messages',[])
 if size({'messages':messages,'tools':out.get('tools',[])})<=maximum:return out,{'applied':False}
 groups=[]
 for message in messages:
  if message.get('role')=='tool' and groups and groups[-1][0].get('role')=='assistant':groups[-1].append(message)
  else:groups.append([message])
 last_user=max((i for i,g in enumerate(groups) if g[0].get('role')=='user'),default=-1)
 pinned={i for i,g in enumerate(groups) if g[0].get('role')=='system'}|({last_user} if last_user>=0 else set());before=size({'messages':messages,'tools':out.get('tools',[])});selected=set(range(len(groups)));dropped=0
 def measured():return size({'messages':[m for i,g in enumerate(groups) if i in selected for m in g],'tools':out.get('tools',[])})
 for i in range(max(0,len(groups)-4)):
  if measured()<=maximum:break
  if i not in pinned:selected.discard(i);dropped+=len(groups[i])
 shortened=0
 if measured()>maximum:
  for i,g in enumerate(groups):
   if i not in selected or i in pinned:continue
   for message in g:
    content=message.get('content')
    if isinstance(content,str) and len(content)>6000:
     message['content']=content[:2500]+'\n[Older tool output elided from model context; reread files or run_tests for current evidence.]\n'+content[-2500:];shortened+=1
    if message.get('role')=='assistant':
     for call in message.get('tool_calls',[]):
      try:args=json.loads(call['function']['arguments'])
      except Exception:continue
      for key,value in args.items():
       if isinstance(value,str) and len(value)>4000:args[key]='[Prior argument content omitted for context budget; the actual file is on disk and original call is archived.]';shortened+=1
      call['function']['arguments']=json.dumps(args)
   if measured()<=maximum:break
 for i in range(len(groups)-1):
  if measured()<=maximum:break
  if i not in pinned and i in selected:selected.remove(i);dropped+=len(groups[i])
 if measured()>maximum:raise ValueError('Pinned instructions/tools exceed the experimental context budget')
 out['messages']=[m for i,g in enumerate(groups) if i in selected for m in g]
 return out,{'applied':True,'before_bytes':before,'after_bytes':measured(),'maximum_bytes':maximum,'dropped_messages':dropped,'shortened_history_fields':shortened}
