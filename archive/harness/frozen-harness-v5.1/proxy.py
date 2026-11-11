"""Loopback-only measured transport. Archives original and delivered wire data."""
import http.server,urllib.request,urllib.error,json,time,uuid,threading
from common import O,event,atomic
from transport_policy import bounded_context,xml_tool
LOG=O/'transport';LOG.mkdir(exist_ok=True)
def encoded(message):return b'data: '+json.dumps(message).encode()+b'\n\n'
def convert(messages,body):
 text='';native=False;finish=None;template={}
 for message in messages:
  for choice in message.get('choices',[]):
   delta=choice.get('delta',{});text+=delta.get('content') or '';native=native or bool(delta.get('tool_calls'));finish=choice.get('finish_reason') or finish
   if delta.get('content'):template={k:v for k,v in message.items() if k not in ['choices','usage']}
 if native or finish not in ['stop','tool_calls']:return None
 call=xml_tool(text,body.get('tools',[]))
 if call is None:return None
 delta={'role':'assistant','tool_calls':[{'index':0,'id':'call_'+uuid.uuid4().hex,'type':'function','function':{'name':call['name'],'arguments':json.dumps(call['arguments'],ensure_ascii=False)}}]}
 result=[{**template,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**template,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls'}]}]
 result.extend(m for m in messages if m.get('usage') and not m.get('choices'))
 if not any(m.get('usage') for m in result):
  usage=next((m['usage'] for m in reversed(messages) if m.get('usage')),None)
  if usage:result.append({**template,'choices':[],'usage':usage})
 return result
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  begin=time.monotonic();rid=uuid.uuid4().hex;data=self.rfile.read(int(self.headers.get('Content-Length','0')));parts=self.path.split('/v1/',1)
  if len(parts)!=2 or len(data)>4*2**20:self.send_error(400);return
  row={'id':rid,'prefix':parts[0].strip('/'),'at':time.time(),'first_any_seconds':None,'first_content_seconds':None,'first_delivered_seconds':None,'usage':None,'normalized_tool_call':False};folder=LOG/rid;folder.mkdir();headers=False
  try:
   original=json.loads(data);(folder/'request.json').write_bytes(data);body,policy=bounded_context(original);row['context_policy']=policy;row['model']=body.get('model');body['reasoning_effort']='low' if 'gpt' in str(body.get('model')) else 'none'
   if body.get('stream'):body['stream_options']={'include_usage':True}
   atomic(folder/'upstream-request.json',body);req=urllib.request.Request('http://127.0.0.1:11437/v1/'+parts[1],json.dumps(body).encode(),{'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=1200) as response,(folder/'response.jsonl').open('wb') as raw,(folder/'delivered-response.jsonl').open('wb') as delivered:
    self.send_response(response.status);self.send_header('Content-Type',response.headers.get('Content-Type','application/json'));self.end_headers();headers=True
    def send(line):
     if row['first_delivered_seconds'] is None:row['first_delivered_seconds']=time.monotonic()-begin
     delivered.write(line);self.wfile.write(line);self.wfile.flush()
    held=[];messages=[];content='';mode='probe';saw_done=False
    for line in response:
     raw.write(line);msg=None
     if line.startswith(b'data:'):
      if line[5:].strip()==b'[DONE]':saw_done=True
      else:
       try:
        msg=json.loads(line[5:]);delta=(msg.get('choices') or [{}])[0].get('delta',{});now=time.monotonic()-begin
        if row['first_any_seconds'] is None and (delta.get('content') or delta.get('reasoning_content') or delta.get('tool_calls')):row['first_any_seconds']=now
        if row['first_content_seconds'] is None and (delta.get('content') or delta.get('tool_calls')):row['first_content_seconds']=now
        if msg.get('usage'):row['usage']=msg['usage']
        content+=delta.get('content') or ''
        if mode=='probe' and (delta.get('tool_calls') or delta.get('reasoning_content')):mode='pass'
       except (ValueError,KeyError,TypeError):pass
     if mode=='probe' and content.strip():
      prefix=content.lstrip();candidates=['<tool_call>','<function=']
      if any(prefix.startswith(x) for x in candidates):mode='hold'
      elif not any(x.startswith(prefix) for x in candidates):mode='pass'
     if mode=='pass':
      for old in held:send(old)
      held=[];send(line)
     else:
      held.append(line)
      if msg is not None:messages.append(msg)
    if held:
     converted=convert(messages,body) if saw_done else None
     if converted is not None:
      row['normalized_tool_call']=True
      for item in converted:send(encoded(item))
      send(b'data: [DONE]\n\n')
     else:
      for old in held:send(old)
    row['complete']=saw_done if body.get('stream') else True
    if body.get('stream') and not saw_done:row['error']='Upstream stream ended without DONE; no partial tool call repaired'
  except Exception as e:
   row.update(complete=False,error=str(e))
   if isinstance(e,urllib.error.HTTPError):
    error=e.read(65536);(folder/'upstream-error.txt').write_bytes(error);row['upstream_status']=e.code
   if not headers:
    try:self.send_error(502,str(e)[:100])
    except Exception:pass
  finally:
   row['seconds']=time.monotonic()-begin;atomic(folder/'metrics.json',row);event('inference_request',**row)
def serve():http.server.ThreadingHTTPServer(('127.0.0.1',11438),Handler).serve_forever()
if __name__=='__main__':serve()
