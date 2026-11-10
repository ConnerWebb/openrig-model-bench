"""Read-only campaign export. Never imports or controls the running harness."""
import argparse,collections,datetime,hashlib,io,json,os,pathlib,re,tarfile,tempfile,time
SECRET=[re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),re.compile(rb'github_pat_[A-Za-z0-9_]{30,}'),re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{24,}'),re.compile(rb'AKIA[0-9A-Z]{16}'),re.compile(rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z]+ )?PRIVATE KEY-----',re.S)]
PRIVATE={'auth.json','settings.json','models-store.json','.env','.gitconfig','.netrc','id_rsa','id_ed25519','paths.json'}
ROOT_FILES={'RESULTS.txt','leaderboard.json','campaign-status.json','heartbeat.json','active-harness-revision.json','inference-profile.json','qualified-models.json','aliases.json','toolchains.json','breadth-screen-plan.json','COMPLETED.json','ATTENTION.json','FINAL-COMPARISON.txt','FINAL-COMPARISON.json','recovery-test.json','soak-plan.json','RUNNING-READ-ME.txt'}
def atomic(path,data):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.snapshot-')
 with os.fdopen(fd,'wb') as f:f.write(data)
 os.replace(tmp,path)
def write_json(path,data):atomic(path,(json.dumps(data,indent=2,sort_keys=True)+'\n').encode())
def scrub(data):
 count=0
 for pattern in SECRET:data,n=pattern.subn(b'[REDACTED_CREDENTIAL]',data);count+=n
 return data,count
def digest(data):return hashlib.sha256(data).hexdigest()
def allowed(path,relative):
 if path.is_symlink() or not path.is_file():return False
 if any(p in PRIVATE or p in ['.git','__pycache__','node_modules','agent'] for p in relative.parts):return False
 if 'project' not in relative.parts and (any(p in ['build','CMakeFiles'] for p in relative.parts) or path.suffix in ['.sqlite','.db','.o','.a','.pyc']):return False
 return True
def stable_bytes(path,maximum=16*2**20):
 before=path.stat()
 if before.st_size>maximum:raise ValueError('oversize')
 data=path.read_bytes();after=path.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('changed-during-read')
 return data
def bundle(files,target):
 """A completed artifact bundle is immutable and includes an integrity ledger."""
 target=pathlib.Path(target)
 if target.exists():return False
 target.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=target.parent,prefix='.snapshot-');os.close(fd);ledger=[]
 try:
  with tarfile.open(tmp,'w:gz',compresslevel=1) as archive:
   for path,name in sorted(files,key=lambda x:x[1]):
    rel=pathlib.PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or not allowed(path,rel):continue
    try:raw=stable_bytes(path)
    except (OSError,ValueError) as e:ledger.append({'path':name,'omitted':str(e)});continue
    data,n=scrub(raw);info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=int(path.stat().st_mtime);archive.addfile(info,io.BytesIO(data));ledger.append({'path':name,'source_sha256':digest(raw),'stored_sha256':digest(data),'bytes':len(data),'credential_redactions':n})
   data=json.dumps({'files':ledger,'note':'Credential files, symlinks and external build caches omitted. Candidate workspace files are untrusted; do not execute outside the grader.'},indent=2).encode();info=tarfile.TarInfo('EXPORT-MANIFEST.json');info.size=len(data);info.mode=0o644;archive.addfile(info,io.BytesIO(data))
  if pathlib.Path(tmp).stat().st_size>90*2**20:raise ValueError('Bundle exceeds repository file budget; local originals remain intact')
  os.replace(tmp,target)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return True
def tree(root,prefix=''):
 for directory,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=[n for n in dirs if n not in ['.git','__pycache__','node_modules','agent'] and not (pathlib.Path(directory)/n).is_symlink()]
  for name in files:
   p=pathlib.Path(directory)/name;rel=p.relative_to(root);yield p,str(pathlib.PurePosixPath(prefix)/rel)
def append_log(source,destination,state,key):
 if not source.is_file():return
 position=state.get(key,{}).get('offset',0);limit=source.stat().st_size
 if limit<position:raise ValueError('Append-only source shrank: '+key)
 chunks=state.get(key,{}).get('chunks',[])
 with source.open('rb') as f:
  f.seek(position)
  while f.tell()<limit:
   start=f.tell();block=f.read(min(4*2**20,limit-start));end=block.rfind(b'\n')+1
   if not end:break
   block=block[:end];f.seek(start+end);data,n=scrub(block);name=f'{start:016d}-{start+end:016d}-{digest(data)[:16]}.jsonl.gz'
   import gzip
   out=destination/name
   if not out.exists():atomic(out,gzip.compress(data,compresslevel=1,mtime=0))
   chunks.append({'file':name,'start':start,'end':start+end,'source_sha256':digest(block),'stored_sha256':digest(data),'credential_redactions':n});position=start+end
 state[key]={'offset':position,'chunks':chunks};write_json(destination/'INDEX.json',state[key])
def snapshot(source,repository):
 source=pathlib.Path(source).resolve();repository=pathlib.Path(repository).resolve()
 if not (source/'campaign-status.json').is_file():raise ValueError('Not a campaign directory')
 if repository==source or repository.is_relative_to(source) or source.is_relative_to(repository):raise ValueError('Repository and live campaign must be separate trees')
 local=repository/'.local-backup';local.mkdir(exist_ok=True);statefile=local/'state.json';state=json.loads(statefile.read_text()) if statefile.exists() else {};cutoff=time.time();destination=repository/'results'/source.name;destination.mkdir(parents=True,exist_ok=True);records=[];partial=[];errors=[]
 heartbeat=json.loads((source/'heartbeat.json').read_text()) if (source/'heartbeat.json').exists() else {};active=set(heartbeat.get('active_jobs',[])) if cutoff-heartbeat.get('at',0)<10 else set()
 for case in sorted((source/'runs').iterdir()):
  if not case.is_dir() or case.is_symlink():continue
  result=case/'result.json'
  try:
   if not result.exists():partial.append(case.name);continue
   raw=stable_bytes(result);r=json.loads(raw)
   if r.get('finished',cutoff)>cutoff-30 or r.get('id') in active:partial.append(case.name);continue
   data,n=scrub(raw);atomic(destination/'cases'/case.name/'result.json',data)
   bundle(tree(case),destination/'artifacts/cases'/(case.name+'.tar.gz'));records.append({'directory':case.name,'id':r.get('id'),'phase':r.get('phase'),'revision':r.get('harness_revision','historical'),'language':r.get('language'),'models':r.get('models'),'complete':r.get('complete'),'interrupted':r.get('interrupted',False),'source_result_sha256':digest(raw),'stored_result_sha256':digest(data)})
  except (OSError,ValueError) as e:errors.append({'scope':'case','id':case.name,'error':str(e)})
 # Only finished HTTP streams have a metrics record. Every UUID is archived once.
 done=set(state.get('transport_ids',[]));pending=[]
 for d in (source/'transport').iterdir():
  if d.name in done or not d.is_dir():continue
  try:
   metrics=d/'metrics.json'
   if not metrics.exists() or metrics.stat().st_mtime>cutoff-2:continue
   json.loads(stable_bytes(metrics));pending.append(d)
  except (OSError,ValueError):continue
 for offset in range(0,len(pending),64):
  batch=sorted(pending[offset:offset+64],key=lambda p:p.name);identity=digest('\n'.join(p.name for p in batch).encode())[:20];files=[]
  for d in batch:files.extend(tree(d,d.name))
  bundle(files,destination/'artifacts/transport'/('batch-'+identity+'.tar.gz'));done.update(d.name for d in batch)
 state['transport_ids']=sorted(done)
 metrics=[]
 for id in sorted(done):
  try:row=json.loads(stable_bytes(source/'transport'/id/'metrics.json'));data,n=scrub(json.dumps(row).encode());metrics.append(json.loads(data))
  except (OSError,ValueError):continue
 write_json(destination/'STREAM-INDEX.json',{'streams':metrics,'raw_bundles':'artifacts/transport/','note':'Each UUID identifies request.json, response.jsonl and metrics.json within one immutable bundle.'})
 for name in ['events.jsonl','memory-timeline.jsonl']:append_log(source/name,destination/'telemetry'/name,state,name)
 for p in source.iterdir():
  if p.is_file() and (p.name in ROOT_FILES or p.name.endswith('-sha256.json')):
   try:data,n=scrub(stable_bytes(p));atomic(destination/'status'/p.name,data)
   except (OSError,ValueError):continue
  elif p.is_dir() and (p.name.startswith(('qualification','frozen-qualification','guard-qualification','harness-repair-checks','topology-qualification')) or p.name in ['baseline-replay','compatibility','repairs','progress','parallel-inference','parallel-jobs','role-probes','runtime-evidence','soak','topology-warnings','ineligible-cells']):
   # Qualification and diagnostic folders can grow while a run continues.
   # Content-addressed snapshots retain every version instead of freezing an
   # incomplete first export under a fixed archive name.
   files=list(tree(p));stamp=digest('\n'.join(f'{str(f.relative_to(p))}:{f.stat().st_size}:{f.stat().st_mtime_ns}' for f,_ in files if allowed(f,pathlib.PurePosixPath(_))).encode())[:20];name=p.name+'-'+stamp
   try:bundle(files,destination/'artifacts/evidence'/(name+'.tar.gz'))
   except (OSError,ValueError) as e:errors.append({'scope':p.name,'error':str(e)})
 status=json.loads(stable_bytes(source/'campaign-status.json'));counts=collections.Counter((r['revision'],r['phase'],r['language'],r['complete'],r['interrupted']) for r in records)
 summary={'campaign':source.name,'as_of_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'completed_case_records':len(records),'finished_transport_streams':len(done),'in_progress_not_scored':partial,'counts':[{'revision':k[0],'phase':k[1],'language':k[2],'passed':k[3],'interrupted':k[4],'count':v} for k,v in counts.items()],'status':status,'export_errors':errors,'exclusions':['model weights','credentials and agent auth/settings','production configuration/state','native SQLite checkpoints','external compiler caches'],'consistency':'Completed result records older than30 seconds and finished transport streams. Append-only telemetry ends at full newline boundaries. Live work is not stopped, locked, or rewritten.'}
 write_json(destination/'CASE-INDEX.json',records);write_json(destination/'SNAPSHOT.json',summary);write_json(local/'state.json',state)
 return summary
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--repo',required=True,type=pathlib.Path);a=p.parse_args();print(json.dumps(snapshot(a.source,a.repo),indent=2))
