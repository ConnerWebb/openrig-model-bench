"""Loopback-only measured OpenAI transport for experimental seats."""
import http.server,urllib.request,urllib.error,json,time,uuid,pathlib,threading
from common import O,event
LOG=O/'transport';LOG.mkdir(exist_ok=True)
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  begin=time.monotonic();rid=uuid.uuid4().hex;data=self.rfile.read(int(self.headers.get('Content-Length','0')));parts=self.path.split('/v1/',1)
  if len(parts)!=2 or len(data)>4*2**20:self.send_error(400);return
  prefix=parts[0].strip('/');row={'id':rid,'prefix':prefix,'at':time.time(),'first_any_seconds':None,'first_content_seconds':None,'usage':None};folder=LOG/rid;folder.mkdir()
  try:
   body=json.loads(data);row['model']=body.get('model');body['reasoning_effort']='low' if 'gpt' in str(body.get('model')) else 'none';body['stream_options']={'include_usage':True} if body.get('stream') else body.get('stream_options',{});(folder/'request.json').write_text(json.dumps(body));req=urllib.request.Request('http://127.0.0.1:11437/v1/'+parts[1],json.dumps(body).encode(),{'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=1200) as response,(folder/'response.jsonl').open('wb') as raw:
    self.send_response(response.status);self.send_header('Content-Type',response.headers.get('Content-Type','application/json'));self.end_headers()
    for line in response:
     raw.write(line)
     if line.strip() and line.startswith(b'data:'):
      try:
       msg=json.loads(line[5:]);delta=(msg.get('choices') or [{}])[0].get('delta',{});now=time.monotonic()-begin
       if row['first_any_seconds'] is None and (delta.get('content') or delta.get('reasoning_content') or delta.get('tool_calls')):row['first_any_seconds']=now
       if row['first_content_seconds'] is None and (delta.get('content') or delta.get('tool_calls')):row['first_content_seconds']=now
       if msg.get('usage'):row['usage']=msg['usage']
      except Exception:pass
     self.wfile.write(line);self.wfile.flush()
    row['complete']=True
  except Exception as e:
   row.update(complete=False,error=str(e))
   try:self.send_error(502,str(e)[:100])
   except Exception:pass
  finally:row['seconds']=time.monotonic()-begin;(folder/'metrics.json').write_text(json.dumps(row,indent=2));event('inference_request',**row)
def serve():http.server.ThreadingHTTPServer(('127.0.0.1',11438),Handler).serve_forever()
if __name__=='__main__':serve()
